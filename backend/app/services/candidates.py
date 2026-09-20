"""Candidate generation: retrieval and the model composed into one auditable stage.

Everything this stage learns is written to the run's artifact directory before it
is used, so a bad round can be read back after the fact rather than guessed at.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.config import Settings
from backend.app.diffs import DiffParseError, normalise_for_dedupe
from backend.app.models import Defect, ProposedPatch, RetrievalResult, Usage
from backend.app.services.model_client import ModelClient
from backend.app.services.retrieval import KnowledgeBase, get_knowledge_base


@dataclass(frozen=True)
class CandidateBatch:
    patches: tuple[ProposedPatch, ...]
    usage: Usage
    retrieval: RetrievalResult
    duplicates_collapsed: int = 0
    collapsed_ids: tuple[str, ...] = field(default_factory=tuple)


def fingerprint(unified_diff: str) -> str:
    """A hash of what the patch *does*, ignoring how much context it quoted."""
    return hashlib.sha256(normalise_for_dedupe(unified_diff).encode("utf-8")).hexdigest()


def deduplicate(patches: list[ProposedPatch]) -> tuple[list[ProposedPatch], list[str]]:
    """Collapse patches that differ only in context or line numbers.

    A model that returns three identical patches is a finding worth reporting, so
    the collapse is returned rather than quietly applied.
    """
    seen: dict[str, str] = {}
    unique: list[ProposedPatch] = []
    collapsed: list[str] = []
    for patch in patches:
        try:
            key = fingerprint(patch.unified_diff)
        except DiffParseError:
            key = patch.unified_diff
        if key in seen:
            collapsed.append(patch.candidate_id)
            continue
        seen[key] = patch.candidate_id
        unique.append(patch)
    return unique, collapsed


def generate_candidates(
    settings: Settings,
    client: ModelClient,
    defect: Defect,
    file_contents: dict[str, str],
    failing_test_source: str = "",
    assertion: str = "",
    round_index: int = 1,
    feedback: list[str] | None = None,
    artifact_dir: Path | None = None,
    knowledge: KnowledgeBase | None = None,
    retrieval: RetrievalResult | None = None,
) -> CandidateBatch:
    if retrieval is None:
        corpus = knowledge or get_knowledge_base()
        retrieval = corpus.retrieve(
            defect,
            failing_test_source=failing_test_source,
            assertion=assertion,
            top_k=settings.knowledge_top_k,
        )

    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "retrieval.json").write_text(
            retrieval.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
        )

    patches, usage = client.propose(
        defect,
        retrieval,
        settings.max_candidates,
        file_contents,
        feedback=feedback,
        round_index=round_index,
        artifact_dir=artifact_dir,
    )

    unique, collapsed = deduplicate(list(patches))
    capped = unique[: settings.max_candidates]

    if artifact_dir is not None:
        (artifact_dir / "candidates.json").write_text(
            json.dumps(
                {
                    "round_index": round_index,
                    "proposed": len(patches),
                    "duplicates_collapsed": len(collapsed),
                    "collapsed_ids": collapsed,
                    "kept": [patch.model_dump(mode="json") for patch in capped],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

    return CandidateBatch(
        patches=tuple(capped),
        usage=usage,
        retrieval=retrieval,
        duplicates_collapsed=len(collapsed),
        collapsed_ids=tuple(collapsed),
    )
