"""Configuration that refuses to load when it is wrong.

A pipeline that runs for nine minutes and then discovers it has no API key has
wasted nine minutes.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

AppMode = Literal["local", "demo"]
ModelMode = Literal["fake", "fake_solve", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_mode: AppMode = "local"
    model_mode: ModelMode = "fake"
    gemini_api_key: str = ""
    gemini_model: str = ""

    database_path: str = "runtime/fixproof.sqlite"
    artifact_root: str = "runtime/runs"
    cors_origins: str = "*"

    max_candidates: int = Field(default=3, ge=1, le=10)
    max_run_seconds: int = Field(default=900, ge=0)
    model_timeout_seconds: int = Field(default=90, ge=1)
    verifier_timeout_seconds: int = Field(default=120, ge=1)

    max_propose_rounds: int = Field(default=1, ge=1, le=5)
    max_diff_lines: int = Field(default=40, ge=1)
    verifier_image: str = "fixproof-verifier:1"
    verifier_memory: str = "512m"
    verifier_cpus: str = "1"
    knowledge_top_k: int = Field(default=8, ge=1, le=64)

    gemini_price_in: float | None = None
    gemini_price_out: float | None = None

    log_level: str = "INFO"

    @field_validator("gemini_price_in", "gemini_price_out", mode="before")
    @classmethod
    def _blank_price_is_none(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("gemini_api_key", "gemini_model", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: Any) -> Any:
        if isinstance(value, str):
            upper = value.strip().upper()
            if upper not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                raise ValueError(
                    f"LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL; got {value!r}"
                )
            return upper
        return value

    @model_validator(mode="after")
    def _check_conditional_requirements(self) -> Settings:
        if self.model_mode == "gemini":
            missing = [
                name
                for name, value in (
                    ("GEMINI_API_KEY", self.gemini_api_key),
                    ("GEMINI_MODEL", self.gemini_model),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "MODEL_MODE=gemini requires " + " and ".join(missing) + " to be set"
                )
        if self.app_mode == "demo" and self.model_mode == "gemini":
            raise ValueError(
                "APP_MODE=demo cannot be combined with MODEL_MODE=gemini: "
                "a read-only public demonstration must not be able to spend your key"
            )
        return self

    @property
    def artifact_root_path(self) -> Path:
        path = self._resolve(self.artifact_root)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def database_file(self) -> Path:
        path = self._resolve(self.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def priced(self) -> bool:
        return self.gemini_price_in is not None and self.gemini_price_out is not None

    def _resolve(self, raw: str) -> Path:
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate
        return PROJECT_ROOT / candidate

    def behaviour_signature(self) -> dict[str, Any]:
        """The settings that change what the system decides, not where it writes."""
        return {
            "model_mode": self.model_mode,
            "gemini_model": self.gemini_model,
            "max_candidates": self.max_candidates,
            "max_propose_rounds": self.max_propose_rounds,
            "max_diff_lines": self.max_diff_lines,
            "knowledge_top_k": self.knowledge_top_k,
            "max_run_seconds": self.max_run_seconds,
            "model_timeout_seconds": self.model_timeout_seconds,
            "verifier_timeout_seconds": self.verifier_timeout_seconds,
            "verifier_image": self.verifier_image,
            "verifier_memory": self.verifier_memory,
            "verifier_cpus": self.verifier_cpus,
        }

    def redacted(self) -> dict[str, Any]:
        """A dict safe to log. The key never appears, present or absent."""
        data = self.model_dump()
        data["gemini_api_key"] = "***" if self.gemini_api_key else ""
        return data


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
