"""The FastAPI application.

`create_app` takes explicit settings so tests can build an app against a
temporary database and artifact root without touching the developer's own.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.api.runner import RunManager
from backend.app.config import PROJECT_ROOT, Settings, get_settings
from backend.app.logging_setup import configure_logging
from backend.app.services.store import Store

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

DESCRIPTION = """\
fixproof repairs a defect and **proves** the repair.

A fix is reported only when a container with no network has run the target's own
test suite and shown that the failing test now passes and nothing that passed
before now fails. The name is the contract: the proof is a container exit code,
not a model's opinion.

* `MODEL_MODE=fake` measures the harness, not a model.
* `MODEL_MODE=fake_solve` reads the fixture's answer key and is never a measurement.
* `APP_MODE=demo` returns 403 from every mutating endpoint.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved)
    store = Store(resolved.database_file)
    manager = RunManager(resolved, store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        manager.shutdown()

    app = FastAPI(
        title="fixproof",
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    origins = [origin.strip() for origin in resolved.cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = resolved
    app.state.store = store
    app.state.manager = manager
    app.include_router(router)

    if FRONTEND_DIST.is_dir():
        assets = FRONTEND_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        # Derived from the router rather than hand-listed, so a new endpoint
        # cannot start silently returning the SPA instead of a 404.
        api_roots = {
            route.path.lstrip("/").split("/", 1)[0]
            for route in router.routes
            if getattr(route, "path", "").startswith("/")
        }
        api_roots |= {"docs", "redoc", "openapi.json", "assets"}
        api_roots.discard("")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            head = path.split("/", 1)[0]
            if head in api_roots:
                raise HTTPException(status_code=404, detail=f"no such endpoint: /{path}")
            candidate = (FRONTEND_DIST / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(FRONTEND_DIST.resolve()):
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
