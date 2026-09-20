import pytest
from diffstat import format_summary, largest_file, percent_added, summarise

ONE_FILE = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n context\n-old\n+new\n"

TWO_FILES = (
    "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n context\n-old\n+new\n"
    "--- a/y.py\n+++ b/y.py\n@@ -1,3 +1,4 @@\n context\n-a\n-b\n+A\n+B\n+C\n"
)


def test_summarise_counts_one_file():
    summary = summarise(ONE_FILE)
    assert summary.file_count == 1
    assert summary.added == 1
    assert summary.removed == 1


def test_summarise_records_the_path():
    assert summarise(ONE_FILE).files[0].path == "x.py"


def test_summarise_counts_several_files():
    summary = summarise(TWO_FILES)
    assert summary.file_count == 2
    assert summary.added == 4
    assert summary.removed == 3


def test_summarise_ignores_the_header_lines():
    # The +++ and --- lines must never be counted as added or removed lines.
    assert summarise(ONE_FILE).added == 1


def test_summarise_ignores_text_outside_any_hunk():
    noisy = "Here is my patch:\n" + ONE_FILE
    assert summarise(noisy).added == 1


def test_summarise_of_an_empty_diff_has_no_files():
    assert summarise("").file_count == 0


def test_summarise_handles_crlf_line_endings():
    assert summarise(ONE_FILE.replace("\n", "\r\n")).added == 1


def test_summarise_counts_several_hunks_in_one_file():
    raw = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n c\n-a\n+A\n@@ -9,2 +9,2 @@\n c\n-b\n+B\n"
    assert summarise(raw).added == 2


def test_summarise_names_a_created_file_from_the_new_path():
    raw = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+hello\n"
    assert summarise(raw).files[0].path == "new.py"


def test_churn_is_the_sum_of_both_sides():
    assert summarise(TWO_FILES).churn == 7


def test_net_is_added_minus_removed():
    assert summarise(TWO_FILES).net == 1


def test_per_file_churn():
    assert summarise(TWO_FILES).files[1].churn == 5


def test_per_file_net():
    assert summarise(TWO_FILES).files[1].net == 1


def test_percent_added_of_a_balanced_diff():
    assert percent_added(summarise(ONE_FILE)) == pytest.approx(50.0)


def test_percent_added_rounds_to_one_place():
    assert percent_added(summarise(TWO_FILES)) == pytest.approx(57.1)


def test_percent_added_honours_a_wider_precision():
    assert percent_added(summarise(TWO_FILES), places=3) == pytest.approx(57.143)


def test_percent_added_of_an_empty_diff_is_zero():
    assert percent_added(summarise("")) == pytest.approx(0.0)


def test_largest_file_is_the_one_with_most_churn():
    assert largest_file(summarise(TWO_FILES)).path == "y.py"


def test_largest_file_breaks_ties_towards_the_earlier_file():
    raw = ONE_FILE + "--- a/z.py\n+++ b/z.py\n@@ -1,2 +1,2 @@\n c\n-a\n+A\n"
    assert largest_file(summarise(raw)).path == "x.py"


def test_largest_file_of_an_empty_diff_is_none():
    assert largest_file(summarise("")) is None


def test_format_a_multi_file_summary():
    assert format_summary(summarise(TWO_FILES)) == (
        "2 files changed, 4 insertions(+), 3 deletions(-)"
    )


def test_format_uses_the_singular_for_one_file():
    assert format_summary(summarise(ONE_FILE)) == "1 file changed, 1 insertions(+), 1 deletions(-)"


def test_format_of_an_empty_diff():
    assert format_summary(summarise("")) == "0 files changed"
