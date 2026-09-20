from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from backend.app.models import Defect, ProposedPatch
from backend.app.services.fixtures import get_fixture
from backend.app.services.workspace import (
    PatchFailed,
    PatchRefused,
    apply_candidate,
    build_broken_tree,
    make_candidate_workspace,
    refusals,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TARGET_APP = PROJECT_ROOT / "target_app"
MAX_DIFF_LINES = 40
VALID_HUNK = "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"


@pytest.fixture
def fixture():
    return get_fixture("dev-off_by_one-001")


@pytest.fixture
def defect(fixture) -> Defect:
    return fixture.defect


@pytest.fixture
def broken_tree(fixture, tmp_path) -> Path:
    return build_broken_tree(TARGET_APP, fixture.break_patch, tmp_path / "baseline" / "workspace")


def diff_against(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def patch_for(diff: str, candidate_id: str = "c1") -> ProposedPatch:
    return ProposedPatch(candidate_id=candidate_id, unified_diff=diff)


def working_fix(broken_tree: Path) -> ProposedPatch:
    """The real repair for dev-off_by_one-001, generated against the broken file."""
    path = "paging.py"
    before = (broken_tree / path).read_text(encoding="utf-8")
    after = before.replace("(total + limit) // limit", "(total + limit - 1) // limit")
    assert after != before
    return patch_for(diff_against(path, before, after))


class TestRefusals:
    def test_a_legitimate_patch_is_not_refused(self, broken_tree, defect) -> None:
        assert refusals(working_fix(broken_tree), defect.allowed_paths, MAX_DIFF_LINES) == []

    def test_path_traversal_refused(self, defect) -> None:
        diff = "--- a/../../../etc/hosts\n+++ b/../../../etc/hosts\n@@ -1,2 +1,2 @@\n x\n-a\n+b\n"
        reasons = refusals(patch_for(diff), defect.allowed_paths, MAX_DIFF_LINES)
        assert any("parent traversal" in reason for reason in reasons)

    def test_absolute_path_refused(self, defect) -> None:
        diff = "--- /etc/passwd\n+++ /etc/passwd\n@@ -1,2 +1,2 @@\n x\n-a\n+b\n"
        reasons = refusals(patch_for(diff), defect.allowed_paths, MAX_DIFF_LINES)
        assert any("absolute path" in reason for reason in reasons)

    def test_symlink_creation_refused(self, defect) -> None:
        diff = (
            "diff --git a/link b/link\nnew file mode 120000\n"
            "--- /dev/null\n+++ b/link\n@@ -0,0 +1 @@\n+/etc/passwd\n"
        )
        reasons = refusals(patch_for(diff), defect.allowed_paths, MAX_DIFF_LINES)
        assert "creates a symlink" in reasons

    def test_new_file_refused(self, defect) -> None:
        diff = (
            "diff --git a/paging.py b/evil.py\nnew file mode 100644\n"
            "--- /dev/null\n+++ b/evil.py\n@@ -0,0 +1 @@\n+import os\n"
        )
        reasons = refusals(patch_for(diff), defect.allowed_paths, MAX_DIFF_LINES)
        assert "creates a file" in reasons

    def test_file_deletion_refused(self, defect) -> None:
        diff = (
            "diff --git a/paging.py b/paging.py\ndeleted file mode 100644\n"
            "--- a/paging.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-import x\n"
        )
        reasons = refusals(patch_for(diff), defect.allowed_paths, MAX_DIFF_LINES)
        assert "deletes a file" in reasons

    def test_a_structural_change_alone_cannot_even_be_constructed(self) -> None:
        """A rename with no hunks changes no lines, so it is not a patch at all."""
        diff = (
            "diff --git a/paging.py b/pages.py\nsimilarity index 100%\n"
            "rename from paging.py\nrename to pages.py\n"
        )
        with pytest.raises(Exception, match="changes nothing"):
            patch_for(diff)

    def test_rename_smuggled_alongside_a_real_edit_refused(self, defect) -> None:
        diff = VALID_HUNK + (
            "diff --git a/slugs.py b/renamed.py\nsimilarity index 100%\n"
            "rename from slugs.py\nrename to renamed.py\n"
        )
        reasons = refusals(patch_for(diff), defect.allowed_paths, MAX_DIFF_LINES)
        assert "renames a file" in reasons

    def test_mode_change_smuggled_alongside_a_real_edit_refused(self, defect) -> None:
        diff = VALID_HUNK + (
            "diff --git a/slugs.py b/slugs.py\nold mode 100644\nnew mode 100755\n"
        )
        reasons = refusals(patch_for(diff), defect.allowed_paths, MAX_DIFF_LINES)
        assert "changes a file mode" in reasons

    def test_binary_hunk_smuggled_alongside_a_real_edit_refused(self, defect) -> None:
        diff = VALID_HUNK + (
            "diff --git a/logo.png b/logo.png\nindex 1..2 100644\nGIT binary patch\n"
        )
        reasons = refusals(patch_for(diff), defect.allowed_paths, MAX_DIFF_LINES)
        assert "contains a binary hunk" in reasons

    def test_test_file_edit_refused(self, defect) -> None:
        diff = (
            "--- a/tests/test_paging.py\n+++ b/tests/test_paging.py\n"
            "@@ -1,2 +1,2 @@\n def test_x():\n-    assert a == b\n+    assert a != b\n"
        )
        reasons = refusals(patch_for(diff), defect.allowed_paths, MAX_DIFF_LINES)
        assert any("test file" in reason for reason in reasons)

    def test_out_of_scope_edit_refused(self, defect) -> None:
        diff = "--- a/slugs.py\n+++ b/slugs.py\n@@ -1,2 +1,2 @@\n x\n-a\n+b\n"
        reasons = refusals(patch_for(diff), defect.allowed_paths, MAX_DIFF_LINES)
        assert any("outside allowed_paths" in reason for reason in reasons)

    def test_oversize_diff_refused_at_one_over_the_limit(self, defect) -> None:
        limit = 6
        body = "".join(f"-line{index}\n+LINE{index}\n" for index in range(limit // 2 + 1))
        header = f"--- a/paging.py\n+++ b/paging.py\n@@ -1,{limit // 2 + 1} +1,{limit // 2 + 1} @@\n"
        reasons = refusals(patch_for(header + body), defect.allowed_paths, limit)
        assert any("above the limit" in reason for reason in reasons)

    def test_a_diff_exactly_at_the_limit_is_allowed(self, broken_tree, defect) -> None:
        patch = working_fix(broken_tree)
        assert refusals(patch, defect.allowed_paths, patch.changed_lines) == []

    def test_unparsable_diff_refused(self, defect) -> None:
        patch = ProposedPatch.model_construct(
            candidate_id="c1", unified_diff="not a diff at all", touched_paths=(), changed_lines=1
        )
        reasons = refusals(patch, defect.allowed_paths, MAX_DIFF_LINES)
        assert any("does not parse" in reason for reason in reasons)


class TestApplication:
    def test_a_legitimate_patch_applies(self, broken_tree, defect, tmp_path) -> None:
        workspace = make_candidate_workspace(broken_tree, tmp_path / "candidates" / "c1" / "ws")
        result = apply_candidate(workspace, working_fix(broken_tree), defect, MAX_DIFF_LINES)
        assert result.applied_paths == ("paging.py",)
        assert "(total + limit - 1)" in (workspace / "paging.py").read_text(encoding="utf-8")

    def test_artifacts_are_written(self, broken_tree, defect, tmp_path) -> None:
        workspace = make_candidate_workspace(broken_tree, tmp_path / "c" / "ws")
        artifacts = tmp_path / "c"
        apply_candidate(workspace, working_fix(broken_tree), defect, MAX_DIFF_LINES, artifacts)
        assert (artifacts / "applied.patch").is_file()
        assert (artifacts / "apply.log").is_file()

    def test_a_refusal_is_logged_and_nothing_is_written(self, broken_tree, defect, tmp_path) -> None:
        workspace = make_candidate_workspace(broken_tree, tmp_path / "c" / "ws")
        artifacts = tmp_path / "c"
        diff = "--- a/slugs.py\n+++ b/slugs.py\n@@ -1,2 +1,2 @@\n x\n-a\n+b\n"
        with pytest.raises(PatchRefused):
            apply_candidate(workspace, patch_for(diff), defect, MAX_DIFF_LINES, artifacts)
        assert "REFUSED" in (artifacts / "apply.log").read_text(encoding="utf-8")
        assert not (artifacts / "applied.patch").exists()

    def test_traversal_never_writes_outside_the_workspace(self, broken_tree, defect, tmp_path) -> None:
        workspace = make_candidate_workspace(broken_tree, tmp_path / "c" / "ws")
        victim = tmp_path / "victim.txt"
        victim.write_text("untouched", encoding="utf-8")
        diff = (
            "--- a/../../victim.txt\n+++ b/../../victim.txt\n"
            "@@ -1,1 +1,1 @@\n-untouched\n+owned\n"
        )
        with pytest.raises(PatchRefused):
            apply_candidate(workspace, patch_for(diff), defect, MAX_DIFF_LINES)
        assert victim.read_text(encoding="utf-8") == "untouched"

    def test_a_patch_that_does_not_apply_fails_cleanly(self, broken_tree, defect, tmp_path) -> None:
        workspace = make_candidate_workspace(broken_tree, tmp_path / "c" / "ws")
        diff = (
            "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n"
            " this context does not exist\n-neither does this\n+nor this\n"
        )
        with pytest.raises(PatchFailed, match="git apply"):
            apply_candidate(workspace, patch_for(diff), defect, MAX_DIFF_LINES)

    def test_the_patch_file_is_not_left_behind(self, broken_tree, defect, tmp_path) -> None:
        workspace = make_candidate_workspace(broken_tree, tmp_path / "c" / "ws")
        apply_candidate(workspace, working_fix(broken_tree), defect, MAX_DIFF_LINES)
        assert not (workspace / ".fixproof-candidate.patch").exists()

    def test_applied_paths_match_declared(self, broken_tree, defect, tmp_path) -> None:
        """A patch whose declared paths and applied paths disagree is an error."""
        workspace = make_candidate_workspace(broken_tree, tmp_path / "c" / "ws")
        patch = working_fix(broken_tree)
        lying = ProposedPatch.model_construct(
            candidate_id="liar",
            round_index=1,
            rationale="",
            unified_diff=patch.unified_diff,
            touched_paths=("paging.py", "slugs.py"),
            changed_lines=patch.changed_lines,
            confidence=0.5,
        )
        with pytest.raises(PatchFailed, match="does not match the diff"):
            apply_candidate(workspace, lying, defect, MAX_DIFF_LINES)

    def test_workspace_isolated(self, broken_tree, defect, tmp_path) -> None:
        first = make_candidate_workspace(broken_tree, tmp_path / "a" / "ws")
        second = make_candidate_workspace(broken_tree, tmp_path / "b" / "ws")
        apply_candidate(first, working_fix(broken_tree), defect, MAX_DIFF_LINES)
        assert "(total + limit - 1)" in (first / "paging.py").read_text(encoding="utf-8")
        assert "(total + limit - 1)" not in (second / "paging.py").read_text(encoding="utf-8")

    def test_the_broken_tree_itself_is_never_modified(self, broken_tree, defect, tmp_path) -> None:
        before = (broken_tree / "paging.py").read_text(encoding="utf-8")
        workspace = make_candidate_workspace(broken_tree, tmp_path / "c" / "ws")
        apply_candidate(workspace, working_fix(broken_tree), defect, MAX_DIFF_LINES)
        assert (broken_tree / "paging.py").read_text(encoding="utf-8") == before

    def test_the_broken_tree_really_is_broken(self, broken_tree) -> None:
        assert "(total + limit) // limit" in (broken_tree / "paging.py").read_text(encoding="utf-8")

    def test_no_git_directory_is_copied_into_a_candidate(self, broken_tree, tmp_path) -> None:
        make_candidate_workspace(broken_tree, tmp_path / "c" / "ws")
        assert not (broken_tree / ".git").exists()

    def test_pycache_is_not_copied(self, broken_tree, tmp_path) -> None:
        (broken_tree / "__pycache__").mkdir(exist_ok=True)
        (broken_tree / "__pycache__" / "junk.pyc").write_bytes(b"x")
        workspace = make_candidate_workspace(broken_tree, tmp_path / "c" / "ws")
        assert not (workspace / "__pycache__").exists()
