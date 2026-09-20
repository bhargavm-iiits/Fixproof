import pytest
from slugs import fold_unicode, is_slug, slugify, slugify_all, unique_slug


def test_fold_unicode_strips_accents():
    assert fold_unicode("Crème Brûlée") == "Creme Brulee"


def test_fold_unicode_drops_unmappable_characters():
    assert fold_unicode("hello 世界") == "hello "


def test_fold_unicode_leaves_ascii_alone():
    assert fold_unicode("plain text") == "plain text"


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Hello World") == "hello-world"


def test_slugify_collapses_runs_of_punctuation():
    assert slugify("a -- b __ c") == "a-b-c"


def test_slugify_trims_leading_and_trailing_hyphens():
    assert slugify("!!! edges !!!") == "edges"


def test_slugify_folds_unicode():
    assert slugify("Crème Brûlée") == "creme-brulee"


def test_slugify_keeps_digits():
    assert slugify("Report 2026 Q3") == "report-2026-q3"


def test_slugify_truncates_to_max_length():
    assert slugify("abcdefghij", max_length=4) == "abcd"


def test_slugify_truncation_trims_a_trailing_hyphen():
    assert slugify("abc defgh", max_length=4) == "abc"


def test_slugify_of_unusable_text_is_empty():
    assert slugify("!!!") == ""


def test_slugify_of_empty_text_is_empty():
    assert slugify("") == ""


def test_slugify_rejects_zero_max_length():
    with pytest.raises(ValueError):
        slugify("anything", max_length=0)


def test_unique_slug_returns_the_base_when_free():
    assert unique_slug("Hello World", set()) == "hello-world"


def test_unique_slug_appends_two_on_first_collision():
    assert unique_slug("Hello World", {"hello-world"}) == "hello-world-2"


def test_unique_slug_skips_suffixes_already_taken():
    taken = {"hello-world", "hello-world-2", "hello-world-3"}
    assert unique_slug("Hello World", taken) == "hello-world-4"


def test_unique_slug_of_blank_text_falls_back_to_item():
    assert unique_slug("!!!", set()) == "item"


def test_unique_slug_keeps_suffixed_result_within_max_length():
    result = unique_slug("abcdefghij", {"abcdefgh"}, max_length=8)
    assert result == "abcdef-2"
    assert len(result) == 8


def test_slugify_all_resolves_collisions_in_input_order():
    assert slugify_all(["Report", "report", "REPORT"]) == ["report", "report-2", "report-3"]


def test_slugify_all_handles_a_blank_entry_in_the_middle():
    assert slugify_all(["First", "!!!", "Last"]) == ["first", "item", "last"]


def test_slugify_all_handles_a_whitespace_entry_in_the_middle():
    assert slugify_all(["First", "   ", "Last"]) == ["first", "item", "last"]


def test_slugify_all_of_an_empty_list_is_empty():
    assert slugify_all([]) == []


def test_slugify_all_leaves_distinct_names_alone():
    assert slugify_all(["Alpha", "Beta"]) == ["alpha", "beta"]


def test_is_slug_true_for_a_canonical_slug():
    assert is_slug("hello-world") is True


def test_is_slug_false_for_uppercase():
    assert is_slug("Hello-World") is False


def test_is_slug_false_for_empty_text():
    assert is_slug("") is False
