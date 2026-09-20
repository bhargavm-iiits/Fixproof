"""Read the fixture sets from disk.

A fixture's reference patch is loaded only by the scorer and the `fake_solve`
client. Nothing that builds a prompt is allowed to reach it, so it lives behind
a separate call with a name that says what it is.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import PROJECT_ROOT
from backend.app.models import Defect, FixtureSet

FIXTURES_ROOT = PROJECT_ROOT / "fixtures"
TARGET_APP = PROJECT_ROOT / "target_app"


class FixtureNotFound(KeyError):
    """No fixture with that defect id."""


@dataclass(frozen=True)
class Fixture:
    defect: Defect
    directory: Path

    @property
    def break_patch(self) -> str:
        return (self.directory / "break.patch").read_text(encoding="utf-8")

    def read_reference_patch(self) -> str:
        """The answer key. Scoring and `fake_solve` only — never a prompt."""
        return (self.directory / "reference.patch").read_text(encoding="utf-8")

    @property
    def notes(self) -> str:
        path = self.directory / "notes.md"
        return path.read_text(encoding="utf-8") if path.is_file() else ""


def _load_set(fixture_set: FixtureSet, root: Path) -> dict[str, Fixture]:
    directory = root / fixture_set
    if not directory.is_dir():
        return {}
    fixtures: dict[str, Fixture] = {}
    for child in sorted(path for path in directory.iterdir() if path.is_dir()):
        defect_file = child / "defect.json"
        if not defect_file.is_file():
            continue
        defect = Defect(**json.loads(defect_file.read_text(encoding="utf-8")))
        fixtures[defect.defect_id] = Fixture(defect=defect, directory=child)
    return fixtures


@functools.lru_cache(maxsize=4)
def load_fixtures(root: Path = FIXTURES_ROOT) -> dict[str, Fixture]:
    """Every fixture in both sets, keyed by defect id."""
    combined: dict[str, Fixture] = {}
    for fixture_set in ("dev", "holdout"):
        combined.update(_load_set(fixture_set, root))
    return combined


def list_defects(fixture_set: FixtureSet | None = None) -> list[Defect]:
    defects = [fixture.defect for fixture in load_fixtures().values()]
    if fixture_set is not None:
        defects = [defect for defect in defects if defect.fixture_set == fixture_set]
    return sorted(defects, key=lambda defect: defect.defect_id)


def get_fixture(defect_id: str) -> Fixture:
    try:
        return load_fixtures()[defect_id]
    except KeyError as error:
        raise FixtureNotFound(defect_id) from error


def read_failing_test_source(node_id: str) -> str:
    """The source of the failing test, so the agent can read the contract."""
    path_part, _, test_name = node_id.partition("::")
    path = TARGET_APP / path_part
    if not path.is_file():
        return ""
    import ast

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=path_part)
    lines = source.splitlines(keepends=True)
    bare_name = test_name.split("[")[0]
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == bare_name:
            start = node.lineno - 1
            for decorator in node.decorator_list:
                start = min(start, decorator.lineno - 1)
            end = node.end_lineno or node.lineno
            return "".join(lines[start:end])
    return ""
