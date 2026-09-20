"""In-container test runner. Writes exactly one JSON document to stdout.

pytest failures are data, not runner errors: the exit code is zero whenever this
script completed its job, and non-zero only when the script itself could not run
the suite. The host decides what the results mean.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

WORK = Path("/work")
REPORT_DIR = Path("/tmp")
SUITE_TIMEOUT_SECONDS = 30
TAIL_CHARS = 4000
SCHEMA = 1


def run_pytest(arguments: list[str], report_path: Path) -> tuple[int, str, dict]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--json-report",
        f"--json-report-file={report_path}",
        *arguments,
    ]
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=WORK,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    output = completed.stdout + completed.stderr
    report: dict = {}
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
        report_path.unlink(missing_ok=True)
    report["_elapsed_ms"] = elapsed_ms
    return completed.returncode, output, report


def outcomes_of(report: dict) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for test in report.get("tests", []):
        node_id = str(test.get("nodeid", "")).replace("\\", "/")
        if node_id:
            outcomes[node_id] = str(test.get("outcome", "unknown"))
    return outcomes


def main() -> int:
    if len(sys.argv) < 2:
        json.dump(
            {"schema": SCHEMA, "runner_error": "no target test node id was given"},
            sys.stdout,
        )
        sys.stdout.write("\n")
        return 2

    target = sys.argv[1]
    result: dict = {"schema": SCHEMA, "target_test": target, "runner_error": None}

    try:
        target_code, target_output, target_report = run_pytest(
            [target], REPORT_DIR / "target.json"
        )
        target_outcomes = outcomes_of(target_report)
        result["target_test_passed"] = (
            target_code == 0 and target_outcomes.get(target, "failed") == "passed"
        )
        result["target_duration_ms"] = target_report.get("_elapsed_ms", 0)
        result["target_exit_code"] = target_code

        suite_code, suite_output, suite_report = run_pytest(
            [f"--timeout={SUITE_TIMEOUT_SECONDS}"], REPORT_DIR / "suite.json"
        )
        summary = suite_report.get("summary", {})
        outcomes = outcomes_of(suite_report)
        result["suite"] = {
            "outcomes": outcomes,
            "tests_run": int(summary.get("total", len(outcomes))),
            "passed": int(summary.get("passed", 0)),
            "failed": int(summary.get("failed", 0)),
            "errors": int(summary.get("error", 0)),
            "skipped": int(summary.get("skipped", 0)),
            "duration_ms": suite_report.get("_elapsed_ms", 0),
            "exit_code": suite_code,
        }
        result["stdout_tail"] = (target_output + "\n" + suite_output)[-TAIL_CHARS:]
    except Exception as error:  # noqa: BLE001 - reported to the host, never hidden
        result["runner_error"] = f"{type(error).__name__}: {error}"
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return 3

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
