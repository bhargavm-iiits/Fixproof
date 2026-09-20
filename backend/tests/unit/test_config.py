from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.config import Settings

SECRET = "AIza-this-must-never-be-logged-0123456789"


def build(**overrides: str) -> Settings:
    """Construct settings from explicit values only, never from a developer's .env."""
    return Settings(_env_file=None, **overrides)


def test_fake_mode_needs_no_key() -> None:
    settings = build(model_mode="fake")
    assert settings.model_mode == "fake"
    assert settings.gemini_api_key == ""


def test_gemini_mode_requires_key() -> None:
    with pytest.raises(ValidationError) as excinfo:
        build(model_mode="gemini", gemini_model="gemini-3.8-flash")
    assert "GEMINI_API_KEY" in str(excinfo.value)


def test_gemini_mode_requires_model_name() -> None:
    with pytest.raises(ValidationError) as excinfo:
        build(model_mode="gemini", gemini_api_key=SECRET)
    assert "GEMINI_MODEL" in str(excinfo.value)


def test_gemini_mode_loads_when_both_present() -> None:
    settings = build(model_mode="gemini", gemini_api_key=SECRET, gemini_model="gemini-3.8-flash")
    assert settings.gemini_model == "gemini-3.8-flash"


def test_demo_mode_forbids_gemini() -> None:
    with pytest.raises(ValidationError) as excinfo:
        build(
            app_mode="demo",
            model_mode="gemini",
            gemini_api_key=SECRET,
            gemini_model="gemini-3.8-flash",
        )
    assert "demo" in str(excinfo.value)


def test_demo_mode_allows_fake() -> None:
    assert build(app_mode="demo", model_mode="fake").app_mode == "demo"


def test_unknown_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        build(model_mode="banana")


def test_unknown_app_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        build(app_mode="production")


def test_redacted_never_contains_the_key() -> None:
    settings = build(model_mode="gemini", gemini_api_key=SECRET, gemini_model="gemini-3.8-flash")
    redacted = settings.redacted()
    assert SECRET not in repr(redacted)
    assert redacted["gemini_api_key"] == "***"


def test_redacted_reports_absent_key_as_empty() -> None:
    assert build(model_mode="fake").redacted()["gemini_api_key"] == ""


def test_artifact_root_is_created(tmp_path) -> None:
    target = tmp_path / "nested" / "runs"
    settings = build(artifact_root=str(target))
    assert not target.exists()
    assert settings.artifact_root_path == target
    assert target.is_dir()


def test_database_parent_is_created(tmp_path) -> None:
    target = tmp_path / "nested" / "db" / "fixproof.sqlite"
    settings = build(database_path=str(target))
    assert settings.database_file == target
    assert target.parent.is_dir()


def test_blank_prices_become_none() -> None:
    settings = build(gemini_price_in="", gemini_price_out="")
    assert settings.gemini_price_in is None
    assert settings.priced is False


def test_set_prices_are_priced() -> None:
    settings = build(gemini_price_in="0.1", gemini_price_out="0.4")
    assert settings.priced is True


def test_bad_log_level_rejected() -> None:
    with pytest.raises(ValidationError):
        build(log_level="chatty")


def test_behaviour_signature_excludes_paths_and_secrets() -> None:
    signature = build(
        model_mode="gemini", gemini_api_key=SECRET, gemini_model="gemini-3.8-flash"
    ).behaviour_signature()
    assert "gemini_api_key" not in signature
    assert "artifact_root" not in signature
    assert "database_path" not in signature
    assert signature["gemini_model"] == "gemini-3.8-flash"
