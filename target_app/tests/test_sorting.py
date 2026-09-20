import pytest
from sorting import SortKey, is_missing, is_sorted, multikey_sort, rank, sort_by, top_n

PEOPLE = [
    {"name": "ada", "team": "b", "score": 2},
    {"name": "bob", "team": "a", "score": 3},
    {"name": "cyd", "team": "b", "score": 1},
    {"name": "dee", "team": "a", "score": 3},
]


def names(rows):
    return [row["name"] for row in rows]


def test_is_missing_for_an_absent_field():
    assert is_missing({}, "score") is True


def test_is_missing_for_a_none_value():
    assert is_missing({"score": None}, "score") is True


def test_is_missing_is_false_for_a_present_value():
    assert is_missing({"score": 0}, "score") is False


def test_sort_by_orders_ascending():
    assert names(sort_by(PEOPLE, SortKey("score"))) == ["cyd", "ada", "bob", "dee"]


def test_sort_by_orders_descending():
    assert names(sort_by(PEOPLE, SortKey("score", descending=True))) == ["bob", "dee", "ada", "cyd"]


def test_descending_sort_keeps_ties_in_input_order():
    ordered = sort_by(PEOPLE, SortKey("score", descending=True))
    assert names(ordered)[:2] == ["bob", "dee"]


def test_sort_by_puts_missing_values_last_by_default():
    rows = [{"a": 2}, {}, {"a": 1}]
    assert sort_by(rows, SortKey("a")) == [{"a": 1}, {"a": 2}, {}]


def test_sort_by_can_put_missing_values_first():
    rows = [{"a": 2}, {}, {"a": 1}]
    assert sort_by(rows, SortKey("a", missing_last=False)) == [{}, {"a": 1}, {"a": 2}]


def test_missing_values_stay_last_when_descending():
    rows = [{"a": 2}, {}, {"a": 1}]
    assert sort_by(rows, SortKey("a", descending=True)) == [{"a": 2}, {"a": 1}, {}]


def test_sort_by_orders_strings():
    rows = [{"a": "pear"}, {"a": "apple"}]
    assert sort_by(rows, SortKey("a")) == [{"a": "apple"}, {"a": "pear"}]


def test_sort_by_groups_differing_types_without_raising():
    rows = [{"a": "x"}, {"a": 2}, {"a": 1}]
    assert sort_by(rows, SortKey("a")) == [{"a": 1}, {"a": 2}, {"a": "x"}]


def test_sort_by_of_an_empty_list_is_empty():
    assert sort_by([], SortKey("a")) == []


def test_sort_by_leaves_the_input_untouched():
    rows = [{"a": 2}, {"a": 1}]
    sort_by(rows, SortKey("a"))
    assert rows == [{"a": 2}, {"a": 1}]


def test_multikey_sort_applies_the_first_key_first():
    ordered = multikey_sort(PEOPLE, [SortKey("team"), SortKey("score")])
    assert names(ordered) == ["bob", "dee", "cyd", "ada"]


def test_multikey_sort_applies_per_key_directions():
    ordered = multikey_sort(PEOPLE, [SortKey("team"), SortKey("score", descending=True)])
    assert names(ordered) == ["bob", "dee", "ada", "cyd"]


def test_rows_equal_on_every_key_keep_their_input_order():
    rows = [
        {"name": "first", "group": "x"},
        {"name": "second", "group": "x"},
        {"name": "third", "group": "x"},
    ]
    ordered = multikey_sort(rows, [SortKey("group")])
    assert names(ordered) == ["first", "second", "third"]


def test_multikey_sort_with_no_keys_preserves_order():
    assert names(multikey_sort(PEOPLE, [])) == ["ada", "bob", "cyd", "dee"]


def test_multikey_sort_of_an_empty_list_is_empty():
    assert multikey_sort([], [SortKey("a")]) == []


def test_rank_reports_each_row_s_final_position():
    assert rank(PEOPLE, [SortKey("score")]) == [1, 2, 0, 3]


def test_rank_of_an_empty_list_is_empty():
    assert rank([], [SortKey("a")]) == []


def test_rank_does_not_leak_its_index_column():
    rows = [{"a": 2}, {"a": 1}]
    rank(rows, [SortKey("a")])
    assert rows == [{"a": 2}, {"a": 1}]


def test_top_n_returns_the_leading_rows():
    assert names(top_n(PEOPLE, [SortKey("score")], 2)) == ["cyd", "ada"]


def test_top_n_beyond_the_data_returns_everything():
    assert len(top_n(PEOPLE, [SortKey("score")], 99)) == 4


def test_top_n_of_zero_is_empty():
    assert top_n(PEOPLE, [SortKey("score")], 0) == []


def test_top_n_rejects_a_negative_count():
    with pytest.raises(ValueError):
        top_n(PEOPLE, [SortKey("score")], -1)


def test_is_sorted_is_true_for_ordered_rows():
    ordered = multikey_sort(PEOPLE, [SortKey("score")])
    assert is_sorted(ordered, [SortKey("score")]) is True


def test_is_sorted_is_false_for_unordered_rows():
    assert is_sorted(PEOPLE, [SortKey("score")]) is False
