from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

FIXPROOF_ENV_PREFIXES = (
    "APP_MODE",
    "MODEL_MODE",
    "GEMINI_",
    "DATABASE_PATH",
    "ARTIFACT_ROOT",
    "MAX_",
    "MODEL_TIMEOUT_SECONDS",
    "VERIFIER_",
    "KNOWLEDGE_TOP_K",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test inherits the developer's own .env-derived environment."""
    for name in list(os.environ):
        if name.upper().startswith(FIXPROOF_ENV_PREFIXES):
            monkeypatch.delenv(name, raising=False)
    yield
