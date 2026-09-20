"""HTTP surface.

Demo mode returns 403 with a body explaining that the deployment is read-only,
never 404 — a 404 would be a lie about the route existing.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.app.config import PROJECT_ROOT, Settings
from backend.app.models import Decision, Defect, RunRecord, RunStatus
from backend.app.services.fingerprint import config_hash
from backend.app.services.fixtures import FixtureNotFound, get_fixture, list_defects
from backend.app.services.orchestrator import STAGES
from backend.app.services.reporting import decision_explanation
from backend.app.services.selection import is_eligible
from backend.app.services.store import Store
from backend.app.services.verifier import docker_reachable, image_present, leaked_containers

router = APIRouter()

ALLOWED_ARTIFACTS = frozenset(
    {
        "run.json",
        "defect.json",
        "baseline.json",
        "retrieval.json",
        "report.md",
        "report.json",
        "error.txt",
    }
)
REPORTS_DIR = PROJECT_ROOT / "reports"
DEMO_MESSAGE = (
    "This deployment is read-only: APP_MODE=demo disables every mutating endpoint. "
    "Runs shown here were recorded in advance."
)
_HEALTH_CACHE: dict[str, Any] = {"at": 0.0, "value": None}
HEALTH_TTL_SECONDS = 5.0


# --------------------------------------------------------------------- models


class HealthResponse(BaseModel):
    status: str
    app_mode: str
    model_mode: str
    model_name: str
    config_hash: str
    docker_reachable: bool
    image: str
    image_present: bool
    leaked_containers: int
    schema_version: int
    mutations_enabled: bool


class CreateRunRequest(BaseModel):
    defect_id: str = Field(min_length=1, examples=["dev-off_by_one-001"])


class CreateRunResponse(BaseModel):
    run_id: str
    defect_id: str
    fixture_set: str
    status: str
    queue_position: int


class GateView(BaseModel):
    gate: str
    passed: bool
    detail: str


class CandidateView(BaseModel):
    candidate_id: str
    round_index: int
    rationale: str
    unified_diff: str
    touched_paths: list[str]
    changed_lines: int
    confidence: float
    status: str
    rejected_by: str | None
    eligible: bool
    gates: list[GateView]
    verification: dict[str, Any] | None


class RunView(BaseModel):
    run_id: str
    defect_id: str
    fixture_set: str
    status: str
    decision: str | None
    decision_explanation: str
    chosen_candidate_id: str | None
    queue_position: int
    model_mode: str
    model_name: str
    config_hash: str
    rounds_used: int
    timeout_stage: str | None
    error: str | None
    stage_timings: dict[str, float]
    duration_seconds: float | None
    usage: dict[str, Any]
    candidates: list[CandidateView]
    artifacts: list[str]


class RunSummaryView(BaseModel):
    run_id: str
    defect_id: str
    fixture_set: str
    status: str
    decision: str | None
    chosen_candidate_id: str | None
    model_mode: str
    config_hash: str
    started_at: str | None
    finished_at: str | None


class RunListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    runs: list[RunSummaryView]


class DefectView(BaseModel):
    defect_id: str
    fixture_set: str
    summary: str
    failing_test: str
    allowed_paths: list[str]
    category: str
    difficulty: str
    last_decision: str | None = None


class GraphResponse(BaseModel):
    stages: list[str]
    nodes: list[dict[str, str]]
    edges: list[dict[str, str]]


# ------------------------------------------------------------------- helpers


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def store_of(request: Request) -> Store:
    return request.app.state.store


def manager_of(request: Request):
    return request.app.state.manager


def refuse_in_demo(request: Request) -> None:
    if settings_of(request).app_mode == "demo":
        raise HTTPException(status_code=403, detail=DEMO_MESSAGE)


def defect_view(defect: Defect, last_decision: str | None = None) -> DefectView:
    return DefectView(
        defect_id=defect.defect_id,
        fixture_set=defect.fixture_set,
        summary=defect.summary,
        failing_test=defect.failing_test,
        allowed_paths=list(defect.allowed_paths),
        category=defect.category,
        difficulty=defect.difficulty,
        last_decision=last_decision,
    )


def run_view(record: RunRecord, queue_position: int = 0) -> RunView:
    artifacts = []
    if record.artifact_dir:
        directory = Path(record.artifact_dir)
        artifacts = sorted(name for name in ALLOWED_ARTIFACTS if (directory / name).is_file())
    return RunView(
        run_id=record.run_id,
        defect_id=record.defect_id,
        fixture_set=record.fixture_set,
        status=record.status.value,
        decision=record.decision.value if record.decision else None,
        decision_explanation=decision_explanation(record.decision),
        chosen_candidate_id=record.chosen_candidate_id,
        queue_position=queue_position,
        model_mode=record.model_mode,
        model_name=record.model_name,
        config_hash=record.config_hash,
        rounds_used=record.rounds_used,
        timeout_stage=record.timeout_stage,
        error=record.error,
        stage_timings=record.stage_timings,
        duration_seconds=record.duration_seconds,
        usage={
            "calls": record.usage.calls,
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cost_usd": record.usage.cost_usd,
            "priced": record.usage.priced,
        },
        candidates=[
            CandidateView(
                candidate_id=outcome.candidate.candidate_id,
                round_index=outcome.candidate.round_index,
                rationale=outcome.candidate.rationale,
                unified_diff=outcome.candidate.unified_diff,
                touched_paths=list(outcome.candidate.touched_paths),
                changed_lines=outcome.candidate.changed_lines,
                confidence=outcome.candidate.confidence,
                status=outcome.status.value,
                rejected_by=outcome.rejecting_gate,
                eligible=is_eligible(outcome),
                gates=[
                    GateView(gate=gate.gate, passed=gate.passed, detail=gate.detail)
                    for gate in outcome.gates
                ],
                verification=(
                    outcome.verification.model_dump(mode="json")
                    if outcome.verification is not None
                    else None
                ),
            )
            for outcome in record.outcomes
        ],
        artifacts=artifacts,
    )


def resolve_run(request: Request, run_id: str) -> tuple[RunRecord, int]:
    manager = manager_of(request)
    handle = manager.get(run_id)
    if handle is not None:
        position = manager.queue_position(run_id)
        if handle.record is not None:
            return handle.record, position
        return (
            RunRecord(
                run_id=handle.run_id,
                defect_id=handle.defect_id,
                fixture_set=handle.fixture_set,
                status=handle.status,
                model_mode=settings_of(request).model_mode,
                config_hash=config_hash(settings_of(request)),
            ),
            position,
        )
    stored = store_of(request).get_run(run_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"no run with id {run_id!r}")
    return stored, 0


# -------------------------------------------------------------------- routes


@router.get("/healthz", response_model=HealthResponse, tags=["system"])
def healthz(request: Request) -> HealthResponse:
    settings = settings_of(request)
    now = time.monotonic()
    if _HEALTH_CACHE["value"] is None or now - _HEALTH_CACHE["at"] > HEALTH_TTL_SECONDS:
        _HEALTH_CACHE["value"] = (
            docker_reachable(),
            image_present(settings.verifier_image),
            len(leaked_containers()),
        )
        _HEALTH_CACHE["at"] = now
    reachable, present, leaked = _HEALTH_CACHE["value"]
    return HealthResponse(
        status="ok",
        app_mode=settings.app_mode,
        model_mode=settings.model_mode,
        model_name=settings.gemini_model or settings.model_mode,
        config_hash=config_hash(settings),
        docker_reachable=reachable,
        image=settings.verifier_image,
        image_present=present,
        leaked_containers=leaked,
        schema_version=store_of(request).schema_version,
        mutations_enabled=settings.app_mode != "demo",
    )


@router.get("/defects", response_model=list[DefectView], tags=["defects"])
def get_defects(
    request: Request,
    set: str | None = Query(default=None, pattern="^(dev|holdout)$"),  # noqa: A002
) -> list[DefectView]:
    last = store_of(request).last_decision_by_defect()
    return [defect_view(defect, last.get(defect.defect_id)) for defect in list_defects(set)]


@router.get("/defects/{defect_id}", response_model=DefectView, tags=["defects"])
def get_defect(request: Request, defect_id: str) -> DefectView:
    """The defect. Never the reference patch, which is scoring material."""
    try:
        fixture = get_fixture(defect_id)
    except FixtureNotFound as missing:
        raise HTTPException(status_code=404, detail=f"no defect {defect_id!r}") from missing
    last = store_of(request).last_decision_by_defect()
    return defect_view(fixture.defect, last.get(defect_id))


@router.post("/runs", response_model=CreateRunResponse, status_code=202, tags=["runs"])
def create_run(request: Request, body: CreateRunRequest) -> CreateRunResponse:
    refuse_in_demo(request)
    try:
        get_fixture(body.defect_id)
    except FixtureNotFound as missing:
        raise HTTPException(status_code=404, detail=f"no defect {body.defect_id!r}") from missing
    handle = manager_of(request).submit(body.defect_id)
    return CreateRunResponse(
        run_id=handle.run_id,
        defect_id=handle.defect_id,
        fixture_set=handle.fixture_set,
        status=handle.status.value,
        queue_position=manager_of(request).queue_position(handle.run_id),
    )


@router.get("/runs", response_model=RunListResponse, tags=["runs"])
def get_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RunListResponse:
    store = store_of(request)
    summaries = store.latest_runs(limit=limit, offset=offset)
    return RunListResponse(
        total=store.count_runs(),
        limit=limit,
        offset=offset,
        runs=[
            RunSummaryView(
                run_id=summary.run_id,
                defect_id=summary.defect_id,
                fixture_set=summary.fixture_set,
                status=summary.status,
                decision=summary.decision,
                chosen_candidate_id=summary.chosen_candidate_id,
                model_mode=summary.model_mode,
                config_hash=summary.config_hash,
                started_at=summary.started_at,
                finished_at=summary.finished_at,
            )
            for summary in summaries
        ],
    )


@router.get("/runs/{run_id}", response_model=RunView, tags=["runs"])
def get_run(request: Request, run_id: str) -> RunView:
    record, position = resolve_run(request, run_id)
    return run_view(record, position)


@router.get("/runs/{run_id}/events", tags=["runs"])
def run_events(request: Request, run_id: str) -> StreamingResponse:
    """Server-sent events: one per stage transition and per candidate result."""
    manager = manager_of(request)
    if manager.get(run_id) is None:
        if store_of(request).get_run(run_id) is None:
            raise HTTPException(status_code=404, detail=f"no run with id {run_id!r}")
        raise HTTPException(
            status_code=409, detail="that run finished in an earlier process; read /runs/{id}"
        )

    def generate():
        for event in manager.stream(run_id):
            yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event)}\n\n"
        yield "event: close\ndata: {}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/artifacts/{name}", tags=["runs"])
def get_artifact(request: Request, run_id: str, name: str) -> Response:
    """Allow-listed names only. A path from the client is never joined."""
    if name not in ALLOWED_ARTIFACTS:
        raise HTTPException(
            status_code=404,
            detail=f"unknown artifact {name!r}; allowed: {sorted(ALLOWED_ARTIFACTS)}",
        )
    record, _ = resolve_run(request, run_id)
    directory = Path(record.artifact_dir or settings_of(request).artifact_root_path / run_id)
    path = directory / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"{name} has not been written for this run")
    text = path.read_text(encoding="utf-8")
    if name.endswith(".json"):
        return Response(content=text, media_type="application/json")
    return PlainTextResponse(text)


@router.post("/runs/{run_id}/cancel", tags=["runs"])
def cancel_run(request: Request, run_id: str) -> dict[str, Any]:
    refuse_in_demo(request)
    manager = manager_of(request)
    if manager.get(run_id) is None:
        raise HTTPException(status_code=404, detail=f"no active run with id {run_id!r}")
    cancelled = manager.cancel(run_id)
    return {"run_id": run_id, "cancel_requested": cancelled}


@router.get("/reports/latest", tags=["reports"])
def latest_report() -> dict[str, Any]:
    if not REPORTS_DIR.is_dir():
        raise HTTPException(status_code=404, detail="no reports have been committed yet")
    candidates = sorted(REPORTS_DIR.glob("eval-*.json"))
    if not candidates:
        raise HTTPException(status_code=404, detail="no reports have been committed yet")
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    payload = json.loads(newest.read_text(encoding="utf-8"))
    payload["report_file"] = newest.name
    return payload


@router.get("/reports", tags=["reports"])
def all_reports() -> list[dict[str, Any]]:
    if not REPORTS_DIR.is_dir():
        return []
    reports: list[dict[str, Any]] = []
    for path in sorted(REPORTS_DIR.glob("eval-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["report_file"] = path.name
        reports.append(payload)
    return reports


@router.get("/graph", response_model=GraphResponse, tags=["system"])
def graph() -> GraphResponse:
    """The stage machine, so the frontend renders what the backend actually does."""
    descriptions = {
        "prepare": "Copy the target app and apply the fixture's break patch",
        "baseline": "Verify the unpatched broken workspace to learn what passes",
        "retrieve": "Rank knowledge chunks and force-include the editable files",
        "propose": "Ask the model for candidate patches",
        "gate": "Run the nine static gates, short-circuiting on the first rejection",
        "verify": "Run each survivor's tests in a sandboxed container",
        "select": "Choose deterministically among eligible candidates",
    }
    return GraphResponse(
        stages=list(STAGES),
        nodes=[
            {"id": stage, "label": stage, "description": descriptions[stage]} for stage in STAGES
        ],
        edges=[
            {"source": source, "target": target}
            for source, target in zip(STAGES, STAGES[1:], strict=False)
        ]
        + [{"source": "verify", "target": "propose", "label": "another round, if enabled"}],
    )


@router.get("/decisions", tags=["system"])
def decisions() -> list[dict[str, str]]:
    return [
        {"decision": decision.value, "meaning": decision_explanation(decision)}
        for decision in Decision
    ]


@router.get("/statuses", tags=["system"])
def statuses() -> list[str]:
    return [status.value for status in RunStatus]
