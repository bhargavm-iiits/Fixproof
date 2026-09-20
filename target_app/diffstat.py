"""Summarise a unified diff. A pleasing self-reference."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")


@dataclass
class FileStat:
    path: str
    added: int = 0
    removed: int = 0

    @property
    def churn(self) -> int:
        return self.added + self.removed

    @property
    def net(self) -> int:
        return self.added - self.removed


@dataclass
class Summary:
    files: list[FileStat] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def added(self) -> int:
        return sum(stat.added for stat in self.files)

    @property
    def removed(self) -> int:
        return sum(stat.removed for stat in self.files)

    @property
    def churn(self) -> int:
        return self.added + self.removed

    @property
    def net(self) -> int:
        return self.added - self.removed


def _path_from_header(line: str) -> str:
    raw = line[4:].split("\t", 1)[0].strip()
    if raw == "/dev/null":
        return ""
    for prefix in ("a/", "b/"):
        if raw.startswith(prefix):
            return raw[len(prefix) :]
    return raw


def summarise(diff_text: str) -> Summary:
    """Count added and removed lines per file. Header lines are never counted."""
    summary = Summary()
    current: FileStat | None = None
    in_hunk = False
    for line in diff_text.replace("\r\n", "\n").split("\n"):
        if line.startswith("--- "):
            in_hunk = False
            continue
        if line.startswith("+++ "):
            path = _path_from_header(line)
            current = FileStat(path=path or "unknown")
            summary.files.append(current)
            in_hunk = False
            continue
        if HUNK.match(line):
            in_hunk = True
            continue
        if not in_hunk or current is None:
            continue
        if line.startswith("+"):
            current.added += 1
        elif line.startswith("-"):
            current.removed += 1
    return summary


def percent_added(summary: Summary, places: int = 1) -> float:
    """Added lines as a percentage of churn, rounded to `places`."""
    if summary.churn == 0:
        return 0.0
    return round(summary.added * 100.0 / summary.churn, places)


def largest_file(summary: Summary) -> FileStat | None:
    """The file with the most churn. Ties go to the earliest in the diff."""
    if not summary.files:
        return None
    best = summary.files[0]
    for stat in summary.files[1:]:
        if stat.churn > best.churn:
            best = stat
    return best


def format_summary(summary: Summary) -> str:
    """A one-line rendering in the style of `git diff --shortstat`."""
    if not summary.files:
        return "0 files changed"
    noun = "file" if summary.file_count == 1 else "files"
    return (
        f"{summary.file_count} {noun} changed, "
        f"{summary.added} insertions(+), {summary.removed} deletions(-)"
    )
