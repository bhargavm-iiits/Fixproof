"""A token-bucket state machine. The clock is always an argument."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Bucket:
    capacity: float
    refill_per_second: float
    tokens: float
    updated_at: float

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if self.refill_per_second < 0:
            raise ValueError("refill_per_second must not be negative")


def new_bucket(capacity: float, refill_per_second: float, now: float) -> Bucket:
    """A full bucket at time `now`."""
    return Bucket(
        capacity=capacity,
        refill_per_second=refill_per_second,
        tokens=capacity,
        updated_at=now,
    )


def refill(bucket: Bucket, now: float) -> Bucket:
    """Advance the bucket to `now`. Time never runs backwards."""
    if now < bucket.updated_at:
        raise ValueError("now must not precede the bucket's last update")
    elapsed = now - bucket.updated_at
    gained = elapsed * bucket.refill_per_second
    tokens = bucket.tokens + gained
    if tokens > bucket.capacity:
        tokens = bucket.capacity
    return replace(bucket, tokens=tokens, updated_at=now)


def consume(bucket: Bucket, now: float, cost: float = 1.0) -> tuple[Bucket, bool]:
    """Try to spend `cost` tokens. Returns the new bucket and whether it was allowed."""
    if cost <= 0:
        raise ValueError("cost must be positive")
    if cost > bucket.capacity:
        raise ValueError("cost exceeds the bucket's capacity and can never be served")
    filled = refill(bucket, now)
    if filled.tokens >= cost:
        return replace(filled, tokens=filled.tokens - cost), True
    return filled, False


def time_until(bucket: Bucket, now: float, cost: float = 1.0) -> float:
    """Seconds until `cost` tokens are available. Zero when they already are."""
    if cost <= 0:
        raise ValueError("cost must be positive")
    if cost > bucket.capacity:
        raise ValueError("cost exceeds the bucket's capacity and can never be served")
    filled = refill(bucket, now)
    if filled.tokens >= cost:
        return 0.0
    if filled.refill_per_second == 0:
        return float("inf")
    return (cost - filled.tokens) / filled.refill_per_second


def drain(bucket: Bucket, now: float, requests: int, cost: float = 1.0) -> tuple[Bucket, int]:
    """Serve as many of `requests` as the bucket allows at a single instant."""
    if requests < 0:
        raise ValueError("requests must not be negative")
    current = bucket
    served = 0
    for _ in range(requests):
        current, allowed = consume(current, now, cost)
        if not allowed:
            break
        served += 1
    return current, served
