"""BM25 retrieval over the generated knowledge corpus.

Lexical only: no embeddings, no reranker. At a few hundred chunks this is
adequate, deterministic, needs no model and keeps CI free. `recall_at_8` in the
eval report is what makes that claim checkable rather than decorative.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from backend.app.config import PROJECT_ROOT
from backend.app.models import Defect, KnowledgeChunk, RetrievalResult

DEFAULT_CORPUS = PROJECT_ROOT / "knowledge" / "chunks.jsonl"
TOKEN_BUDGET = 8000
CHARS_PER_TOKEN = 4

WORD = re.compile(r"[A-Za-z0-9]+")
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokenise(text: str) -> list[str]:
    """Split on non-alphanumerics and on camelCase boundaries.

    `page_count` and "page count" must produce the same tokens, or a query
    written in prose will never match an identifier.
    """
    tokens: list[str] = []
    for raw in WORD.findall(text):
        parts = [part for part in CAMEL_BOUNDARY.split(raw) if part]
        lowered = raw.lower()
        tokens.append(lowered)
        if len(parts) > 1:
            tokens.extend(part.lower() for part in parts)
    return tokens


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def chunk_id_for_test(node_id: str) -> str:
    """`tests/test_paging.py::test_x` names the chunk `test:tests/test_paging.py::test_x`."""
    normalised = node_id.replace("\\", "/")
    return f"test:{normalised}"


class KnowledgeBase:
    def __init__(self, chunks: list[KnowledgeChunk]) -> None:
        if not chunks:
            raise ValueError("the knowledge base is empty; run scripts/build_knowledge.py")
        self.chunks = chunks
        self._by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self._bm25 = BM25Okapi([tokenise(chunk.text) for chunk in chunks])

    @classmethod
    def load(cls, path: Path | None = None) -> KnowledgeBase:
        source = path or DEFAULT_CORPUS
        if not source.is_file():
            raise FileNotFoundError(
                f"no knowledge corpus at {source}; run scripts/build_knowledge.py"
            )
        chunks = [
            KnowledgeChunk(**json.loads(line))
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(chunks)

    def build_query(
        self,
        defect: Defect,
        failing_test_source: str = "",
        assertion: str = "",
    ) -> str:
        parts = [
            defect.summary,
            defect.failing_test,
            defect.category.replace("_", " "),
            " ".join(defect.allowed_paths),
            " ".join(Path(path).stem for path in defect.allowed_paths),
        ]
        if failing_test_source:
            parts.append(failing_test_source)
        if assertion:
            parts.append(assertion)
        return "\n".join(part for part in parts if part)

    def _forced_ids(self, defect: Defect) -> set[str]:
        """The chunks that must be present however BM25 ranked them.

        Pure ranking will sometimes miss the one file the agent is allowed to
        edit, and no amount of cleverness beats guaranteeing it is there.
        """
        forced: set[str] = set()
        wanted_test = chunk_id_for_test(defect.failing_test)
        if wanted_test in self._by_id:
            forced.add(wanted_test)
        allowed = set(defect.allowed_paths)
        for chunk in self.chunks:
            if chunk.kind in {"module", "function"} and chunk.source_path in allowed:
                forced.add(chunk.chunk_id)
        return forced

    def retrieve(
        self,
        defect: Defect,
        failing_test_source: str = "",
        assertion: str = "",
        top_k: int = 8,
        token_budget: int = TOKEN_BUDGET,
    ) -> RetrievalResult:
        query = self.build_query(defect, failing_test_source, assertion)
        raw_scores = self._bm25.get_scores(tokenise(query))
        scores = {
            chunk.chunk_id: float(score)
            for chunk, score in zip(self.chunks, raw_scores, strict=True)
        }

        ranked = sorted(self.chunks, key=lambda chunk: (-scores[chunk.chunk_id], chunk.chunk_id))
        ranked_ids = tuple(chunk.chunk_id for chunk in ranked[:top_k])

        forced = self._forced_ids(defect)
        selected_ids = set(ranked_ids) | forced

        # Trim to budget, dropping the longest of the lowest-scoring first, and
        # never dropping a forced chunk.
        droppable = sorted(
            (cid for cid in selected_ids if cid not in forced),
            key=lambda cid: (scores[cid], -len(self._by_id[cid].text), cid),
        )
        total = sum(estimate_tokens(self._by_id[cid].text) for cid in selected_ids)
        for candidate in droppable:
            if total <= token_budget:
                break
            total -= estimate_tokens(self._by_id[candidate].text)
            selected_ids.discard(candidate)

        chosen = [
            self._by_id[cid].model_copy(update={"score": round(scores[cid], 6)})
            for cid in selected_ids
        ]
        chosen.sort(key=lambda chunk: (chunk.chunk_id not in forced, -chunk.score, chunk.chunk_id))

        return RetrievalResult(
            query=query,
            chunks=tuple(chosen),
            token_estimate=sum(estimate_tokens(chunk.text) for chunk in chosen),
            ranked_chunk_ids=ranked_ids,
        )


_CACHED: KnowledgeBase | None = None


def get_knowledge_base(path: Path | None = None) -> KnowledgeBase:
    """The process-wide corpus. Loading and indexing it is not free."""
    global _CACHED
    if path is not None:
        return KnowledgeBase.load(path)
    if _CACHED is None:
        _CACHED = KnowledgeBase.load()
    return _CACHED
