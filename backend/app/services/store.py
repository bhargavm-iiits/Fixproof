"""SQLite persistence. Plain `sqlite3`, no ORM.

Foreign keys and WAL are enabled on every connection: SQLite defaults foreign
keys to *off*, so a schema that declares them and never enables them enforces
nothing.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.app.models import (
    CandidateOutcome,
    CandidateStatus,
    Decision,
    GateResult,
    ProposedPatch,
    RunRecord,
    RunStatus,
    Usage,
    VerificationResult,
)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    defect_id: str
    fixture_set: str
    status: str
    decision: str | None
    chosen_candidate_id: str | None
    model_mode: str
    model_name: str
    config_hash: str
    started_at: str | None
    finished_at: str | None
    artifact_dir: str


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def migrate(self) -> None:
        """Idempotent: running it twice on the same file is a no-op."""
        script = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.connect() as connection:
            connection.executescript(script)
            row = connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
                )

    @property
    def schema_version(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT version FROM schema_version").fetchone()
        return int(row["version"]) if row else 0

    # ------------------------------------------------------------------ write

    def save_run(self, record: RunRecord) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, defect_id, fixture_set, status, decision, chosen_candidate_id,
                    model_mode, model_name, config_hash, rounds_used, timeout_stage, error,
                    stage_timings, started_at, finished_at, artifact_dir
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record.run_id,
                    record.defect_id,
                    record.fixture_set,
                    record.status.value,
                    record.decision.value if record.decision else None,
                    record.chosen_candidate_id,
                    record.model_mode,
                    record.model_name,
                    record.config_hash,
                    record.rounds_used,
                    record.timeout_stage,
                    record.error,
                    json.dumps(record.stage_timings),
                    _iso(record.started_at),
                    _iso(record.finished_at),
                    record.artifact_dir,
                ),
            )
            connection.execute("DELETE FROM candidates WHERE run_id = ?", (record.run_id,))
            connection.execute(
                """
                INSERT OR REPLACE INTO usage
                    (run_id, calls, input_tokens, output_tokens, cost_usd, priced)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    record.run_id,
                    record.usage.calls,
                    record.usage.input_tokens,
                    record.usage.output_tokens,
                    record.usage.cost_usd,
                    int(record.usage.priced),
                ),
            )

            for outcome in record.outcomes:
                candidate = outcome.candidate
                connection.execute(
                    """
                    INSERT INTO candidates (
                        run_id, candidate_id, round_index, rationale, unified_diff,
                        changed_lines, touched_paths, confidence, status
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record.run_id,
                        candidate.candidate_id,
                        candidate.round_index,
                        candidate.rationale,
                        candidate.unified_diff,
                        candidate.changed_lines,
                        json.dumps(list(candidate.touched_paths)),
                        candidate.confidence,
                        outcome.status.value,
                    ),
                )
                for position, gate in enumerate(outcome.gates):
                    connection.execute(
                        """
                        INSERT INTO gate_results
                            (run_id, candidate_id, position, gate, passed, detail)
                        VALUES (?,?,?,?,?,?)
                        """,
                        (
                            record.run_id,
                            candidate.candidate_id,
                            position,
                            gate.gate,
                            int(gate.passed),
                            gate.detail,
                        ),
                    )
                verification = outcome.verification
                if verification is not None:
                    connection.execute(
                        """
                        INSERT INTO verifications (
                            run_id, candidate_id, target_test_passed, regressions,
                            newly_passing, tests_run, duration_ms, timed_out, exit_code,
                            stdout_tail
                        ) VALUES (?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            record.run_id,
                            candidate.candidate_id,
                            int(verification.target_test_passed),
                            json.dumps(list(verification.regressions)),
                            json.dumps(list(verification.newly_passing)),
                            verification.tests_run,
                            verification.duration_ms,
                            int(verification.timed_out),
                            verification.container_exit_code,
                            verification.stdout_tail,
                        ),
                    )

    # ------------------------------------------------------------------- read

    def latest_runs(self, limit: int = 20, offset: int = 0) -> list[RunSummary]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, defect_id, fixture_set, status, decision, chosen_candidate_id,
                       model_mode, model_name, config_hash, started_at, finished_at, artifact_dir
                FROM runs
                ORDER BY started_at DESC, run_id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [RunSummary(**dict(row)) for row in rows]

    def count_runs(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"])

    def last_decision_by_defect(self) -> dict[str, str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT defect_id, decision
                FROM runs
                WHERE decision IS NOT NULL
                GROUP BY defect_id
                HAVING MAX(started_at)
                """
            ).fetchall()
        return {row["defect_id"]: row["decision"] for row in rows}

    def get_run(self, run_id: str) -> RunRecord | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                return None
            usage_row = connection.execute(
                "SELECT * FROM usage WHERE run_id = ?", (run_id,)
            ).fetchone()
            candidate_rows = connection.execute(
                "SELECT * FROM candidates WHERE run_id = ? ORDER BY round_index, candidate_id",
                (run_id,),
            ).fetchall()
            gate_rows = connection.execute(
                "SELECT * FROM gate_results WHERE run_id = ? ORDER BY candidate_id, position",
                (run_id,),
            ).fetchall()
            verification_rows = connection.execute(
                "SELECT * FROM verifications WHERE run_id = ?", (run_id,)
            ).fetchall()

        gates_by_candidate: dict[str, list[GateResult]] = {}
        for gate_row in gate_rows:
            gates_by_candidate.setdefault(gate_row["candidate_id"], []).append(
                GateResult(
                    gate=gate_row["gate"],
                    passed=bool(gate_row["passed"]),
                    detail=gate_row["detail"],
                )
            )
        verifications = {
            verification_row["candidate_id"]: VerificationResult(
                candidate_id=verification_row["candidate_id"],
                container_exit_code=verification_row["exit_code"],
                target_test_passed=bool(verification_row["target_test_passed"]),
                regressions=tuple(json.loads(verification_row["regressions"])),
                newly_passing=tuple(json.loads(verification_row["newly_passing"])),
                tests_run=verification_row["tests_run"],
                duration_ms=verification_row["duration_ms"],
                stdout_tail=verification_row["stdout_tail"],
                timed_out=bool(verification_row["timed_out"]),
            )
            for verification_row in verification_rows
        }

        outcomes: list[CandidateOutcome] = []
        for candidate_row in candidate_rows:
            candidate_id = candidate_row["candidate_id"]
            outcomes.append(
                CandidateOutcome(
                    candidate=ProposedPatch.model_construct(
                        candidate_id=candidate_id,
                        round_index=candidate_row["round_index"],
                        rationale=candidate_row["rationale"],
                        unified_diff=candidate_row["unified_diff"],
                        touched_paths=tuple(json.loads(candidate_row["touched_paths"])),
                        changed_lines=candidate_row["changed_lines"],
                        confidence=candidate_row["confidence"],
                    ),
                    gates=tuple(gates_by_candidate.get(candidate_id, [])),
                    verification=verifications.get(candidate_id),
                    status=CandidateStatus(candidate_row["status"]),
                )
            )

        usage = Usage()
        if usage_row is not None:
            usage = Usage(
                calls=usage_row["calls"],
                input_tokens=usage_row["input_tokens"],
                output_tokens=usage_row["output_tokens"],
                cost_usd=usage_row["cost_usd"],
                priced=bool(usage_row["priced"]),
            )

        return RunRecord(
            run_id=row["run_id"],
            defect_id=row["defect_id"],
            fixture_set=row["fixture_set"],
            status=RunStatus(row["status"]),
            decision=Decision(row["decision"]) if row["decision"] else None,
            chosen_candidate_id=row["chosen_candidate_id"],
            stage_timings=json.loads(row["stage_timings"]),
            usage=usage,
            artifact_dir=row["artifact_dir"],
            model_mode=row["model_mode"],
            model_name=row["model_name"],
            config_hash=row["config_hash"],
            rounds_used=row["rounds_used"],
            timeout_stage=row["timeout_stage"],
            error=row["error"],
            outcomes=tuple(outcomes),
            started_at=_parse(row["started_at"]),
            finished_at=_parse(row["finished_at"]),
        )

    def rejections_by_gate(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT gate, COUNT(*) AS n
                FROM gate_results
                WHERE passed = 0
                GROUP BY gate
                ORDER BY n DESC
                """
            ).fetchall()
        return {row["gate"]: int(row["n"]) for row in rows}
