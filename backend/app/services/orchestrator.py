"""The run state machine.

prepare → baseline → retrieve → propose → gate → verify → select.

Three independent budgets are enforced: the whole-run wall clock here, the model
call inside the client, and the container host-side in the verifier. Resuming an
interrupted run is deliberately out of scope — a new run is cheap and a
half-resumed run is hard to reason about.
"""

from __future__ import annotations

import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.config import PROJECT_ROOT, Settings
from backend.app.logging_setup import get_logger
from backend.app.models import (
    CandidateOutcome,
    CandidateStatus,
    Decision,
    Defect,
    GateResult,
    ProposedPatch,
    RunRecord,
    RunStatus,
    Usage,
    VerificationResult,
)
from backend.app.services.candidates import generate_candidates
from backend.app.services.fingerprint import config_hash
from backend.app.services.fixtures import Fixture, get_fixture, read_failing_test_source
from backend.app.services.gates import build_context, rejecting_gate, run_gates, run_pure_gates
from backend.app.services.model_client import ModelClient, ModelError, build_model_client
from backend.app.services.retrieval import KnowledgeBase, get_knowledge_base
from backend.app.services.selection import decide, select
from backend.app.services.verifier import Verifier
from backend.app.services.workspace import (
    PatchFailed,
    PatchRefused,
    apply_candidate,
    build_broken_tree,
    make_candidate_workspace,
)

TARGET_APP = PROJECT_ROOT / "target_app"
RUFF_CONFIG = PROJECT_ROOT / "ruff.toml"
STAGES = ("prepare", "baseline", "retrieve", "propose", "gate", "verify", "select")

EventSink = Callable[[dict[str, Any]], None]


class RunTimeout(Exception):
    """The whole-run wall clock expired. Carries the stage it expired in."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"the run budget expired during {stage}")
        self.stage = stage


class RunCancelled(Exception):
    """A cooperative cancellation was requested."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"the run was cancelled during {stage}")
        self.stage = stage


@dataclass
class Deadline:
    seconds: int
    started: float = field(default_factory=time.monotonic)

    @property
    def remaining(self) -> float:
        return self.seconds - (time.monotonic() - self.started)

    @property
    def expired(self) -> bool:
        return self.remaining <= 0


def new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"run-{stamp}-{uuid.uuid4().hex[:8]}"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def feedback_from(outcomes: list[CandidateOutcome]) -> list[str]:
    """What the previous round proved, in the model's own terms."""
    lines: list[str] = []
    for outcome in outcomes:
        candidate_id = outcome.candidate.candidate_id
        gate = outcome.rejecting_gate
        if gate is not None:
            detail = next(result.detail for result in outcome.gates if not result.passed)
            lines.append(f"{candidate_id} was rejected by the {gate} gate: {detail}")
            continue
        verification = outcome.verification
        if verification is None:
            continue
        if verification.timed_out:
            lines.append(f"{candidate_id} did not finish: the test run timed out.")
        elif not verification.target_test_passed:
            tail = verification.stdout_tail.strip().splitlines()[-4:]
            lines.append(
                f"{candidate_id} applied cleanly but the failing test still fails: "
                + " / ".join(line.strip() for line in tail)
            )
        elif verification.regressions:
            lines.append(
                f"{candidate_id} fixed the target test but broke: "
                + ", ".join(verification.regressions)
            )
    return lines


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        client: ModelClient | None = None,
        verifier: Any | None = None,
        knowledge: KnowledgeBase | None = None,
        store: Any | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or build_model_client(settings)
        self.verifier = verifier if verifier is not None else Verifier(settings)
        self.knowledge = knowledge or get_knowledge_base()
        self.store = store

    # ---------------------------------------------------------------- helpers

    def _guard(self, deadline: Deadline, stage: str, cancel: Callable[[], bool] | None) -> None:
        if cancel is not None and cancel():
            raise RunCancelled(stage)
        if deadline.expired:
            raise RunTimeout(stage)

    def _emit(self, sink: EventSink | None, payload: dict[str, Any]) -> None:
        if sink is not None:
            sink(payload)

    # ------------------------------------------------------------------- main

    def run(
        self,
        defect_id: str,
        run_id: str | None = None,
        on_event: EventSink | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> RunRecord:
        fixture = get_fixture(defect_id)
        defect = fixture.defect
        run_id = run_id or new_run_id()
        artifact_dir = self.settings.artifact_root_path / run_id

        record = RunRecord(
            run_id=run_id,
            defect_id=defect.defect_id,
            fixture_set=defect.fixture_set,
            status=RunStatus.RUNNING,
            artifact_dir=str(artifact_dir),
            model_mode=self.settings.model_mode,
            model_name=getattr(self.client, "name", self.settings.model_mode),
            config_hash=config_hash(self.settings),
            started_at=datetime.now(UTC),
        )

        deadline = Deadline(self.settings.max_run_seconds)
        timings: dict[str, float] = {}
        outcomes: list[CandidateOutcome] = []
        usage = Usage(priced=self.settings.priced)
        rounds_used = 0
        decision: Decision
        timeout_stage: str | None = None
        error: str | None = None

        log = get_logger(run_id)
        log.info("run started", extra={"extra_fields": {"defect_id": defect.defect_id,
                                                        "model_mode": self.settings.model_mode}})

        def stage_start(name: str) -> float:
            self._emit(on_event, {"type": "stage", "stage": name, "state": "started"})
            log.info("stage started", extra={"extra_fields": {"stage": name}})
            return time.monotonic()

        def stage_end(name: str, started: float) -> None:
            timings[name] = round((time.monotonic() - started) * 1000, 2)
            self._emit(
                on_event,
                {"type": "stage", "stage": name, "state": "finished", "ms": timings[name]},
            )
            log.info(
                "stage finished", extra={"extra_fields": {"stage": name, "ms": timings[name]}}
            )

        try:
            # ---------------------------------------------------- 1. prepare
            started = stage_start("prepare")
            artifact_dir.mkdir(parents=True, exist_ok=True)
            _write(artifact_dir / "defect.json", defect.model_dump_json(indent=2) + "\n")
            broken_tree = build_broken_tree(
                TARGET_APP, fixture.break_patch, artifact_dir / "baseline" / "workspace"
            )
            file_contents = {
                path: (broken_tree / path).read_text(encoding="utf-8")
                for path in defect.allowed_paths
            }
            stage_end("prepare", started)

            # --------------------------------------------------- 2. baseline
            self._guard(deadline, "baseline", cancel)
            started = stage_start("baseline")
            baseline_output, _ = self.verifier.baseline(
                broken_tree, defect.failing_test, run_id, artifact_dir
            )
            baseline_passing = baseline_output.passing
            stage_end("baseline", started)

            failing_test_source = read_failing_test_source(defect.failing_test)
            feedback: list[str] = []

            for round_index in range(1, self.settings.max_propose_rounds + 1):
                rounds_used = round_index
                round_dir = artifact_dir / f"round-{round_index}"

                # ------------------------------------------- 3. retrieve
                self._guard(deadline, "retrieve", cancel)
                started = stage_start("retrieve")
                retrieval = self.knowledge.retrieve(
                    defect,
                    failing_test_source=failing_test_source,
                    assertion=baseline_output.stdout_tail[-1200:],
                    top_k=self.settings.knowledge_top_k,
                )
                if round_index == 1:
                    _write(
                        artifact_dir / "retrieval.json",
                        retrieval.model_dump_json(indent=2) + "\n",
                    )
                stage_end("retrieve", started)

                # -------------------------------------------- 4. propose
                self._guard(deadline, "propose", cancel)
                started = stage_start("propose")
                batch = generate_candidates(
                    self.settings,
                    self.client,
                    defect,
                    file_contents,
                    failing_test_source=failing_test_source,
                    round_index=round_index,
                    feedback=feedback or None,
                    artifact_dir=round_dir,
                    knowledge=self.knowledge,
                    retrieval=retrieval,
                )
                usage = usage.merged_with(batch.usage)
                stage_end("propose", started)

                round_outcomes = [
                    self._assess(
                        patch=patch,
                        defect=defect,
                        broken_tree=broken_tree,
                        artifact_dir=artifact_dir,
                        run_id=run_id,
                        baseline_passing=baseline_passing,
                        deadline=deadline,
                        cancel=cancel,
                        on_event=on_event,
                        stage_start=stage_start,
                        stage_end=stage_end,
                    )
                    for patch in batch.patches
                ]
                outcomes.extend(round_outcomes)

                if select(outcomes) is not None:
                    break
                feedback = feedback_from(round_outcomes)

            # ----------------------------------------------------- 7. select
            self._guard(deadline, "select", cancel)
            started = stage_start("select")
            chosen = select(outcomes)
            decision = decide(outcomes)
            stage_end("select", started)
            record = record.model_copy(
                update={
                    "chosen_candidate_id": chosen.candidate.candidate_id if chosen else None,
                    "status": RunStatus.SUCCEEDED,
                }
            )

        except RunTimeout as expiry:
            timeout_stage = expiry.stage
            decision = Decision.TIMEOUT
            record = record.model_copy(update={"status": RunStatus.FAILED})
        except RunCancelled as cancellation:
            timeout_stage = cancellation.stage
            decision = Decision.NO_VERIFIED_FIX
            record = record.model_copy(update={"status": RunStatus.CANCELLED})
        except (ModelError, PatchFailed, Exception) as failure:  # noqa: BLE001 - recorded
            error = f"{type(failure).__name__}: {failure}"
            _write(artifact_dir / "error.txt", traceback.format_exc())
            decision = Decision.ERROR
            record = record.model_copy(update={"status": RunStatus.FAILED})

        record = record.model_copy(
            update={
                "decision": decision,
                "stage_timings": timings,
                "usage": usage,
                "rounds_used": rounds_used,
                "timeout_stage": timeout_stage,
                "error": error,
                "outcomes": tuple(outcomes),
                "finished_at": datetime.now(UTC),
            }
        )

        log.info(
            "run finished",
            extra={
                "extra_fields": {
                    "decision": decision.value,
                    "chosen": record.chosen_candidate_id,
                    "status": record.status.value,
                }
            },
        )
        _write(artifact_dir / "run.json", record.model_dump_json(indent=2) + "\n")
        self._write_report(record, artifact_dir)
        if self.store is not None:
            self.store.save_run(record)
        self._emit(
            on_event,
            {"type": "done", "run_id": run_id, "decision": decision.value,
             "chosen": record.chosen_candidate_id},
        )
        return record

    # -------------------------------------------------- per-candidate stages

    def _assess(
        self,
        patch: ProposedPatch,
        defect: Defect,
        broken_tree: Path,
        artifact_dir: Path,
        run_id: str,
        baseline_passing: set[str],
        deadline: Deadline,
        cancel: Callable[[], bool] | None,
        on_event: EventSink | None,
        stage_start: Callable[[str], float],
        stage_end: Callable[[str, float], None],
    ) -> CandidateOutcome:
        candidate_dir = artifact_dir / "candidates" / patch.candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------- 5. gates
        self._guard(deadline, "gate", cancel)
        started = stage_start("gate")
        context = build_context(patch, defect, self.settings.max_diff_lines, {}, {}, RUFF_CONFIG)
        results = run_pure_gates(context)
        workspace: Path | None = None

        if rejecting_gate(results) is None:
            try:
                workspace = make_candidate_workspace(
                    broken_tree, candidate_dir / "workspace"
                )
                baseline_files = {
                    path: (broken_tree / path).read_text(encoding="utf-8")
                    for path in patch.touched_paths
                    if (broken_tree / path).is_file()
                }
                apply_candidate(
                    workspace, patch, defect, self.settings.max_diff_lines, candidate_dir
                )
                patched_files = {
                    path: (workspace / path).read_text(encoding="utf-8")
                    for path in patch.touched_paths
                    if (workspace / path).is_file()
                }
                results = run_gates(
                    build_context(
                        patch,
                        defect,
                        self.settings.max_diff_lines,
                        baseline_files,
                        patched_files,
                        RUFF_CONFIG,
                    )
                )
            except PatchRefused as refusal:
                results = [*results, GateResult(gate="apply", passed=False,
                                                detail="; ".join(refusal.reasons))]
            except PatchFailed as failure:
                results = [*results, GateResult(gate="apply", passed=False, detail=str(failure))]

        _write(
            candidate_dir / "gates.json",
            "[\n" + ",\n".join(f"  {r.model_dump_json()}" for r in results) + "\n]\n",
        )
        stage_end("gate", started)

        gate = rejecting_gate(results)
        if gate is not None or workspace is None:
            outcome = CandidateOutcome(
                candidate=patch, gates=tuple(results), status=CandidateStatus.GATED
            )
            self._emit(
                on_event,
                {"type": "candidate", "candidate_id": patch.candidate_id,
                 "status": "gated", "gate": gate},
            )
            return outcome

        # ------------------------------------------------------ 6. verify
        self._guard(deadline, "verify", cancel)
        started = stage_start("verify")
        try:
            verification: VerificationResult = self.verifier.verify(
                workspace,
                defect.failing_test,
                run_id,
                patch.candidate_id,
                baseline_passing,
                candidate_dir,
            )
            status = CandidateStatus.VERIFIED
        except Exception as failure:  # noqa: BLE001 - one bad container is not a bad run
            verification = VerificationResult(
                candidate_id=patch.candidate_id,
                stdout_tail=f"{type(failure).__name__}: {failure}",
            )
            status = CandidateStatus.ERRORED
        stage_end("verify", started)

        outcome = CandidateOutcome(
            candidate=patch,
            gates=tuple(results),
            verification=verification,
            status=status,
        )
        self._emit(
            on_event,
            {
                "type": "candidate",
                "candidate_id": patch.candidate_id,
                "status": status.value,
                "target_test_passed": verification.target_test_passed,
                "regressions": list(verification.regressions),
                "eligible": outcome.eligible,
            },
        )
        return outcome

    def _write_report(self, record: RunRecord, artifact_dir: Path) -> None:
        from backend.app.services.reporting import render_json, render_markdown

        _write(artifact_dir / "report.md", render_markdown(record, self.settings))
        _write(artifact_dir / "report.json", render_json(record, self.settings))


def run_defect(
    settings: Settings,
    defect_id: str,
    run_id: str | None = None,
    on_event: EventSink | None = None,
    cancel: Callable[[], bool] | None = None,
    **overrides: Any,
) -> RunRecord:
    """Convenience entry point for scripts and evals."""
    return Orchestrator(settings, **overrides).run(defect_id, run_id, on_event, cancel)


__all__ = [
    "STAGES",
    "Deadline",
    "Fixture",
    "Orchestrator",
    "RunCancelled",
    "RunTimeout",
    "feedback_from",
    "new_run_id",
    "run_defect",
]
