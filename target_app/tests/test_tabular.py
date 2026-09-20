import pytest
from tabular import (
    ColumnError,
    add_column,
    aggregate,
    columns_of,
    drop,
    rename,
    require_columns,
    select,
    summarise_column,
    tally,
)

SALES = [
    {"region": "north", "rep": "ada", "amount": 10},
    {"region": "south", "rep": "bob", "amount": 20},
    {"region": "north", "rep": "cyd", "amount": 5},
    {"region": "south", "rep": "dee", "amount": None},
]


def test_columns_are_listed_in_first_seen_order():
    assert columns_of(SALES) == ["region", "rep", "amount"]


def test_columns_of_ragged_rows_are_unioned():
    assert columns_of([{"a": 1}, {"b": 2}]) == ["a", "b"]


def test_columns_of_an_empty_list_is_empty():
    assert columns_of([]) == []


def test_require_columns_accepts_present_columns():
    require_columns(SALES, ["region"])


def test_require_columns_names_what_is_missing():
    with pytest.raises(ColumnError, match="nope"):
        require_columns(SALES, ["nope"])


def test_select_keeps_only_the_named_columns():
    assert select(SALES, ["rep"])[0] == {"rep": "ada"}


def test_select_honours_the_requested_order():
    assert list(select(SALES, ["rep", "region"])[0]) == ["rep", "region"]


def test_select_rejects_an_unknown_column():
    with pytest.raises(ColumnError):
        select(SALES, ["missing"])


def test_select_of_an_empty_list_is_empty():
    assert select([], []) == []


def test_drop_removes_the_named_columns():
    assert drop(SALES, ["amount"])[0] == {"region": "north", "rep": "ada"}


def test_drop_rejects_an_unknown_column():
    with pytest.raises(ColumnError):
        drop(SALES, ["missing"])


def test_rename_maps_the_named_columns():
    assert rename(SALES, {"rep": "person"})[0]["person"] == "ada"


def test_rename_leaves_unmapped_columns_alone():
    assert "region" in rename(SALES, {"rep": "person"})[0]


def test_rename_rejects_an_unknown_source_column():
    with pytest.raises(ColumnError):
        rename(SALES, {"missing": "x"})


def test_summarise_counts_present_values():
    assert summarise_column(SALES, "amount")["count"] == 3


def test_summarise_counts_nulls():
    assert summarise_column(SALES, "amount")["nulls"] == 1


def test_summarise_sums_the_numbers():
    assert summarise_column(SALES, "amount")["sum"] == pytest.approx(35)


def test_summarise_means_the_numbers():
    assert summarise_column(SALES, "amount")["mean"] == pytest.approx(11.6667)


def test_summarise_reports_min_and_max():
    summary = summarise_column(SALES, "amount")
    assert (summary["min"], summary["max"]) == (5, 20)


def test_summarise_of_a_text_column_has_no_numeric_keys():
    assert "mean" not in summarise_column(SALES, "rep")


def test_summarise_rejects_an_unknown_column():
    with pytest.raises(ColumnError):
        summarise_column(SALES, "missing")


def test_aggregate_groups_and_sums():
    result = aggregate(SALES, ["region"], {"amount": "sum"})
    assert result == [
        {"region": "north", "amount_sum": 15},
        {"region": "south", "amount_sum": 20},
    ]


def test_aggregate_returns_groups_in_first_seen_order():
    result = aggregate(SALES, ["region"], {"amount": "count"})
    assert [row["region"] for row in result] == ["north", "south"]


def test_aggregate_counts_ignore_nulls():
    result = aggregate(SALES, ["region"], {"amount": "count"})
    assert result[1]["amount_count"] == 1


def test_aggregate_means_a_group():
    result = aggregate(SALES, ["region"], {"amount": "mean"})
    assert result[0]["amount_mean"] == pytest.approx(7.5)


def test_aggregate_takes_the_minimum():
    assert aggregate(SALES, ["region"], {"amount": "min"})[0]["amount_min"] == 5


def test_aggregate_takes_the_maximum():
    assert aggregate(SALES, ["region"], {"amount": "max"})[0]["amount_max"] == 10


def test_aggregate_takes_the_first_value():
    assert aggregate(SALES, ["region"], {"rep": "first"})[0]["rep_first"] == "ada"


def test_aggregate_takes_the_last_value():
    assert aggregate(SALES, ["region"], {"rep": "last"})[0]["rep_last"] == "cyd"


def test_aggregate_of_an_all_null_group_is_none():
    rows = [{"g": "x", "v": None}]
    assert aggregate(rows, ["g"], {"v": "sum"})[0]["v_sum"] is None


def test_aggregate_on_several_group_columns():
    result = aggregate(SALES, ["region", "rep"], {"amount": "sum"})
    assert len(result) == 4


def test_aggregate_rejects_an_unknown_aggregation():
    with pytest.raises(ValueError):
        aggregate(SALES, ["region"], {"amount": "median"})


def test_aggregate_rejects_an_unknown_group_column():
    with pytest.raises(ColumnError):
        aggregate(SALES, ["missing"], {"amount": "sum"})


def test_aggregate_of_no_rows_is_empty():
    assert aggregate([], [], {}) == []


def test_tally_adds_into_a_supplied_counter():
    counts = {"north": 5}
    tally(SALES, "region", counts)
    assert counts["north"] == 7


def test_tally_counts_each_value():
    assert tally(SALES, "region") == {"north": 2, "south": 2}


def test_tally_calls_do_not_share_state():
    tally(SALES, "region")
    assert tally([{"region": "north"}], "region") == {"north": 1}


def test_add_column_appends_a_computed_value():
    result = add_column([{"a": 2}], "double", lambda row: row["a"] * 2)
    assert result == [{"a": 2, "double": 4}]


def test_add_column_leaves_the_input_untouched():
    rows = [{"a": 2}]
    add_column(rows, "double", lambda row: row["a"] * 2)
    assert rows == [{"a": 2}]


def test_add_column_twice_does_not_share_state():
    first = add_column([{"a": 1}], "b", lambda row: row["a"])
    second = add_column([{"a": 9}], "b", lambda row: row["a"])
    assert first[0]["b"] == 1
    assert second[0]["b"] == 9
