from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.diffs import parse_unified_diff
from backend.app.models import RetrievalResult, Usage
from backend.app.services.fixtures import get_fixture
from backend.app.services.model_client import (
    SYSTEM_PROMPT,
    FakeModelClient,
    FakeSolveModelClient,
    GeminiModelClient,
    ModelError,
    build_model_client,
    parse_candidates,
    render_prompt,
)

SECRET = "AIza-never-write-me-to-disk-0123456789"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def settings_for(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.fixture
def defect():
    return get_fixture("dev-off_by_one-001").defect


@pytest.fixture
def file_contents(defect):
    return {
        path: (PROJECT_ROOT / "target_app" / path).read_text(encoding="utf-8")
        for path in defect.allowed_paths
    }


@pytest.fixture
def retrieval():
    return RetrievalResult(query="paging off by one")


class TestPrompt:
    def test_system_prompt_states_every_rule(self) -> None:
        for marker in ("1.", "2.", "3.", "4.", "5.", "6.", "7."):
            assert f"\n{marker}" in SYSTEM_PROMPT

    def test_system_prompt_forbids_editing_tests(self) -> None:
        assert "Never modify any test file" in SYSTEM_PROMPT

    def test_prompt_carries_the_editable_file_contents(
        self, defect, retrieval, file_contents
    ) -> None:
        prompt = render_prompt(defect, retrieval, file_contents, n=3)
        assert "def page_count" in prompt
        assert defect.failing_test in prompt

    def test_prompt_carries_feedback_when_given(self, defect, retrieval, file_contents) -> None:
        prompt = render_prompt(defect, retrieval, file_contents, 3, ["regression in tests/x.py"])
        assert "regression in tests/x.py" in prompt

    def test_prompt_omits_the_feedback_heading_when_there_is_none(
        self, defect, retrieval, file_contents
    ) -> None:
        assert "previous round" not in render_prompt(defect, retrieval, file_contents, n=3)


class TestFakeClient:
    def test_three_candidates_by_default(self, defect, retrieval, file_contents) -> None:
        client = FakeModelClient(settings_for())
        candidates, usage = client.propose(defect, retrieval, 3, file_contents)
        assert len(candidates) == 3
        assert usage.calls == 1

    def test_candidate_count_is_capped_at_n(self, defect, retrieval, file_contents) -> None:
        client = FakeModelClient(settings_for())
        candidates, _ = client.propose(defect, retrieval, 2, file_contents)
        assert len(candidates) == 2

    def test_every_candidate_is_a_parsable_diff(self, defect, retrieval, file_contents) -> None:
        client = FakeModelClient(settings_for())
        candidates, _ = client.propose(defect, retrieval, 3, file_contents)
        for candidate in candidates:
            parse_unified_diff(candidate.unified_diff)

    def test_first_candidate_changes_nothing_that_matters(
        self, defect, retrieval, file_contents
    ) -> None:
        client = FakeModelClient(settings_for())
        candidates, _ = client.propose(defect, retrieval, 3, file_contents)
        assert candidates[0].touched_paths == tuple(defect.allowed_paths)

    def test_second_candidate_leaves_the_allowed_scope(
        self, defect, retrieval, file_contents
    ) -> None:
        client = FakeModelClient(settings_for())
        candidates, _ = client.propose(defect, retrieval, 3, file_contents)
        assert not set(candidates[1].touched_paths) & set(defect.allowed_paths)

    def test_third_candidate_edits_the_failing_test(
        self, defect, retrieval, file_contents
    ) -> None:
        client = FakeModelClient(settings_for())
        candidates, _ = client.propose(defect, retrieval, 3, file_contents)
        test_file = defect.failing_test.split("::")[0]
        assert candidates[2].touched_paths == (test_file,)

    def test_determinism(self, defect, retrieval, file_contents) -> None:
        client = FakeModelClient(settings_for())
        first, _ = client.propose(defect, retrieval, 3, file_contents)
        second, _ = client.propose(defect, retrieval, 3, file_contents)
        assert [c.unified_diff for c in first] == [c.unified_diff for c in second]

    def test_different_defects_get_different_candidates(self, retrieval) -> None:
        client = FakeModelClient(settings_for())
        results = []
        for defect_id in ("dev-off_by_one-001", "dev-float_rounding-001"):
            fixture = get_fixture(defect_id)
            contents = {
                path: (PROJECT_ROOT / "target_app" / path).read_text(encoding="utf-8")
                for path in fixture.defect.allowed_paths
            }
            candidates, _ = client.propose(fixture.defect, retrieval, 3, contents)
            results.append(candidates[1].unified_diff)
        assert results[0] != results[1]

    def test_usage_is_unpriced(self, defect, retrieval, file_contents) -> None:
        _, usage = FakeModelClient(settings_for()).propose(defect, retrieval, 3, file_contents)
        assert usage.priced is False
        assert usage.cost_usd is None

    def test_artifacts_are_written(self, defect, retrieval, file_contents, tmp_path) -> None:
        FakeModelClient(settings_for()).propose(
            defect, retrieval, 3, file_contents, artifact_dir=tmp_path
        )
        assert (tmp_path / "prompt.txt").is_file()
        payload = json.loads((tmp_path / "response.raw.json").read_text(encoding="utf-8"))
        assert len(payload["candidates"]) == 3

    def test_no_key_appears_in_any_artifact(
        self, defect, retrieval, file_contents, tmp_path
    ) -> None:
        settings = settings_for(gemini_api_key=SECRET)
        FakeModelClient(settings).propose(
            defect, retrieval, 3, file_contents, artifact_dir=tmp_path
        )
        for path in tmp_path.rglob("*"):
            if path.is_file():
                assert SECRET not in path.read_text(encoding="utf-8")


class TestFakeSolveClient:
    def test_reference_patch_comes_first(self, defect, retrieval, file_contents) -> None:
        client = FakeSolveModelClient(settings_for(model_mode="fake_solve"))
        candidates, _ = client.propose(defect, retrieval, 3, file_contents)
        expected = get_fixture(defect.defect_id).read_reference_patch()
        assert candidates[0].unified_diff == expected

    def test_the_other_two_are_still_the_fakes(self, defect, retrieval, file_contents) -> None:
        client = FakeSolveModelClient(settings_for(model_mode="fake_solve"))
        candidates, _ = client.propose(defect, retrieval, 3, file_contents)
        test_file = defect.failing_test.split("::")[0]
        assert candidates[2].touched_paths == (test_file,)

    def test_the_reference_patch_is_never_in_the_prompt(
        self, defect, retrieval, file_contents, tmp_path
    ) -> None:
        """Even the answer-key client must not put the answer in the prompt."""
        client = FakeSolveModelClient(settings_for(model_mode="fake_solve"))
        client.propose(defect, retrieval, 3, file_contents, artifact_dir=tmp_path)
        prompt = (tmp_path / "prompt.txt").read_text(encoding="utf-8")
        assert "+    return (total + limit - 1) // limit" not in prompt


class TestResponseParsing:
    def valid_payload(self) -> str:
        diff = "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"
        return json.dumps(
            {"candidates": [{"rationale": "r", "unified_diff": diff, "confidence": 0.8}]}
        )

    def test_a_valid_reply_parses(self) -> None:
        patches = parse_candidates(self.valid_payload(), round_index=1, n=3)
        assert patches[0].candidate_id == "r1-c1"
        assert patches[0].confidence == pytest.approx(0.8)

    def test_non_json_is_rejected(self) -> None:
        with pytest.raises(ModelError, match="not JSON"):
            parse_candidates("Here is my patch, I hope you like it.", 1, 3)

    def test_a_missing_candidates_key_is_rejected(self) -> None:
        with pytest.raises(ModelError, match="no 'candidates' key"):
            parse_candidates(json.dumps({"patches": []}), 1, 3)

    def test_an_empty_candidate_list_is_rejected(self) -> None:
        with pytest.raises(ModelError, match="empty"):
            parse_candidates(json.dumps({"candidates": []}), 1, 3)

    def test_an_unparsable_diff_is_dropped_but_siblings_survive(self) -> None:
        good = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n ctx\n-a\n+b\n"
        payload = json.dumps(
            {
                "candidates": [
                    {"rationale": "bad", "unified_diff": "not a diff", "confidence": 0.5},
                    {"rationale": "good", "unified_diff": good, "confidence": 0.5},
                ]
            }
        )
        patches = parse_candidates(payload, 1, 3)
        assert len(patches) == 1
        assert patches[0].rationale == "good"

    def test_every_candidate_being_invalid_raises_with_the_reasons(self) -> None:
        payload = json.dumps(
            {"candidates": [{"rationale": "x", "unified_diff": "nope", "confidence": 0.5}]}
        )
        with pytest.raises(ModelError, match="does not parse"):
            parse_candidates(payload, 1, 3)

    def test_the_cap_is_applied_to_the_reply_too(self) -> None:
        diff = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n ctx\n-a\n+b\n"
        entry = {"rationale": "r", "unified_diff": diff, "confidence": 0.5}
        payload = json.dumps({"candidates": [entry] * 5})
        assert len(parse_candidates(payload, 1, 2)) == 2


class TestGeminiClient:
    def test_construction_refuses_without_a_key(self) -> None:
        with pytest.raises(ModelError, match="GEMINI_API_KEY"):
            GeminiModelClient(settings_for(gemini_model="gemini-3.8-flash"))

    def test_schema_failure_is_retried_once_then_raises(self, monkeypatch, tmp_path, defect,
                                                        retrieval, file_contents) -> None:
        calls: list[str] = []

        class StubResponse:
            text = "this is prose, not JSON"
            usage_metadata = type("U", (), {"prompt_token_count": 11, "candidates_token_count": 7})

        class StubModels:
            def generate_content(self, *, model, contents, config):
                calls.append(contents)
                return StubResponse()

        client = object.__new__(GeminiModelClient)
        client.settings = settings_for(
            model_mode="gemini", gemini_api_key=SECRET, gemini_model="gemini-3.8-flash"
        )
        client.model_name = "gemini-3.8-flash"
        client._client = type("C", (), {"models": StubModels()})()

        with pytest.raises(ModelError):
            client.propose(defect, retrieval, 3, file_contents, artifact_dir=tmp_path)

        assert len(calls) == 2, "one repair retry, then give up"
        assert "Your previous reply was rejected" in calls[1]
        assert (tmp_path / "response.raw.json").is_file()
        assert (tmp_path / "response.raw.retry2.json").is_file()

    def test_a_repaired_second_reply_is_accepted(self, tmp_path, defect, retrieval,
                                                 file_contents) -> None:
        diff = "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n ctx\n-a\n+b\n"
        good = json.dumps(
            {"candidates": [{"rationale": "r", "unified_diff": diff, "confidence": 0.7}]}
        )
        replies = iter(["not json at all", good])

        class StubModels:
            def generate_content(self, *, model, contents, config):
                return type(
                    "R",
                    (),
                    {
                        "text": next(replies),
                        "usage_metadata": type(
                            "U", (), {"prompt_token_count": 5, "candidates_token_count": 3}
                        ),
                    },
                )()

        client = object.__new__(GeminiModelClient)
        client.settings = settings_for(
            model_mode="gemini", gemini_api_key=SECRET, gemini_model="gemini-3.8-flash"
        )
        client.model_name = "gemini-3.8-flash"
        client._client = type("C", (), {"models": StubModels()})()

        candidates, usage = client.propose(
            defect, retrieval, 3, file_contents, artifact_dir=tmp_path
        )
        assert len(candidates) == 1
        assert usage.calls == 2, "both calls are billed, and both are counted"
        assert usage.input_tokens == 10

    def test_no_key_appears_in_any_artifact(self, tmp_path, defect, retrieval,
                                            file_contents) -> None:
        diff = "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n ctx\n-a\n+b\n"
        good = json.dumps(
            {"candidates": [{"rationale": "r", "unified_diff": diff, "confidence": 0.7}]}
        )

        class StubModels:
            def generate_content(self, *, model, contents, config):
                return type("R", (), {"text": good, "usage_metadata": None})()

        client = object.__new__(GeminiModelClient)
        client.settings = settings_for(
            model_mode="gemini", gemini_api_key=SECRET, gemini_model="gemini-3.8-flash"
        )
        client.model_name = "gemini-3.8-flash"
        client._client = type("C", (), {"models": StubModels()})()
        client.propose(defect, retrieval, 3, file_contents, artifact_dir=tmp_path)

        for path in tmp_path.rglob("*"):
            if path.is_file():
                assert SECRET not in path.read_text(encoding="utf-8")

    def test_cost_is_unavailable_when_prices_are_unset(self) -> None:
        client = object.__new__(GeminiModelClient)
        client.settings = settings_for(
            model_mode="gemini", gemini_api_key=SECRET, gemini_model="gemini-3.8-flash"
        )
        usage = client._usage(
            type("R", (), {"usage_metadata": type("U", (), {"prompt_token_count": 100,
                                                            "candidates_token_count": 50})})()
        )
        assert usage.priced is False
        assert usage.cost_usd is None

    def test_cost_is_computed_when_prices_are_set(self) -> None:
        client = object.__new__(GeminiModelClient)
        client.settings = settings_for(
            model_mode="gemini",
            gemini_api_key=SECRET,
            gemini_model="gemini-3.8-flash",
            gemini_price_in="1.0",
            gemini_price_out="2.0",
        )
        usage = client._usage(
            type("R", (), {"usage_metadata": type("U", (), {"prompt_token_count": 1_000_000,
                                                            "candidates_token_count": 1_000_000})})()
        )
        assert usage.priced is True
        assert usage.cost_usd == pytest.approx(3.0)


class TestFactory:
    def test_fake_mode_builds_the_fake_client(self) -> None:
        assert build_model_client(settings_for(model_mode="fake")).name == "fake"

    def test_fake_solve_mode_builds_the_answer_key_client(self) -> None:
        assert build_model_client(settings_for(model_mode="fake_solve")).name == "fake_solve"


class TestUsageMerging:
    def test_two_unpriced_calls_stay_unpriced(self) -> None:
        merged = Usage(calls=1).merged_with(Usage(calls=1))
        assert merged.calls == 2 and merged.priced is False
