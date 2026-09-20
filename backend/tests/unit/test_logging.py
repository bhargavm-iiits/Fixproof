from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime

import pytest

from backend.app.config import Settings
from backend.app.logging_setup import (
    LOGGER_NAME,
    REDACTED,
    RedactingJsonFormatter,
    configure_logging,
    get_logger,
    redact,
)
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
from backend.app.services.reporting import COST_UNAVAILABLE, render_json, render_markdown

SECRET = "AIzaSyD-this-is-a-fake-key-000000000000000"
DIFF = "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"


def settings_for(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.fixture
def captured():
    """Attach a buffer to the real logger, exactly as production is configured."""
    settings = settings_for(gemini_api_key=SECRET)
    logger = configure_logging(settings)
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(RedactingJsonFormatter(SECRET))
    logger.handlers = [handler]
    yield logger, buffer
    logger.handlers.clear()


class TestRedaction:
    def test_the_configured_key_is_replaced(self) -> None:
        assert SECRET not in redact(f"using {SECRET} now", SECRET)

    @pytest.mark.parametrize(
        "text",
        [
            "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "api_key=super-secret-value",
            "SECRET: hunter2hunter2hunter2",
            "sk-abcdefghijklmnopqrstuvwxyz0123",
        ],
    )
    def test_generic_key_shapes_are_replaced_even_when_unconfigured(self, text: str) -> None:
        """Redaction at the handler must not depend on knowing the key in advance."""
        assert REDACTED in redact(text)

    def test_ordinary_text_is_left_alone(self) -> None:
        assert redact("the run finished with NO_VERIFIED_FIX") == (
            "the run finished with NO_VERIFIED_FIX"
        )


class TestLogFormat:
    def test_each_line_is_one_json_object(self, captured) -> None:
        logger, buffer = captured
        logger.info("first")
        logger.info("second")
        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        assert len(lines) == 2
        assert all(json.loads(line)["message"] for line in lines)

    def test_every_line_carries_a_run_id_field(self, captured) -> None:
        logger, buffer = captured
        get_logger("run-42").info("hello")
        payload = json.loads(buffer.getvalue().strip())
        assert payload["run_id"] == "run-42"

    def test_extra_fields_are_included(self, captured) -> None:
        logger, buffer = captured
        logger.info("stage", extra={"extra_fields": {"stage": "verify", "ms": 12.5}})
        payload = json.loads(buffer.getvalue().strip())
        assert payload["stage"] == "verify"
        assert payload["ms"] == 12.5

    def test_the_key_never_appears_in_a_log_line(self, captured) -> None:
        logger, buffer = captured
        logger.error("the call failed with key %s", SECRET)
        logger.info("context", extra={"extra_fields": {"authorization": f"Bearer {SECRET}"}})
        assert SECRET not in buffer.getvalue()
        assert REDACTED in buffer.getvalue()

    def test_an_exception_traceback_is_also_redacted(self, captured) -> None:
        logger, buffer = captured
        try:
            raise RuntimeError(f"bad key {SECRET}")
        except RuntimeError:
            logger.exception("call failed")
        assert SECRET not in buffer.getvalue()

    def test_the_level_is_taken_from_settings(self) -> None:
        logger = configure_logging(settings_for(log_level="WARNING"))
        assert logger.level == logging.WARNING

    def test_configuring_twice_does_not_duplicate_handlers(self) -> None:
        configure_logging(settings_for())
        configure_logging(settings_for())
        assert len(logging.getLogger(LOGGER_NAME).handlers) == 1


def record_for(decision: Decision, **overrides) -> RunRecord:
    started = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    outcomes: tuple[CandidateOutcome, ...] = ()
    chosen = None
    if decision in {Decision.FIX_VERIFIED, Decision.NO_VERIFIED_FIX}:
        passed = decision is Decision.FIX_VERIFIED
        outcomes = (
            CandidateOutcome(
                candidate=ProposedPatch(
                    candidate_id="r1-a", rationale="off by one", unified_diff=DIFF
                ),
                gates=(GateResult(gate="diff_parses", passed=True),),
                verification=VerificationResult(
                    candidate_id="r1-a", target_test_passed=passed, tests_run=330, duration_ms=900
                ),
                status=CandidateStatus.VERIFIED,
            ),
        )
        chosen = "r1-a" if passed else None
    elif decision is Decision.ALL_GATED:
        outcomes = (
            CandidateOutcome(
                candidate=ProposedPatch(candidate_id="r1-b", unified_diff=DIFF),
                gates=(
                    GateResult(gate="diff_parses", passed=True),
                    GateResult(gate="scope", passed=False, detail="outside allowed_paths"),
                ),
                status=CandidateStatus.GATED,
            ),
        )

    payload = {
        "run_id": "run-report",
        "defect_id": "dev-off_by_one-001",
        "fixture_set": "dev",
        "status": RunStatus.SUCCEEDED,
        "decision": decision,
        "chosen_candidate_id": chosen,
        "stage_timings": {"prepare": 10.0, "verify": 900.0},
        "usage": Usage(calls=1, input_tokens=100, output_tokens=50),
        "artifact_dir": "runtime/runs/run-report",
        "model_mode": "fake",
        "model_name": "fake",
        "config_hash": "deadbeefdeadbeef",
        "rounds_used": 1,
        "outcomes": outcomes,
        "started_at": started,
        "finished_at": started,
    }
    payload.update(overrides)
    return RunRecord(**payload)


class TestReportRenders:
    @pytest.mark.parametrize("decision", list(Decision))
    def test_report_renders_for_every_decision(self, decision: Decision) -> None:
        extra = {}
        if decision is Decision.TIMEOUT:
            extra = {"timeout_stage": "verify", "status": RunStatus.FAILED}
        if decision is Decision.ERROR:
            extra = {"error": "RuntimeError: the engine went away", "status": RunStatus.FAILED}
        markdown = render_markdown(record_for(decision, **extra), settings_for())
        assert decision.value in markdown
        assert "## Candidates" in markdown

    def test_an_error_report_names_the_error(self) -> None:
        markdown = render_markdown(
            record_for(Decision.ERROR, error="RuntimeError: boom", status=RunStatus.FAILED),
            settings_for(),
        )
        assert "RuntimeError: boom" in markdown

    def test_a_timeout_report_names_the_stage(self) -> None:
        markdown = render_markdown(
            record_for(Decision.TIMEOUT, timeout_stage="verify", status=RunStatus.FAILED),
            settings_for(),
        )
        assert "**verify**" in markdown

    def test_a_verified_fix_shows_the_winning_diff(self) -> None:
        markdown = render_markdown(record_for(Decision.FIX_VERIFIED), settings_for())
        assert "## Verified fix" in markdown
        assert "```diff" in markdown
        assert "-old" in markdown

    def test_a_gated_run_names_the_rejecting_gate(self) -> None:
        markdown = render_markdown(record_for(Decision.ALL_GATED), settings_for())
        assert "scope" in markdown

    def test_cost_is_reported_as_unavailable_rather_than_zero(self) -> None:
        markdown = render_markdown(record_for(Decision.FIX_VERIFIED), settings_for())
        assert COST_UNAVAILABLE in markdown
        assert "$0.00" not in markdown

    def test_cost_is_printed_when_prices_are_configured(self) -> None:
        record = record_for(
            Decision.FIX_VERIFIED,
            usage=Usage(calls=1, input_tokens=10, output_tokens=5, cost_usd=0.25, priced=True),
        )
        assert "$0.250000" in render_markdown(record, settings_for())

    def test_stage_timings_are_tabulated(self) -> None:
        markdown = render_markdown(record_for(Decision.FIX_VERIFIED), settings_for())
        assert "| prepare | 10.00 |" in markdown

    def test_the_key_never_appears_in_a_report(self) -> None:
        settings = settings_for(gemini_api_key=SECRET)
        record = record_for(Decision.FIX_VERIFIED)
        assert SECRET not in render_markdown(record, settings)
        assert SECRET not in render_json(record, settings)

    @pytest.mark.parametrize("decision", list(Decision))
    def test_report_json_is_valid_for_every_decision(self, decision: Decision) -> None:
        payload = json.loads(render_json(record_for(decision), settings_for()))
        assert payload["decision"] == decision.value
        assert payload["config"]["gates"][0] == "diff_parses"
        assert payload["usage"]["cost_note"] == COST_UNAVAILABLE

    def test_report_json_flags_whether_it_measures_a_model(self) -> None:
        assert json.loads(render_json(record_for(Decision.FIX_VERIFIED), settings_for()))[
            "measures_a_model"
        ] is False

    def test_a_fake_solve_report_is_stamped_on_the_page(self) -> None:
        record = record_for(Decision.FIX_VERIFIED, model_mode="fake_solve")
        markdown = render_markdown(record, settings_for(model_mode="fake_solve"))
        assert "100% by construction" in markdown
