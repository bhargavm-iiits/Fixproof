"""Verifier tests.

Everything marked `docker` needs a reachable engine and the built image:

    docker build -f docker/verifier.Dockerfile -t fixproof-verifier:1 .
    python -m pytest verifier/tests -q -m docker

After the run, `docker ps -a --filter name=fixproof-` must print nothing.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.models import ProposedPatch
from backend.app.services.fixtures import get_fixture
from backend.app.services.verifier import (
    Verifier,
    container_name,
    docker_reachable,
    image_present,
    leaked_containers,
    leaked_volumes,
    parse_runner_output,
)
from backend.app.services.workspace import (
    apply_candidate,
    build_broken_tree,
    make_candidate_workspace,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGET_APP = PROJECT_ROOT / "target_app"
DEFECT_ID = "dev-off_by_one-001"
BROKEN = "(total + limit) // limit"
FIXED = "(total + limit - 1) // limit"


def settings_for(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def diff_for(path: str, before: str, after: str) -> ProposedPatch:
    text = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    return ProposedPatch(candidate_id="c1", unified_diff=text)


@pytest.fixture(scope="module")
def fixture():
    return get_fixture(DEFECT_ID)


@pytest.fixture
def broken_tree(fixture, tmp_path) -> Path:
    return build_broken_tree(TARGET_APP, fixture.break_patch, tmp_path / "baseline" / "workspace")


@pytest.fixture
def verifier() -> Verifier:
    return Verifier(settings_for(verifier_timeout_seconds=180))


def patched_workspace(broken_tree: Path, destination: Path, defect, transform) -> Path:
    workspace = make_candidate_workspace(broken_tree, destination)
    before = (broken_tree / "paging.py").read_text(encoding="utf-8")
    after = transform(before)
    assert after != before, "the test's own patch must actually change something"
    apply_candidate(workspace, diff_for("paging.py", before, after), defect, max_diff_lines=200)
    return workspace


class TestResultParsing:
    """No Docker needed: the runner's JSON must map onto the domain model exactly."""

    def payload(self, **overrides) -> str:
        document = {
            "schema": 1,
            "target_test": "tests/test_paging.py::test_a",
            "target_test_passed": True,
            "target_duration_ms": 100,
            "suite": {
                "outcomes": {
                    "tests/test_paging.py::test_a": "passed",
                    "tests/test_paging.py::test_b": "failed",
                    "tests/test_slugs.py::test_c": "passed",
                },
                "tests_run": 3,
                "passed": 2,
                "failed": 1,
                "duration_ms": 400,
                "exit_code": 1,
            },
            "stdout_tail": "1 failed, 2 passed",
            "runner_error": None,
        }
        document.update(overrides)
        return json.dumps(document)

    def test_outcomes_are_split_into_passing_and_failing(self) -> None:
        output = parse_runner_output(self.payload())
        assert output.passing == {
            "tests/test_paging.py::test_a",
            "tests/test_slugs.py::test_c",
        }
        assert output.failing == {"tests/test_paging.py::test_b"}

    def test_durations_are_summed_across_both_runs(self) -> None:
        assert parse_runner_output(self.payload()).duration_ms == 500

    def test_the_target_result_is_carried(self) -> None:
        assert parse_runner_output(self.payload()).target_test_passed is True
        flipped = parse_runner_output(self.payload(target_test_passed=False))
        assert flipped.target_test_passed is False

    def test_noise_before_the_json_is_ignored(self) -> None:
        output = parse_runner_output("warning: something\n" + self.payload())
        assert output.tests_run == 3

    def test_empty_output_is_a_runner_error(self) -> None:
        assert "no output" in (parse_runner_output("   ").runner_error or "")

    def test_non_json_output_is_a_runner_error(self) -> None:
        assert parse_runner_output("Traceback (most recent call last)").runner_error

    def test_a_reported_runner_error_is_carried(self) -> None:
        output = parse_runner_output(self.payload(runner_error="ImportError: no pytest"))
        assert output.runner_error == "ImportError: no pytest"

    def test_container_names_are_docker_safe(self) -> None:
        name = container_name("run/with:bad chars", "cand#1")
        assert name.startswith("fixproof-")
        assert all(character.isalnum() or character in "_.-" for character in name)

    def test_container_names_are_bounded(self) -> None:
        assert len(container_name("r" * 300, "c" * 300)) <= 120


@pytest.mark.docker
class TestAgainstRealContainers:
    def test_docker_is_reachable_and_the_image_exists(self) -> None:
        assert docker_reachable(), "start Docker Desktop"
        assert image_present("fixproof-verifier:1"), "build the verifier image"

    def test_baseline_reports_the_seeded_failure(self, verifier, broken_tree, fixture) -> None:
        output, result = verifier.baseline(
            broken_tree, fixture.defect.failing_test, run_id="t-baseline"
        )
        assert result.target_test_passed is False
        assert fixture.defect.failing_test in output.failing
        assert result.tests_run > 300
        assert len(output.failing) == 1, "the fixture must break exactly one test"

    def test_reference_patch_verifies(self, verifier, broken_tree, fixture, tmp_path) -> None:
        baseline, _ = verifier.baseline(broken_tree, fixture.defect.failing_test, "t-ref")
        workspace = patched_workspace(
            broken_tree, tmp_path / "ref" / "ws", fixture.defect,
            lambda text: text.replace(BROKEN, FIXED),
        )
        result = verifier.verify(
            workspace, fixture.defect.failing_test, "t-ref", "c-ref", baseline.passing
        )
        assert result.target_test_passed is True
        assert result.regressions == ()
        assert result.timed_out is False
        assert result.eligible is True

    def test_noop_patch_fails(self, verifier, broken_tree, fixture, tmp_path) -> None:
        baseline, _ = verifier.baseline(broken_tree, fixture.defect.failing_test, "t-noop")
        workspace = patched_workspace(
            broken_tree, tmp_path / "noop" / "ws", fixture.defect, lambda text: text + "\n"
        )
        result = verifier.verify(
            workspace, fixture.defect.failing_test, "t-noop", "c-noop", baseline.passing
        )
        assert result.target_test_passed is False
        assert result.eligible is False

    def test_regression_detected(self, verifier, broken_tree, fixture, tmp_path) -> None:
        """A patch that fixes the target but breaks another test is not a fix."""
        baseline, _ = verifier.baseline(broken_tree, fixture.defect.failing_test, "t-reg")

        def sabotage(text: str) -> str:
            fixed = text.replace(BROKEN, FIXED)
            return fixed.replace(
                "    if offset > total:\n        return total\n    return offset",
                "    if offset > total:\n        return total\n    return 0",
            )

        workspace = patched_workspace(
            broken_tree, tmp_path / "reg" / "ws", fixture.defect, sabotage
        )
        result = verifier.verify(
            workspace, fixture.defect.failing_test, "t-reg", "c-reg", baseline.passing
        )
        assert result.target_test_passed is True
        assert result.regressions, "clamp_offset was broken and must be reported"
        assert any("clamp_offset" in node for node in result.regressions)
        assert result.eligible is False, "a regression disqualifies it however well it scored"

    def test_newly_passing_is_reported(self, verifier, broken_tree, fixture, tmp_path) -> None:
        baseline, _ = verifier.baseline(broken_tree, fixture.defect.failing_test, "t-new")
        workspace = patched_workspace(
            broken_tree, tmp_path / "new" / "ws", fixture.defect,
            lambda text: text.replace(BROKEN, FIXED),
        )
        result = verifier.verify(
            workspace, fixture.defect.failing_test, "t-new", "c-new", baseline.passing
        )
        assert fixture.defect.failing_test in result.newly_passing

    def test_timeout_reported(self, broken_tree, fixture, tmp_path) -> None:
        """A wedged interpreter is killed by the host, not asked nicely to stop."""
        verifier = Verifier(settings_for(verifier_timeout_seconds=20))

        def wedge(text: str) -> str:
            return text.replace(
                "    if total <= 0:\n        return 0",
                "    if total <= 0:\n        return 0\n    while True:\n        pass",
            )

        workspace = patched_workspace(
            broken_tree, tmp_path / "hang" / "ws", fixture.defect, wedge
        )
        result = verifier.verify(
            workspace, fixture.defect.failing_test, "t-hang", "c-hang", set()
        )
        assert result.timed_out is True
        assert result.target_test_passed is False
        assert result.eligible is False
        assert container_name("t-hang", "c-hang") not in leaked_containers()

    def test_no_network_in_container(self, verifier, broken_tree, fixture, tmp_path) -> None:
        def reach_out(text: str) -> str:
            return text.replace(
                "    if total <= 0:\n        return 0",
                "    if total <= 0:\n        return 0\n"
                "    import socket\n"
                "    try:\n"
                "        socket.create_connection(('example.com', 80), timeout=3)\n"
                "        return -999\n"
                "    except OSError:\n"
                "        return -111\n",
            )

        workspace = patched_workspace(
            broken_tree, tmp_path / "net" / "ws", fixture.defect, reach_out
        )
        result = verifier.verify(
            workspace, fixture.defect.failing_test, "t-net", "c-net", set()
        )
        assert result.target_test_passed is False
        assert "-111" in result.stdout_tail, "the outbound call must have been refused"
        assert "-999" not in result.stdout_tail, "the container reached the network"

    def test_artifacts_are_written(self, verifier, broken_tree, fixture, tmp_path) -> None:
        baseline, _ = verifier.baseline(
            broken_tree, fixture.defect.failing_test, "t-art", artifact_dir=tmp_path
        )
        workspace = patched_workspace(
            broken_tree, tmp_path / "art" / "ws", fixture.defect,
            lambda text: text.replace(BROKEN, FIXED),
        )
        verifier.verify(
            workspace, fixture.defect.failing_test, "t-art", "c-art", baseline.passing,
            artifact_dir=tmp_path / "art",
        )
        assert (tmp_path / "baseline.json").is_file()
        assert (tmp_path / "art" / "verification.json").is_file()
        assert (tmp_path / "art" / "stdout.txt").is_file()

    def test_nothing_leaks(self) -> None:
        """Runs last in this class: every container and volume above must be gone."""
        assert leaked_containers() == []
        assert leaked_volumes() == []
