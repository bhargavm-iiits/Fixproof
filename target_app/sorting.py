"""Stable multi-key sorting with per-key direction flags."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Row = dict[str, Any]


@dataclass(frozen=True)
class SortKey:
    field: str
    descending: bool = False
    missing_last: bool = True


class _Comparable:
    """Orders values of one type naturally, and differing types by type name."""

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value

    def _sort_tuple(self) -> tuple[str, Any]:
        if isinstance(self.value, bool):
            return ("number", int(self.value))
        if isinstance(self.value, int | float):
            return ("number", self.value)
        return (type(self.value).__name__, self.value)

    def __lt__(self, other: _Comparable) -> bool:
        mine, theirs = self._sort_tuple(), other._sort_tuple()
        if mine[0] != theirs[0]:
            return mine[0] < theirs[0]
        return mine[1] < theirs[1]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _Comparable):
            return NotImplemented
        return self._sort_tuple() == other._sort_tuple()


def is_missing(row: Row, field: str) -> bool:
    """A field is missing when it is absent or None."""
    return field not in row or row[field] is None


def sort_by(rows: list[Row], key: SortKey) -> list[Row]:
    """Sort by one key. Missing values are grouped, never compared."""
    present = [row for row in rows if not is_missing(row, key.field)]
    absent = [row for row in rows if is_missing(row, key.field)]
    present.sort(key=lambda row: _Comparable(row[key.field]), reverse=key.descending)
    if key.missing_last:
        return present + absent
    return absent + present


def multikey_sort(rows: list[Row], keys: list[SortKey]) -> list[Row]:
    """Sort by several keys, the first key most significant.

    Successive stable sorts are applied from the least significant key to the
    most significant, so rows equal on every key keep their input order.
    """
    result = list(rows)
    for key in reversed(keys):
        result = sort_by(result, key)
    return result


def rank(rows: list[Row], keys: list[SortKey]) -> list[int]:
    """The position each input row takes after sorting."""
    decorated = [{"__index__": index, **row} for index, row in enumerate(rows)]
    positions = [0] * len(rows)
    for position, row in enumerate(multikey_sort(decorated, keys)):
        positions[row["__index__"]] = position
    return positions


def top_n(rows: list[Row], keys: list[SortKey], count: int) -> list[Row]:
    """The first `count` rows in sorted order."""
    if count < 0:
        raise ValueError("count must not be negative")
    return multikey_sort(rows, keys)[:count]


def is_sorted(rows: list[Row], keys: list[SortKey]) -> bool:
    """True when `rows` is already in the order `multikey_sort` would produce."""
    return multikey_sort(rows, keys) == rows
