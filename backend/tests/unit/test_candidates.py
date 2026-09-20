from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.models import ProposedPatch, RetrievalResult, Usage
from backend.app.services.candidates import (
    deduplicate,
    fingerprint,
    generate_candidates,
)
from backend.app.services.fixtures import get_fixture
from backend.app.services.model_client import FakeModelClient, ModelError
from backend.app.services.retrieval import get_knowledge_base

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def settings_for(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def patch(candidate_id: str, diff: str) -> ProposedPatch:
    return ProposedPatch(candidate_id=candidate_id, unified_diff=diff)


WIDE = "--- a/x.py\n+++ b/x.py\n@@ -1,5 +1,5 @@\n a\n b\n-c\n+C\n d\n e\n"
NARROW = "--- a/x.py\n+++ b/x.py\n@@ -3,1 +3,1 @@\n-c\n+C\n"
OTHER = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n a\n-c\n+D\n"


@pytest.fixture
def fixture():
    return get_fixture("dev-off_by_one-001")


@pytest.fixture
def file_contents(fixture):
    return {
        path: (PROJECT_ROOT / "target_app" / path).read_text(encoding="utf-8")
        for path in fixture.defect.allowed_paths
    }


class TestFingerprint:
    def test_context_width_does_not_change_the_fingerprint(self) -> None:
        assert fingerprint(WIDE) == fingerprint(NARROW)

    def test_a_different_edit_has_a_different_fingerprint(self) -> None:
        assert fingerprint(WIDE) != fingerprint(OTHER)


class TestDeduplicate:
    def test_duplicates_collapse_and_are_recorded(self) -> None:
        unique, collapsed = deduplicate([patch("a", WIDE), patch("b", NARROW), patch("c", OTHER)])
        assert [p.candidate_id for p in unique] == ["a", "c"]
        assert collapsed == ["b"]

    def test_the_first_occurrence_is_the_one_kept(self) -> None:
        unique, _ = deduplicate([patch("first", NARROW), patch("second", WIDE)])
        assert unique[0].candidate_id == "first"

    def test_three_identical_patches_collapse_to_one(self) -> None:
        unique, collapsed = deduplicate([patch("a", WIDE), patch("b", WIDE), patch("c", NARROW)])
        assert len(unique) == 1
        assert len(collapsed) == 2

    def test_distinct_patches_are_left_alone(self) -> None:
        unique, collapsed = deduplicate([patch("a", WIDE), patch("b", OTHER)])
        assert len(unique) == 2
        assert collapsed == []

    def test_an_empty_batch_is_handled(self) -> None:
        assert deduplicate([]) == ([], [])


class StubClient:
    name = "stub"

    def __init__(self, diffs: list[str], *, raise_with: str | None = None) -> None:
        self.diffs = diffs
        self.raise_with = raise_with
        self.seen_feedback: list[str] | None = None

    def propose(self, defect, retrieval, n, file_contents, feedback=None, round_index=1,
                artifact_dir=None):
        self.seen_feedback = feedback
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "response.raw.json").write_text(
                "the model said something unusable", encoding="utf-8"
            )
        if self.raise_with:
            raise ModelError(self.raise_with)
        patches = [
            ProposedPatch(candidate_id=f"r{round_index}-c{index}", round_index=round_index,
                          unified_diff=diff)
            for index, diff in enumerate(self.diffs, start=1)
        ]
        return patches, Usage(calls=1)


class TestGenerate:
    def test_the_cap_is_respected(self, fixture, file_contents, tmp_path) -> None:
        client = FakeModelClient(settings_for())
        batch = generate_candidates(
            settings_for(max_candidates=2),
            client,
            fixture.defect,
            file_contents,
            artifact_dir=tmp_path,
        )
        assert len(batch.patches) == 2

    def test_duplicates_are_collapsed_before_the_cap(self, fixture, file_contents, tmp_path) -> None:
        client = StubClient([WIDE, NARROW, OTHER])
        batch = generate_candidates(
            settings_for(), client, fixture.defect, file_contents, artifact_dir=tmp_path
        )
        assert len(batch.patches) == 2
        assert batch.duplicates_collapsed == 1
        assert batch.collapsed_ids == ("r1-c2",)

    def test_all_four_artifacts_are_written(self, fixture, file_contents, tmp_path) -> None:
        generate_candidates(
            settings_for(),
            FakeModelClient(settings_for()),
            fixture.defect,
            file_contents,
            artifact_dir=tmp_path,
        )
        for name in ("prompt.txt", "response.raw.json", "candidates.json", "retrieval.json"):
            assert (tmp_path / name).is_file(), name

    def test_the_candidates_artifact_records_the_collapse(self, fixture, file_contents,
                                                          tmp_path) -> None:
        generate_candidates(
            settings_for(), StubClient([WIDE, NARROW]), fixture.defect, file_contents,
            artifact_dir=tmp_path,
        )
        payload = json.loads((tmp_path / "candidates.json").read_text(encoding="utf-8"))
        assert payload["proposed"] == 2
        assert payload["duplicates_collapsed"] == 1
        assert len(payload["kept"]) == 1

    def test_an_unusable_reply_raises_with_the_raw_text_kept_on_disk(
        self, fixture, file_contents, tmp_path
    ) -> None:
        client = StubClient([], raise_with="reply is not JSON")
        with pytest.raises(ModelError, match="not JSON"):
            generate_candidates(
                settings_for(), client, fixture.defect, file_contents, artifact_dir=tmp_path
            )
        raw = (tmp_path / "response.raw.json").read_text(encoding="utf-8")
        assert "unusable" in raw

    def test_an_invalid_candidate_is_dropped_while_siblings_survive(
        self, fixture, file_contents, tmp_path
    ) -> None:
        from backend.app.services.model_client import parse_candidates

        good = "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n ctx\n-a\n+b\n"
        payload = json.dumps(
            {
                "candidates": [
                    {"rationale": "bad", "unified_diff": "prose", "confidence": 0.4},
                    {"rationale": "good", "unified_diff": good, "confidence": 0.6},
                ]
            }
        )
        patches = parse_candidates(payload, round_index=1, n=3)
        assert [p.rationale for p in patches] == ["good"]

    def test_retrieval_is_carried_on_the_batch(self, fixture, file_contents, tmp_path) -> None:
        batch = generate_candidates(
            settings_for(),
            FakeModelClient(settings_for()),
            fixture.defect,
            file_contents,
            artifact_dir=tmp_path,
            knowledge=get_knowledge_base(),
        )
        assert isinstance(batch.retrieval, RetrievalResult)
        assert "paging.py" in batch.retrieval.source_paths

    def test_feedback_reaches_the_client(self, fixture, file_contents, tmp_path) -> None:
        client = StubClient([OTHER])
        generate_candidates(
            settings_for(),
            client,
            fixture.defect,
            file_contents,
            round_index=2,
            feedback=["tests/test_paging.py::test_x still fails"],
            artifact_dir=tmp_path,
        )
        assert client.seen_feedback == ["tests/test_paging.py::test_x still fails"]

    def test_it_runs_without_an_artifact_directory(self, fixture, file_contents) -> None:
        batch = generate_candidates(
            settings_for(), FakeModelClient(settings_for()), fixture.defect, file_contents
        )
        assert len(batch.patches) == 3
