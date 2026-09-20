from __future__ import annotations

import pytest

from backend.app.diffs import (
    DiffParseError,
    normalise_for_dedupe,
    normalise_path,
    parse_unified_diff,
    path_violations,
)

SIMPLE = "--- a/paging.py\n+++ b/paging.py\n@@ -3,2 +3,2 @@\n def page(rows):\n-    return rows[:n + 1]\n+    return rows[:n]\n"


class TestParsing:
    def test_simple_diff(self) -> None:
        parsed = parse_unified_diff(SIMPLE)
        assert parsed.touched_paths == ("paging.py",)
        assert parsed.changed_lines == 2
        assert parsed.files[0].hunk_count == 1

    def test_git_style_headers(self) -> None:
        raw = (
            "diff --git a/paging.py b/paging.py\n"
            "index 1234567..89abcde 100644\n"
            "--- a/paging.py\n"
            "+++ b/paging.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        assert parse_unified_diff(raw).touched_paths == ("paging.py",)

    def test_multiple_files(self) -> None:
        raw = SIMPLE + "--- a/slugs.py\n+++ b/slugs.py\n@@ -1 +1 @@\n-a\n+b\n"
        parsed = parse_unified_diff(raw)
        assert parsed.touched_paths == ("paging.py", "slugs.py")
        assert parsed.changed_lines == 4

    def test_multiple_hunks_in_one_file(self) -> None:
        raw = (
            "--- a/x.py\n+++ b/x.py\n"
            "@@ -1,2 +1,2 @@\n a\n-b\n+B\n"
            "@@ -10,2 +10,2 @@\n c\n-d\n+D\n"
        )
        parsed = parse_unified_diff(raw)
        assert parsed.files[0].hunk_count == 2
        assert parsed.changed_lines == 4

    def test_zero_context_hunk(self) -> None:
        raw = "--- a/x.py\n+++ b/x.py\n@@ -5,0 +6 @@\n+inserted\n"
        assert parse_unified_diff(raw).changed_lines == 1

    def test_no_newline_marker_tolerated(self) -> None:
        raw = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n\\ No newline at end of file\n+b\n"
        assert parse_unified_diff(raw).changed_lines == 2

    def test_blank_context_line_counts_as_context(self) -> None:
        raw = "--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,3 @@\n a\n\n-b\n+B\n"
        assert parse_unified_diff(raw).changed_lines == 2

    def test_crlf_input(self) -> None:
        assert parse_unified_diff(SIMPLE.replace("\n", "\r\n")).touched_paths == ("paging.py",)

    def test_empty_is_rejected(self) -> None:
        with pytest.raises(DiffParseError, match="empty"):
            parse_unified_diff("   \n  ")

    def test_prose_is_rejected(self) -> None:
        with pytest.raises(DiffParseError):
            parse_unified_diff("Change line 12 so that it adds one fewer row.")

    def test_malformed_hunk_header_rejected(self) -> None:
        raw = "--- a/x.py\n+++ b/x.py\n@@ nonsense @@\n-a\n+b\n"
        with pytest.raises(DiffParseError, match="malformed hunk header"):
            parse_unified_diff(raw)

    def test_hunk_longer_than_declared_rejected(self) -> None:
        raw = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n+c\n"
        with pytest.raises(DiffParseError):
            parse_unified_diff(raw)

    def test_truncated_hunk_rejected(self) -> None:
        raw = "--- a/x.py\n+++ b/x.py\n@@ -1,5 +1,5 @@\n a\n"
        with pytest.raises(DiffParseError, match="middle of a hunk"):
            parse_unified_diff(raw)

    def test_miscounted_hunk_cannot_smuggle_a_second_file(self) -> None:
        """An over-long hunk header must not swallow the next file's headers."""
        raw = (
            "--- a/paging.py\n+++ b/paging.py\n"
            "@@ -3,3 +3,3 @@\n def page(rows):\n-    old\n+    new\n"
            "--- a/secret.py\n+++ b/secret.py\n@@ -1 +1 @@\n-a\n+b\n"
        )
        with pytest.raises(DiffParseError, match="file header appears inside a hunk"):
            parse_unified_diff(raw)

    def test_headers_without_hunks_rejected(self) -> None:
        with pytest.raises(DiffParseError, match="no hunks"):
            parse_unified_diff("--- a/x.py\n+++ b/x.py\n")


class TestStructuralFlags:
    def test_new_file_detected(self) -> None:
        raw = (
            "diff --git a/new.py b/new.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+print('hi')\n"
        )
        parsed = parse_unified_diff(raw)
        assert parsed.creates_files
        assert parsed.touched_paths == ("new.py",)

    def test_deleted_file_detected(self) -> None:
        raw = (
            "diff --git a/gone.py b/gone.py\n"
            "deleted file mode 100644\n"
            "--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-print('bye')\n"
        )
        assert parse_unified_diff(raw).deletes_files

    def test_rename_detected(self) -> None:
        raw = (
            "diff --git a/old.py b/new.py\n"
            "similarity index 100%\n"
            "rename from old.py\nrename to new.py\n"
        )
        assert parse_unified_diff(raw).renames_files

    def test_mode_change_detected(self) -> None:
        raw = "diff --git a/x.py b/x.py\nold mode 100644\nnew mode 100755\n"
        assert parse_unified_diff(raw).changes_modes

    def test_symlink_detected(self) -> None:
        raw = (
            "diff --git a/link b/link\n"
            "new file mode 120000\n"
            "--- /dev/null\n+++ b/link\n@@ -0,0 +1 @@\n+/etc/passwd\n"
        )
        assert parse_unified_diff(raw).has_symlink

    def test_binary_detected(self) -> None:
        raw = "diff --git a/x.png b/x.png\nindex 1..2 100644\nGIT binary patch\n"
        assert parse_unified_diff(raw).has_binary


class TestPaths:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("a/paging.py", "paging.py"),
            ("b/paging.py", "paging.py"),
            ("a/paging.py\t2026-09-20 10:00:00", "paging.py"),
            ("/dev/null", ""),
            ("a/sub\\dir\\x.py", "sub/dir/x.py"),
        ],
    )
    def test_normalise(self, raw: str, expected: str) -> None:
        assert normalise_path(raw) == expected

    @pytest.mark.parametrize(
        "path",
        ["/etc/passwd", "C:/Windows/x.py", "..\\..\\x.py", "../secret", "tests/test_x.py"],
    )
    def test_unsafe_paths_flagged(self, path: str) -> None:
        assert path_violations(normalise_path(path))

    @pytest.mark.parametrize("path", ["paging.py", "pkg/sub/mod.py"])
    def test_safe_paths_not_flagged(self, path: str) -> None:
        assert path_violations(path) == []


class TestDedupeNormalisation:
    def test_context_differences_collapse(self) -> None:
        wide = "--- a/x.py\n+++ b/x.py\n@@ -1,5 +1,5 @@\n a\n b\n-c\n+C\n d\n e\n"
        narrow = "--- a/x.py\n+++ b/x.py\n@@ -3,1 +3,1 @@\n-c\n+C\n"
        assert normalise_for_dedupe(wide) == normalise_for_dedupe(narrow)

    def test_line_number_differences_collapse(self) -> None:
        here = "--- a/x.py\n+++ b/x.py\n@@ -10 +10 @@\n-c\n+C\n"
        there = "--- a/x.py\n+++ b/x.py\n@@ -99 +99 @@\n-c\n+C\n"
        assert normalise_for_dedupe(here) == normalise_for_dedupe(there)

    def test_genuinely_different_patches_do_not_collapse(self) -> None:
        one = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-c\n+C\n"
        two = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-c\n+D\n"
        assert normalise_for_dedupe(one) != normalise_for_dedupe(two)

    def test_trailing_whitespace_ignored(self) -> None:
        clean = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-c\n+C\n"
        spaced = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-c   \n+C  \n"
        assert normalise_for_dedupe(clean) == normalise_for_dedupe(spaced)
