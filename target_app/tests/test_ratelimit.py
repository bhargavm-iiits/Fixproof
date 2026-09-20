import pytest
from ratelimit import Bucket, consume, drain, new_bucket, refill, time_until


def test_a_new_bucket_starts_full():
    bucket = new_bucket(capacity=10, refill_per_second=1, now=100.0)
    assert bucket.tokens == pytest.approx(10)


def test_capacity_must_be_positive():
    with pytest.raises(ValueError):
        Bucket(capacity=0, refill_per_second=1, tokens=0, updated_at=0.0)


def test_refill_rate_must_not_be_negative():
    with pytest.raises(ValueError):
        Bucket(capacity=1, refill_per_second=-1, tokens=0, updated_at=0.0)


def test_refill_adds_tokens_for_elapsed_time():
    bucket = Bucket(capacity=10, refill_per_second=2, tokens=0, updated_at=0.0)
    assert refill(bucket, 3.0).tokens == pytest.approx(6)


def test_refill_stops_at_capacity():
    bucket = Bucket(capacity=10, refill_per_second=2, tokens=0, updated_at=0.0)
    assert refill(bucket, 1000.0).tokens == pytest.approx(10)


def test_refill_to_exactly_capacity_is_not_clamped_away():
    bucket = Bucket(capacity=10, refill_per_second=2, tokens=0, updated_at=0.0)
    assert refill(bucket, 5.0).tokens == pytest.approx(10)


def test_refill_advances_the_clock():
    bucket = Bucket(capacity=10, refill_per_second=2, tokens=0, updated_at=0.0)
    assert refill(bucket, 3.0).updated_at == pytest.approx(3.0)


def test_refill_with_no_elapsed_time_changes_nothing():
    bucket = Bucket(capacity=10, refill_per_second=2, tokens=4, updated_at=7.0)
    assert refill(bucket, 7.0).tokens == pytest.approx(4)


def test_refill_rejects_a_clock_that_runs_backwards():
    bucket = Bucket(capacity=10, refill_per_second=2, tokens=4, updated_at=7.0)
    with pytest.raises(ValueError):
        refill(bucket, 6.0)


def test_consume_spends_tokens_when_they_are_available():
    bucket = new_bucket(capacity=10, refill_per_second=1, now=0.0)
    updated, allowed = consume(bucket, 0.0, cost=3)
    assert allowed is True
    assert updated.tokens == pytest.approx(7)


def test_consume_is_refused_when_tokens_are_short():
    bucket = Bucket(capacity=10, refill_per_second=0, tokens=2, updated_at=0.0)
    updated, allowed = consume(bucket, 0.0, cost=3)
    assert allowed is False
    assert updated.tokens == pytest.approx(2)


def test_consume_of_exactly_the_remaining_tokens_is_allowed():
    bucket = Bucket(capacity=10, refill_per_second=0, tokens=3, updated_at=0.0)
    updated, allowed = consume(bucket, 0.0, cost=3)
    assert allowed is True
    assert updated.tokens == pytest.approx(0)


def test_consume_refills_before_deciding():
    bucket = Bucket(capacity=10, refill_per_second=1, tokens=0, updated_at=0.0)
    _, allowed = consume(bucket, 5.0, cost=4)
    assert allowed is True


def test_consume_rejects_a_zero_cost():
    bucket = new_bucket(capacity=10, refill_per_second=1, now=0.0)
    with pytest.raises(ValueError):
        consume(bucket, 0.0, cost=0)


def test_consume_rejects_a_cost_beyond_capacity():
    bucket = new_bucket(capacity=10, refill_per_second=1, now=0.0)
    with pytest.raises(ValueError):
        consume(bucket, 0.0, cost=11)


def test_time_until_is_zero_when_tokens_are_ready():
    bucket = new_bucket(capacity=10, refill_per_second=1, now=0.0)
    assert time_until(bucket, 0.0, cost=3) == pytest.approx(0.0)


def test_time_until_counts_the_shortfall():
    bucket = Bucket(capacity=10, refill_per_second=2, tokens=1, updated_at=0.0)
    assert time_until(bucket, 0.0, cost=5) == pytest.approx(2.0)


def test_time_until_is_infinite_without_refill():
    bucket = Bucket(capacity=10, refill_per_second=0, tokens=1, updated_at=0.0)
    assert time_until(bucket, 0.0, cost=5) == float("inf")


def test_time_until_rejects_a_cost_beyond_capacity():
    bucket = new_bucket(capacity=10, refill_per_second=1, now=0.0)
    with pytest.raises(ValueError):
        time_until(bucket, 0.0, cost=11)


def test_drain_serves_what_the_bucket_allows():
    bucket = Bucket(capacity=10, refill_per_second=0, tokens=4, updated_at=0.0)
    updated, served = drain(bucket, 0.0, requests=10)
    assert served == 4
    assert updated.tokens == pytest.approx(0)


def test_drain_serves_every_request_when_tokens_are_plentiful():
    bucket = new_bucket(capacity=10, refill_per_second=0, now=0.0)
    _, served = drain(bucket, 0.0, requests=3)
    assert served == 3


def test_drain_of_zero_requests_serves_nothing():
    bucket = new_bucket(capacity=10, refill_per_second=0, now=0.0)
    _, served = drain(bucket, 0.0, requests=0)
    assert served == 0


def test_drain_rejects_a_negative_request_count():
    bucket = new_bucket(capacity=10, refill_per_second=0, now=0.0)
    with pytest.raises(ValueError):
        drain(bucket, 0.0, requests=-1)
