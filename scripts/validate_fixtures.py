"""Prove every fixture behaves the way its defect.json claims.

For each fixture, in a throwaway workspace:

1. Copy target_app and confirm the suite is green.
2. Apply break.patch and confirm the named failing test now fails and that no
   other test fails.
3. Apply reference.patch and confirm the suite is green again.
4. Confirm both patches touch only `allowed_paths`.
5. Confirm defect.json gives nothing away from reference.patch.

An unvalidated fixture set produces meaningless metrics for the rest of the
project, so this exits non-zero on the first fixture that cannot be proven.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.diffs import parse_unified_diff  # noqa: E402
from backend.app.models import Defect  # noqa: E402

TARGET_APP = PROJECT_ROOT / "target_app"
FIXTURES = PROJECT_ROOT / "fixtures"
IGNORED = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git", "*.pyc")
MIN_LEAK_PHRASE = 12


@dataclass
class Report:
    defect_id: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


#: `-B` is load-bearing, not tidiness.
#:
#: Python invalidates a .pyc on the source's (mtime, size). Two of these
#: fixtures substitute a single character for another of the same width
#: (`places: int = 1` -> `0`, and `>` -> `<`), so break.patch and
#: reference.patch produce files of identical size. When both `git apply`
#: calls land inside one filesystem timestamp tick, the stale bytecode
#: compiled from the *broken* source is reused and the fixture is reported
#: as invalid. The verifier image already sets PYTHONDONTWRITEBYTECODE=1;
#: this makes the local validator agree with it.
NO_BYTECODE = ("-B",)


def run_pytest(workspace: Path, node_id: str | None = None) -> tuple[int, str]:
    command = [sys.executable, *NO_BYTECODE, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if node_id:
        command.append(node_id)
    completed = subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return completed.returncode, completed.stdout + completed.stderr


def failing_node_ids(workspace: Path) -> tuple[int, list[str], str]:
    """Run the whole suite and return (exit code, failing node ids, output)."""
    completed = subprocess.run(
        [
            sys.executable, *NO_BYTECODE, "-m", "pytest",
            "-q", "--no-header", "-rf", "-p", "no:cacheprovider",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = completed.stdout + completed.stderr
    failures: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(("FAILED ", "ERROR ")):
            node = stripped.split(" ", 1)[1].split(" - ", 1)[0].strip()
            failures.append(node.replace("\\", "/"))
    return completed.returncode, failures, output


def apply_patch(workspace: Path, patch: Path) -> tuple[bool, str]:
    completed = subprocess.run(
        ["git", "apply", "--unidiff-zero", "--whitespace=nowarn", str(patch)],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return completed.returncode == 0, completed.stdout + completed.stderr


def patch_content_lines(patch_text: str) -> list[str]:
    lines = []
    for line in patch_text.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line[:1] in {"+", "-"}:
            lines.append(line[1:].strip())
    return lines


def validate(directory: Path) -> Report:
    report = Report(defect_id=directory.name)

    for required in ("defect.json", "break.patch", "reference.patch", "notes.md"):
        if not (directory / required).is_file():
            report.problems.append(f"missing {required}")
    if report.problems:
        return report

    raw = json.loads((directory / "defect.json").read_text(encoding="utf-8"))
    try:
        defect = Defect(**raw)
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        report.problems.append(f"defect.json does not validate: {error}")
        return report

    if defect.defect_id != directory.name:
        report.problems.append(f"defect_id {defect.defect_id!r} does not match its directory")
    if defect.fixture_set != directory.parent.name:
        report.problems.append(f"fixture_set {defect.fixture_set!r} does not match its directory")

    break_text = (directory / "break.patch").read_text(encoding="utf-8")
    reference_text = (directory / "reference.patch").read_text(encoding="utf-8")
    allowed = set(defect.allowed_paths)

    # 4. Both patches stay inside the declared scope.
    for name, text in (("break.patch", break_text), ("reference.patch", reference_text)):
        try:
            parsed = parse_unified_diff(text)
        except Exception as error:  # noqa: BLE001 - reported, not swallowed
            report.problems.append(f"{name} does not parse: {error}")
            continue
        outside = sorted(set(parsed.touched_paths) - allowed)
        if outside:
            report.problems.append(f"{name} touches paths outside allowed_paths: {outside}")

    # 5. The defect description must not contain the answer.
    described = json.dumps(raw, ensure_ascii=False).lower()
    for line in patch_content_lines(reference_text):
        if len(line) >= MIN_LEAK_PHRASE and line.lower() in described:
            report.problems.append(f"defect.json leaks a line of the reference fix: {line!r}")

    with tempfile.TemporaryDirectory(prefix="fixproof-validate-") as raw_temp:
        workspace = Path(raw_temp) / "work"
        shutil.copytree(TARGET_APP, workspace, ignore=IGNORED)

        # 1. The clean suite is green.
        code, failures, output = failing_node_ids(workspace)
        if code != 0:
            report.problems.append(
                f"the clean target suite is not green: {failures or output[-400:]}"
            )
            return report

        # 2. break.patch fails exactly the named test.
        applied, message = apply_patch(workspace, directory / "break.patch")
        if not applied:
            report.problems.append(f"break.patch does not apply: {message.strip()[:400]}")
            return report

        code, failures, output = failing_node_ids(workspace)
        if code == 0:
            report.problems.append("break.patch does not break anything")
        elif defect.failing_test not in failures:
            report.problems.append(
                f"break.patch does not fail {defect.failing_test}; it failed {failures}"
            )
        collateral = [node for node in failures if node != defect.failing_test]
        if collateral:
            report.problems.append(f"break.patch also fails other tests: {collateral}")

        # 3. reference.patch restores a green suite.
        applied, message = apply_patch(workspace, directory / "reference.patch")
        if not applied:
            report.problems.append(f"reference.patch does not apply: {message.strip()[:400]}")
            return report

        code, failures, output = failing_node_ids(workspace)
        if code != 0:
            report.problems.append(f"reference.patch does not restore a green suite: {failures}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="fixture_set", choices=("dev", "holdout"), required=True)
    parser.add_argument("--only", help="validate a single defect id")
    parser.add_argument("--expect", type=int, default=12, help="required fixture count")
    args = parser.parse_args()

    root = FIXTURES / args.fixture_set
    if not root.is_dir():
        print(f"no such fixture set: {root}")
        return 1

    directories = sorted(path for path in root.iterdir() if path.is_dir())
    if args.only:
        directories = [path for path in directories if path.name == args.only]

    reports = [validate(directory) for directory in directories]
    for report in reports:
        marker = "ok  " if report.ok else "FAIL"
        print(f"{marker} {report.defect_id}")
        for problem in report.problems:
            print(f"       - {problem}")

    valid = sum(1 for report in reports if report.ok)
    categories = set()
    for directory in directories:
        with contextlib.suppress(Exception):
            categories.add(json.loads((directory / "defect.json").read_text())["category"])

    print(f"\n{valid}/{len(reports)} valid in {args.fixture_set}; {len(categories)} categories")

    failed = len(reports) - valid
    if failed:
        return 1
    if not args.only and len(reports) != args.expect:
        print(f"expected {args.expect} fixtures, found {len(reports)}")
        return 1
    if not args.only and len(categories) != args.expect:
        print(f"expected {args.expect} distinct categories, found {len(categories)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
