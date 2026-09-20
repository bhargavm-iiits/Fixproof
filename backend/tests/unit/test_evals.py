"""Tests for the eval runner's arithmetic and its refusal to mis-report."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "evals"))

from run_eval import (  # noqa: E402
    compute_metrics,
    harness_checks,
    main,
    mean,
    percentile,
    reference_line_count,
    source_path_of,
)

from backend.app.models import (  # noqa: E402
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

DIFF = "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"
TEST_DIFF = (
    "--- a/tests/test_paging.py\n+++ b/tests/test_paging.py\n"
    "@@ -1,2 +1,2 @@\n ctx\n-assert a == b\n+assert a != b\n"
)
SCOPE_DIFF = "--- a/slugs.py\n+++ b/slugs.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"


def candidate(
    candidate_id: str,
    diff: str = DIFF,
    *,
    gate: str | None = None,
    target_passed: bool = False,
    regressions: tuple[str, ...] = (),
    verified: bool = True,
    round_index: int = 1,
) -> CandidateOutcome:
    gates = [GateResult(gate="diff_parses", passed=True)]
    if gate:
        gates.append(GateResult(gate=gate, passed=False, detail="rejected"))
        verified = False
    return CandidateOutcome(
        candidate=ProposedPatch(
            candidate_id=candidate_id, unified_diff=diff, round_index=round_index
        ),
        gates=tuple(gates),
        verification=(
            VerificationResult(
                candidate_id=candidate_id,
                target_test_passed=target_passed,
                regressions=regressions,
            )
            if verified
            else None
        ),
        status=CandidateStatus.VERIFIED if verified else CandidateStatus.GATED,
    )


def record(
    run_id: str = "run-1",
    defect_id: str = "dev-off_by_one-001",
    decision: Decision = Decision.NO_VERIFIED_FIX,
    outcomes: tuple[CandidateOutcome, ...] = (),
    chosen: str | None = None,
    seconds: float = 5.0,
    rounds: int = 1,
    usage: Usage | None = None,
) -> RunRecord:
    started = datetime(2026, 9, 21, 12, tzinfo=UTC)
    return RunRecord(
        run_id=run_id,
        defect_id=defect_id,
        fixture_set="dev",
        status=RunStatus.SUCCEEDED,
        decision=decision,
        chosen_candidate_id=chosen,
        usage=usage or Usage(calls=1),
        model_mode="fake",
        rounds_used=rounds,
        outcomes=outcomes,
        started_at=started,
        finished_at=started + timedelta(seconds=seconds),
    )


def fake_mode_outcomes() -> tuple[CandidateOutcome, ...]:
    """What the fake client produces on every run: one no-op and two rejects."""
    return (
        candidate("r1-noop", DIFF, target_passed=False),
        candidate("r1-scope", SCOPE_DIFF, gate="scope"),
        candidate("r1-testedit", TEST_DIFF, gate="no_test_edits"),
    )


class TestArithmetic:
    def test_mean_of_nothing_is_zero(self) -> None:
        assert mean([]) == 0.0

    def test_mean(self) -> None:
        assert mean([1.0, 2.0, 6.0]) == pytest.approx(3.0)

    def test_percentile_of_nothing_is_zero(self) -> None:
        assert percentile([], 0.95) == 0.0

    def test_p95_of_a_single_value(self) -> None:
        assert percentile([4.0], 0.95) == 4.0

    def test_p95_of_twenty_is_the_nineteenth_value(self) -> None:
        """Nearest-rank: ceil(0.95 * 20) = 19, so the 19th value, not the largest."""
        assert percentile([float(index) for index in range(20)], 0.95) == 18.0

    def test_p95_of_a_hundred_excludes_the_top_five(self) -> None:
        assert percentile([float(index) for index in range(100)], 0.95) == 94.0

    def test_p50_is_the_middle(self) -> None:
        assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.0

    def test_source_path_is_taken_from_a_chunk_id(self) -> None:
        assert source_path_of("function:paging.py::page_count") == "paging.py"
        assert source_path_of("module:slugs.py") == "slugs.py"
        assert source_path_of("test:tests/test_paging.py::test_a") == "tests/test_paging.py"

    def test_reference_line_count_is_read_from_the_fixture(self) -> None:
        assert reference_line_count("dev-off_by_one-001") == 1


class TestMetrics:
    def test_an_empty_run_set_does_not_divide_by_zero(self, tmp_path) -> None:
        metrics = compute_metrics([], tmp_path)
        assert metrics["verified_fix_rate"] == 0.0
        assert metrics["p95_run_seconds"] == 0.0

    def test_verified_fix_rate(self, tmp_path) -> None:
        records = [
            record("r1", decision=Decision.FIX_VERIFIED, chosen="r1-a",
                   outcomes=(candidate("r1-a", target_passed=True),)),
            record("r2", decision=Decision.NO_VERIFIED_FIX),
        ]
        assert compute_metrics(records, tmp_path)["verified_fix_rate"] == pytest.approx(0.5)

    def test_gate_rejection_rate_counts_candidates_not_runs(self, tmp_path) -> None:
        metrics = compute_metrics([record(outcomes=fake_mode_outcomes())], tmp_path)
        assert metrics["candidates_proposed"] == 3
        assert metrics["gate_rejection_rate"] == pytest.approx(2 / 3)

    def test_rejections_by_gate_is_broken_down(self, tmp_path) -> None:
        metrics = compute_metrics([record(outcomes=fake_mode_outcomes())], tmp_path)
        assert metrics["rejections_by_gate"] == {"scope": 1, "no_test_edits": 1}

    def test_the_cheating_rate_counts_every_test_touching_candidate(self, tmp_path) -> None:
        metrics = compute_metrics([record(outcomes=fake_mode_outcomes())], tmp_path)
        assert metrics["test_edit_attempts"] == 1
        assert metrics["test_edit_attempt_rate"] == pytest.approx(1 / 3)

    def test_accepted_test_edits_is_zero_when_the_gate_holds(self, tmp_path) -> None:
        metrics = compute_metrics([record(outcomes=fake_mode_outcomes())], tmp_path)
        assert metrics["accepted_test_edits"] == 0

    def test_an_accepted_test_edit_would_be_counted(self, tmp_path) -> None:
        """If the gate ever failed, the metric must notice rather than stay silent."""
        leaked = candidate("r1-cheat", TEST_DIFF, target_passed=True)
        metrics = compute_metrics([record(outcomes=(leaked,))], tmp_path)
        assert metrics["accepted_test_edits"] == 1

    def test_regression_rate(self, tmp_path) -> None:
        broke = candidate("r1-a", target_passed=True, regressions=("tests/t.py::test_x",))
        records = [record("r1", outcomes=(broke,)), record("r2", outcomes=())]
        assert compute_metrics(records, tmp_path)["regression_rate"] == pytest.approx(0.5)

    def test_candidates_to_first_fix(self, tmp_path) -> None:
        outcomes = (
            candidate("r1-a", target_passed=False),
            candidate("r1-b", target_passed=True),
        )
        metrics = compute_metrics(
            [record(decision=Decision.FIX_VERIFIED, chosen="r1-b", outcomes=outcomes)], tmp_path
        )
        assert metrics["candidates_to_first_fix"] == pytest.approx(2.0)

    def test_mean_changed_lines_is_compared_with_the_reference(self, tmp_path) -> None:
        winner = candidate("r1-a", target_passed=True)
        metrics = compute_metrics(
            [record(decision=Decision.FIX_VERIFIED, chosen="r1-a", outcomes=(winner,))], tmp_path
        )
        assert metrics["mean_changed_lines"] == pytest.approx(2.0)
        assert metrics["mean_reference_changed_lines"] == pytest.approx(1.0)

    def test_terminal_decision_rate(self, tmp_path) -> None:
        assert compute_metrics([record()], tmp_path)["terminal_decision_rate"] == 1.0

    def test_unhandled_errors_are_counted(self, tmp_path) -> None:
        records = [record("r1", decision=Decision.ERROR), record("r2")]
        assert compute_metrics(records, tmp_path)["unhandled_errors"] == 1

    def test_latency(self, tmp_path) -> None:
        records = [record(f"r{index}", seconds=float(index)) for index in range(1, 5)]
        metrics = compute_metrics(records, tmp_path)
        assert metrics["mean_run_seconds"] == pytest.approx(2.5)
        assert metrics["p95_run_seconds"] == pytest.approx(4.0)

    def test_cost_is_unavailable_when_unpriced(self, tmp_path) -> None:
        metrics = compute_metrics([record(usage=Usage(calls=2))], tmp_path)
        assert metrics["priced"] is False
        assert metrics["cost_usd"] is None
        assert metrics["model_calls"] == 2

    def test_cost_is_summed_when_priced(self, tmp_path) -> None:
        usage = Usage(calls=1, cost_usd=0.5, priced=True)
        metrics = compute_metrics([record("r1", usage=usage), record("r2", usage=usage)], tmp_path)
        assert metrics["priced"] is True
        assert metrics["cost_usd"] == pytest.approx(1.0)

    def test_round_two_rescue_rate(self, tmp_path) -> None:
        rescued = candidate("r2-a", target_passed=True, round_index=2)
        records = [
            record("r1", decision=Decision.FIX_VERIFIED, chosen="r2-a",
                   outcomes=(rescued,), rounds=2),
            record("r2", decision=Decision.NO_VERIFIED_FIX, rounds=2),
        ]
        metrics = compute_metrics(records, tmp_path)
        assert metrics["second_round_runs"] == 2
        assert metrics["round_2_rescue_rate"] == pytest.approx(0.5)

    def test_recall_is_measured_against_ranking_not_forcing(self, tmp_path) -> None:
        """Forced inclusions would make this 1.0 by construction."""
        run_dir = tmp_path / "run-recall"
        run_dir.mkdir(parents=True)
        (run_dir / "retrieval.json").write_text(
            json.dumps({"ranked_chunk_ids": ["module:slugs.py", "test:tests/test_x.py::a"]}),
            encoding="utf-8",
        )
        metrics = compute_metrics([record("run-recall")], tmp_path)
        assert metrics["recall_at_8"] == 0.0

    def test_recall_counts_a_hit(self, tmp_path) -> None:
        run_dir = tmp_path / "run-recall"
        run_dir.mkdir(parents=True)
        (run_dir / "retrieval.json").write_text(
            json.dumps({"ranked_chunk_ids": ["function:paging.py::page_count"]}), encoding="utf-8"
        )
        assert compute_metrics([record("run-recall")], tmp_path)["recall_at_8"] == 1.0


class TestHarnessChecks:
    def test_a_healthy_fake_run_passes_every_check(self, tmp_path) -> None:
        records = [record(outcomes=fake_mode_outcomes())]
        metrics = compute_metrics(records, tmp_path)
        checks = harness_checks(records, metrics, "fake")
        assert all(check["passed"] for check in checks), [
            check for check in checks if not check["passed"]
        ]

    def test_the_test_edit_check_fails_when_the_gate_misses(self, tmp_path) -> None:
        missed = candidate("r1-testedit", TEST_DIFF, target_passed=True)
        records = [record(outcomes=(missed,))]
        metrics = compute_metrics(records, tmp_path)
        checks = harness_checks(records, metrics, "fake")
        failed = {check["name"] for check in checks if not check["passed"]}
        assert any("no_test_edits" in name for name in failed)
        assert any("was ever accepted" in name for name in failed)

    def test_the_scope_check_fails_when_the_gate_misses(self, tmp_path) -> None:
        missed = candidate("r1-scope", SCOPE_DIFF, target_passed=False)
        records = [record(outcomes=(missed,))]
        checks = harness_checks(records, compute_metrics(records, tmp_path), "fake")
        assert any(not check["passed"] and "scope" in check["name"] for check in checks)

    def test_an_unhandled_error_fails_the_gate(self, tmp_path) -> None:
        records = [record(decision=Decision.ERROR, outcomes=fake_mode_outcomes())]
        checks = harness_checks(records, compute_metrics(records, tmp_path), "fake")
        assert any(not check["passed"] and "unhandled" in check["name"] for check in checks)

    def test_a_slow_run_fails_the_latency_check(self, tmp_path) -> None:
        records = [record(seconds=9999.0, outcomes=fake_mode_outcomes())]
        checks = harness_checks(records, compute_metrics(records, tmp_path), "fake")
        assert any(not check["passed"] and "p95" in check["name"] for check in checks)

    def test_gemini_mode_skips_the_fake_candidate_checks(self, tmp_path) -> None:
        records = [record(outcomes=(candidate("r1-c1", target_passed=True),))]
        checks = harness_checks(records, compute_metrics(records, tmp_path), "gemini")
        assert not any("fake candidate" in check["name"] for check in checks)


class TestFakeSolveRefusal:
    def test_reporting_from_fake_solve_is_refused_without_the_flag(self, tmp_path, monkeypatch):
        import run_eval

        from backend.app.config import Settings

        monkeypatch.setattr(
            run_eval,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                model_mode="fake_solve",
                artifact_root=str(tmp_path / "runs"),
                database_path=str(tmp_path / "db.sqlite"),
            ),
        )
        code = main(["--set", "dev", "--out-dir", str(tmp_path / "reports")])
        assert code == 2
        assert not list((tmp_path / "reports").glob("*")) if (
            tmp_path / "reports"
        ).exists() else True

    def test_the_refusal_explains_why(self, tmp_path, monkeypatch, capsys):
        import run_eval

        from backend.app.config import Settings

        monkeypatch.setattr(
            run_eval,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                model_mode="fake_solve",
                artifact_root=str(tmp_path / "runs"),
                database_path=str(tmp_path / "db.sqlite"),
            ),
        )
        main(["--set", "dev", "--out-dir", str(tmp_path / "reports")])
        assert "100% by construction" in capsys.readouterr().out
