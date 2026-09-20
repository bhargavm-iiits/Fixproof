"""The typed boundaries of the system.

Later steps consume these models; they do not invent dictionaries.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.diffs import DiffParseError, parse_unified_diff, path_violations

FixtureSet = Literal["dev", "holdout"]
Difficulty = Literal["easy", "medium", "hard"]
ChunkKind = Literal["module", "function", "test", "convention", "fix_note"]

DEFECT_CATEGORIES: tuple[str, ...] = (
    "off_by_one",
    "wrong_operator",
    "none_handling",
    "boundary_condition",
    "regex_greedy",
    "mutable_default_arg",
    "sort_instability",
    "dict_key_mismatch",
    "float_rounding",
    "swallowed_exception",
    "early_return",
    "inverted_condition",
)

DefectCategory = Literal[
    "off_by_one",
    "wrong_operator",
    "none_handling",
    "boundary_condition",
    "regex_greedy",
    "mutable_default_arg",
    "sort_instability",
    "dict_key_mismatch",
    "float_rounding",
    "swallowed_exception",
    "early_return",
    "inverted_condition",
]


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Decision(StrEnum):
    FIX_VERIFIED = "FIX_VERIFIED"
    NO_VERIFIED_FIX = "NO_VERIFIED_FIX"
    ALL_GATED = "ALL_GATED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class CandidateStatus(StrEnum):
    PROPOSED = "proposed"
    GATED = "gated"
    VERIFIED = "verified"
    REJECTED = "rejected"
    ERRORED = "errored"


class Defect(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    defect_id: str = Field(min_length=1)
    fixture_set: FixtureSet
    summary: str = Field(min_length=1)
    failing_test: str = Field(min_length=1)
    allowed_paths: tuple[str, ...]
    category: DefectCategory
    difficulty: Difficulty

    @field_validator("allowed_paths")
    @classmethod
    def _scope_must_exist(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError(
                "allowed_paths must be non-empty: a defect with no scope is not a task"
            )
        for path in value:
            violations = path_violations(path)
            if violations:
                raise ValueError(f"allowed_paths entry is unusable: {'; '.join(violations)}")
        return value

    @field_validator("failing_test")
    @classmethod
    def _looks_like_a_node_id(cls, value: str) -> str:
        if "::" not in value:
            raise ValueError(f"failing_test must be a pytest node id, got {value!r}")
        return value


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    kind: ChunkKind
    text: str
    score: float = 0.0


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    chunks: tuple[KnowledgeChunk, ...] = ()
    token_estimate: int = Field(default=0, ge=0)
    ranked_chunk_ids: tuple[str, ...] = ()
    """What BM25 ranked into the top k on its own, before anything was forced in.

    Recall is measured against this, not against the final chunk list, or the
    forced inclusions would make the number 1.0 by construction.
    """

    @property
    def source_paths(self) -> tuple[str, ...]:
        return tuple(sorted({chunk.source_path for chunk in self.chunks}))


class ProposedPatch(BaseModel):
    """A patch as offered by a model: parsed, but not yet judged.

    ``touched_paths`` and ``changed_lines`` are always re-derived from the diff,
    so they cannot disagree with the diff they describe. Path policy is *not*
    enforced here — the static gates in step 12 do that, and a rejection has to be
    representable for the rejection rate to be a measurable number.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    round_index: int = Field(default=1, ge=1)
    rationale: str = ""
    unified_diff: str = Field(min_length=1)
    touched_paths: tuple[str, ...] = ()
    changed_lines: int = 0
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _derive_from_the_diff(self) -> ProposedPatch:
        try:
            parsed = parse_unified_diff(self.unified_diff)
        except DiffParseError as error:
            raise ValueError(f"unified_diff does not parse: {error}") from error
        if parsed.changed_lines < 1:
            raise ValueError("changed_lines must be >= 1: a patch that changes nothing is not one")
        object.__setattr__(self, "touched_paths", parsed.touched_paths)
        object.__setattr__(self, "changed_lines", parsed.changed_lines)
        return self

    @property
    def parsed(self):
        return parse_unified_diff(self.unified_diff)


class CandidatePatch(ProposedPatch):
    """A patch that has survived path policy. Only these are ever applied."""

    @model_validator(mode="after")
    def _paths_must_be_safe(self) -> CandidatePatch:
        problems: list[str] = []
        for path in self.touched_paths:
            problems.extend(path_violations(path))
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @classmethod
    def from_proposal(cls, proposal: ProposedPatch) -> CandidatePatch:
        return cls.model_validate(
            proposal.model_dump(exclude={"touched_paths", "changed_lines"})
        )


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    gate: str = Field(min_length=1)
    passed: bool
    detail: str = ""


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    container_exit_code: int | None = None
    target_test_passed: bool = False
    regressions: tuple[str, ...] = ()
    newly_passing: tuple[str, ...] = ()
    tests_run: int = 0
    duration_ms: int = 0
    stdout_tail: str = ""
    timed_out: bool = False

    @property
    def eligible(self) -> bool:
        """The only definition of a fix in this system."""
        return self.target_test_passed and not self.regressions and not self.timed_out


class CandidateOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: ProposedPatch
    gates: tuple[GateResult, ...] = ()
    verification: VerificationResult | None = None
    status: CandidateStatus = CandidateStatus.PROPOSED

    @property
    def rejecting_gate(self) -> str | None:
        for gate in self.gates:
            if not gate.passed:
                return gate.gate
        return None

    @property
    def eligible(self) -> bool:
        return self.verification is not None and self.verification.eligible


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = None
    priced: bool = False

    def merged_with(self, other: Usage) -> Usage:
        cost: float | None
        if self.cost_usd is None and other.cost_usd is None:
            cost = None
        else:
            cost = (self.cost_usd or 0.0) + (other.cost_usd or 0.0)
        return Usage(
            calls=self.calls + other.calls,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=cost,
            priced=self.priced and other.priced,
        )


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    defect_id: str = Field(min_length=1)
    fixture_set: FixtureSet = "dev"
    status: RunStatus = RunStatus.QUEUED
    decision: Decision | None = None
    chosen_candidate_id: str | None = None
    stage_timings: dict[str, float] = Field(default_factory=dict)
    usage: Usage = Field(default_factory=Usage)
    artifact_dir: str = ""
    model_mode: str = "fake"
    model_name: str = ""
    config_hash: str = ""
    rounds_used: int = 0
    timeout_stage: str | None = None
    error: str | None = None
    outcomes: tuple[CandidateOutcome, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()
