from intervals import (
    adjacent,
    collect,
    contains,
    gaps,
    intersect,
    intersect_all,
    length,
    merge,
    normalise,
    overlaps,
    subtract,
    subtract_all,
    total_length,
)


def test_normalise_orders_reversed_endpoints():
    assert normalise((5, 2)) == (2, 5)


def test_normalise_leaves_ordered_endpoints_alone():
    assert normalise((2, 5)) == (2, 5)


def test_length_is_inclusive():
    assert length((1, 3)) == 3


def test_length_of_a_point_is_one():
    assert length((4, 4)) == 1


def test_contains_is_true_inside():
    assert contains((1, 5), 3) is True


def test_contains_is_true_at_the_lower_bound():
    assert contains((1, 5), 1) is True


def test_contains_is_true_at_the_upper_bound():
    assert contains((1, 5), 5) is True


def test_contains_is_false_outside():
    assert contains((1, 5), 6) is False


def test_overlaps_when_spans_cross():
    assert overlaps((1, 5), (4, 9)) is True


def test_overlaps_when_one_contains_the_other():
    assert overlaps((1, 9), (4, 5)) is True


def test_overlaps_at_a_shared_endpoint():
    assert overlaps((1, 5), (5, 9)) is True


def test_overlaps_is_false_for_adjacent_spans():
    assert overlaps((1, 3), (4, 6)) is False


def test_overlaps_is_false_for_disjoint_spans():
    assert overlaps((1, 3), (7, 9)) is False


def test_adjacent_is_true_for_contiguous_spans():
    assert adjacent((1, 3), (4, 6)) is True


def test_adjacent_is_true_in_either_order():
    assert adjacent((4, 6), (1, 3)) is True


def test_adjacent_is_false_when_they_overlap():
    assert adjacent((1, 5), (4, 6)) is False


def test_adjacent_is_false_with_a_gap():
    assert adjacent((1, 3), (5, 7)) is False


def test_merge_of_an_empty_list_is_empty():
    assert merge([]) == []


def test_merge_combines_overlapping_spans():
    assert merge([(1, 5), (4, 9)]) == [(1, 9)]


def test_merge_combines_adjacent_spans():
    assert merge([(1, 3), (4, 6)]) == [(1, 6)]


def test_merge_keeps_disjoint_spans_separate():
    assert merge([(1, 3), (7, 9)]) == [(1, 3), (7, 9)]


def test_merge_sorts_unordered_input():
    assert merge([(7, 9), (1, 3)]) == [(1, 3), (7, 9)]


def test_merge_absorbs_a_fully_contained_span():
    assert merge([(1, 9), (3, 4)]) == [(1, 9)]


def test_merge_normalises_reversed_endpoints():
    assert merge([(5, 1)]) == [(1, 5)]


def test_intersect_returns_the_shared_span():
    assert intersect((1, 5), (4, 9)) == (4, 5)


def test_intersect_of_disjoint_spans_is_none():
    assert intersect((1, 3), (7, 9)) is None


def test_intersect_of_adjacent_spans_is_none():
    assert intersect((1, 3), (4, 6)) is None


def test_intersect_at_a_single_shared_point():
    assert intersect((1, 5), (5, 9)) == (5, 5)


def test_intersect_all_finds_every_shared_span():
    assert intersect_all([(1, 5), (10, 15)], [(4, 12)]) == [(4, 5), (10, 12)]


def test_intersect_all_with_no_overlap_is_empty():
    assert intersect_all([(1, 3)], [(7, 9)]) == []


def test_subtract_a_middle_slice_leaves_two_spans():
    assert subtract((1, 9), (4, 5)) == [(1, 3), (6, 9)]


def test_subtract_a_leading_slice_leaves_one_span():
    assert subtract((1, 9), (1, 4)) == [(5, 9)]


def test_subtract_a_trailing_slice_leaves_one_span():
    assert subtract((1, 9), (5, 9)) == [(1, 4)]


def test_subtract_the_whole_span_leaves_nothing():
    assert subtract((1, 9), (1, 9)) == []


def test_subtract_a_disjoint_span_changes_nothing():
    assert subtract((1, 3), (7, 9)) == [(1, 3)]


def test_subtract_a_covering_span_leaves_nothing():
    assert subtract((4, 5), (1, 9)) == []


def test_subtract_all_removes_every_cut():
    assert subtract_all([(1, 20)], [(5, 6), (10, 12)]) == [(1, 4), (7, 9), (13, 20)]


def test_subtract_all_with_no_cuts_returns_the_merged_input():
    assert subtract_all([(1, 3), (4, 6)], []) == [(1, 6)]


def test_collect_merges_into_a_supplied_list():
    existing = [(1, 3)]
    assert collect([(4, 6)], existing) == [(1, 6)]


def test_collect_without_a_target_merges_its_input():
    assert collect([(1, 3), (4, 6)]) == [(1, 6)]


def test_collect_calls_do_not_share_state():
    collect([(100, 200)])
    assert collect([(1, 3)]) == [(1, 3)]


def test_total_length_counts_overlaps_once():
    assert total_length([(1, 5), (4, 9)]) == 9


def test_total_length_of_disjoint_spans_sums():
    assert total_length([(1, 3), (7, 9)]) == 6


def test_total_length_of_nothing_is_zero():
    assert total_length([]) == 0


def test_gaps_reports_the_hole_between_spans():
    assert gaps([(1, 3), (7, 9)]) == [(4, 6)]


def test_gaps_of_contiguous_spans_is_empty():
    assert gaps([(1, 3), (4, 6)]) == []


def test_gaps_of_a_single_span_is_empty():
    assert gaps([(1, 3)]) == []
