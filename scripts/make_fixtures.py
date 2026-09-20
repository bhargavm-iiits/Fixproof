"""Generate the dev and holdout fixture sets from a table of seeded defects.

Each defect is one exact snippet replacement in one target module. The break
patch is the diff that introduces it; the reference patch is the diff that undoes
it. Both are generated, so a fixture's patches can never drift from the code they
describe. Run `scripts/validate_fixtures.py` afterwards to prove each one behaves.
"""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_APP = PROJECT_ROOT / "target_app"
FIXTURES = PROJECT_ROOT / "fixtures"


@dataclass(frozen=True)
class Spec:
    defect_id: str
    fixture_set: str
    category: str
    module: str
    failing_test: str
    summary: str
    notes: str
    old: str = ""
    new: str = ""
    edits: tuple[tuple[str, str], ...] = ()

    def replacements(self) -> tuple[tuple[str, str], ...]:
        return self.edits or ((self.old, self.new),)


SPECS: tuple[Spec, ...] = (
    # ---------------------------------------------------------------- dev set
    Spec(
        defect_id="dev-off_by_one-001",
        fixture_set="dev",
        category="off_by_one",
        module="paging.py",
        old="    return (total + limit - 1) // limit",
        new="    return (total + limit) // limit",
        failing_test="tests/test_paging.py::test_page_count_for_an_exact_multiple",
        summary=(
            "The number of pages is reported as one too many whenever the row count "
            "divides exactly by the page size."
        ),
        notes=(
            "The classic ceiling-division mistake. It is invisible for every input "
            "that does *not* divide evenly, which is why a single well-chosen test "
            "is worth more here than a dozen random ones."
        ),
    ),
    Spec(
        defect_id="dev-wrong_operator-001",
        fixture_set="dev",
        category="wrong_operator",
        module="intervals.py",
        old="    return a_start <= b_end and b_start <= a_end",
        new="    return a_start <= b_end and b_start < a_end",
        failing_test="tests/test_intervals.py::test_overlaps_at_a_shared_endpoint",
        summary=(
            "Two closed intervals that meet at exactly one shared endpoint are "
            "reported as not overlapping."
        ),
        notes=(
            "Closed intervals include both endpoints, so touching at one point is an "
            "overlap. Only one of the two comparisons is wrong, so the symptom appears "
            "in one direction and not the other."
        ),
    ),
    Spec(
        defect_id="dev-none_handling-001",
        fixture_set="dev",
        category="none_handling",
        module="sorting.py",
        old="    return field not in row or row[field] is None",
        new="    return field not in row",
        failing_test="tests/test_sorting.py::test_is_missing_for_a_none_value",
        summary=(
            "A field that is present but holds no value is treated as present, so "
            "empty values are sorted rather than grouped."
        ),
        notes=(
            "Absent and null are different shapes of the same idea. Handling one and "
            "forgetting the other is the most common way this function goes wrong."
        ),
    ),
    Spec(
        defect_id="dev-boundary_condition-001",
        fixture_set="dev",
        category="boundary_condition",
        module="retry.py",
        old="    if attempt >= max_attempts:",
        new="    if attempt > max_attempts:",
        failing_test="tests/test_retry.py::test_retry_stops_at_the_attempt_limit",
        summary=(
            "The retry limit permits one more attempt than it should: reaching the "
            "limit is treated as still being below it."
        ),
        notes=(
            "An off-by-one at a limit check. In production this shape of defect costs "
            "one extra request per failing call, which is invisible until it is not."
        ),
    ),
    Spec(
        defect_id="dev-regex_greedy-001",
        fixture_set="dev",
        category="regex_greedy",
        module="slugs.py",
        old='NON_ALNUM = re.compile(r"[^a-z0-9]+")',
        new='NON_ALNUM = re.compile(r"[^a-z0-9]+?")',
        failing_test="tests/test_slugs.py::test_slugify_collapses_runs_of_punctuation",
        summary=(
            "Runs of punctuation are no longer collapsed into a single separator, so "
            "slugs gain one separator per discarded character."
        ),
        notes=(
            "A lazy quantifier matches the shortest run it can, which for a "
            "substitution means one replacement per character instead of one per run. "
            "Single-character runs behave identically, so most tests stay green."
        ),
    ),
    Spec(
        defect_id="dev-mutable_default_arg-001",
        fixture_set="dev",
        category="mutable_default_arg",
        module="tabular.py",
        edits=(
            (
                "counts: dict[Any, int] | None = None) -> dict[Any, int]:",
                "counts: dict[Any, int] = {}) -> dict[Any, int]:",
            ),
            ("    if counts is None:\n        counts = {}\n    for row in rows:", "    for row in rows:"),
        ),
        failing_test="tests/test_tabular.py::test_tally_calls_do_not_share_state",
        summary=(
            "Counts leak between calls: a second call without an explicit counter "
            "sees the totals accumulated by the first."
        ),
        notes=(
            "A default argument is evaluated once, when the function is defined. The "
            "first call looks perfectly correct, which is what makes this defect "
            "interesting: only the second call can reveal it."
        ),
    ),
    Spec(
        defect_id="dev-sort_instability-001",
        fixture_set="dev",
        category="sort_instability",
        module="sorting.py",
        old="    for key in reversed(keys):",
        new="    for key in keys:",
        failing_test="tests/test_sorting.py::test_multikey_sort_applies_the_first_key_first",
        summary=(
            "Sort keys are applied in the wrong order, so the least significant key "
            "wins and the most significant key only breaks its ties."
        ),
        notes=(
            "Successive stable sorts must run from the least significant key to the "
            "most significant. Reversing that inverts key precedence. When both keys "
            "happen to agree on an ordering the output is identical, which hides it."
        ),
    ),
    Spec(
        defect_id="dev-dict_key_mismatch-001",
        fixture_set="dev",
        category="dict_key_mismatch",
        module="tabular.py",
        old='        "nulls": len(rows) - len(present),',
        new='        "null_count": len(rows) - len(present),',
        failing_test="tests/test_tabular.py::test_summarise_counts_nulls",
        summary=(
            "The column summary publishes its missing-value count under a different "
            "name than its consumers read."
        ),
        notes=(
            "Nothing raises at the point of the mistake. The failure surfaces at the "
            "reader, one layer away from the cause."
        ),
    ),
    Spec(
        defect_id="dev-float_rounding-001",
        fixture_set="dev",
        category="float_rounding",
        module="diffstat.py",
        old="def percent_added(summary: Summary, places: int = 1) -> float:",
        new="def percent_added(summary: Summary, places: int = 0) -> float:",
        failing_test="tests/test_diffstat.py::test_percent_added_rounds_to_one_place",
        summary=(
            "Percentages are rounded to whole numbers by default instead of to one "
            "decimal place."
        ),
        notes=(
            "Callers that pass an explicit precision are unaffected, so the defect is "
            "only visible through the default. Values that happen to be whole numbers "
            "also hide it."
        ),
    ),
    Spec(
        defect_id="dev-swallowed_exception-001",
        fixture_set="dev",
        category="swallowed_exception",
        module="parsing.py",
        old="        except ParseError as error:",
        new="        except Exception as error:",
        failing_test="tests/test_parsing.py::test_parse_many_propagates_a_non_parse_error",
        summary=(
            "Bulk parsing catches every exception rather than only parse failures, so "
            "genuine programming faults are reported as bad input."
        ),
        notes=(
            "The broadest and most damaging shape of this defect: it converts a crash "
            "you would have fixed into a silently wrong result you will not notice."
        ),
    ),
    Spec(
        defect_id="dev-early_return-001",
        fixture_set="dev",
        category="early_return",
        module="slugs.py",
        old=(
            "    for text in texts:\n"
            "        slug = unique_slug(text, taken, max_length)"
        ),
        new=(
            "    for text in texts:\n"
            "        if not text.strip():\n"
            "            return slugs\n"
            "        slug = unique_slug(text, taken, max_length)"
        ),
        failing_test="tests/test_slugs.py::test_slugify_all_handles_a_whitespace_entry_in_the_middle",
        summary=(
            "A blank entry ends the whole batch instead of being given the fallback "
            "name, so every later entry is silently dropped."
        ),
        notes=(
            "A guard that should have continued returns instead. The output is short "
            "rather than wrong, which is exactly the kind of failure a length "
            "assertion catches and a spot check does not."
        ),
    ),
    Spec(
        defect_id="dev-inverted_condition-001",
        fixture_set="dev",
        category="inverted_condition",
        module="diffstat.py",
        old="        if stat.churn > best.churn:",
        new="        if stat.churn < best.churn:",
        failing_test="tests/test_diffstat.py::test_largest_file_is_the_one_with_most_churn",
        summary="The largest-file search returns the smallest file instead of the largest.",
        notes=(
            "Inverting the comparison in a running-maximum loop turns it into a "
            "running minimum. Tied inputs still produce the expected answer, so the "
            "tie-breaking test keeps passing and only the ordering test fails."
        ),
    ),
    # ------------------------------------------------------------ holdout set
    Spec(
        defect_id="holdout-off_by_one-001",
        fixture_set="holdout",
        category="off_by_one",
        module="paging.py",
        old="    for start in range(0, len(rows), limit):",
        new="    for start in range(0, len(rows) - 1, limit):",
        failing_test="tests/test_paging.py::test_iter_pages_ends_with_a_short_page",
        summary="Iterating pages drops the final partial page.",
        notes=(
            "Shortening the range by one only changes the result when the last page "
            "is partial, so evenly divisible inputs look correct."
        ),
    ),
    Spec(
        defect_id="holdout-wrong_operator-001",
        fixture_set="holdout",
        category="wrong_operator",
        module="ratelimit.py",
        old="    return (cost - filled.tokens) / filled.refill_per_second",
        new="    return (cost - filled.tokens) * filled.refill_per_second",
        failing_test="tests/test_ratelimit.py::test_time_until_counts_the_shortfall",
        summary=(
            "The wait for more tokens is computed by multiplying by the refill rate "
            "rather than dividing by it."
        ),
        notes=(
            "Dimensionally wrong but numerically plausible, and identical whenever the "
            "rate is exactly one. A test with a rate of two is what separates them."
        ),
    ),
    Spec(
        defect_id="holdout-none_handling-001",
        fixture_set="holdout",
        category="none_handling",
        module="tabular.py",
        old="        return len([value for value in values if value is not None])",
        new="        return len(values)",
        failing_test="tests/test_tabular.py::test_aggregate_counts_ignore_nulls",
        summary="Grouped counts include missing values instead of ignoring them.",
        notes=(
            "Counting rows and counting values are different questions. Groups with no "
            "missing values give the same answer either way."
        ),
    ),
    Spec(
        defect_id="holdout-boundary_condition-001",
        fixture_set="holdout",
        category="boundary_condition",
        module="retry.py",
        old="        if spent + nxt > budget_seconds:",
        new="        if spent + nxt >= budget_seconds:",
        failing_test="tests/test_retry.py::test_attempts_within_a_generous_budget",
        summary=(
            "An attempt that would exactly consume the remaining budget is rejected, "
            "so the budget is under-used by one attempt."
        ),
        notes=(
            "Only budgets that land exactly on a schedule boundary reveal this. Every "
            "other budget gives the same answer under both comparisons."
        ),
    ),
    Spec(
        defect_id="holdout-regex_greedy-001",
        fixture_set="holdout",
        category="regex_greedy",
        module="csvclean.py",
        old='NON_WORD = re.compile(r"[^a-z0-9]+")',
        new='NON_WORD = re.compile(r"[^a-z0-9]+?")',
        failing_test="tests/test_csvclean.py::test_header_punctuation_collapses",
        summary=(
            "Header names keep one separator per punctuation character instead of one "
            "per run of punctuation."
        ),
        notes=(
            "The same lazy-quantifier shape as the dev set's slug defect, in a "
            "different module. Headers separated by a single space are unaffected, "
            "which covers most real headers and hides it."
        ),
    ),
    Spec(
        defect_id="holdout-mutable_default_arg-001",
        fixture_set="holdout",
        category="mutable_default_arg",
        module="intervals.py",
        edits=(
            (
                "into: list[Interval] | None = None) -> list[Interval]:",
                "into: list[Interval] = []) -> list[Interval]:",
            ),
            ("    if into is None:\n        into = []\n    into.extend", "    into.extend"),
        ),
        failing_test="tests/test_intervals.py::test_collect_calls_do_not_share_state",
        summary=(
            "Spans leak between calls: a call without an explicit target sees every "
            "span collected by earlier calls."
        ),
        notes=(
            "Identical in mechanism to the dev set's counting defect, but the leaked "
            "state is a list rather than a dictionary and the symptom is extra "
            "results rather than inflated numbers."
        ),
    ),
    Spec(
        defect_id="holdout-sort_instability-001",
        fixture_set="holdout",
        category="sort_instability",
        module="sorting.py",
        old="    for key in reversed(keys):",
        new="    for key in reversed(keys[:1]):",
        failing_test="tests/test_sorting.py::test_multikey_sort_applies_the_first_key_first",
        summary=(
            "Only the first sort key is ever applied, so rows tied on it keep their "
            "input order instead of being ordered by the remaining keys."
        ),
        notes=(
            "A truncation rather than a reversal. Where the keys agree on an ordering "
            "the result is indistinguishable from correct."
        ),
    ),
    Spec(
        defect_id="holdout-dict_key_mismatch-001",
        fixture_set="holdout",
        category="dict_key_mismatch",
        module="parsing.py",
        old='    "w": 604800,',
        new='    "wk": 604800,',
        failing_test="tests/test_parsing.py::test_parse_weeks",
        summary=(
            "The week unit is registered under a name the parser never produces, so "
            "week durations are rejected as unknown."
        ),
        notes=(
            "Rendering still works, because rendering only reads the table and never "
            "looks a token up in it. Only the parse direction fails."
        ),
    ),
    Spec(
        defect_id="holdout-float_rounding-001",
        fixture_set="holdout",
        category="float_rounding",
        module="tabular.py",
        old='        summary["mean"] = round(sum(numbers) / len(numbers), places)',
        new='        summary["mean"] = round(sum(numbers) / len(numbers), 2)',
        failing_test="tests/test_tabular.py::test_summarise_means_the_numbers",
        summary=(
            "The mean ignores the requested precision and is always rounded to two "
            "decimal places."
        ),
        notes=(
            "A hard-coded constant shadowing a parameter. Sums in the same function "
            "still honour the parameter, so the inconsistency is within one result."
        ),
    ),
    Spec(
        defect_id="holdout-swallowed_exception-001",
        fixture_set="holdout",
        category="swallowed_exception",
        module="parsing.py",
        old=(
            "    for amount, unit in terms:\n"
            "        if unit not in DURATION_UNITS:\n"
            '            raise ParseError(f"unknown duration unit: {unit!r}")\n'
            "        total += int(amount) * DURATION_UNITS[unit]"
        ),
        new=(
            "    for amount, unit in terms:\n"
            "        try:\n"
            "            total += int(amount) * DURATION_UNITS[unit]\n"
            "        except KeyError:\n"
            "            continue"
        ),
        failing_test="tests/test_parsing.py::test_parse_duration_rejects_an_unknown_unit",
        summary=(
            "An unrecognised duration unit is skipped instead of rejected, so bad "
            "input parses to a confidently wrong number."
        ),
        notes=(
            "The most dangerous variant in the set, because the caller receives a "
            "plausible value rather than an error. A duration of zero looks like a "
            "legitimate answer."
        ),
    ),
    Spec(
        defect_id="holdout-early_return-001",
        fixture_set="holdout",
        category="early_return",
        module="intervals.py",
        old=("        else:\n            merged.append((start, end))\n    return merged"),
        new=(
            "        else:\n"
            "            merged.append((start, end))\n"
            "            return merged\n"
            "    return merged"
        ),
        failing_test="tests/test_intervals.py::test_subtract_all_removes_every_cut",
        summary=(
            "Merging stops at the first gap, so everything after the first disjoint "
            "span is discarded."
        ),
        notes=(
            "Needs three or more disjoint spans to show at all: with two, returning "
            "after appending the second is the same as falling through. The failure "
            "surfaces two layers away, in subtraction rather than in merging."
        ),
    ),
    Spec(
        defect_id="holdout-inverted_condition-001",
        fixture_set="holdout",
        category="inverted_condition",
        module="tabular.py",
        old=(
            "    return [{key: value for key, value in row.items() if key not in unwanted}"
            " for row in rows]"
        ),
        new=(
            "    return [{key: value for key, value in row.items() if key in unwanted}"
            " for row in rows]"
        ),
        failing_test="tests/test_tabular.py::test_drop_removes_the_named_columns",
        summary="Dropping columns keeps exactly the columns it was asked to remove.",
        notes=(
            "A single negation. The validation path is untouched, so the error-handling "
            "test still passes and only the behaviour test fails."
        ),
    ),
)


def make_patch(before: str, after: str, path: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)


def changed_line_count(patch: str) -> int:
    """Source lines the patch touches — a one-line substitution touches one line."""
    added = removed = 0
    for line in patch.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return max(added, removed)


def difficulty_for(changed: int) -> str:
    if changed <= 1:
        return "easy"
    if changed <= 5:
        return "medium"
    return "hard"


def build(spec: Spec) -> dict:
    source = (TARGET_APP / spec.module).read_text(encoding="utf-8")
    broken = source
    for old, new in spec.replacements():
        occurrences = broken.count(old)
        if occurrences != 1:
            raise SystemExit(
                f"{spec.defect_id}: snippet occurs {occurrences} times in {spec.module}; "
                f"it must occur exactly once:\n{old!r}"
            )
        broken = broken.replace(old, new)

    break_patch = make_patch(source, broken, spec.module)
    reference_patch = make_patch(broken, source, spec.module)
    changed = changed_line_count(reference_patch)

    defect = {
        "defect_id": spec.defect_id,
        "fixture_set": spec.fixture_set,
        "summary": spec.summary,
        "failing_test": spec.failing_test,
        "allowed_paths": [spec.module],
        "category": spec.category,
        "difficulty": difficulty_for(changed),
    }

    directory = FIXTURES / spec.fixture_set / spec.defect_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "defect.json").write_text(
        json.dumps(defect, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (directory / "break.patch").write_text(break_patch, encoding="utf-8", newline="\n")
    (directory / "reference.patch").write_text(reference_patch, encoding="utf-8", newline="\n")
    (directory / "notes.md").write_text(
        f"# {spec.defect_id}\n\n"
        f"**Category:** {spec.category} · **Module:** `{spec.module}` · "
        f"**Reference fix:** {changed} changed line(s)\n\n"
        f"{spec.notes}\n\n"
        "> This file is never placed in a model prompt.\n",
        encoding="utf-8",
        newline="\n",
    )
    return defect


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="fixture_set", choices=("dev", "holdout", "all"), default="all")
    parser.add_argument(
        "--clean", action="store_true", help="remove the existing fixture directories first"
    )
    args = parser.parse_args()

    wanted = [
        spec
        for spec in SPECS
        if args.fixture_set == "all" or spec.fixture_set == args.fixture_set
    ]
    if args.clean:
        for name in {spec.fixture_set for spec in wanted}:
            shutil.rmtree(FIXTURES / name, ignore_errors=True)

    counts: dict[str, int] = {}
    for spec in wanted:
        defect = build(spec)
        counts[spec.fixture_set] = counts.get(spec.fixture_set, 0) + 1
        print(f"  {defect['defect_id']:<38} {defect['difficulty']:<7} {spec.module}")

    for name, count in sorted(counts.items()):
        print(f"{name}: {count} fixtures written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
