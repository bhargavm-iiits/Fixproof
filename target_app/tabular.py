"""Column selection, renaming and aggregation over lists of dictionaries."""

from __future__ import annotations

from typing import Any

Row = dict[str, Any]

AGGREGATIONS = ("count", "sum", "mean", "min", "max", "first", "last")


class ColumnError(KeyError):
    """A column was requested that the data does not have."""


def columns_of(rows: list[Row]) -> list[str]:
    """Every column name, in first-seen order."""
    seen: dict[str, None] = {}
    for row in rows:
        for key in row:
            seen.setdefault(key, None)
    return list(seen)


def require_columns(rows: list[Row], columns: list[str]) -> None:
    """Raise ColumnError naming every requested column the data lacks."""
    available = set(columns_of(rows))
    missing = [column for column in columns if column not in available]
    if missing:
        raise ColumnError(f"unknown columns: {', '.join(sorted(missing))}")


def select(rows: list[Row], columns: list[str]) -> list[Row]:
    """Keep only `columns`, in the order given."""
    require_columns(rows, columns)
    return [{column: row.get(column) for column in columns} for row in rows]


def drop(rows: list[Row], columns: list[str]) -> list[Row]:
    """Remove `columns`, keeping the rest in their original order."""
    require_columns(rows, columns)
    unwanted = set(columns)
    return [{key: value for key, value in row.items() if key not in unwanted} for row in rows]


def rename(rows: list[Row], mapping: dict[str, str]) -> list[Row]:
    """Rename columns. Keys absent from `mapping` keep their names."""
    require_columns(rows, list(mapping))
    return [{mapping.get(key, key): value for key, value in row.items()} for row in rows]


def _numeric(values: list[Any]) -> list[float]:
    return [float(value) for value in values if isinstance(value, int | float)]


def summarise_column(rows: list[Row], column: str, places: int = 4) -> dict[str, Any]:
    """Count, sum, mean, min and max for one column, ignoring missing values."""
    require_columns(rows, [column])
    present = [row[column] for row in rows if row.get(column) is not None]
    numbers = _numeric(present)
    summary: dict[str, Any] = {
        "column": column,
        "count": len(present),
        "nulls": len(rows) - len(present),
    }
    if numbers:
        summary["sum"] = round(sum(numbers), places)
        summary["mean"] = round(sum(numbers) / len(numbers), places)
        summary["min"] = min(numbers)
        summary["max"] = max(numbers)
    return summary


def _apply(name: str, values: list[Any], places: int) -> Any:
    if name == "count":
        return len([value for value in values if value is not None])
    if name == "first":
        return values[0] if values else None
    if name == "last":
        return values[-1] if values else None
    numbers = _numeric(values)
    if not numbers:
        return None
    if name == "sum":
        return round(sum(numbers), places)
    if name == "mean":
        return round(sum(numbers) / len(numbers), places)
    if name == "min":
        return min(numbers)
    if name == "max":
        return max(numbers)
    raise ValueError(f"unknown aggregation: {name!r}")


def aggregate(
    rows: list[Row],
    group_by: list[str],
    aggregations: dict[str, str],
    places: int = 4,
) -> list[Row]:
    """Group rows and apply one aggregation per named column.

    Groups are returned in first-seen order, which keeps the output stable
    without needing the group keys to be orderable.
    """
    require_columns(rows, group_by)
    require_columns(rows, list(aggregations))
    for name in aggregations.values():
        if name not in AGGREGATIONS:
            raise ValueError(f"unknown aggregation: {name!r}")

    groups: dict[tuple, list[Row]] = {}
    for row in rows:
        signature = tuple(row.get(column) for column in group_by)
        groups.setdefault(signature, []).append(row)

    output: list[Row] = []
    for signature, members in groups.items():
        result: Row = dict(zip(group_by, signature, strict=True))
        for column, name in aggregations.items():
            values = [row.get(column) for row in members]
            result[f"{column}_{name}"] = _apply(name, values, places)
        output.append(result)
    return output


def tally(rows: list[Row], column: str, counts: dict[Any, int] | None = None) -> dict[Any, int]:
    """Count how often each value appears in `column`.

    Pass `counts` to accumulate into an existing tally; omit it and each call
    starts from an empty one.
    """
    if counts is None:
        counts = {}
    for row in rows:
        value = row.get(column)
        counts[value] = counts.get(value, 0) + 1
    return counts


def add_column(rows: list[Row], name: str, compute) -> list[Row]:
    """Append a computed column to every row, leaving the inputs untouched."""
    return [{**row, name: compute(row)} for row in rows]
