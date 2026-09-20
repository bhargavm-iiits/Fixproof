"""Backoff schedule computation. Pure arithmetic; nothing here sleeps."""

from __future__ import annotations

DEFAULT_RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504)


def backoff_delay(
    attempt: int,
    base: float = 0.5,
    factor: float = 2.0,
    cap: float = 30.0,
) -> float:
    """Delay before retry number `attempt`, one-based, capped at `cap`."""
    if attempt < 1:
        raise ValueError("attempt must be at least 1")
    if base <= 0:
        raise ValueError("base must be positive")
    if factor < 1:
        raise ValueError("factor must be at least 1")
    delay = base * (factor ** (attempt - 1))
    if delay > cap:
        return cap
    return delay


def backoff_schedule(
    attempts: int,
    base: float = 0.5,
    factor: float = 2.0,
    cap: float = 30.0,
) -> list[float]:
    """Every delay for a run of `attempts` retries."""
    if attempts < 0:
        raise ValueError("attempts must not be negative")
    return [backoff_delay(index, base, factor, cap) for index in range(1, attempts + 1)]


def total_backoff(
    attempts: int,
    base: float = 0.5,
    factor: float = 2.0,
    cap: float = 30.0,
) -> float:
    """Total time spent waiting across the whole schedule."""
    return sum(backoff_schedule(attempts, base, factor, cap))


def jittered(delay: float, ratio: float, seed: float) -> float:
    """Deterministic jitter in `[delay * (1 - ratio), delay * (1 + ratio)]`.

    `seed` is a caller-supplied value in `[0, 1)`; nothing here is random.
    """
    if not 0.0 <= ratio <= 1.0:
        raise ValueError("ratio must be between 0 and 1")
    if not 0.0 <= seed < 1.0:
        raise ValueError("seed must be in [0, 1)")
    spread = delay * ratio
    return delay - spread + (2 * spread * seed)


def should_retry(
    attempt: int,
    max_attempts: int,
    status: int | None = None,
    retryable: tuple[int, ...] = DEFAULT_RETRYABLE_STATUS,
) -> bool:
    """True when another attempt is both permitted and worthwhile."""
    if attempt >= max_attempts:
        return False
    if status is None:
        return True
    return status in retryable


def attempts_within(budget_seconds: float, base: float = 0.5, factor: float = 2.0,
                    cap: float = 30.0) -> int:
    """How many retries fit inside a time budget."""
    if budget_seconds < 0:
        raise ValueError("budget_seconds must not be negative")
    spent = 0.0
    attempts = 0
    while True:
        nxt = backoff_delay(attempts + 1, base, factor, cap)
        if spent + nxt > budget_seconds:
            return attempts
        spent += nxt
        attempts += 1
