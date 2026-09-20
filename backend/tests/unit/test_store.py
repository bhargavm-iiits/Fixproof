from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

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
from backend.app.services.store import SCHEMA_VERSION, Store

DIFF = "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "nested" / "fixproof.sqlite")


def full_record(run_id: str = "run-1", started: datetime | None = None) -> RunRecord:
    started = started or datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    verified = CandidateOutcome(
        candidate=ProposedPatch(
            candidate_id="r1-noop", rationale="whitespace", unified_diff=DIFF, confidence=0.25
        ),
        gates=(
            GateResult(gate="diff_parses", passed=True, detail="1 file(s) touched"),
            GateResult(gate="scope", passed=True),
        ),
        verification=VerificationResult(
            candidate_id="r1-noop",
            container_exit_code=0,
            target_test_passed=False,
            regressions=("tests/test_slugs.py::test_a",),
            newly_passing=("tests/test_x.py::test_b",),
            tests_run=330,
            duration_ms=4200,
            stdout_tail="1 failed",
        ),
        status=CandidateStatus.VERIFIED,
    )
    gated = CandidateOutcome(
        candidate=ProposedPatch(candidate_id="r1-testedit", unified_diff=DIFF),
        gates=(
            GateResult(gate="diff_parses", passed=True),
            GateResult(gate="no_test_edits", passed=False, detail="edits a test file"),
        ),
        status=CandidateStatus.GATED,
    )
    return RunRecord(
        run_id=run_id,
        defect_id="dev-off_by_one-001",
        fixture_set="dev",
        status=RunStatus.SUCCEEDED,
        decision=Decision.NO_VERIFIED_FIX,
        chosen_candidate_id=None,
        stage_timings={"prepare": 12.5, "verify": 4200.0},
        usage=Usage(calls=1, input_tokens=1200, output_tokens=340),
        artifact_dir="runtime/runs/run-1",
        model_mode="fake",
        model_name="fake",
        config_hash="abc123",
        rounds_used=1,
        outcomes=(verified, gated),
        started_at=started,
        finished_at=started + timedelta(seconds=9),
    )


class TestSchema:
    def test_the_version_row_is_written(self, store: Store) -> None:
        assert store.schema_version == SCHEMA_VERSION

    def test_migrate_is_idempotent(self, store: Store) -> None:
        store.migrate()
        store.migrate()
        assert store.schema_version == SCHEMA_VERSION
        with store.connect() as connection:
            rows = connection.execute("SELECT COUNT(*) AS n FROM schema_version").fetchone()
        assert rows["n"] == 1

    def test_the_parent_directory_is_created(self, tmp_path) -> None:
        store = Store(tmp_path / "a" / "b" / "c.sqlite")
        assert store.path.parent.is_dir()

    def test_foreign_keys_are_enforced(self, store: Store) -> None:
        """SQLite defaults them off; a schema that declares them must enable them."""
        with pytest.raises(sqlite3.IntegrityError), store.connect() as connection:
            connection.execute(
                """
                INSERT INTO candidates
                    (run_id, candidate_id, round_index, changed_lines, status)
                VALUES ('no-such-run', 'c1', 1, 2, 'proposed')
                """
            )

    def test_wal_is_enabled(self, store: Store) -> None:
        with store.connect() as connection:
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"


class TestRoundTrip:
    def test_a_full_run_round_trips(self, store: Store) -> None:
        original = full_record()
        store.save_run(original)
        restored = store.get_run("run-1")
        assert restored is not None
        assert restored.run_id == original.run_id
        assert restored.decision is Decision.NO_VERIFIED_FIX
        assert restored.status is RunStatus.SUCCEEDED
        assert restored.config_hash == "abc123"
        assert restored.stage_timings == {"prepare": 12.5, "verify": 4200.0}
        assert restored.started_at == original.started_at

    def test_candidates_round_trip(self, store: Store) -> None:
        store.save_run(full_record())
        restored = store.get_run("run-1")
        assert restored is not None
        assert [o.candidate.candidate_id for o in restored.outcomes] == ["r1-noop", "r1-testedit"]
        assert restored.outcomes[0].candidate.touched_paths == ("paging.py",)
        assert restored.outcomes[0].candidate.confidence == pytest.approx(0.25)

    def test_gate_results_round_trip_in_order(self, store: Store) -> None:
        store.save_run(full_record())
        restored = store.get_run("run-1")
        assert restored is not None
        gated = restored.outcomes[1]
        assert [gate.gate for gate in gated.gates] == ["diff_parses", "no_test_edits"]
        assert gated.rejecting_gate == "no_test_edits"

    def test_verifications_round_trip(self, store: Store) -> None:
        store.save_run(full_record())
        restored = store.get_run("run-1")
        assert restored is not None
        verification = restored.outcomes[0].verification
        assert verification is not None
        assert verification.regressions == ("tests/test_slugs.py::test_a",)
        assert verification.newly_passing == ("tests/test_x.py::test_b",)
        assert verification.tests_run == 330

    def test_a_gated_candidate_has_no_verification(self, store: Store) -> None:
        store.save_run(full_record())
        restored = store.get_run("run-1")
        assert restored is not None
        assert restored.outcomes[1].verification is None

    def test_usage_round_trips(self, store: Store) -> None:
        store.save_run(full_record())
        restored = store.get_run("run-1")
        assert restored is not None
        assert restored.usage.calls == 1
        assert restored.usage.input_tokens == 1200
        assert restored.usage.priced is False
        assert restored.usage.cost_usd is None

    def test_saving_twice_replaces_rather_than_duplicates(self, store: Store) -> None:
        store.save_run(full_record())
        store.save_run(full_record())
        restored = store.get_run("run-1")
        assert restored is not None
        assert len(restored.outcomes) == 2
        assert store.count_runs() == 1

    def test_an_unknown_run_is_none(self, store: Store) -> None:
        assert store.get_run("nope") is None


class TestQueries:
    def test_latest_runs_are_newest_first(self, store: Store) -> None:
        base = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
        for index in range(5):
            store.save_run(full_record(f"run-{index}", base + timedelta(minutes=index)))
        summaries = store.latest_runs(limit=3)
        assert [summary.run_id for summary in summaries] == ["run-4", "run-3", "run-2"]

    def test_latest_runs_paginate(self, store: Store) -> None:
        base = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
        for index in range(5):
            store.save_run(full_record(f"run-{index}", base + timedelta(minutes=index)))
        assert [s.run_id for s in store.latest_runs(limit=2, offset=2)] == ["run-2", "run-1"]

    def test_counting_runs(self, store: Store) -> None:
        store.save_run(full_record("run-a"))
        store.save_run(full_record("run-b"))
        assert store.count_runs() == 2

    def test_rejections_by_gate(self, store: Store) -> None:
        store.save_run(full_record())
        assert store.rejections_by_gate() == {"no_test_edits": 1}

    def test_last_decision_by_defect(self, store: Store) -> None:
        store.save_run(full_record())
        assert store.last_decision_by_defect() == {"dev-off_by_one-001": "NO_VERIFIED_FIX"}

    def test_an_empty_store_answers_cleanly(self, store: Store) -> None:
        assert store.latest_runs() == []
        assert store.count_runs() == 0
        assert store.rejections_by_gate() == {}
