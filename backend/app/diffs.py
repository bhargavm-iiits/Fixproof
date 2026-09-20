"""Unified-diff parsing.

Everything downstream derives what a patch touches from the diff itself. Nothing
downstream believes a claim the model made about its own patch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
GIT_HEADER = re.compile(r"^diff --git (?P<old>.+?) (?P<new>.+)$")
SYMLINK_MODE = "120000"
TEST_BASENAME = re.compile(r"^(test_.*\.py|.*_test\.py|conftest\.py)$")


class DiffParseError(ValueError):
    """The text offered as a unified diff is not one."""


@dataclass
class FileChange:
    path: str
    old_path: str | None = None
    new_path: str | None = None
    is_new: bool = False
    is_deleted: bool = False
    is_rename: bool = False
    is_mode_change: bool = False
    is_binary: bool = False
    is_symlink: bool = False
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    hunk_count: int = 0

    @property
    def changed_lines(self) -> int:
        return len(self.added_lines) + len(self.removed_lines)


@dataclass(frozen=True)
class ParsedDiff:
    files: tuple[FileChange, ...]

    @property
    def touched_paths(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for change in self.files:
            seen.setdefault(change.path, None)
            if change.is_rename and change.old_path:
                seen.setdefault(change.old_path, None)
        return tuple(sorted(seen))

    @property
    def changed_lines(self) -> int:
        return sum(change.changed_lines for change in self.files)

    @property
    def creates_files(self) -> bool:
        return any(change.is_new for change in self.files)

    @property
    def deletes_files(self) -> bool:
        return any(change.is_deleted for change in self.files)

    @property
    def renames_files(self) -> bool:
        return any(change.is_rename for change in self.files)

    @property
    def changes_modes(self) -> bool:
        return any(change.is_mode_change for change in self.files)

    @property
    def has_binary(self) -> bool:
        return any(change.is_binary for change in self.files)

    @property
    def has_symlink(self) -> bool:
        return any(change.is_symlink for change in self.files)


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        body = raw[1:-1]
        try:
            return body.encode("latin-1", "backslashreplace").decode("unicode_escape")
        except UnicodeDecodeError:
            return body
    return raw


def normalise_path(raw: str) -> str:
    """Strip the timestamp column and the a//b/ prefix git puts on diff headers."""
    text = raw.split("\t", 1)[0].strip()
    text = _unquote(text)
    if text in {"/dev/null", "dev/null"}:
        return ""
    for prefix in ("a/", "b/"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.replace("\\", "/")


def is_absolute(path: str) -> bool:
    return (
        path.startswith("/")
        or path.startswith("\\")
        or bool(re.match(r"^[A-Za-z]:[\\/]", path))
        or path.startswith("//")
    )


def is_test_path(path: str) -> bool:
    parts = [part for part in path.split("/") if part]
    if any(part in {"tests", "test"} for part in parts):
        return True
    return bool(parts) and bool(TEST_BASENAME.match(parts[-1]))


def path_violations(path: str) -> list[str]:
    """Every reason this path may not be written, in a stable order."""
    reasons: list[str] = []
    if not path:
        reasons.append("empty path")
        return reasons
    if is_absolute(path):
        reasons.append(f"absolute path: {path}")
    parts = path.split("/")
    if ".." in parts:
        reasons.append(f"parent traversal: {path}")
    if any(ord(character) < 32 for character in path):
        reasons.append("control character in path")
    if is_test_path(path):
        reasons.append(f"test file: {path}")
    return reasons


def _consume_hunk(lines: list[str], index: int, change: FileChange) -> int:
    match = HUNK_HEADER.match(lines[index])
    if match is None:  # pragma: no cover - only called on a matched line
        raise DiffParseError(f"line {index + 1}: expected a hunk header")
    old_remaining = int(match.group(2)) if match.group(2) is not None else 1
    new_remaining = int(match.group(4)) if match.group(4) is not None else 1
    change.hunk_count += 1
    index += 1

    while old_remaining > 0 or new_remaining > 0:
        if index >= len(lines):
            raise DiffParseError("diff ends in the middle of a hunk")
        line = lines[index]
        marker = line[:1]
        body = line[1:]
        if marker == "\\":
            index += 1
            continue
        if (
            line.startswith("--- ")
            and index + 1 < len(lines)
            and lines[index + 1].startswith("+++ ")
        ):
            # A miscounted hunk header would otherwise swallow the next file's
            # headers, hiding a second touched path from every scope check.
            raise DiffParseError(
                f"line {index + 1}: a file header appears inside a hunk; "
                "the hunk line counts are wrong"
            )
        if marker == "+":
            if new_remaining == 0:
                raise DiffParseError(f"line {index + 1}: more added lines than the hunk declares")
            change.added_lines.append(body)
            new_remaining -= 1
        elif marker == "-":
            if old_remaining == 0:
                raise DiffParseError(f"line {index + 1}: more removed lines than the hunk declares")
            change.removed_lines.append(body)
            old_remaining -= 1
        elif marker in {" ", ""}:
            if old_remaining == 0 or new_remaining == 0:
                raise DiffParseError(f"line {index + 1}: more context lines than the hunk declares")
            old_remaining -= 1
            new_remaining -= 1
        else:
            raise DiffParseError(f"line {index + 1}: unexpected content inside a hunk: {line!r}")
        index += 1
    return index


def parse_unified_diff(text: str) -> ParsedDiff:
    """Parse a unified diff, or raise DiffParseError explaining why it is not one."""
    if not text or not text.strip():
        raise DiffParseError("diff is empty")

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    files: list[FileChange] = []
    current: FileChange | None = None
    pending_old: str | None = None
    pending_new: str | None = None
    declared_old: str | None = None
    declared_new: str | None = None
    flags: dict[str, bool] = {}
    index = 0

    def flush() -> None:
        nonlocal current, pending_old, pending_new, declared_old, declared_new, flags
        if current is not None:
            files.append(current)
        current = None
        pending_old = None
        pending_new = None
        declared_old = None
        declared_new = None
        flags = {}

    def ensure_change() -> FileChange:
        nonlocal current
        if current is None:
            old = pending_old if pending_old else None
            new = pending_new if pending_new else None
            path = new or old or declared_new or declared_old
            if not path:
                raise DiffParseError("a hunk appeared before any file header")
            current = FileChange(
                path=path,
                old_path=old,
                new_path=new,
                is_new=old is None or flags.get("new_file", False),
                is_deleted=new is None or flags.get("deleted_file", False),
                is_rename=flags.get("rename", False),
                is_mode_change=flags.get("mode_change", False),
                is_binary=flags.get("binary", False),
                is_symlink=flags.get("symlink", False),
            )
        return current

    while index < len(lines):
        line = lines[index]

        git_match = GIT_HEADER.match(line)
        if git_match:
            if current is not None or pending_old or pending_new or flags:
                ensure_change()
                flush()
            declared_old = normalise_path(git_match.group("old"))
            declared_new = normalise_path(git_match.group("new"))
            pending_old = declared_old or None
            pending_new = declared_new or None
            index += 1
            continue

        if line.startswith("new file mode "):
            flags["new_file"] = True
            if line.split()[-1] == SYMLINK_MODE:
                flags["symlink"] = True
            pending_old = None
            index += 1
            continue
        if line.startswith("deleted file mode "):
            flags["deleted_file"] = True
            pending_new = None
            index += 1
            continue
        if line.startswith(("old mode ", "new mode ")):
            flags["mode_change"] = True
            if line.split()[-1] == SYMLINK_MODE:
                flags["symlink"] = True
            index += 1
            continue
        if line.startswith(("rename from ", "rename to ", "copy from ", "copy to ")):
            flags["rename"] = True
            index += 1
            continue
        if line.startswith("GIT binary patch") or (
            line.startswith("Binary files ") and line.rstrip().endswith("differ")
        ):
            flags["binary"] = True
            change = ensure_change()
            change.is_binary = True
            index += 1
            continue
        if line.startswith(("index ", "similarity index ", "dissimilarity index ")):
            index += 1
            continue

        if line.startswith("--- "):
            if current is not None:
                flush()
            pending_old = normalise_path(line[4:]) or None
            index += 1
            continue
        if line.startswith("+++ "):
            pending_new = normalise_path(line[4:]) or None
            index += 1
            continue

        if line.startswith("@@"):
            if HUNK_HEADER.match(line) is None:
                raise DiffParseError(f"line {index + 1}: malformed hunk header: {line!r}")
            change = ensure_change()
            index = _consume_hunk(lines, index, change)
            continue

        if line.strip() == "":
            index += 1
            continue

        if current is not None or pending_old or pending_new:
            raise DiffParseError(f"line {index + 1}: unexpected line between hunks: {line!r}")
        index += 1

    if current is not None or pending_old or pending_new or flags:
        ensure_change()
        flush()

    if not files:
        raise DiffParseError("diff contains no file headers")
    for change in files:
        if not change.path:
            raise DiffParseError("diff names a file with an empty path")
        if not (change.hunk_count or change.is_binary or change.is_rename or change.is_mode_change):
            raise DiffParseError(f"no hunks for {change.path}")
    return ParsedDiff(files=tuple(files))


def normalise_for_dedupe(text: str) -> str:
    """Strip hunk line numbers, context and trailing whitespace, for hashing.

    Two candidates that differ only in how much context they quoted are one
    candidate.
    """
    parsed = parse_unified_diff(text)
    parts: list[str] = []
    for change in sorted(parsed.files, key=lambda item: item.path):
        parts.append(f"file:{change.path}")
        for removed in change.removed_lines:
            parts.append(f"-{removed.rstrip()}")
        for added in change.added_lines:
            parts.append(f"+{added.rstrip()}")
    return "\n".join(parts)
