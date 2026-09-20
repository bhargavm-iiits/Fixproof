from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import (
    CandidateOutcome,
    CandidateStatus,
    Decision,
    GateResult,
    ProposedPatch,
    RunRecord,
    RunStatus,
    VerificationResult,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def build_settings(tmp_path: Path, **overrides) -> Settings:
    base = {
        "artifact_root": str(tmp_path / "runs"),
        "database_path": str(tmp_path / "fixproof.sqlite"),
        "model_mode": "fake",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
async def client_factory(tmp_path) -> AsyncIterator:
    created: list[httpx.AsyncClient] = []

    def build(**overrides) -> httpx.AsyncClient:
        settings = build_settings(tmp_path, **overrides)
        app = create_app(settings)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            timeout=120,
        )
        client.app = app  # type: ignore[attr-defined]
        created.append(client)
        return client

    yield build
    for client in created:
        client.app.state.manager.shutdown()  # type: ignore[attr-defined]
        await client.aclose()


@pytest.fixture
async def client(client_factory) -> AsyncIterator[httpx.AsyncClient]:
    yield client_factory()


@pytest.fixture
async def demo_client(client_factory) -> AsyncIterator[httpx.AsyncClient]:
    yield client_factory(app_mode="demo")


def seed_run(client: httpx.AsyncClient, run_id: str = "run-seeded") -> Path:
    """Write a finished run straight into the store, without executing anything."""
    store = client.app.state.store  # type: ignore[attr-defined]
    settings = client.app.state.settings  # type: ignore[attr-defined]
    artifact_dir = settings.artifact_root_path / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text("# seeded\n", encoding="utf-8")
    (artifact_dir / "report.json").write_text(json.dumps({"seeded": True}), encoding="utf-8")

    diff = "--- a/paging.py\n+++ b/paging.py\n@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"
    record = RunRecord(
        run_id=run_id,
        defect_id="dev-off_by_one-001",
        fixture_set="dev",
        status=RunStatus.SUCCEEDED,
        decision=Decision.NO_VERIFIED_FIX,
        artifact_dir=str(artifact_dir),
        model_mode="fake",
        model_name="fake",
        config_hash="seeded",
        rounds_used=1,
        outcomes=(
            CandidateOutcome(
                candidate=ProposedPatch(candidate_id="r1-noop", unified_diff=diff),
                gates=(GateResult(gate="diff_parses", passed=True),),
                verification=VerificationResult(candidate_id="r1-noop", tests_run=330),
                status=CandidateStatus.VERIFIED,
            ),
        ),
        started_at=datetime(2026, 9, 21, 9, tzinfo=UTC),
        finished_at=datetime(2026, 9, 21, 9, 1, tzinfo=UTC),
    )
    store.save_run(record)
    return artifact_dir


async def drain_events(client: httpx.AsyncClient, run_id: str) -> list[dict]:
    """Follow a run's SSE stream until it reports a terminal status."""
    events: list[dict] = []
    async with client.stream("GET", f"/runs/{run_id}/events") as response:
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            events.append(event)
            if event.get("terminal"):
                break
    return events
