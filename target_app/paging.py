"""Offset/limit paging with explicit boundary and empty-set handling."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any


def page_count(total: int, limit: int) -> int:
    """Number of pages needed for `total` rows. Zero rows means zero pages."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if total <= 0:
        return 0
    return (total + limit - 1) // limit


def clamp_offset(offset: int, total: int) -> int:
    """Pull an out-of-range offset back onto the data."""
    if offset < 0:
        return 0
    if offset > total:
        return total
    return offset


def page_bounds(total: int, offset: int, limit: int) -> tuple[int, int]:
    """The half-open [start, end) slice bounds for one page."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    start = clamp_offset(offset, total)
    end = start + limit
    if end > total:
        end = total
    return start, end


def page_of(rows: Sequence[Any], offset: int, limit: int) -> list[Any]:
    """One page of rows. An offset past the end yields an empty page, not an error."""
    start, end = page_bounds(len(rows), offset, limit)
    return list(rows[start:end])


def page_number(offset: int, limit: int) -> int:
    """One-based page number containing `offset`."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if offset <= 0:
        return 1
    return offset // limit + 1


def has_next(total: int, offset: int, limit: int) -> bool:
    """True when rows remain after this page."""
    _, end = page_bounds(total, offset, limit)
    return end < total


def has_previous(offset: int) -> bool:
    return offset > 0


def iter_pages(rows: Sequence[Any], limit: int) -> Iterator[list[Any]]:
    """Yield every page in order. An empty sequence yields nothing at all."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    for start in range(0, len(rows), limit):
        yield list(rows[start : start + limit])


@dataclass(frozen=True)
class PageSummary:
    total: int
    offset: int
    limit: int
    returned: int
    page_number: int
    page_count: int
    has_next: bool
    has_previous: bool


def summarise(total: int, offset: int, limit: int) -> PageSummary:
    start, end = page_bounds(total, offset, limit)
    return PageSummary(
        total=total,
        offset=offset,
        limit=limit,
        returned=end - start,
        page_number=page_number(start, limit),
        page_count=page_count(total, limit),
        has_next=has_next(total, offset, limit),
        has_previous=has_previous(start),
    )
