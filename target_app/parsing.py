"""Lenient date and duration parsing whose failures are explicit."""

from __future__ import annotations

import re
from datetime import date

DURATION_UNITS = {
    "w": 604800,
    "d": 86400,
    "h": 3600,
    "m": 60,
    "s": 1,
}

DURATION_TERM = re.compile(r"(\d+)\s*([a-z]+?)(?=\d|\s|$)")
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y", "%b %d %Y")
TRUE_WORDS = frozenset({"true", "t", "yes", "y", "1", "on"})
FALSE_WORDS = frozenset({"false", "f", "no", "n", "0", "off"})


class ParseError(ValueError):
    """Raised when input cannot be parsed. Never swallowed silently."""


def parse_date(text: str) -> date:
    """Parse a date in any supported format, or raise ParseError naming the input."""
    from datetime import datetime

    candidate = text.strip()
    if not candidate:
        raise ParseError("empty date")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"unrecognised date: {text!r}")


def try_parse_date(text: str) -> date | None:
    """Parse a date, returning None only for a ParseError."""
    try:
        return parse_date(text)
    except ParseError:
        return None


def parse_duration(text: str) -> int:
    """Parse `1h30m`, `90s`, `2d` into whole seconds.

    Units are weeks, days, hours, minutes and seconds. A bare number is seconds.
    """
    candidate = text.strip().lower()
    if not candidate:
        raise ParseError("empty duration")
    if candidate.isdigit():
        return int(candidate)
    terms = DURATION_TERM.findall(candidate)
    if not terms:
        raise ParseError(f"unrecognised duration: {text!r}")
    consumed = sum(len(amount) + len(unit) for amount, unit in terms)
    if consumed != len(candidate.replace(" ", "")):
        raise ParseError(f"unrecognised duration: {text!r}")
    total = 0
    for amount, unit in terms:
        if unit not in DURATION_UNITS:
            raise ParseError(f"unknown duration unit: {unit!r}")
        total += int(amount) * DURATION_UNITS[unit]
    return total


def format_duration(seconds: int) -> str:
    """Render whole seconds back into the compact form `parse_duration` accepts."""
    if seconds < 0:
        raise ParseError("duration must not be negative")
    if seconds == 0:
        return "0s"
    parts: list[str] = []
    remaining = seconds
    for unit, size in DURATION_UNITS.items():
        count, remaining = divmod(remaining, size)
        if count:
            parts.append(f"{count}{unit}")
    return "".join(parts)


def parse_bool(text: str) -> bool:
    """Parse a human-written boolean, or raise ParseError."""
    candidate = text.strip().lower()
    if candidate in TRUE_WORDS:
        return True
    if candidate in FALSE_WORDS:
        return False
    raise ParseError(f"unrecognised boolean: {text!r}")


def parse_many(texts: list[str], parser) -> tuple[list, list[str]]:
    """Parse every entry, collecting values and error messages separately.

    Only ParseError is collected. Any other exception is a programming fault and
    propagates.
    """
    values: list = []
    errors: list[str] = []
    for text in texts:
        try:
            values.append(parser(text))
        except ParseError as error:
            errors.append(str(error))
    return values, errors
