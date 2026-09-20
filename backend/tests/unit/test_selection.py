from __future__ import annotations

import pytest

from backend.app.models import (
    CandidateOutcome,
    CandidateStatus,
    Decision,
    GateResult,
    ProposedPatch,
    VerificationResult,
)
from backend.app.services.selection import decide, is_eligible, rank_key, select


def diff_touching(paths: list[str], pairs: int = 1) -> str:
    parts = []
    for path in paths:
        body = "".join(f"-old{index}\n+new{index}\n" for index in range(pairs))
        parts.append(f"--- a/{path}\n+++ b/{path}\n@@ -1,{pairs} +1,{pairs} @@\n{body}")
    return "".join(parts)


def outcome(
    candidate_id: str,
    *,
    paths: list[str] | None = None,
    pairs: int = 1,
    confidence: float = 0.5,
    round_index: int = 1,
    verified: bool = True,
    target_passed: bool = True,
    regressions: tuple[str, ...] = (),
    timed_out: bool = False,
) -> CandidateOutcome:
    candidate = ProposedPatch(
        candidate_id=candidate_id,
        round_index=round_index,
        confidence=confidence,
        unified_diff=diff_touching(paths or ["paging.py"], pairs),
    )
    verification = None
    if verified:
        verification = VerificationResult(
            candidate_id=candidate_id,
            target_test_passed=target_passed,
            regressions=regressions,
            timed_out=timed_out,
        )
    return CandidateOutcome(
        candidate=candidate,
        gates=(GateResult(gate="diff_parses", passed=True),),
        verification=verification,
        status=CandidateStatus.VERIFIED if verified else CandidateStatus.GATED,
    )


def gated(candidate_id: str, gate: str = "scope") -> CandidateOutcome:
    return CandidateOutcome(
        candidate=ProposedPatch(candidate_id=candidate_id, unified_diff=diff_touching(["x.py"])),
        gates=(
            GateResult(gate="diff_parses", passed=True),
            GateResult(gate=gate, passed=False, detail="rejected"),
        ),
        status=CandidateStatus.GATED,
    )


class TestEligibility:
    def test_a_verified_clean_candidate_is_eligible(self) -> None:
        assert is_eligible(outcome("c1"))

    def test_a_failing_target_is_not_eligible(self) -> None:
        assert not is_eligible(outcome("c1", target_passed=False))

    def test_a_regression_disqualifies_however_confident_the_model_was(self) -> None:
        assert not is_eligible(outcome("c1", confidence=1.0, regressions=("tests/t.py::test_a",)))

    def test_a_timeout_disqualifies(self) -> None:
        assert not is_eligible(outcome("c1", timed_out=True))

    def test_an_unverified_candidate_is_not_eligible(self) -> None:
        assert not is_eligible(gated("c1"))


class TestRanking:
    def test_fewest_changed_lines_wins(self) -> None:
        small = outcome("big-id-but-small", pairs=1)
        large = outcome("aaa-large", pairs=4)
        assert select([large, small]) is small

    def test_fewest_touched_files_breaks_a_line_tie(self) -> None:
        one_file = outcome("b", paths=["paging.py"], pairs=2)
        two_files = outcome("a", paths=["paging.py", "slugs.py"], pairs=1)
        assert one_file.candidate.changed_lines == two_files.candidate.changed_lines
        assert select([two_files, one_file]) is one_file

    def test_highest_confidence_breaks_a_file_tie(self) -> None:
        shy = outcome("a", confidence=0.2)
        bold = outcome("z", confidence=0.9)
        assert select([shy, bold]) is bold

    def test_lowest_round_index_breaks_a_confidence_tie(self) -> None:
        first = outcome("z", round_index=1)
        second = outcome("a", round_index=2)
        assert select([second, first]) is first

    def test_lowest_candidate_id_is_the_final_tie_break(self) -> None:
        alpha = outcome("a")
        omega = outcome("z")
        assert select([omega, alpha]) is alpha

    def test_selection_is_deterministic_under_reordering(self) -> None:
        candidates = [outcome("c"), outcome("a"), outcome("b")]
        first = select(candidates)
        second = select(list(reversed(candidates)))
        assert first is not None and second is not None
        assert first.candidate.candidate_id == second.candidate.candidate_id

    def test_ineligible_candidates_are_never_selected(self) -> None:
        tiny_but_broken = outcome("a", pairs=1, regressions=("tests/t.py::test_a",))
        larger_but_clean = outcome("z", pairs=5)
        assert select([tiny_but_broken, larger_but_clean]) is larger_but_clean

    def test_nothing_eligible_selects_nothing(self) -> None:
        assert select([outcome("a", target_passed=False), gated("b")]) is None

    def test_an_empty_list_selects_nothing(self) -> None:
        assert select([]) is None

    def test_rank_key_has_no_time_component(self) -> None:
        key = rank_key(outcome("c1"))
        assert key == (2, 1, pytest.approx(-0.5), 1, "c1")


class TestDecisions:
    def test_an_eligible_candidate_is_a_verified_fix(self) -> None:
        assert decide([outcome("c1")]) is Decision.FIX_VERIFIED

    def test_verified_but_none_eligible_is_no_verified_fix(self) -> None:
        assert decide([outcome("c1", target_passed=False)]) is Decision.NO_VERIFIED_FIX

    def test_every_candidate_gated_is_all_gated(self) -> None:
        assert decide([gated("c1"), gated("c2")]) is Decision.ALL_GATED

    def test_a_mix_of_gated_and_verified_is_not_all_gated(self) -> None:
        """One candidate reaching a container means the gates did not stop everything."""
        outcomes = [gated("c1"), outcome("c2", target_passed=False)]
        assert decide(outcomes) is Decision.NO_VERIFIED_FIX

    def test_a_timeout_wins_over_the_candidate_state(self) -> None:
        assert decide([outcome("c1")], timed_out=True) is Decision.TIMEOUT

    def test_an_error_wins_over_everything(self) -> None:
        assert decide([outcome("c1")], timed_out=True, errored=True) is Decision.ERROR

    def test_no_candidates_at_all_is_no_verified_fix(self) -> None:
        assert decide([]) is Decision.NO_VERIFIED_FIX
