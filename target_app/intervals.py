"""Merge, intersect and subtract closed integer intervals.

An interval is a `(start, end)` pair with `start <= end`, and both ends are
inclusive. Adjacent intervals such as `(1, 3)` and `(4, 6)` are contiguous over
the integers and merge into `(1, 6)`.
"""

from __future__ import annotations

Interval = tuple[int, int]


def normalise(interval: Interval) -> Interval:
    """Order the endpoints. `(5, 2)` means the same span as `(2, 5)`."""
    start, end = interval
    if start > end:
        return end, start
    return start, end


def length(interval: Interval) -> int:
    """Inclusive length. A point interval has length 1."""
    start, end = normalise(interval)
    return end - start + 1


def contains(interval: Interval, point: int) -> bool:
    start, end = normalise(interval)
    return start <= point <= end


def overlaps(first: Interval, second: Interval) -> bool:
    """True when the two intervals share at least one integer."""
    a_start, a_end = normalise(first)
    b_start, b_end = normalise(second)
    return a_start <= b_end and b_start <= a_end


def adjacent(first: Interval, second: Interval) -> bool:
    """True when the intervals are contiguous but do not overlap."""
    a_start, a_end = normalise(first)
    b_start, b_end = normalise(second)
    if overlaps(first, second):
        return False
    return a_end + 1 == b_start or b_end + 1 == a_start


def merge(intervals: list[Interval]) -> list[Interval]:
    """Merge overlapping and adjacent intervals into a sorted, disjoint list."""
    if not intervals:
        return []
    ordered = sorted(normalise(interval) for interval in intervals)
    merged: list[Interval] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def intersect(first: Interval, second: Interval) -> Interval | None:
    """The shared span, or None when the intervals are disjoint."""
    a_start, a_end = normalise(first)
    b_start, b_end = normalise(second)
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start > end:
        return None
    return start, end


def intersect_all(lefts: list[Interval], rights: list[Interval]) -> list[Interval]:
    """Every shared span between two interval lists, merged and sorted."""
    shared: list[Interval] = []
    for left in merge(lefts):
        for right in merge(rights):
            overlap = intersect(left, right)
            if overlap is not None:
                shared.append(overlap)
    return merge(shared)


def subtract(minuend: Interval, subtrahend: Interval) -> list[Interval]:
    """`minuend` with `subtrahend` removed: zero, one or two intervals."""
    a_start, a_end = normalise(minuend)
    b_start, b_end = normalise(subtrahend)
    if not overlaps(minuend, subtrahend):
        return [(a_start, a_end)]
    remainder: list[Interval] = []
    if b_start > a_start:
        remainder.append((a_start, b_start - 1))
    if b_end < a_end:
        remainder.append((b_end + 1, a_end))
    return remainder


def subtract_all(minuends: list[Interval], subtrahends: list[Interval]) -> list[Interval]:
    """Remove every subtrahend from every minuend."""
    remaining = merge(minuends)
    for cut in merge(subtrahends):
        next_remaining: list[Interval] = []
        for interval in remaining:
            next_remaining.extend(subtract(interval, cut))
        remaining = next_remaining
    return merge(remaining)


def collect(intervals: list[Interval], into: list[Interval] | None = None) -> list[Interval]:
    """Merge `intervals` into an existing list.

    Pass `into` to accumulate across calls; omit it and each call starts empty.
    """
    if into is None:
        into = []
    into.extend(normalise(interval) for interval in intervals)
    return merge(into)


def total_length(intervals: list[Interval]) -> int:
    """Total covered integers, counting overlaps once."""
    return sum(length(interval) for interval in merge(intervals))


def gaps(intervals: list[Interval]) -> list[Interval]:
    """The uncovered spans between the merged intervals."""
    merged = merge(intervals)
    holes: list[Interval] = []
    for earlier, later in zip(merged, merged[1:], strict=False):
        holes.append((earlier[1] + 1, later[0] - 1))
    return holes
