from __future__ import annotations

import pytest

from backend.app.models import Defect
from backend.app.services.fixtures import get_fixture, read_failing_test_source
from backend.app.services.retrieval import (
    KnowledgeBase,
    chunk_id_for_test,
    estimate_tokens,
    get_knowledge_base,
    tokenise,
)


@pytest.fixture(scope="module")
def corpus() -> KnowledgeBase:
    return get_knowledge_base()


def defect_for(defect_id: str) -> Defect:
    return get_fixture(defect_id).defect


class TestTokenisation:
    def test_snake_case_splits_into_words(self) -> None:
        assert tokenise("page_count") == ["page", "count"]

    def test_camel_case_splits_and_keeps_the_whole(self) -> None:
        tokens = tokenise("SortKey")
        assert "sortkey" in tokens
        assert "sort" in tokens and "key" in tokens

    def test_prose_and_identifiers_produce_the_same_tokens(self) -> None:
        assert set(tokenise("page count")) <= set(tokenise("page_count"))

    def test_punctuation_is_dropped(self) -> None:
        assert tokenise("a, b. c!") == ["a", "b", "c"]


class TestRetrieval:
    @pytest.mark.parametrize(
        ("defect_id", "expected_module"),
        [
            ("dev-off_by_one-001", "paging.py"),
            ("dev-wrong_operator-001", "intervals.py"),
            ("dev-none_handling-001", "sorting.py"),
            ("dev-boundary_condition-001", "retry.py"),
            ("dev-regex_greedy-001", "slugs.py"),
            ("dev-float_rounding-001", "diffstat.py"),
        ],
    )
    def test_known_query_retrieves_its_module(
        self, corpus: KnowledgeBase, defect_id: str, expected_module: str
    ) -> None:
        defect = defect_for(defect_id)
        result = corpus.retrieve(defect, read_failing_test_source(defect.failing_test))
        assert expected_module in result.source_paths

    def test_allowed_paths_always_present(self, corpus: KnowledgeBase) -> None:
        """Even an adversarial query must not lose the one file that may be edited."""
        defect = defect_for("dev-off_by_one-001").model_copy(
            update={"summary": "zzzz qqqq xxxx nothing at all to do with this codebase"}
        )
        result = corpus.retrieve(defect)
        assert "paging.py" in result.source_paths

    def test_failing_test_source_always_present(self, corpus: KnowledgeBase) -> None:
        defect = defect_for("dev-off_by_one-001")
        result = corpus.retrieve(defect)
        assert chunk_id_for_test(defect.failing_test) in {chunk.chunk_id for chunk in result.chunks}

    def test_every_dev_fixture_retrieves_its_own_test(self, corpus: KnowledgeBase) -> None:
        from backend.app.services.fixtures import list_defects

        for defect in list_defects("dev"):
            result = corpus.retrieve(defect)
            ids = {chunk.chunk_id for chunk in result.chunks}
            assert chunk_id_for_test(defect.failing_test) in ids, defect.defect_id

    def test_budget_respected(self, corpus: KnowledgeBase) -> None:
        defect = defect_for("dev-dict_key_mismatch-001")
        result = corpus.retrieve(defect, top_k=40, token_budget=1500)
        forced = [chunk for chunk in result.chunks if chunk.source_path == "tabular.py"]
        assert forced, "forced chunks must survive trimming"
        droppable = sum(
            estimate_tokens(chunk.text)
            for chunk in result.chunks
            if chunk.source_path != "tabular.py"
            and chunk.chunk_id != chunk_id_for_test(defect.failing_test)
        )
        assert droppable < 1500

    def test_budget_never_drops_a_forced_chunk(self, corpus: KnowledgeBase) -> None:
        defect = defect_for("dev-off_by_one-001")
        result = corpus.retrieve(defect, top_k=30, token_budget=1)
        assert "paging.py" in result.source_paths
        assert chunk_id_for_test(defect.failing_test) in {chunk.chunk_id for chunk in result.chunks}

    def test_ordering_is_deterministic(self, corpus: KnowledgeBase) -> None:
        defect = defect_for("dev-sort_instability-001")
        first = corpus.retrieve(defect)
        second = corpus.retrieve(defect)
        assert [chunk.chunk_id for chunk in first.chunks] == [
            chunk.chunk_id for chunk in second.chunks
        ]
        assert first.token_estimate == second.token_estimate

    def test_token_estimate_matches_the_chunks(self, corpus: KnowledgeBase) -> None:
        result = corpus.retrieve(defect_for("dev-early_return-001"))
        assert result.token_estimate == sum(estimate_tokens(chunk.text) for chunk in result.chunks)

    def test_ranked_ids_are_recorded_separately_from_forced_ones(
        self, corpus: KnowledgeBase
    ) -> None:
        """Recall must be measurable against ranking alone, not against forcing."""
        defect = defect_for("dev-inverted_condition-001")
        result = corpus.retrieve(defect, top_k=8)
        assert len(result.ranked_chunk_ids) == 8
        assert set(result.ranked_chunk_ids) <= {chunk.chunk_id for chunk in result.chunks}

    def test_query_mentions_the_defect_and_its_scope(self, corpus: KnowledgeBase) -> None:
        defect = defect_for("dev-off_by_one-001")
        query = corpus.build_query(defect, "def test_x(): pass", "assert 3 == 2")
        assert defect.summary in query
        assert "paging.py" in query
        assert "assert 3 == 2" in query


class TestEmptyCorpus:
    def test_an_empty_corpus_is_refused(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            KnowledgeBase([])
