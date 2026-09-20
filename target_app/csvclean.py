"""Header normalisation, type coercion and ragged-row repair for tabular input."""

from __future__ import annotations

import re
from typing import Any

NON_WORD = re.compile(r"[^a-z0-9]+")
EDGE_UNDERSCORES = re.compile(r"^_+|_+$")
INTEGER = re.compile(r"^[+-]?\d+$")
DECIMAL = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
TRUE_WORDS = frozenset({"true", "yes", "y"})
FALSE_WORDS = frozenset({"false", "no", "n"})
NULL_WORDS = frozenset({"", "null", "none", "n/a", "na", "-"})


def normalise_header(name: str) -> str:
    """Lowercase a column name into snake_case. Unusable names become `column`."""
    lowered = name.strip().lower()
    snake = NON_WORD.sub("_", lowered)
    snake = EDGE_UNDERSCORES.sub("", snake)
    if not snake:
        return "column"
    if snake[0].isdigit():
        snake = f"column_{snake}"
    return snake


def normalise_headers(names: list[str]) -> list[str]:
    """Normalise every header, suffixing duplicates as `name_2`, `name_3`, ..."""
    seen: dict[str, int] = {}
    output: list[str] = []
    for name in names:
        base = normalise_header(name)
        if base not in seen:
            seen[base] = 1
            output.append(base)
            continue
        seen[base] += 1
        output.append(f"{base}_{seen[base]}")
    return output


def coerce(value: Any) -> Any:
    """Coerce a cell to int, float, bool or None, leaving anything else as text."""
    if value is None:
        return None
    if isinstance(value, bool | int | float):
        return value
    text = value.strip()
    if text.lower() in NULL_WORDS:
        return None
    if text.lower() in TRUE_WORDS:
        return True
    if text.lower() in FALSE_WORDS:
        return False
    if INTEGER.match(text):
        return int(text)
    if DECIMAL.match(text):
        return float(text)
    return text


def repair_row(row: list[Any], width: int, fill: Any = None) -> list[Any]:
    """Pad a short row and truncate a long one, so every row has `width` cells."""
    if width < 0:
        raise ValueError("width must not be negative")
    if len(row) < width:
        return list(row) + [fill] * (width - len(row))
    if len(row) > width:
        return list(row[:width])
    return list(row)


def clean(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Turn a header row plus data rows into coerced, normalised dictionaries."""
    if not rows:
        return []
    headers = normalise_headers([str(cell) for cell in rows[0]])
    width = len(headers)
    cleaned: list[dict[str, Any]] = []
    for row in rows[1:]:
        repaired = repair_row(row, width)
        cleaned.append(
            {header: coerce(cell) for header, cell in zip(headers, repaired, strict=True)}
        )
    return cleaned


def column_types(rows: list[dict[str, Any]]) -> dict[str, str]:
    """The single type name of each column, or `mixed` where values disagree.

    Columns that are entirely null report `null`.
    """
    types: dict[str, set[str]] = {}
    for row in rows:
        for key, value in row.items():
            name = "null" if value is None else type(value).__name__
            types.setdefault(key, set()).add(name)
    resolved: dict[str, str] = {}
    for key, names in types.items():
        concrete = names - {"null"}
        if not concrete:
            resolved[key] = "null"
        elif len(concrete) == 1:
            resolved[key] = concrete.pop()
        else:
            resolved[key] = "mixed"
    return resolved
