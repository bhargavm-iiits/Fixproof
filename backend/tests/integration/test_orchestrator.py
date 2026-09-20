"""Orchestrator tests with a stubbed verifier. No Docker is started here."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.models import Decision, RunStatus, VerificationResult
from backend.app.services.orchestrator import (
    Orchestrator,
    feedback_from,
    new_run_id,
)
from backend.app.services.verifier import RunnerOutput

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFECT_ID = "dev-off_by_one-001"
SECRET = "AIza-must-never-reach-an-artifact-01234"


class StubVerifier:
    """Stands in for Docker. Records what it was asked, answers from a script."""

    def __init__(self, *, fix_works: bool = True, regressions: tuple[str, ...] = ()) -> None:
        self.fix_works = fix_works
        self.regressions = regressions
        self.verified: list[str] = []
        self.baseline_calls = 0

    def preflight(self) -> None:
        return None

    def baseline(self, workspace, node_id, run_id, artifact_dir=None):
        self.baseline_calls += 1
        outcome_map = {
            node_id: "failed",
            "tests/test_paging.py::test_page_count_of_zero_rows_is_zero_pages": "passed",
            "tests/test_slugs.py::test_slugify_lowercases_and_hyphenates": "passed",
        }
        output = RunnerOutput(
            target_test_passed=False, outcomes=outcome_map, tests_run=3, stdout_tail="1 failed"
        )
        if artifact_dir is not None:
            Path(artifact_dir).mkdir(parents=True, exist_ok=True)
            (Path(artifact_dir) / "baseline.json").write_text(
                json.dumps({"passing": sorted(output.passing)}), encoding="utf-8"
            )
        result = VerificationResult(candidate_id="baseline", tests_run=3)
        return output, result

    def verify(self, workspace, node_id, run_id, candidate_id, baseline_passing=None,
               artifact_dir=None):
        self.verified.append(candidate_id)
        result = VerificationResult(
            candidate_id=candidate_id,
            container_exit_code=0,
            target_test_passed=self.fix_works,
            regressions=self.regressions,
            tests_run=3,
            duration_ms=120,
            stdout_tail="stub verifier output",
        )
        if artifact_dir is not None:
            Path(artifact_dir).mkdir(parents=True, exist_ok=True)
            (Path(artifact_dir) / "verification.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
            (Path(artifact_dir) / "stdout.txt").write_text(result.stdout_tail, encoding="utf-8")
        return result


def settings_for(tmp_path: Path, **overrides) -> Settings:
    base = {
        "artifact_root": str(tmp_path / "runs"),
        "database_path": str(tmp_path / "fixproof.sqlite"),
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def run_with(settings: Settings, verifier=None, **kwargs):
    orchestrator = Orchestrator(settings, verifier=verifier or StubVerifier(), **kwargs)
    return orchestrator.run(DEFECT_ID)


class TestAllGatedPath:
    def test_fake_candidates_two_and_three_are_gated(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake"))
        gates = {
            outcome.candidate.candidate_id: outcome.rejecting_gate
            for outcome in record.outcomes
        }
        assert gates["r1-scope"] == "scope"
        assert gates["r1-testedit"] == "no_test_edits"

    def test_the_noop_candidate_reaches_a_container(self, tmp_path) -> None:
        verifier = StubVerifier(fix_works=False)
        record = run_with(settings_for(tmp_path, model_mode="fake"), verifier)
        assert verifier.verified == ["r1-noop"]
        assert record.decision is Decision.NO_VERIFIED_FIX

    def test_all_gated_when_nothing_survives_the_gates(self, tmp_path) -> None:
        """With MAX_CANDIDATES=2 the no-op is dropped and only rejects remain."""
        settings = settings_for(tmp_path, model_mode="fake", max_candidates=3)
        orchestrator = Orchestrator(settings, verifier=StubVerifier())
        record = orchestrator.run(DEFECT_ID)
        surviving = [o for o in record.outcomes if o.rejecting_gate is None]
        assert len(surviving) == 1, "only the whitespace candidate should survive the gates"


class TestNoVerifiedFixPath:
    def test_a_noop_candidate_verifies_and_fails_eligibility(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake"), StubVerifier(fix_works=False))
        assert record.decision is Decision.NO_VERIFIED_FIX
        assert record.chosen_candidate_id is None

    def test_a_regression_is_not_a_fix(self, tmp_path) -> None:
        verifier = StubVerifier(fix_works=True, regressions=("tests/test_slugs.py::test_a",))
        record = run_with(settings_for(tmp_path, model_mode="fake"), verifier)
        assert record.decision is Decision.NO_VERIFIED_FIX


class TestFixVerifiedPath:
    def test_fake_solve_reaches_a_verified_fix(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake_solve"), StubVerifier())
        assert record.decision is Decision.FIX_VERIFIED
        assert record.status is RunStatus.SUCCEEDED

    def test_the_reference_patch_is_the_one_selected(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake_solve"), StubVerifier())
        assert record.chosen_candidate_id == "r1-reference"


class TestBudgets:
    def test_run_timeout_names_the_stage(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake", max_run_seconds=0))
        assert record.decision is Decision.TIMEOUT
        assert record.timeout_stage == "baseline"
        assert record.status is RunStatus.FAILED

    def test_a_timeout_still_writes_its_artifacts(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake", max_run_seconds=0))
        artifacts = Path(record.artifact_dir)
        assert (artifacts / "run.json").is_file()
        assert (artifacts / "report.md").is_file()

    def test_cancellation_is_cooperative(self, tmp_path) -> None:
        settings = settings_for(tmp_path, model_mode="fake")
        orchestrator = Orchestrator(settings, verifier=StubVerifier())
        record = orchestrator.run(DEFECT_ID, cancel=lambda: True)
        assert record.status is RunStatus.CANCELLED


class TestSecondRound:
    def test_one_round_by_default(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake"), StubVerifier(fix_works=False))
        assert record.rounds_used == 1

    def test_a_second_round_runs_when_enabled_and_nothing_was_eligible(self, tmp_path) -> None:
        settings = settings_for(tmp_path, model_mode="fake", max_propose_rounds=2)
        record = run_with(settings, StubVerifier(fix_works=False))
        assert record.rounds_used == 2
        assert (Path(record.artifact_dir) / "round-2" / "prompt.txt").is_file()

    def test_the_second_round_receives_the_first_round_s_failures(self, tmp_path) -> None:
        settings = settings_for(tmp_path, model_mode="fake", max_propose_rounds=2)
        record = run_with(settings, StubVerifier(fix_works=False))
        prompt = (Path(record.artifact_dir) / "round-2" / "prompt.txt").read_text(encoding="utf-8")
        assert "What the previous round proved" in prompt
        assert "no_test_edits" in prompt

    def test_no_second_round_once_something_is_eligible(self, tmp_path) -> None:
        settings = settings_for(tmp_path, model_mode="fake_solve", max_propose_rounds=2)
        record = run_with(settings, StubVerifier())
        assert record.rounds_used == 1


class TestFeedback:
    def test_a_gated_candidate_reports_its_gate(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake"), StubVerifier(fix_works=False))
        lines = feedback_from(list(record.outcomes))
        assert any("scope" in line for line in lines)
        assert any("no_test_edits" in line for line in lines)

    def test_a_regression_is_named(self, tmp_path) -> None:
        verifier = StubVerifier(regressions=("tests/test_slugs.py::test_a",))
        record = run_with(settings_for(tmp_path, model_mode="fake"), verifier)
        assert any("tests/test_slugs.py::test_a" in line for line in feedback_from(list(record.outcomes)))


class TestArtifacts:
    def test_artifacts_complete(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake"), StubVerifier(fix_works=False))
        artifacts = Path(record.artifact_dir)
        for name in (
            "run.json",
            "defect.json",
            "baseline.json",
            "retrieval.json",
            "report.md",
            "report.json",
            "round-1/prompt.txt",
            "round-1/response.raw.json",
            "round-1/candidates.json",
        ):
            assert (artifacts / name).is_file(), name

        candidate_dir = artifacts / "candidates" / "r1-noop"
        for name in ("applied.patch", "apply.log", "gates.json", "verification.json", "stdout.txt"):
            assert (candidate_dir / name).is_file(), name

    def test_a_gated_candidate_still_records_its_gates(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake"), StubVerifier())
        gates_file = Path(record.artifact_dir) / "candidates" / "r1-testedit" / "gates.json"
        payload = json.loads(gates_file.read_text(encoding="utf-8"))
        assert any(entry["gate"] == "no_test_edits" and not entry["passed"] for entry in payload)

    def test_no_secret_in_artifacts(self, tmp_path) -> None:
        settings = settings_for(tmp_path, model_mode="fake", gemini_api_key=SECRET)
        record = run_with(settings, StubVerifier())
        for path in Path(record.artifact_dir).rglob("*"):
            if path.is_file() and path.suffix in {".json", ".txt", ".md", ".patch", ".log"}:
                assert SECRET not in path.read_text(encoding="utf-8", errors="ignore"), path

    def test_the_run_record_round_trips_through_its_artifact(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake"), StubVerifier())
        payload = json.loads((Path(record.artifact_dir) / "run.json").read_text(encoding="utf-8"))
        assert payload["run_id"] == record.run_id
        assert payload["decision"] == (record.decision.value if record.decision else None)


class TestReport:
    @pytest.mark.parametrize(
        ("mode", "verifier_kwargs", "expected"),
        [
            ("fake", {"fix_works": False}, "NO_VERIFIED_FIX"),
            ("fake_solve", {}, "FIX_VERIFIED"),
        ],
    )
    def test_report_renders_for_each_decision(self, tmp_path, mode, verifier_kwargs, expected):
        record = run_with(settings_for(tmp_path, model_mode=mode), StubVerifier(**verifier_kwargs))
        report = (Path(record.artifact_dir) / "report.md").read_text(encoding="utf-8")
        assert expected in report
        assert "cost unavailable" in report

    def test_a_fake_solve_report_is_stamped_as_not_a_measurement(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake_solve"), StubVerifier())
        report = (Path(record.artifact_dir) / "report.md").read_text(encoding="utf-8")
        assert "reads the fixture's reference patch" in report
        assert "100% by construction" in report

    def test_the_report_json_says_whether_it_measures_a_model(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake"), StubVerifier())
        payload = json.loads(
            (Path(record.artifact_dir) / "report.json").read_text(encoding="utf-8")
        )
        assert payload["measures_a_model"] is False

    def test_a_timeout_report_names_the_stage(self, tmp_path) -> None:
        record = run_with(settings_for(tmp_path, model_mode="fake", max_run_seconds=0))
        report = (Path(record.artifact_dir) / "report.md").read_text(encoding="utf-8")
        assert "TIMEOUT" in report
        assert "baseline" in report


class TestEvents:
    def test_stages_are_emitted_in_order(self, tmp_path) -> None:
        events: list[dict] = []
        settings = settings_for(tmp_path, model_mode="fake_solve")
        Orchestrator(settings, verifier=StubVerifier()).run(DEFECT_ID, on_event=events.append)
        started = [
            event["stage"]
            for event in events
            if event["type"] == "stage" and event["state"] == "started"
        ]
        assert started[:4] == ["prepare", "baseline", "retrieve", "propose"]
        assert "verify" in started
        assert started[-1] == "select"

    def test_a_candidate_event_is_emitted_per_candidate(self, tmp_path) -> None:
        events: list[dict] = []
        settings = settings_for(tmp_path, model_mode="fake")
        Orchestrator(settings, verifier=StubVerifier()).run(DEFECT_ID, on_event=events.append)
        candidate_events = [event for event in events if event["type"] == "candidate"]
        assert len(candidate_events) == 3
        assert {event["status"] for event in candidate_events} == {"gated", "verified"}

    def test_a_done_event_closes_the_run(self, tmp_path) -> None:
        events: list[dict] = []
        settings = settings_for(tmp_path, model_mode="fake_solve")
        Orchestrator(settings, verifier=StubVerifier()).run(DEFECT_ID, on_event=events.append)
        assert events[-1]["type"] == "done"
        assert events[-1]["decision"] == "FIX_VERIFIED"


class TestRunIds:
    def test_run_ids_are_unique(self) -> None:
        assert new_run_id() != new_run_id()

    def test_run_ids_are_filesystem_safe(self) -> None:
        assert all(character.isalnum() or character == "-" for character in new_run_id())
