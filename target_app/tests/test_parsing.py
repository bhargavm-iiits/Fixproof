from datetime import date

import pytest
from parsing import (
    ParseError,
    format_duration,
    parse_bool,
    parse_date,
    parse_duration,
    parse_many,
    try_parse_date,
)


def test_parse_iso_date():
    assert parse_date("2026-09-20") == date(2026, 9, 20)


def test_parse_slashed_day_first_date():
    assert parse_date("20/09/2026") == date(2026, 9, 20)


def test_parse_spelled_month_date():
    assert parse_date("20 Sep 2026") == date(2026, 9, 20)


def test_parse_month_first_spelled_date():
    assert parse_date("Sep 20 2026") == date(2026, 9, 20)


def test_parse_date_tolerates_surrounding_space():
    assert parse_date("  2026-09-20  ") == date(2026, 9, 20)


def test_parse_date_rejects_nonsense():
    with pytest.raises(ParseError):
        parse_date("the day after tomorrow")


def test_parse_date_rejects_empty_text():
    with pytest.raises(ParseError):
        parse_date("   ")


def test_parse_date_error_names_the_input():
    with pytest.raises(ParseError, match="banana"):
        parse_date("banana")


def test_try_parse_date_returns_the_date():
    assert try_parse_date("2026-09-20") == date(2026, 9, 20)


def test_try_parse_date_returns_none_for_nonsense():
    assert try_parse_date("banana") is None


def test_parse_bare_seconds():
    assert parse_duration("90") == 90


def test_parse_seconds_with_a_unit():
    assert parse_duration("90s") == 90


def test_parse_minutes():
    assert parse_duration("5m") == 300


def test_parse_hours():
    assert parse_duration("2h") == 7200


def test_parse_days():
    assert parse_duration("2d") == 172800


def test_parse_weeks():
    assert parse_duration("1w") == 604800


def test_parse_a_compound_duration():
    assert parse_duration("1h30m") == 5400


def test_parse_a_three_part_duration():
    assert parse_duration("1d2h3m") == 93780


def test_parse_duration_tolerates_spaces_between_terms():
    assert parse_duration("1h 30m") == 5400


def test_parse_duration_is_case_insensitive():
    assert parse_duration("1H30M") == 5400


def test_parse_duration_rejects_an_unknown_unit():
    with pytest.raises(ParseError):
        parse_duration("5x")


def test_parse_duration_rejects_empty_text():
    with pytest.raises(ParseError):
        parse_duration("  ")


def test_parse_duration_rejects_trailing_rubbish():
    with pytest.raises(ParseError):
        parse_duration("1h30m!!")


def test_format_a_compound_duration():
    assert format_duration(5400) == "1h30m"


def test_format_zero_seconds():
    assert format_duration(0) == "0s"


def test_format_exact_seconds():
    assert format_duration(45) == "45s"


def test_format_rejects_a_negative_duration():
    with pytest.raises(ParseError):
        format_duration(-1)


def test_format_then_parse_round_trips():
    assert parse_duration(format_duration(93780)) == 93780


@pytest.mark.parametrize("text", ["true", "TRUE", "yes", "y", "1", "on"])
def test_truthy_words(text):
    assert parse_bool(text) is True


@pytest.mark.parametrize("text", ["false", "FALSE", "no", "n", "0", "off"])
def test_falsy_words(text):
    assert parse_bool(text) is False


def test_parse_bool_rejects_anything_else():
    with pytest.raises(ParseError):
        parse_bool("maybe")


def test_parse_many_collects_values_and_errors_separately():
    values, errors = parse_many(["2026-09-20", "banana"], parse_date)
    assert values == [date(2026, 9, 20)]
    assert len(errors) == 1


def test_parse_many_of_all_valid_input_reports_no_errors():
    values, errors = parse_many(["1h", "30m"], parse_duration)
    assert values == [3600, 1800]
    assert errors == []


def test_parse_many_propagates_a_non_parse_error():
    def explode(_text):
        raise ZeroDivisionError("this is a programming fault, not bad input")

    with pytest.raises(ZeroDivisionError):
        parse_many(["anything"], explode)
