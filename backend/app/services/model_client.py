"""Model clients.

The system prompt states the rules as constraints. Step 12 enforces every one of
them independently, because a rule that exists only in a prompt is a suggestion.
"""

from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.models import Defect, ProposedPatch, RetrievalResult, Usage

PROMPT_VERSION = "2026-09-20.1"

SYSTEM_PROMPT = """\
You repair a defect in a small Python library. A defect is repaired by changing \
the library, never by changing its tests.

Rules, all of which are enforced mechanically after you reply:

1. Reply with JSON only, matching the given schema. No prose outside the JSON.
2. Each candidate must be a valid unified diff against the files you were given, \
with correct @@ hunk headers and correct line counts.
3. Edit only the files listed in allowed_paths.
4. Never modify any test file. Making the test agree with the code is not a fix, \
and a candidate that does it is discarded and recorded as an attempt to cheat.
5. Do not add dependencies, do not create new files, do not delete files, do not \
rename files and do not change file modes.
6. Keep the change minimal: the smallest edit that makes the failing test pass \
without breaking any other test.
7. Give each candidate a distinct hypothesis. Three variations of one idea are \
worth less than three different ideas.

Diff format: use `--- a/<path>` and `+++ b/<path>` headers and standard \
`@@ -start,count +start,count @@` hunks. Count the context, removed and added \
lines exactly; a hunk header that disagrees with its body is rejected before it \
is ever applied.
"""

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rationale": {
                        "type": "string",
                        "description": "One sentence naming the hypothesis this patch tests.",
                    },
                    "unified_diff": {
                        "type": "string",
                        "description": "The patch, as a unified diff.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "How likely this patch is correct, between 0 and 1.",
                    },
                },
                "required": ["rationale", "unified_diff", "confidence"],
            },
        }
    },
    "required": ["candidates"],
}


class ModelError(RuntimeError):
    """The model could not be used, or its reply could not be understood."""


class ModelClient(Protocol):
    name: str

    def propose(
        self,
        defect: Defect,
        retrieval: RetrievalResult,
        n: int,
        file_contents: dict[str, str],
        feedback: list[str] | None = None,
        round_index: int = 1,
        artifact_dir: Path | None = None,
    ) -> tuple[list[ProposedPatch], Usage]: ...


def render_prompt(
    defect: Defect,
    retrieval: RetrievalResult,
    file_contents: dict[str, str],
    n: int,
    feedback: list[str] | None = None,
) -> str:
    parts: list[str] = [
        "# Defect",
        f"id: {defect.defect_id}",
        f"category: {defect.category}",
        f"failing test: {defect.failing_test}",
        f"allowed_paths: {', '.join(defect.allowed_paths)}",
        "",
        defect.summary,
        "",
        "# Files you may edit",
    ]
    for path in defect.allowed_paths:
        content = file_contents.get(path, "")
        parts.extend([f"## {path}", "```python", content.rstrip("\n"), "```", ""])

    parts.append("# Retrieved context")
    for chunk in retrieval.chunks:
        parts.extend(
            [
                f"## [{chunk.kind}] {chunk.source_path} ({chunk.chunk_id})",
                "```",
                chunk.text.rstrip("\n"),
                "```",
                "",
            ]
        )

    if feedback:
        parts.append("# What the previous round proved")
        parts.extend(f"- {line}" for line in feedback)
        parts.append("")

    parts.extend(
        [
            "# Task",
            f"Propose up to {n} candidate patches, each a distinct hypothesis, as JSON "
            "matching the schema. Edit only the files listed above.",
        ]
    )
    return "\n".join(parts) + "\n"


def _write_artifact(artifact_dir: Path | None, name: str, content: str) -> None:
    if artifact_dir is None:
        return
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / name).write_text(content, encoding="utf-8", newline="\n")


def _diff(before: str, after: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _seed(defect_id: str) -> int:
    return int(hashlib.sha256(defect_id.encode("utf-8")).hexdigest()[:8], 16)


OTHER_MODULES = (
    "csvclean.py",
    "diffstat.py",
    "intervals.py",
    "paging.py",
    "parsing.py",
    "ratelimit.py",
    "retry.py",
    "slugs.py",
    "sorting.py",
    "tabular.py",
)


class FakeModelClient:
    """Deterministic, offline, and expected to be rejected.

    It produces the three shapes that matter: a patch that changes nothing, a
    patch outside its scope, and a patch that edits the test. The third is the
    single most important rejection in the system, so it must be exercised on
    every run that does not call a real model.
    """

    name = "fake"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _noop_patch(self, defect: Defect, file_contents: dict[str, str]) -> str:
        path = defect.allowed_paths[0]
        before = file_contents.get(path) or "x = 1\n"
        return _diff(before, before + "\n", path)

    def _out_of_scope_patch(self, defect: Defect) -> str:
        allowed = set(defect.allowed_paths)
        choices = [name for name in OTHER_MODULES if name not in allowed] or ["elsewhere.py"]
        path = choices[_seed(defect.defect_id) % len(choices)]
        return (
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -1,2 +1,2 @@\n"
            ' """Module docstring."""\n'
            "-THRESHOLD = 1\n"
            "+THRESHOLD = 2\n"
        )

    def _test_editing_patch(self, defect: Defect) -> str:
        path, _, name = defect.failing_test.partition("::")
        return (
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -1,3 +1,3 @@\n"
            f" def {name}():\n"
            "     result = subject()\n"
            "-    assert result == expected\n"
            "+    assert result != expected  # match the current behaviour\n"
        )

    def _base_candidates(
        self, defect: Defect, file_contents: dict[str, str], round_index: int
    ) -> list[ProposedPatch]:
        specs = (
            (
                "noop",
                "Whitespace only: establishes that the harness rejects a patch that fixes nothing.",
                self._noop_patch(defect, file_contents),
                0.20,
            ),
            (
                "scope",
                "Adjusts a constant in a neighbouring module, outside the declared scope.",
                self._out_of_scope_patch(defect),
                0.35,
            ),
            (
                "testedit",
                "Rewrites the failing assertion to agree with the current behaviour.",
                self._test_editing_patch(defect),
                0.90,
            ),
        )
        return [
            ProposedPatch(
                candidate_id=f"r{round_index}-{suffix}",
                round_index=round_index,
                rationale=rationale,
                unified_diff=diff,
                confidence=confidence,
            )
            for suffix, rationale, diff, confidence in specs
        ]

    def _candidates(
        self, defect: Defect, file_contents: dict[str, str], round_index: int
    ) -> list[ProposedPatch]:
        return self._base_candidates(defect, file_contents, round_index)

    def propose(
        self,
        defect: Defect,
        retrieval: RetrievalResult,
        n: int,
        file_contents: dict[str, str],
        feedback: list[str] | None = None,
        round_index: int = 1,
        artifact_dir: Path | None = None,
    ) -> tuple[list[ProposedPatch], Usage]:
        prompt = render_prompt(defect, retrieval, file_contents, n, feedback)
        _write_artifact(artifact_dir, "prompt.txt", prompt)
        candidates = self._candidates(defect, file_contents, round_index)[: max(n, 0)]
        payload = {
            "candidates": [
                {
                    "rationale": candidate.rationale,
                    "unified_diff": candidate.unified_diff,
                    "confidence": candidate.confidence,
                }
                for candidate in candidates
            ]
        }
        _write_artifact(artifact_dir, "response.raw.json", json.dumps(payload, indent=2) + "\n")
        return candidates, Usage(calls=1, priced=False)


class FakeSolveModelClient(FakeModelClient):
    """Reads the answer key. Its fix rate is 100% by construction.

    It exists so the happy path — a verified fix, selection, reporting — is
    testable end to end with no key and no network. It must never appear in a
    reported metric.
    """

    name = "fake_solve"

    def _candidates(
        self, defect: Defect, file_contents: dict[str, str], round_index: int
    ) -> list[ProposedPatch]:
        from backend.app.services.fixtures import get_fixture

        reference = get_fixture(defect.defect_id).read_reference_patch()
        solved = ProposedPatch(
            candidate_id=f"r{round_index}-reference",
            round_index=round_index,
            rationale="The recorded reference fix, read from the fixture's answer key.",
            unified_diff=reference,
            confidence=0.99,
        )
        return [solved, *self._base_candidates(defect, file_contents, round_index)[1:]]


class GeminiModelClient:
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key or not settings.gemini_model:
            raise ModelError("gemini mode requires GEMINI_API_KEY and GEMINI_MODEL")
        from google import genai

        self.settings = settings
        self.model_name = settings.gemini_model
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def _config(self):
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            http_options=types.HttpOptions(
                timeout=self.settings.model_timeout_seconds * 1000,
            ),
        )

    def _usage(self, response: Any) -> Usage:
        metadata = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(metadata, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(metadata, "candidates_token_count", 0) or 0)
        cost: float | None = None
        if self.settings.priced:
            cost = (
                input_tokens * (self.settings.gemini_price_in or 0.0)
                + output_tokens * (self.settings.gemini_price_out or 0.0)
            ) / 1_000_000
        return Usage(
            calls=1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            priced=self.settings.priced,
        )

    def propose(
        self,
        defect: Defect,
        retrieval: RetrievalResult,
        n: int,
        file_contents: dict[str, str],
        feedback: list[str] | None = None,
        round_index: int = 1,
        artifact_dir: Path | None = None,
    ) -> tuple[list[ProposedPatch], Usage]:
        prompt = render_prompt(defect, retrieval, file_contents, n, feedback)
        _write_artifact(artifact_dir, "prompt.txt", prompt)

        usage = Usage(priced=self.settings.priced)
        repair_note: str | None = None

        for attempt in (1, 2):
            text = prompt
            if repair_note is not None:
                text = f"{prompt}\n# Your previous reply was rejected\n{repair_note}\n"
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=text,
                config=self._config(),
            )
            raw = response.text or ""
            suffix = "" if attempt == 1 else f".retry{attempt}"
            _write_artifact(artifact_dir, f"response.raw{suffix}.json", raw)
            usage = usage.merged_with(self._usage(response))

            try:
                return parse_candidates(raw, round_index, n), usage
            except ModelError as error:
                if attempt == 2:
                    raise
                repair_note = str(error)

        raise ModelError("unreachable")  # pragma: no cover


def parse_candidates(raw: str, round_index: int, n: int) -> list[ProposedPatch]:
    """Turn a model reply into patches, naming precisely what was wrong if it fails."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ModelError(f"reply is not JSON: {error}") from error
    if not isinstance(payload, dict) or "candidates" not in payload:
        raise ModelError("reply has no 'candidates' key")
    entries = payload["candidates"]
    if not isinstance(entries, list):
        raise ModelError("'candidates' is not a list")

    patches: list[ProposedPatch] = []
    problems: list[str] = []
    for index, entry in enumerate(entries[: max(n, 0)], start=1):
        if not isinstance(entry, dict):
            problems.append(f"candidate {index} is not an object")
            continue
        try:
            patches.append(
                ProposedPatch(
                    candidate_id=f"r{round_index}-c{index}",
                    round_index=round_index,
                    rationale=str(entry.get("rationale", "")),
                    unified_diff=str(entry.get("unified_diff", "")),
                    confidence=float(entry.get("confidence", 0.5)),
                )
            )
        except (ValidationError, TypeError, ValueError) as error:
            problems.append(f"candidate {index}: {error}")

    if not patches:
        detail = "; ".join(problems) or "the candidate list was empty"
        raise ModelError(f"no usable candidate in the reply: {detail}")
    return patches


def build_model_client(settings: Settings) -> ModelClient:
    if settings.model_mode == "fake":
        return FakeModelClient(settings)
    if settings.model_mode == "fake_solve":
        return FakeSolveModelClient(settings)
    return GeminiModelClient(settings)
