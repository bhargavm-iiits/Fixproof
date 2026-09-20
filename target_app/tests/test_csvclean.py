import pytest
from csvclean import clean, coerce, column_types, normalise_header, normalise_headers, repair_row


def test_header_is_lowercased_and_underscored():
    assert normalise_header("First Name") == "first_name"


def test_header_punctuation_collapses():
    assert normalise_header("  Total ($USD)  ") == "total_usd"


def test_header_of_only_punctuation_falls_back():
    assert normalise_header("???") == "column"


def test_header_starting_with_a_digit_is_prefixed():
    assert normalise_header("2026 total") == "column_2026_total"


def test_header_already_snake_case_is_unchanged():
    assert normalise_header("order_id") == "order_id"


def test_headers_are_normalised_in_order():
    assert normalise_headers(["First Name", "Last Name"]) == ["first_name", "last_name"]


def test_duplicate_headers_are_suffixed():
    assert normalise_headers(["Name", "name"]) == ["name", "name_2"]


def test_triplicate_headers_keep_counting():
    assert normalise_headers(["a", "A", "a "]) == ["a", "a_2", "a_3"]


def test_distinct_headers_are_not_suffixed():
    assert normalise_headers(["a", "b"]) == ["a", "b"]


def test_coerce_an_integer():
    assert coerce("42") == 42


def test_coerce_a_negative_integer():
    assert coerce("-7") == -7


def test_coerce_a_decimal():
    assert coerce("1.5") == pytest.approx(1.5)


def test_coerce_scientific_notation():
    assert coerce("1e3") == pytest.approx(1000.0)


def test_coerce_a_true_word():
    assert coerce("yes") is True


def test_coerce_a_false_word():
    assert coerce("no") is False


def test_coerce_an_empty_string_to_none():
    assert coerce("") is None


def test_coerce_a_null_word_to_none():
    assert coerce("N/A") is None


def test_coerce_none_stays_none():
    assert coerce(None) is None


def test_coerce_leaves_free_text_alone():
    assert coerce(" hello ") == "hello"


def test_coerce_leaves_an_existing_int_alone():
    assert coerce(42) == 42


def test_repair_pads_a_short_row():
    assert repair_row([1, 2], 4) == [1, 2, None, None]


def test_repair_pads_with_a_chosen_fill():
    assert repair_row([1], 3, fill=0) == [1, 0, 0]


def test_repair_truncates_a_long_row():
    assert repair_row([1, 2, 3, 4], 2) == [1, 2]


def test_repair_leaves_an_exact_row_alone():
    assert repair_row([1, 2], 2) == [1, 2]


def test_repair_to_zero_width_is_empty():
    assert repair_row([1, 2], 0) == []


def test_repair_rejects_a_negative_width():
    with pytest.raises(ValueError):
        repair_row([1], -1)


def test_clean_builds_dictionaries_from_a_header_row():
    rows = [["Order ID", "Total"], ["1", "9.5"]]
    assert clean(rows) == [{"order_id": 1, "total": 9.5}]


def test_clean_repairs_a_short_data_row():
    rows = [["a", "b", "c"], ["1", "2"]]
    assert clean(rows) == [{"a": 1, "b": 2, "c": None}]


def test_clean_repairs_a_long_data_row():
    rows = [["a", "b"], ["1", "2", "3"]]
    assert clean(rows) == [{"a": 1, "b": 2}]


def test_clean_of_an_empty_input_is_empty():
    assert clean([]) == []


def test_clean_of_a_header_only_input_is_empty():
    assert clean([["a", "b"]]) == []


def test_clean_suffixes_duplicate_headers():
    rows = [["name", "name"], ["ada", "bob"]]
    assert clean(rows) == [{"name": "ada", "name_2": "bob"}]


def test_column_types_reports_a_single_type():
    assert column_types([{"a": 1}, {"a": 2}]) == {"a": "int"}


def test_column_types_reports_mixed_where_values_disagree():
    assert column_types([{"a": 1}, {"a": "x"}]) == {"a": "mixed"}


def test_column_types_ignores_nulls_alongside_a_real_type():
    assert column_types([{"a": 1}, {"a": None}]) == {"a": "int"}


def test_column_types_of_an_all_null_column_is_null():
    assert column_types([{"a": None}, {"a": None}]) == {"a": "null"}
