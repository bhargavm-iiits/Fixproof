"""Per-run reports.

Cost is reported as unavailable rather than as a confident zero. Google does not
publish per-token prices on the models page, so `GEMINI_PRICE_*` are empty by
default and a report that printed `$0.00` would be lying.
"""

from __future__ import annotations

import json

from backend.app.config import Settings
from backend.app.models import CandidateOutcome, Decision, RunRecord
from backend.app.services.fingerprint import behaviour_document
from backend.app.services.selection import is_eligible

COST_UNAVAILABLE = "cost unavailable: token prices not configured"
FAKE_SOLVE_WARNING = (
    "**This run used `MODEL_MODE=fake_solve`, which reads the fixture's reference "
    "patch. Its fix rate is 100% by construction. It is not a measurement of any "
    "model.**"
)
FAKE_WARNING = (
    "This run used `MODEL_MODE=fake`, which proposes deliberately rejectable "
    "patches. It measures the harness, not a model."
)


def cost_line(record: RunRecord) -> str:
    if not record.usage.priced or record.usage.cost_usd is None:
        return COST_UNAVAILABLE
    return f"${record.usage.cost_usd:.6f}"


def _outcome_row(outcome: CandidateOutcome) -> str:
    candidate = outcome.candidate
    gate = outcome.rejecting_gate or "—"
    passed = sum(1 for result in outcome.gates if result.passed)
    verification = outcome.verification
    if verification is None:
        target = "—"
        regressions = "—"
        duration = "—"
    else:
        target = "pass" if verification.target_test_passed else "fail"
        regressions = ", ".join(verification.regressions) if verification.regressions else "none"
        duration = f"{verification.duration_ms} ms"
    return (
        f"| `{candidate.candidate_id}` | {candidate.changed_lines} | "
        f"{', '.join(candidate.touched_paths) or '—'} | {passed}/{len(outcome.gates)} | "
        f"{gate} | {target} | {regressions} | {duration} |"
    )


def render_markdown(record: RunRecord, settings: Settings) -> str:
    lines: list[str] = [
        f"# Run `{record.run_id}`",
        "",
    ]
    if record.model_mode == "fake_solve":
        lines.extend([FAKE_SOLVE_WARNING, ""])
    elif record.model_mode == "fake":
        lines.extend([FAKE_WARNING, ""])

    lines.extend(
        [
            "| | |",
            "|---|---|",
            f"| Defect | `{record.defect_id}` |",
            f"| Fixture set | {record.fixture_set} |",
            f"| Decision | **{record.decision.value if record.decision else 'unknown'}** |",
            f"| Status | {record.status.value} |",
            f"| Model mode | `{record.model_mode}` |",
            f"| Model | `{record.model_name or '—'}` |",
            f"| Config hash | `{record.config_hash}` |",
            f"| Rounds used | {record.rounds_used} |",
            f"| Duration | {record.duration_seconds:.2f} s |"
            if record.duration_seconds is not None
            else "| Duration | — |",
            "",
        ]
    )

    if record.timeout_stage:
        lines.extend([f"The run ended during the **{record.timeout_stage}** stage.", ""])
    if record.error:
        lines.extend([f"Error: `{record.error}`", ""])

    chosen = next(
        (
            outcome
            for outcome in record.outcomes
            if outcome.candidate.candidate_id == record.chosen_candidate_id
        ),
        None,
    )
    if chosen is not None:
        lines.extend(
            [
                "## Verified fix",
                "",
                f"Candidate `{chosen.candidate.candidate_id}` — "
                f"{chosen.candidate.changed_lines} changed line(s) in "
                f"{', '.join(chosen.candidate.touched_paths)}.",
                "",
                f"> {chosen.candidate.rationale}" if chosen.candidate.rationale else "",
                "",
                "```diff",
                chosen.candidate.unified_diff.rstrip("\n"),
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "## Candidates",
            "",
            "| Candidate | Lines | Files | Gates passed | Rejected by | Target test | "
            "Regressions | Duration |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    if record.outcomes:
        lines.extend(_outcome_row(outcome) for outcome in record.outcomes)
    else:
        lines.append("| — | — | — | — | — | — | — | — |")
    lines.append("")

    lines.extend(["## Stage timings", "", "| Stage | ms |", "|---|---|"])
    for stage, milliseconds in record.stage_timings.items():
        lines.append(f"| {stage} | {milliseconds:.2f} |")
    lines.append("")

    lines.extend(
        [
            "## Model usage",
            "",
            f"- Calls: {record.usage.calls}",
            f"- Input tokens: {record.usage.input_tokens}",
            f"- Output tokens: {record.usage.output_tokens}",
            f"- Cost: {cost_line(record)}",
            "",
        ]
    )
    return "\n".join(line for line in lines if line is not None) + "\n"


def render_json(record: RunRecord, settings: Settings) -> str:
    payload = {
        "run_id": record.run_id,
        "defect_id": record.defect_id,
        "fixture_set": record.fixture_set,
        "status": record.status.value,
        "decision": record.decision.value if record.decision else None,
        "chosen_candidate_id": record.chosen_candidate_id,
        "model_mode": record.model_mode,
        "model_name": record.model_name,
        "config_hash": record.config_hash,
        "config": behaviour_document(settings),
        "rounds_used": record.rounds_used,
        "timeout_stage": record.timeout_stage,
        "error": record.error,
        "stage_timings": record.stage_timings,
        "duration_seconds": record.duration_seconds,
        "measures_a_model": record.model_mode == "gemini",
        "usage": {
            "calls": record.usage.calls,
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cost_usd": record.usage.cost_usd,
            "priced": record.usage.priced,
            "cost_note": None if record.usage.priced else COST_UNAVAILABLE,
        },
        "candidates": [
            {
                "candidate_id": outcome.candidate.candidate_id,
                "round_index": outcome.candidate.round_index,
                "rationale": outcome.candidate.rationale,
                "changed_lines": outcome.candidate.changed_lines,
                "touched_paths": list(outcome.candidate.touched_paths),
                "confidence": outcome.candidate.confidence,
                "status": outcome.status.value,
                "rejected_by": outcome.rejecting_gate,
                "eligible": is_eligible(outcome),
                "gates": [
                    {"gate": result.gate, "passed": result.passed, "detail": result.detail}
                    for result in outcome.gates
                ],
                "verification": (
                    outcome.verification.model_dump(mode="json")
                    if outcome.verification is not None
                    else None
                ),
            }
            for outcome in record.outcomes
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def decision_explanation(decision: Decision | None) -> str:
    return {
        Decision.FIX_VERIFIED: (
            "A container proved the failing test now passes with no regressions."
        ),
        Decision.NO_VERIFIED_FIX: "Candidates reached a container, but none was eligible.",
        Decision.ALL_GATED: "Every candidate was rejected before a container was started.",
        Decision.TIMEOUT: "The run's wall clock expired.",
        Decision.ERROR: "The run failed with an unhandled error.",
        None: "The run has not finished.",
    }[decision]
