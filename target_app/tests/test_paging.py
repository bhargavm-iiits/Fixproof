import pytest
from paging import (
    clamp_offset,
    has_next,
    has_previous,
    iter_pages,
    page_bounds,
    page_count,
    page_number,
    page_of,
    summarise,
)

ROWS = list(range(10))


def test_page_count_for_an_exact_multiple():
    assert page_count(10, 5) == 2


def test_page_count_rounds_a_partial_last_page_up():
    assert page_count(11, 5) == 3


def test_page_count_of_zero_rows_is_zero_pages():
    assert page_count(0, 5) == 0


def test_page_count_of_a_single_row_is_one_page():
    assert page_count(1, 5) == 1


def test_page_count_rejects_a_zero_limit():
    with pytest.raises(ValueError):
        page_count(10, 0)


def test_clamp_offset_pulls_a_negative_offset_to_zero():
    assert clamp_offset(-5, 10) == 0


def test_clamp_offset_pulls_an_offset_past_the_end_back_to_total():
    assert clamp_offset(99, 10) == 10


def test_clamp_offset_leaves_an_in_range_offset_alone():
    assert clamp_offset(4, 10) == 4


def test_clamp_offset_at_exactly_total_is_unchanged():
    assert clamp_offset(10, 10) == 10


def test_page_bounds_of_the_first_page():
    assert page_bounds(10, 0, 4) == (0, 4)


def test_page_bounds_of_a_short_final_page():
    assert page_bounds(10, 8, 4) == (8, 10)


def test_page_bounds_past_the_end_is_an_empty_span():
    assert page_bounds(10, 50, 4) == (10, 10)


def test_page_bounds_rejects_a_zero_limit():
    with pytest.raises(ValueError):
        page_bounds(10, 0, 0)


def test_page_of_returns_the_first_page():
    assert page_of(ROWS, 0, 3) == [0, 1, 2]


def test_page_of_returns_a_short_final_page():
    assert page_of(ROWS, 9, 3) == [9]


def test_page_of_past_the_end_is_empty():
    assert page_of(ROWS, 50, 3) == []


def test_page_of_an_empty_sequence_is_empty():
    assert page_of([], 0, 3) == []


def test_page_of_a_negative_offset_starts_at_the_beginning():
    assert page_of(ROWS, -4, 3) == [0, 1, 2]


def test_page_number_of_the_first_page_is_one():
    assert page_number(0, 5) == 1


def test_page_number_of_the_second_page_is_two():
    assert page_number(5, 5) == 2


def test_page_number_mid_page_stays_on_that_page():
    assert page_number(7, 5) == 2


def test_page_number_of_a_negative_offset_is_one():
    assert page_number(-3, 5) == 1


def test_has_next_is_true_while_rows_remain():
    assert has_next(10, 0, 4) is True


def test_has_next_is_false_on_the_final_page():
    assert has_next(10, 8, 4) is False


def test_has_next_is_false_for_an_empty_set():
    assert has_next(0, 0, 4) is False


def test_has_previous_is_false_at_the_start():
    assert has_previous(0) is False


def test_has_previous_is_true_after_the_start():
    assert has_previous(1) is True


def test_iter_pages_splits_an_exact_multiple():
    assert list(iter_pages([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]


def test_iter_pages_ends_with_a_short_page():
    assert list(iter_pages([1, 2, 3], 2)) == [[1, 2], [3]]


def test_iter_pages_of_an_empty_sequence_yields_nothing():
    assert list(iter_pages([], 2)) == []


def test_iter_pages_rejects_a_zero_limit():
    with pytest.raises(ValueError):
        list(iter_pages([1], 0))


def test_summarise_describes_a_middle_page():
    summary = summarise(10, 4, 4)
    assert summary.returned == 4
    assert summary.page_number == 2
    assert summary.page_count == 3
    assert summary.has_next is True
    assert summary.has_previous is True


def test_summarise_describes_an_empty_set():
    summary = summarise(0, 0, 4)
    assert summary.returned == 0
    assert summary.page_count == 0
    assert summary.has_next is False
