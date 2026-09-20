# Conventions of the target application

These are the rules the target application already follows. A repair that
violates one of them is wrong even if the failing test passes.

## Scope of a fix

A defect is repaired by changing the module that contains it. The test that
demonstrates the defect states the intended behaviour, so the test is the
specification and the code is what is wrong. Changing a test to agree with the
code is never a repair.

## Errors are explicit

Invalid input raises, with a message naming what was invalid. Functions do not
return sentinel values such as `-1` or `None` to signal failure, except where the
name says so (`try_parse_date`, and `intersect`, which returns `None` for a
genuinely empty intersection rather than an error).

`except` clauses name the exception they expect. A bare `except` or
`except Exception` in this codebase is a defect: it converts programming faults
into silently wrong results.

## Purity

No module reads the clock, the network, the filesystem or a random source. Where
behaviour depends on time, the time is a parameter (`ratelimit.refill(bucket, now)`,
`retry.jittered(delay, ratio, seed)`). This is what makes the suite fast and
repeatable, and it must stay true.

## Boundaries and intervals

Intervals in `intervals.py` are **closed**: both endpoints are included, so
`(1, 3)` covers 1, 2 and 3 and has length 3. Over the integers `(1, 3)` and
`(4, 6)` are contiguous and merge into `(1, 6)`.

Paging in `paging.py` uses **half-open** slice bounds internally — `page_bounds`
returns `[start, end)` — while offsets from callers are zero-based and page
numbers returned to callers are one-based. Out-of-range offsets are clamped, not
rejected: an offset past the end yields an empty page.

## Missing values

Absent and `None` mean the same thing and must be handled together. `sorting`
groups missing values rather than comparing them; `tabular` aggregations ignore
them; `csvclean.coerce` turns empty and null-ish text into `None`.

## Defaults

Default arguments are never mutable. Optional containers default to `None` and
are replaced inside the function body, because a default is evaluated once at
definition time and would otherwise be shared by every call.

## Rounding

Anything that rounds takes a `places` parameter and honours it. Numbers are not
rounded to a hard-coded precision.

## Stability of order

Sorting is stable: rows that compare equal keep their input order. Multi-key
sorting is implemented as successive stable sorts applied from the **least**
significant key to the most significant, which is why `multikey_sort` iterates
its keys in reverse.

Grouping preserves first-seen order so that results do not depend on the group
keys being orderable.

## Style

Python 3.12, four-space indentation, lines at most 100 characters, `from
__future__ import annotations` at the top of every module, and type annotations
on every public function. Modules are importable from the application root with
no package prefix.
