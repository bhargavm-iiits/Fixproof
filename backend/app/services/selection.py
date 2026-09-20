"""Choosing among verified candidates, and naming the outcome.

Eligibility is not a judgement. A candidate is eligible when a container proved
the failing test passes, nothing that passed before now fails, and the run did
not time out. How confident the model was has no bearing on it.
"""

from __future__ import annotations

from backend.app.models import CandidateOutcome, Decision


def is_eligible(outcome: CandidateOutcome) -> bool:
    verification = outcome.verification
    if verification is None:
        return False
    return (
        verification.target_test_passed
        and not verification.regressions
        and not verification.timed_out
    )


def rank_key(outcome: CandidateOutcome) -> tuple[int, int, float, int, str]:
    """Fewest lines, then fewest files, then most confident, then earliest.

    Fully deterministic: no randomness, and no timestamp anywhere in the
    comparison.
    """
    candidate = outcome.candidate
    return (
        candidate.changed_lines,
        len(candidate.touched_paths),
        -candidate.confidence,
        candidate.round_index,
        candidate.candidate_id,
    )


def select(outcomes: list[CandidateOutcome]) -> CandidateOutcome | None:
    """The winning candidate, or None when nothing is eligible."""
    eligible = [outcome for outcome in outcomes if is_eligible(outcome)]
    if not eligible:
        return None
    return min(eligible, key=rank_key)


def decide(
    outcomes: list[CandidateOutcome],
    timed_out: bool = False,
    errored: bool = False,
) -> Decision:
    """Map the state of a finished run onto one decision.

    `ALL_GATED` is deliberately distinct from `NO_VERIFIED_FIX`: they have
    different causes and different fixes, and collapsing them loses the signal.
    """
    if errored:
        return Decision.ERROR
    if timed_out:
        return Decision.TIMEOUT
    if select(outcomes) is not None:
        return Decision.FIX_VERIFIED
    if outcomes and all(outcome.verification is None for outcome in outcomes):
        return Decision.ALL_GATED
    return Decision.NO_VERIFIED_FIX
