"""Run scheduling for the API.

The verifier is blocking and Docker is a shared resource, so runs execute in a
worker thread behind a semaphore of one. Anything beyond that queues, and the
queue position is reported rather than hidden.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from backend.app.config import Settings
from backend.app.models import Decision, RunRecord, RunStatus
from backend.app.services.fixtures import get_fixture
from backend.app.services.orchestrator import Orchestrator, new_run_id
from backend.app.services.store import Store

POLL_SECONDS = 0.25


@dataclass
class RunHandle:
    run_id: str
    defect_id: str
    fixture_set: str
    status: RunStatus = RunStatus.QUEUED
    events: list[dict[str, Any]] = field(default_factory=list)
    record: RunRecord | None = None
    error: str | None = None
    cancel_requested: bool = False
    finished: threading.Event = field(default_factory=threading.Event)
    updated: threading.Event = field(default_factory=threading.Event)
    future: Future | None = None


class RunManager:
    """One in-flight run at a time, with an ordered queue behind it."""

    def __init__(self, settings: Settings, store: Store) -> None:
        self.settings = settings
        self.store = store
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fixproof-run")
        self._lock = threading.Lock()
        self._handles: dict[str, RunHandle] = {}
        self._queue: list[str] = []

    # ---------------------------------------------------------------- queries

    def get(self, run_id: str) -> RunHandle | None:
        with self._lock:
            return self._handles.get(run_id)

    def queue_position(self, run_id: str) -> int:
        """0 means running or finished; 1 means next up."""
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is None or handle.status is not RunStatus.QUEUED:
                return 0
            try:
                return self._queue.index(run_id) + 1
            except ValueError:
                return 0

    def active_run_id(self) -> str | None:
        with self._lock:
            for run_id, handle in self._handles.items():
                if handle.status is RunStatus.RUNNING:
                    return run_id
        return None

    # ----------------------------------------------------------------- submit

    def submit(self, defect_id: str) -> RunHandle:
        fixture = get_fixture(defect_id)
        run_id = new_run_id()
        handle = RunHandle(
            run_id=run_id,
            defect_id=defect_id,
            fixture_set=fixture.defect.fixture_set,
        )
        with self._lock:
            self._handles[run_id] = handle
            self._queue.append(run_id)
        handle.future = self._executor.submit(self._execute, handle)
        return handle

    def cancel(self, run_id: str) -> bool:
        handle = self.get(run_id)
        if handle is None or handle.finished.is_set():
            return False
        handle.cancel_requested = True
        self._append(handle, {"type": "cancel", "run_id": run_id})
        return True

    # ------------------------------------------------------------------ inner

    def _append(self, handle: RunHandle, event: dict[str, Any]) -> None:
        with self._lock:
            handle.events.append(event)
        handle.updated.set()
        handle.updated.clear()

    def _execute(self, handle: RunHandle) -> None:
        with self._lock:
            if handle.run_id in self._queue:
                self._queue.remove(handle.run_id)
            handle.status = RunStatus.RUNNING
        self._append(handle, {"type": "status", "status": RunStatus.RUNNING.value})

        try:
            orchestrator = Orchestrator(self.settings, store=self.store)
            record = orchestrator.run(
                handle.defect_id,
                run_id=handle.run_id,
                on_event=lambda event: self._append(handle, event),
                cancel=lambda: handle.cancel_requested,
            )
            handle.record = record
            handle.status = record.status
        except Exception as failure:  # noqa: BLE001 - surfaced through the API
            handle.error = f"{type(failure).__name__}: {failure}"
            handle.status = RunStatus.FAILED
            handle.record = RunRecord(
                run_id=handle.run_id,
                defect_id=handle.defect_id,
                fixture_set=handle.fixture_set,
                status=RunStatus.FAILED,
                decision=Decision.ERROR,
                error=handle.error,
            )
            self._append(handle, {"type": "error", "error": handle.error})
        finally:
            self._append(
                handle,
                {"type": "status", "status": handle.status.value, "terminal": True},
            )
            handle.finished.set()
            handle.updated.set()

    # -------------------------------------------------------------------- SSE

    def stream(self, run_id: str) -> Iterator[dict[str, Any]]:
        """Replay what has happened, then follow along until the run is terminal."""
        handle = self.get(run_id)
        if handle is None:
            return
        index = 0
        while True:
            with self._lock:
                pending = handle.events[index:]
                index = len(handle.events)
            yield from pending
            if handle.finished.is_set():
                with self._lock:
                    remaining = handle.events[index:]
                    index = len(handle.events)
                yield from remaining
                return
            handle.updated.wait(timeout=POLL_SECONDS)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
