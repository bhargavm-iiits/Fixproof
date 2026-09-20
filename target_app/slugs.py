"""Slugify text, fold unicode to ASCII, and resolve collisions deterministically."""

from __future__ import annotations

import re
import unicodedata

NON_ALNUM = re.compile(r"[^a-z0-9]+")
EDGE_HYPHENS = re.compile(r"^-+|-+$")
FALLBACK = "item"


def fold_unicode(text: str) -> str:
    """Decompose accents and drop combining marks, leaving ASCII where possible."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.encode("ascii", "ignore").decode("ascii")


def slugify(text: str, max_length: int = 60) -> str:
    """Lowercase, fold, and hyphenate. Returns "" for text with no usable characters."""
    if max_length < 1:
        raise ValueError("max_length must be at least 1")
    folded = fold_unicode(text).lower()
    slug = NON_ALNUM.sub("-", folded)
    slug = EDGE_HYPHENS.sub("", slug)
    if len(slug) > max_length:
        slug = EDGE_HYPHENS.sub("", slug[:max_length])
    return slug


def _suffixed(base: str, suffix: int, max_length: int) -> str:
    tail = f"-{suffix}"
    if len(base) + len(tail) > max_length:
        base = base[: max_length - len(tail)]
        base = EDGE_HYPHENS.sub("", base)
    return f"{base}{tail}"


def unique_slug(text: str, taken: set[str], max_length: int = 60) -> str:
    """Slugify, appending -2, -3, ... until the result is not already in `taken`."""
    base = slugify(text, max_length)
    if not base:
        base = FALLBACK
    if base not in taken:
        return base
    suffix = 2
    while True:
        candidate = _suffixed(base, suffix, max_length)
        if candidate not in taken:
            return candidate
        suffix += 1


def slugify_all(texts: list[str], max_length: int = 60) -> list[str]:
    """Slugify a list, resolving collisions in order. Blank entries become `item`."""
    taken: set[str] = set()
    slugs: list[str] = []
    for text in texts:
        slug = unique_slug(text, taken, max_length)
        taken.add(slug)
        slugs.append(slug)
    return slugs


def is_slug(text: str) -> bool:
    """True when `text` is already a canonical slug."""
    if not text:
        return False
    return slugify(text, max_length=len(text)) == text
