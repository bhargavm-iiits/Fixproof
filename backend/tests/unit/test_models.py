from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.models import (
    CandidateOutcome,
    CandidatePatch,
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


def diff_for(path: str, before: str = "    return 1", after: str = "    return 2") -> str:
    return (
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,2 +1,2 @@\n"
        " def f():\n"
        f"-{before}\n"
        f"+{after}\n"
    )


GOOD_DIFF = diff_for("slugs.py")


def make_defect(**overrides) -> Defect:
    payload = {
        "defect_id": "dev-off_by_one-001",
        "fixture_set": "dev",
        "summary": "paging returns one row too many at the final page",
        "failing_test": "tests/test_paging.py::test_last_page_is_not_over_long",
        "allowed_paths": ("paging.py",),
        "category": "off_by_one",
        "difficulty": "easy",
    }
    payload.update(overrides)
    return Defect(**payload)


class TestDefect:
    def test_valid_defect_loads(self) -> None:
        assert make_defect().category == "off_by_one"

    def test_empty_allowed_paths_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            make_defect(allowed_paths=())

    def test_unknown_category_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_defect(category="cosmic_ray")

    def test_unknown_difficulty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_defect(difficulty="trivial")

    def test_failing_test_must_be_a_node_id(self) -> None:
        with pytest.raises(ValidationError, match="node id"):
            make_defect(failing_test="tests/test_paging.py")

    def test_absolute_allowed_path_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_defect(allowed_paths=("/etc/passwd",))

    def test_traversing_allowed_path_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_defect(allowed_paths=("../../secret",))


class TestProposedPatch:
    def test_valid_patch_parses(self) -> None:
        patch = ProposedPatch(candidate_id="c1", unified_diff=GOOD_DIFF)
        assert patch.touched_paths == ("slugs.py",)
        assert patch.changed_lines == 2

    def test_empty_diff_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProposedPatch(candidate_id="c1", unified_diff="")

    def test_unparsable_diff_rejected(self) -> None:
        with pytest.raises(ValidationError, match="does not parse"):
            ProposedPatch(candidate_id="c1", unified_diff="I think you should change line 12.")

    def test_touched_paths_derived_not_trusted(self) -> None:
        patch = ProposedPatch(
            candidate_id="c1",
            unified_diff=GOOD_DIFF,
            touched_paths=("something_else.py", "and_another.py"),
            changed_lines=999,
        )
        assert patch.touched_paths == ("slugs.py",)
        assert patch.changed_lines == 2

    def test_changed_lines_must_be_at_least_one(self) -> None:
        context_only = "--- a/slugs.py\n+++ b/slugs.py\n@@ -1,2 +1,2 @@\n def f():\n     return 1\n"
        with pytest.raises(ValidationError, match="changes nothing"):
            ProposedPatch(candidate_id="c1", unified_diff=context_only)

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_confidence_outside_unit_interval_rejected(self, confidence: float) -> None:
        with pytest.raises(ValidationError):
            ProposedPatch(candidate_id="c1", unified_diff=GOOD_DIFF, confidence=confidence)

    @pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
    def test_confidence_inside_unit_interval_accepted(self, confidence: float) -> None:
        assert ProposedPatch(
            candidate_id="c1", unified_diff=GOOD_DIFF, confidence=confidence
        ).confidence == pytest.approx(confidence)

    def test_round_index_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            ProposedPatch(candidate_id="c1", unified_diff=GOOD_DIFF, round_index=0)

    def test_a_test_editing_proposal_is_representable(self) -> None:
        """The gate must be able to reject it, so the proposal must be able to exist."""
        patch = ProposedPatch(candidate_id="c3", unified_diff=diff_for("tests/test_slugs.py"))
        assert patch.touched_paths == ("tests/test_slugs.py",)


class TestCandidatePatch:
    def test_valid_candidate_accepted(self) -> None:
        assert CandidatePatch(candidate_id="c1", unified_diff=GOOD_DIFF).touched_paths == (
            "slugs.py",
        )

    def test_diff_touching_tests_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="test file"):
            CandidatePatch(candidate_id="c1", unified_diff=diff_for("tests/test_x.py"))

    def test_nested_test_directory_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="test file"):
            CandidatePatch(candidate_id="c1", unified_diff=diff_for("pkg/tests/test_x.py"))

    def test_conftest_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="test file"):
            CandidatePatch(candidate_id="c1", unified_diff=diff_for("conftest.py"))

    def test_absolute_path_in_diff_rejected(self) -> None:
        raw = "--- /etc/passwd\n+++ /etc/passwd\n@@ -1,2 +1,2 @@\n root\n-x\n+y\n"
        with pytest.raises(ValidationError, match="absolute path"):
            CandidatePatch(candidate_id="c1", unified_diff=raw)

    def test_windows_absolute_path_rejected(self) -> None:
        raw = "--- C:/Windows/system32/x.py\n+++ C:/Windows/system32/x.py\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n"
        with pytest.raises(ValidationError, match="absolute path"):
            CandidatePatch(candidate_id="c1", unified_diff=raw)

    def test_parent_traversal_rejected(self) -> None:
        with pytest.raises(ValidationError, match="parent traversal"):
            CandidatePatch(candidate_id="c1", unified_diff=diff_for("../../secret"))

    def test_from_proposal_promotes_a_safe_patch(self) -> None:
        proposal = ProposedPatch(candidate_id="c1", unified_diff=GOOD_DIFF, confidence=0.9)
        candidate = CandidatePatch.from_proposal(proposal)
        assert candidate.candidate_id == "c1"
        assert candidate.confidence == pytest.approx(0.9)

    def test_from_proposal_refuses_an_unsafe_patch(self) -> None:
        proposal = ProposedPatch(candidate_id="c3", unified_diff=diff_for("tests/test_x.py"))
        with pytest.raises(ValidationError):
            CandidatePatch.from_proposal(proposal)


class TestVerificationResult:
    def test_eligible_when_target_passes_with_no_regressions(self) -> None:
        assert VerificationResult(candidate_id="c1", target_test_passed=True).eligible

    def test_regression_makes_it_ineligible(self) -> None:
        result = VerificationResult(
            candidate_id="c1", target_test_passed=True, regressions=("tests/t.py::test_a",)
        )
        assert not result.eligible

    def test_timeout_makes_it_ineligible(self) -> None:
        assert not VerificationResult(
            candidate_id="c1", target_test_passed=True, timed_out=True
        ).eligible

    def test_failing_target_is_ineligible(self) -> None:
        assert not VerificationResult(candidate_id="c1", target_test_passed=False).eligible


class TestCandidateOutcome:
    def test_rejecting_gate_is_the_first_failure(self) -> None:
        outcome = CandidateOutcome(
            candidate=ProposedPatch(candidate_id="c1", unified_diff=GOOD_DIFF),
            gates=(
                GateResult(gate="diff_parses", passed=True),
                GateResult(gate="scope", passed=False, detail="outside allowed_paths"),
                GateResult(gate="no_test_edits", passed=False, detail="unreached"),
            ),
            status=CandidateStatus.GATED,
        )
        assert outcome.rejecting_gate == "scope"

    def test_no_rejecting_gate_when_all_pass(self) -> None:
        outcome = CandidateOutcome(
            candidate=ProposedPatch(candidate_id="c1", unified_diff=GOOD_DIFF),
            gates=(GateResult(gate="diff_parses", passed=True),),
        )
        assert outcome.rejecting_gate is None


class TestUsage:
    def test_merge_sums_counts(self) -> None:
        merged = Usage(calls=1, input_tokens=10, output_tokens=5).merged_with(
            Usage(calls=1, input_tokens=7, output_tokens=3)
        )
        assert (merged.calls, merged.input_tokens, merged.output_tokens) == (2, 17, 8)

    def test_merge_keeps_cost_unavailable_when_unpriced(self) -> None:
        merged = Usage(calls=1).merged_with(Usage(calls=1))
        assert merged.cost_usd is None
        assert merged.priced is False

    def test_merge_is_priced_only_when_both_are(self) -> None:
        priced = Usage(calls=1, cost_usd=0.1, priced=True)
        assert priced.merged_with(priced).priced is True
        assert priced.merged_with(Usage(calls=1)).priced is False


class TestRunRecord:
    def test_minimal_run_record(self) -> None:
        record = RunRecord(run_id="r1", defect_id="dev-off_by_one-001")
        assert record.status is RunStatus.QUEUED
        assert record.decision is None
        assert record.duration_seconds is None

    def test_decision_enum_round_trips(self) -> None:
        record = RunRecord(run_id="r1", defect_id="d1", decision=Decision.ALL_GATED)
        assert record.model_dump(mode="json")["decision"] == "ALL_GATED"
