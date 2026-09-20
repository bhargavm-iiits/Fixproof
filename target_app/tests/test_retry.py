import pytest
from retry import (
    attempts_within,
    backoff_delay,
    backoff_schedule,
    jittered,
    should_retry,
    total_backoff,
)


def test_first_delay_is_the_base():
    assert backoff_delay(1, base=0.5, factor=2.0) == pytest.approx(0.5)


def test_delay_doubles_with_the_default_factor():
    assert backoff_delay(3, base=0.5, factor=2.0) == pytest.approx(2.0)


def test_delay_is_capped():
    assert backoff_delay(20, base=0.5, factor=2.0, cap=30.0) == pytest.approx(30.0)


def test_delay_exactly_at_the_cap_is_not_altered():
    assert backoff_delay(2, base=5.0, factor=2.0, cap=10.0) == pytest.approx(10.0)


def test_a_factor_of_one_never_grows():
    assert backoff_delay(9, base=1.5, factor=1.0) == pytest.approx(1.5)


def test_attempt_zero_is_rejected():
    with pytest.raises(ValueError):
        backoff_delay(0)


def test_a_non_positive_base_is_rejected():
    with pytest.raises(ValueError):
        backoff_delay(1, base=0.0)


def test_a_factor_below_one_is_rejected():
    with pytest.raises(ValueError):
        backoff_delay(1, factor=0.5)


def test_schedule_lists_every_delay():
    assert backoff_schedule(4, base=1.0, factor=2.0) == pytest.approx([1.0, 2.0, 4.0, 8.0])


def test_schedule_of_zero_attempts_is_empty():
    assert backoff_schedule(0) == []


def test_schedule_applies_the_cap():
    assert backoff_schedule(4, base=1.0, factor=2.0, cap=3.0) == pytest.approx([1.0, 2.0, 3.0, 3.0])


def test_schedule_rejects_negative_attempts():
    with pytest.raises(ValueError):
        backoff_schedule(-1)


def test_total_backoff_sums_the_schedule():
    assert total_backoff(3, base=1.0, factor=2.0) == pytest.approx(7.0)


def test_total_backoff_of_zero_attempts_is_zero():
    assert total_backoff(0) == pytest.approx(0.0)


def test_jitter_of_zero_seed_is_the_lower_bound():
    assert jittered(10.0, ratio=0.5, seed=0.0) == pytest.approx(5.0)


def test_jitter_of_a_half_seed_is_the_original_delay():
    assert jittered(10.0, ratio=0.5, seed=0.5) == pytest.approx(10.0)


def test_jitter_approaches_the_upper_bound():
    assert jittered(10.0, ratio=0.5, seed=0.999) == pytest.approx(14.99)


def test_a_zero_ratio_leaves_the_delay_alone():
    assert jittered(10.0, ratio=0.0, seed=0.3) == pytest.approx(10.0)


def test_a_ratio_above_one_is_rejected():
    with pytest.raises(ValueError):
        jittered(10.0, ratio=1.5, seed=0.5)


def test_a_seed_of_one_is_rejected():
    with pytest.raises(ValueError):
        jittered(10.0, ratio=0.5, seed=1.0)


def test_retry_is_allowed_below_the_attempt_limit():
    assert should_retry(1, 3) is True


def test_retry_stops_at_the_attempt_limit():
    assert should_retry(3, 3) is False


def test_retry_stops_past_the_attempt_limit():
    assert should_retry(4, 3) is False


def test_a_retryable_status_is_retried():
    assert should_retry(1, 3, status=503) is True


def test_a_client_error_is_not_retried():
    assert should_retry(1, 3, status=404) is False


def test_a_successful_status_is_not_retried():
    assert should_retry(1, 3, status=200) is False


def test_a_custom_retryable_set_is_honoured():
    assert should_retry(1, 3, status=418, retryable=(418,)) is True


def test_attempts_within_a_generous_budget():
    assert attempts_within(7.0, base=1.0, factor=2.0) == 3


def test_attempts_within_a_budget_that_fits_none():
    assert attempts_within(0.5, base=1.0, factor=2.0) == 0


def test_attempts_within_a_zero_budget_is_zero():
    assert attempts_within(0.0) == 0


def test_attempts_within_rejects_a_negative_budget():
    with pytest.raises(ValueError):
        attempts_within(-1.0)
