"""The config hash.

It covers everything that changes what the system decides — the model, the
prompt, the gates, the budgets — and nothing about where files are written. It is
what makes the holdout protocol enforceable rather than aspirational: a report
carrying a different hash was produced by a different system.
"""

from __future__ import annotations

import hashlib
import json

from backend.app.config import Settings
from backend.app.services.gates import GATE_NAMES
from backend.app.services.model_client import PROMPT_VERSION, SYSTEM_PROMPT
from backend.app.services.retrieval import TOKEN_BUDGET


def behaviour_document(settings: Settings) -> dict:
    return {
        "settings": settings.behaviour_signature(),
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "gates": list(GATE_NAMES),
        "token_budget": TOKEN_BUDGET,
    }


def config_hash(settings: Settings) -> str:
    document = json.dumps(behaviour_document(settings), sort_keys=True)
    return hashlib.sha256(document.encode("utf-8")).hexdigest()[:16]
