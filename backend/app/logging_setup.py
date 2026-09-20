"""JSON logging with redaction applied at the handler.

Redaction at the call site is a discipline. Redaction at the handler is a
guarantee: a line can only reach stdout through the formatter, so the key cannot
escape by way of a log call somebody forgot to sanitise.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

from backend.app.config import Settings

LOGGER_NAME = "fixproof"
REDACTED = "***REDACTED***"

#: Generic shapes of credential: Google API keys, bearer tokens, long opaque keys.
KEY_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z\-_]{10,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{10,}=*"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[=:]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
)


def redact(text: str, literal: str = "") -> str:
    if literal and literal in text:
        text = text.replace(literal, REDACTED)
    for pattern in KEY_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


class RedactingJsonFormatter(logging.Formatter):
    """One JSON object per line, with every value passed through redaction."""

    def __init__(self, literal: str = "") -> None:
        super().__init__()
        self.literal = literal

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        run_id = getattr(record, "run_id", None)
        payload["run_id"] = run_id
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str), self.literal)


def configure_logging(settings: Settings) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(settings.log_level)
    logger.handlers.clear()
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(RedactingJsonFormatter(settings.gemini_api_key))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(run_id: str | None = None) -> logging.LoggerAdapter:
    """A logger whose every line carries the run id."""
    return logging.LoggerAdapter(logging.getLogger(LOGGER_NAME), {"run_id": run_id})
