from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.models import Defect, ProposedPatch
from backend.app.services.gates import (
    GATE_NAMES,
    build_context,
    rejecting_gate,
    run_gates,
    run_pure_gates,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUFF_CONFIG = PROJECT_ROOT / "ruff.toml"
MAX_DIFF_LINES = 40

CLEAN = '"""Module."""\n\n\ndef page_count(total, limit):\n    return total // limit\n'
VALID_HUNK = "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"
USES_MATH = "\n\ndef rounded(value):\n    return math.ceil(value)\n"


def with_import(module: str, extra: str = "") -> str:
    """CLEAN with a properly placed import, so only the gate under test can fire."""
    return (
        f'"""Module."""\n\nimport {module}\n\n\n'
        f"def page_count(total, limit):\n    return total // limit\n{extra}"
    )


def defect_for(allowed: tuple[str, ...] = ("paging.py",)) -> Defect:
    return Defect(
        defect_id="dev-off_by_one-001",
        fixture_set="dev",
        summary="one page too many",
        failing_test="tests/test_paging.py::test_page_count",
        allowed_paths=allowed,
        category="off_by_one",
        difficulty="easy",
    )


def patch_for(diff: str) -> ProposedPatch:
    return ProposedPatch(candidate_id="c1", unified_diff=diff)


def context_for(
    diff: str,
    patched: str | None = None,
    baseline: str = CLEAN,
    allowed: tuple[str, ...] = ("paging.py",),
    max_diff_lines: int = MAX_DIFF_LINES,
    path: str = "paging.py",
):
    return build_context(
        patch=patch_for(diff),
        defect=defect_for(allowed),
        max_diff_lines=max_diff_lines,
        baseline_files={path: baseline},
        patched_files={path: patched if patched is not None else baseline},
        ruff_config=RUFF_CONFIG,
    )


def result_for(results, gate: str):
    return next(result for result in results if result.gate == gate)


class TestGateOne_DiffParses:
    def test_a_valid_diff_passes(self) -> None:
        results = run_pure_gates(context_for(VALID_HUNK))
        assert result_for(results, "diff_parses").passed

    def test_an_unparsable_diff_is_rejected(self) -> None:
        patch = ProposedPatch.model_construct(
            candidate_id="c1", unified_diff="I suggest changing line 12.", touched_paths=(),
            changed_lines=1, round_index=1, rationale="", confidence=0.5,
        )
        context = build_context(patch, defect_for(), MAX_DIFF_LINES, {}, {}, RUFF_CONFIG)
        assert rejecting_gate(run_pure_gates(context)) == "diff_parses"


class TestGateTwo_Scope:
    def test_a_patch_inside_scope_passes(self) -> None:
        assert result_for(run_pure_gates(context_for(VALID_HUNK)), "scope").passed

    def test_a_patch_outside_scope_is_rejected(self) -> None:
        diff = "--- a/slugs.py\n+++ b/slugs.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"
        results = run_pure_gates(context_for(diff))
        assert rejecting_gate(results) == "scope"
        assert "slugs.py" in result_for(results, "scope").detail


class TestGateThree_NoTestEdits:
    def test_a_non_test_patch_passes(self) -> None:
        assert result_for(run_pure_gates(context_for(VALID_HUNK)), "no_test_edits").passed

    def test_editing_the_failing_test_is_rejected_by_this_gate_not_by_scope(self) -> None:
        """The cheating rate is the number to lead with; scope must not swallow it."""
        diff = (
            "--- a/tests/test_paging.py\n+++ b/tests/test_paging.py\n"
            "@@ -1,2 +1,2 @@\n ctx\n-    assert a == b\n+    assert a != b\n"
        )
        results = run_pure_gates(context_for(diff))
        assert rejecting_gate(results) == "no_test_edits"
        assert result_for(results, "scope").passed
        assert "not a fix" in result_for(results, "no_test_edits").detail

    def test_a_nested_test_directory_is_also_rejected(self) -> None:
        diff = "--- a/pkg/tests/test_x.py\n+++ b/pkg/tests/test_x.py\n@@ -1,2 +1,2 @@\n c\n-a\n+b\n"
        assert rejecting_gate(run_pure_gates(context_for(diff))) == "no_test_edits"

    def test_a_conftest_edit_is_rejected(self) -> None:
        diff = "--- a/conftest.py\n+++ b/conftest.py\n@@ -1,2 +1,2 @@\n c\n-a\n+b\n"
        assert rejecting_gate(run_pure_gates(context_for(diff))) == "no_test_edits"

    def test_a_non_test_file_outside_scope_still_reaches_the_scope_gate(self) -> None:
        diff = "--- a/slugs.py\n+++ b/slugs.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"
        assert rejecting_gate(run_pure_gates(context_for(diff))) == "scope"


class TestGateFour_NoNewOrDeletedFiles:
    def test_an_ordinary_edit_passes(self) -> None:
        assert result_for(
            run_pure_gates(context_for(VALID_HUNK)), "no_new_or_deleted_files"
        ).passed

    def test_a_smuggled_rename_is_rejected(self) -> None:
        diff = VALID_HUNK + (
            "diff --git a/paging.py b/pages.py\nsimilarity index 100%\n"
            "rename from paging.py\nrename to pages.py\n"
        )
        results = run_pure_gates(context_for(diff, allowed=("paging.py", "pages.py")))
        assert rejecting_gate(results) == "no_new_or_deleted_files"

    def test_a_smuggled_symlink_is_rejected(self) -> None:
        diff = VALID_HUNK + (
            "diff --git a/paging.py b/link\nnew file mode 120000\n"
            "--- /dev/null\n+++ b/link\n@@ -0,0 +1 @@\n+/etc/passwd\n"
        )
        results = run_pure_gates(context_for(diff, allowed=("paging.py", "link")))
        assert rejecting_gate(results) == "no_new_or_deleted_files"


class TestGateFive_Size:
    def test_a_small_diff_passes(self) -> None:
        assert result_for(run_pure_gates(context_for(VALID_HUNK)), "size").passed

    def test_a_diff_one_line_over_the_limit_is_rejected(self) -> None:
        pairs = 4
        body = "".join(f"-line{index}\n+LINE{index}\n" for index in range(pairs))
        diff = f"--- a/paging.py\n+++ b/paging.py\n@@ -1,{pairs} +1,{pairs} @@\n" + body
        results = run_pure_gates(context_for(diff, max_diff_lines=pairs * 2 - 1))
        assert rejecting_gate(results) == "size"

    def test_a_diff_exactly_at_the_limit_passes(self) -> None:
        pairs = 4
        body = "".join(f"-line{index}\n+LINE{index}\n" for index in range(pairs))
        diff = f"--- a/paging.py\n+++ b/paging.py\n@@ -1,{pairs} +1,{pairs} @@\n" + body
        assert result_for(
            run_pure_gates(context_for(diff, max_diff_lines=pairs * 2)), "size"
        ).passed


class TestGateSix_Syntax:
    def test_compilable_code_passes(self) -> None:
        assert result_for(run_gates(context_for(VALID_HUNK)), "syntax").passed

    def test_broken_code_is_rejected(self) -> None:
        results = run_gates(context_for(VALID_HUNK, patched="def f(:\n    pass\n"))
        assert rejecting_gate(results) == "syntax"
        assert "paging.py" in result_for(results, "syntax").detail


class TestGateSeven_Lint:
    def test_tidy_code_passes(self) -> None:
        assert result_for(run_gates(context_for(VALID_HUNK)), "lint").passed

    def test_a_newly_introduced_diagnostic_is_rejected(self) -> None:
        patched = CLEAN + "\n\ndef broken():\n    unused = compute_something()\n    return 1\n"
        results = run_gates(context_for(VALID_HUNK, patched=patched))
        assert rejecting_gate(results) == "lint"

    def test_a_pre_existing_diagnostic_is_not_held_against_the_fix(self) -> None:
        """The broken baseline may already be untidy; only new problems count."""
        untidy = '"""M."""\n\n\ndef tally(rows, counts={}):\n    return counts\n'
        patched = '"""M."""\n\n\ndef tally(rows, counts={}):\n    return dict(counts)\n'
        results = run_gates(context_for(VALID_HUNK, patched=patched, baseline=untidy))
        assert result_for(results, "lint").passed, result_for(results, "lint").detail


class TestGateEight_NoNewImports:
    def test_no_new_import_passes(self) -> None:
        assert result_for(run_gates(context_for(VALID_HUNK)), "no_new_imports").passed

    def test_a_new_import_is_rejected(self) -> None:
        results = run_gates(context_for(VALID_HUNK, patched=with_import("math", USES_MATH)))
        assert rejecting_gate(results) == "no_new_imports"
        assert "math" in result_for(results, "no_new_imports").detail

    def test_an_import_already_in_the_baseline_is_allowed(self) -> None:
        baseline = with_import("math", "")
        patched = with_import("math", USES_MATH)
        assert result_for(
            run_gates(context_for(VALID_HUNK, patched=patched, baseline=baseline)),
            "no_new_imports",
        ).passed


class TestGateNine_NoDangerousCalls:
    def test_ordinary_code_passes(self) -> None:
        assert result_for(run_gates(context_for(VALID_HUNK)), "no_dangerous_calls").passed

    @pytest.mark.parametrize(
        ("module", "call"),
        [
            (None, "eval('1 + 1')"),
            (None, "exec('x = 1')"),
            (None, "__import__('os')"),
            ("os", "os.system('rm -rf /')"),
            ("subprocess", "subprocess.run(['ls'])"),
            ("socket", "socket.create_connection(('example.com', 80))"),
            ("requests", "requests.get('http://example.com')"),
            ("shutil", "shutil.rmtree('/')"),
            ("pickle", "pickle.loads(b'')"),
        ],
    )
    def test_dangerous_calls_are_rejected(self, module: str | None, call: str) -> None:
        """The import is already in the baseline, so only the call itself is new."""
        baseline = CLEAN
        if module:
            baseline = f"import {module}\n{CLEAN}\n\ndef already_here():\n    return {module}\n"
        patched = baseline + f"\n\ndef g():\n    return {call}\n"
        results = run_gates(context_for(VALID_HUNK, patched=patched, baseline=baseline))
        assert rejecting_gate(results) == "no_dangerous_calls", result_for(
            results, rejecting_gate(results) or "lint"
        ).detail

    def test_opening_a_file_for_writing_is_flagged(self) -> None:
        from backend.app.services.gates import gate_no_dangerous_calls

        patched = CLEAN + "\n\ndef g():\n    return open('out.txt', 'w')\n"
        result = gate_no_dangerous_calls(context_for(VALID_HUNK, patched=patched))
        assert not result.passed
        assert "open" in result.detail

    def test_opening_a_file_for_reading_is_not_flagged(self) -> None:
        from backend.app.services.gates import gate_no_dangerous_calls

        patched = CLEAN + "\n\ndef g():\n    return open('in.txt', 'r')\n"
        assert gate_no_dangerous_calls(context_for(VALID_HUNK, patched=patched)).passed

    def test_writing_through_a_path_object_is_flagged(self) -> None:
        from backend.app.services.gates import gate_no_dangerous_calls

        patched = CLEAN + "\n\ndef g(target):\n    return target.write_text('x')\n"
        assert not gate_no_dangerous_calls(context_for(VALID_HUNK, patched=patched)).passed

    def test_ordinary_method_calls_are_not_flagged(self) -> None:
        from backend.app.services.gates import gate_no_dangerous_calls

        patched = CLEAN + "\n\ndef g(rows):\n    return sorted(rows.items())\n"
        assert gate_no_dangerous_calls(context_for(VALID_HUNK, patched=patched)).passed

    def test_a_call_already_in_the_baseline_is_not_newly_introduced(self) -> None:
        baseline = CLEAN + "\n\ndef g():\n    return eval('1')\n"
        patched = CLEAN + "\n\ndef g():\n    return eval('2')\n"
        assert result_for(
            run_gates(context_for(VALID_HUNK, patched=patched, baseline=baseline)),
            "no_dangerous_calls",
        ).passed


class TestOrdering:
    def test_all_nine_gates_run_for_a_clean_candidate(self) -> None:
        results = run_gates(context_for(VALID_HUNK))
        assert [result.gate for result in results] == list(GATE_NAMES)
        assert all(result.passed for result in results)

    def test_gate_order_short_circuits(self) -> None:
        """A scope violation must never reach the lint gate."""
        diff = "--- a/slugs.py\n+++ b/slugs.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"
        results = run_gates(context_for(diff, patched="def f(:\n"))
        names = [result.gate for result in results]
        assert names == ["diff_parses", "scope"]
        assert "lint" not in names
        assert "syntax" not in names

    def test_the_first_failure_is_the_rejecting_gate(self) -> None:
        diff = (
            "--- a/tests/test_paging.py\n+++ b/tests/test_paging.py\n"
            "@@ -1,2 +1,2 @@\n ctx\n-a\n+b\n"
        )
        results = run_gates(context_for(diff))
        assert rejecting_gate(results) == "no_test_edits"

    def test_no_rejecting_gate_when_everything_passes(self) -> None:
        assert rejecting_gate(run_gates(context_for(VALID_HUNK))) is None

    def test_pure_gates_need_no_file_contents(self) -> None:
        context = build_context(patch_for(VALID_HUNK), defect_for(), MAX_DIFF_LINES, {}, {})
        results = run_pure_gates(context)
        assert len(results) == 5
        assert all(result.passed for result in results)
