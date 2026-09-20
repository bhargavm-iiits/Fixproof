"""The only component permitted to declare a fix.

Everything else in this system produces hypotheses. A fix is reported when a
container with no network, a read-only root and a host-enforced timeout exits
having run the target's own test suite and proved that the failing test passes
and nothing that passed before now fails.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.config import Settings
from backend.app.models import VerificationResult

NAME_SAFE = re.compile(r"[^A-Za-z0-9_.-]")
CONTAINER_PREFIX = "fixproof-"
PIDS_LIMIT = "256"
TMP_SIZE = "64m"
TAIL_CHARS = 4000


class DockerUnavailable(RuntimeError):
    """The Docker engine could not be reached, or the verifier image is missing."""


@dataclass(frozen=True)
class RunnerOutput:
    target_test_passed: bool = False
    outcomes: dict[str, str] = field(default_factory=dict)
    tests_run: int = 0
    duration_ms: int = 0
    stdout_tail: str = ""
    runner_error: str | None = None

    @property
    def passing(self) -> set[str]:
        return {node for node, outcome in self.outcomes.items() if outcome == "passed"}

    @property
    def failing(self) -> set[str]:
        return {node for node, outcome in self.outcomes.items() if outcome in {"failed", "error"}}


def _last_json_document(text: str) -> dict | None:
    """The runner's document, ignoring any noise the container printed before it.

    Scanning backwards for `{` would land inside the nested outcome map, so each
    opening brace is tried in turn and only a parse that consumes the rest of the
    text counts.
    """
    decoder = json.JSONDecoder()
    index = text.find("{")
    while index >= 0:
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index = text.find("{", index + 1)
            continue
        if isinstance(value, dict) and not text[end:].strip():
            return value
        index = text.find("{", index + 1)
    return None


def parse_runner_output(raw: str) -> RunnerOutput:
    """Map the container's JSON document onto a result, or say why it could not be."""
    text = raw.strip()
    if not text:
        return RunnerOutput(runner_error="the container produced no output")

    payload = _last_json_document(text)
    if payload is None:
        return RunnerOutput(
            runner_error=f"no JSON document in the container output: {text[-400:]}"
        )

    if payload.get("runner_error"):
        return RunnerOutput(
            runner_error=str(payload["runner_error"]),
            stdout_tail=str(payload.get("stdout_tail", ""))[-TAIL_CHARS:],
        )

    suite = payload.get("suite", {})
    outcomes = {str(k): str(v) for k, v in dict(suite.get("outcomes", {})).items()}
    return RunnerOutput(
        target_test_passed=bool(payload.get("target_test_passed", False)),
        outcomes=outcomes,
        tests_run=int(suite.get("tests_run", len(outcomes))),
        duration_ms=int(suite.get("duration_ms", 0)) + int(payload.get("target_duration_ms", 0)),
        stdout_tail=str(payload.get("stdout_tail", ""))[-TAIL_CHARS:],
    )


def _docker(*arguments: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def docker_reachable() -> bool:
    try:
        return _docker("info", "--format", "{{.OSType}}", timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def image_present(image: str) -> bool:
    try:
        result = _docker("image", "inspect", image, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def leaked_containers() -> list[str]:
    """Any container this project left behind. In a healthy run this is empty."""
    try:
        result = _docker(
            "ps", "-a", "--filter", f"name={CONTAINER_PREFIX}", "--format", "{{.Names}}", timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def leaked_volumes() -> list[str]:
    """Workspace volumes left behind. Also empty in a healthy run."""
    try:
        result = _docker(
            "volume", "ls", "--filter", f"name={CONTAINER_PREFIX}", "--format", "{{.Name}}",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def container_name(run_id: str, candidate_id: str) -> str:
    safe = f"{CONTAINER_PREFIX}{NAME_SAFE.sub('-', run_id)}-{NAME_SAFE.sub('-', candidate_id)}"
    return safe[:120]


class Verifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def preflight(self) -> None:
        if not docker_reachable():
            raise DockerUnavailable("the Docker engine is not reachable")
        if not image_present(self.settings.verifier_image):
            raise DockerUnavailable(
                f"the image {self.settings.verifier_image} is not present; build it with "
                "docker build -f docker/verifier.Dockerfile -t fixproof-verifier:1 ."
            )

    def run_suite(
        self, workspace: Path, node_id: str, name: str
    ) -> tuple[RunnerOutput, int | None, bool]:
        """Run one container to completion. Returns (output, exit code, timed out)."""
        # `docker cp` is refused outright into a --read-only rootfs, so /work is a
        # throwaway volume. That keeps both halves of the design: the image stays
        # read-only, and the code under test still arrives as a copied snapshot.
        volume = _docker("volume", "create", name)
        if volume.returncode != 0:
            raise DockerUnavailable(f"docker volume create failed: {volume.stderr.strip()}")

        created = _docker(
            "create",
            "--name",
            name,
            "--network",
            "none",
            "--memory",
            self.settings.verifier_memory,
            "--cpus",
            str(self.settings.verifier_cpus),
            "--pids-limit",
            PIDS_LIMIT,
            "--read-only",
            "--tmpfs",
            f"/tmp:rw,size={TMP_SIZE}",
            "--volume",
            f"{name}:/work",
            self.settings.verifier_image,
            node_id,
        )
        if created.returncode != 0:
            _docker("volume", "rm", "--force", name, timeout=60)
            raise DockerUnavailable(f"docker create failed: {created.stderr.strip()}")

        try:
            # `docker cp` rather than a bind mount: it sidesteps Windows path
            # translation, keeps the image read-only, and makes the container's
            # view of the code a snapshot the host cannot change mid-run.
            copied = _docker("cp", f"{workspace}{os.sep}.", f"{name}:/work/")
            if copied.returncode != 0:
                raise DockerUnavailable(f"docker cp failed: {copied.stderr.strip()}")

            started = time.monotonic()
            try:
                result = _docker(
                    "start", "--attach", name, timeout=self.settings.verifier_timeout_seconds
                )
            except subprocess.TimeoutExpired:
                # A wedged interpreter will not honour a guest-side timeout, so
                # the host is the one that enforces it.
                _docker("kill", name, timeout=60)
                elapsed = int((time.monotonic() - started) * 1000)
                return (
                    RunnerOutput(
                        duration_ms=elapsed,
                        runner_error=(
                            f"the container exceeded VERIFIER_TIMEOUT_SECONDS="
                            f"{self.settings.verifier_timeout_seconds} and was killed"
                        ),
                    ),
                    None,
                    True,
                )
            output = parse_runner_output(result.stdout + result.stderr)
            return output, result.returncode, False
        finally:
            _docker("rm", "--force", name, timeout=60)
            _docker("volume", "rm", "--force", name, timeout=60)

    def verify(
        self,
        workspace: Path,
        node_id: str,
        run_id: str,
        candidate_id: str,
        baseline_passing: set[str] | None = None,
        artifact_dir: Path | None = None,
    ) -> VerificationResult:
        name = container_name(run_id, candidate_id)
        output, exit_code, timed_out = self.run_suite(workspace, node_id, name)

        regressions: tuple[str, ...] = ()
        newly_passing: tuple[str, ...] = ()
        if baseline_passing is not None and not timed_out and output.runner_error is None:
            regressions = tuple(sorted(baseline_passing & output.failing))
            newly_passing = tuple(sorted(output.passing - baseline_passing))

        tail = output.stdout_tail
        if output.runner_error:
            tail = f"{output.runner_error}\n{tail}".strip()

        result = VerificationResult(
            candidate_id=candidate_id,
            container_exit_code=exit_code,
            target_test_passed=output.target_test_passed and not timed_out,
            regressions=regressions,
            newly_passing=newly_passing,
            tests_run=output.tests_run,
            duration_ms=output.duration_ms,
            stdout_tail=tail[-TAIL_CHARS:],
            timed_out=timed_out,
        )

        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "verification.json").write_text(
                result.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
            )
            (artifact_dir / "stdout.txt").write_text(tail, encoding="utf-8", newline="\n")
        return result

    def baseline(
        self,
        workspace: Path,
        node_id: str,
        run_id: str,
        artifact_dir: Path | None = None,
    ) -> tuple[RunnerOutput, VerificationResult]:
        """Verify the unpatched broken workspace, once, before any candidate.

        This is what makes `regressions` a computation rather than a guess.
        """
        name = container_name(run_id, "baseline")
        output, exit_code, timed_out = self.run_suite(workspace, node_id, name)
        if output.runner_error and not timed_out:
            raise DockerUnavailable(f"the baseline run failed: {output.runner_error}")

        result = VerificationResult(
            candidate_id="baseline",
            container_exit_code=exit_code,
            target_test_passed=output.target_test_passed,
            tests_run=output.tests_run,
            duration_ms=output.duration_ms,
            stdout_tail=output.stdout_tail,
            timed_out=timed_out,
        )
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "baseline.json").write_text(
                json.dumps(
                    {
                        "target_test": node_id,
                        "target_test_passed": output.target_test_passed,
                        "tests_run": output.tests_run,
                        "passing": sorted(output.passing),
                        "failing": sorted(output.failing),
                        "duration_ms": output.duration_ms,
                        "timed_out": timed_out,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        return output, result
