"""Per-candidate workspaces and patch application.

Every refusal here happens *before* anything is written. A candidate diff cannot
write outside its own workspace, and the test in
`backend/tests/unit/test_workspace.py` proves it rather than asserting it.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.app.diffs import DiffParseError, parse_unified_diff, path_violations
from backend.app.models import Defect, ProposedPatch

IGNORED = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git", "*.pyc", "runtime")
GIT_IDENTITY = (
    "-c",
    "user.name=fixproof",
    "-c",
    "user.email=fixproof@localhost",
    "-c",
    "commit.gpgsign=false",
)


class PatchRefused(Exception):
    """The patch was refused before the filesystem was touched."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class PatchFailed(Exception):
    """The patch was permitted but git could not apply it."""


@dataclass(frozen=True)
class AppliedPatch:
    workspace: Path
    applied_paths: tuple[str, ...]
    log: str


def refusals(
    patch: ProposedPatch, allowed_paths: tuple[str, ...], max_diff_lines: int
) -> list[str]:
    """Every reason this patch must never reach the filesystem, in a stable order."""
    reasons: list[str] = []
    try:
        parsed = parse_unified_diff(patch.unified_diff)
    except DiffParseError as error:
        return [f"diff does not parse: {error}"]

    allowed = set(allowed_paths)
    for path in parsed.touched_paths:
        reasons.extend(path_violations(path))
        if path not in allowed:
            reasons.append(f"outside allowed_paths: {path}")

    if parsed.creates_files:
        reasons.append("creates a file")
    if parsed.deletes_files:
        reasons.append("deletes a file")
    if parsed.renames_files:
        reasons.append("renames a file")
    if parsed.changes_modes:
        reasons.append("changes a file mode")
    if parsed.has_symlink:
        reasons.append("creates a symlink")
    if parsed.has_binary:
        reasons.append("contains a binary hunk")
    if parsed.changed_lines > max_diff_lines:
        reasons.append(f"changes {parsed.changed_lines} lines, above the limit of {max_diff_lines}")
    return reasons


def _git(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *GIT_IDENTITY, *arguments],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=120,
    )


def build_broken_tree(target_app: Path, break_patch: str, destination: Path) -> Path:
    """A copy of the target application with the fixture's defect introduced."""
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(target_app, destination, ignore=IGNORED)

    patch_file = destination.parent / "break.patch"
    patch_file.write_text(break_patch, encoding="utf-8", newline="\n")
    result = subprocess.run(
        ["git", "apply", "--unidiff-zero", "--whitespace=nowarn", str(patch_file)],
        cwd=destination,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise PatchFailed(f"break.patch does not apply: {result.stderr.strip()}")
    return destination


def make_candidate_workspace(broken_tree: Path, destination: Path) -> Path:
    """A fresh copy of the broken tree. Workspaces are never reused between candidates."""
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(broken_tree, destination, ignore=IGNORED)

    _git(destination, "init", "--quiet")
    _git(destination, "add", "-A")
    commit = _git(destination, "commit", "--quiet", "-m", "broken state")
    if commit.returncode != 0 and "nothing to commit" not in commit.stdout:
        raise PatchFailed(f"could not commit the broken state: {commit.stderr.strip()}")
    return destination


def apply_candidate(
    workspace: Path,
    patch: ProposedPatch,
    defect: Defect,
    max_diff_lines: int,
    artifact_dir: Path | None = None,
) -> AppliedPatch:
    """Refuse, check, apply, then re-derive what was touched and compare."""
    reasons = refusals(patch, defect.allowed_paths, max_diff_lines)
    if reasons:
        if artifact_dir is not None:
            _write(artifact_dir, "apply.log", "REFUSED\n" + "\n".join(reasons) + "\n")
        raise PatchRefused(reasons)

    patch_file = workspace / ".fixproof-candidate.patch"
    patch_file.write_text(patch.unified_diff, encoding="utf-8", newline="\n")
    log_parts: list[str] = []

    try:
        check = _git(workspace, "apply", "--check", "--unidiff-zero", "--whitespace=nowarn",
                     patch_file.name)
        log_parts.append(f"$ git apply --check\n{check.stdout}{check.stderr}")
        if check.returncode != 0:
            raise PatchFailed(f"git apply --check failed: {check.stderr.strip()}")

        applied = _git(workspace, "apply", "--unidiff-zero", "--whitespace=nowarn", patch_file.name)
        log_parts.append(f"$ git apply\n{applied.stdout}{applied.stderr}")
        if applied.returncode != 0:
            raise PatchFailed(f"git apply failed: {applied.stderr.strip()}")
    finally:
        patch_file.unlink(missing_ok=True)

    names = _git(workspace, "diff", "--name-only")
    log_parts.append(f"$ git diff --name-only\n{names.stdout}{names.stderr}")
    actually_touched = tuple(
        sorted(line.strip() for line in names.stdout.splitlines() if line.strip())
    )

    log = "\n".join(log_parts)
    if artifact_dir is not None:
        _write(artifact_dir, "applied.patch", patch.unified_diff)
        _write(artifact_dir, "apply.log", log)

    if actually_touched != tuple(sorted(patch.touched_paths)):
        raise PatchFailed(
            "the applied change does not match the diff: "
            f"declared {sorted(patch.touched_paths)}, applied {list(actually_touched)}"
        )

    return AppliedPatch(workspace=workspace, applied_paths=actually_touched, log=log)


def _write(directory: Path, name: str, content: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(content, encoding="utf-8", newline="\n")
