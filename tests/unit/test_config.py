"""Configuration tests."""

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_demo_mode_defaults_are_disabled() -> None:
    """Demo safeguards should be opt-in."""
    settings = Settings(_env_file=None)

    assert settings.DEMO_MODE is False
    assert settings.DEMO_MAX_UPLOADS_PER_SESSION == 3
    assert settings.DEMO_MAX_QUERIES_PER_SESSION == 20
    assert settings.DEMO_MAX_TOTAL_UPLOAD_MB_PER_SESSION == 25
    assert settings.DEMO_MAX_FILE_SIZE_MB == 10
    assert settings.DEMO_MAX_QUERY_LENGTH == 1000
    assert settings.DEMO_RATE_LIMIT_WINDOW_MINUTES == 60
    assert settings.DEMO_MAX_QUERIES_PER_IP == 30
    assert settings.DEMO_GLOBAL_DAILY_QUERY_LIMIT == 250
    assert settings.DEMO_MAX_COMPLETION_TOKENS == 1000
    assert settings.DEMO_MAX_RETRIEVED_CHUNKS == 10
    assert settings.DEMO_REQUEST_TIMEOUT_SECONDS == 45


def test_demo_mode_settings_can_be_overridden(monkeypatch) -> None:
    """Demo limits should load from environment variables."""
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_MAX_UPLOADS_PER_SESSION", "5")
    monkeypatch.setenv("DEMO_MAX_QUERIES_PER_SESSION", "40")
    monkeypatch.setenv("DEMO_MAX_TOTAL_UPLOAD_MB_PER_SESSION", "50")
    monkeypatch.setenv("DEMO_MAX_FILE_SIZE_MB", "20")
    monkeypatch.setenv("DEMO_MAX_QUERY_LENGTH", "2000")
    monkeypatch.setenv("DEMO_RATE_LIMIT_WINDOW_MINUTES", "30")
    monkeypatch.setenv("DEMO_MAX_QUERIES_PER_IP", "60")
    monkeypatch.setenv("DEMO_GLOBAL_DAILY_QUERY_LIMIT", "500")
    monkeypatch.setenv("DEMO_MAX_COMPLETION_TOKENS", "1500")
    monkeypatch.setenv("DEMO_MAX_RETRIEVED_CHUNKS", "8")
    monkeypatch.setenv("DEMO_REQUEST_TIMEOUT_SECONDS", "20")

    settings = Settings(_env_file=None)

    assert settings.DEMO_MODE is True
    assert settings.DEMO_MAX_UPLOADS_PER_SESSION == 5
    assert settings.DEMO_MAX_QUERIES_PER_SESSION == 40
    assert settings.DEMO_MAX_TOTAL_UPLOAD_MB_PER_SESSION == 50
    assert settings.DEMO_MAX_FILE_SIZE_MB == 20
    assert settings.DEMO_MAX_QUERY_LENGTH == 2000
    assert settings.DEMO_RATE_LIMIT_WINDOW_MINUTES == 30
    assert settings.DEMO_MAX_QUERIES_PER_IP == 60
    assert settings.DEMO_GLOBAL_DAILY_QUERY_LIMIT == 500
    assert settings.DEMO_MAX_COMPLETION_TOKENS == 1500
    assert settings.DEMO_MAX_RETRIEVED_CHUNKS == 8
    assert settings.DEMO_REQUEST_TIMEOUT_SECONDS == 20
    assert settings.DEMO_MAX_FILE_SIZE_BYTES == 20 * 1024 * 1024
    assert settings.DEMO_MAX_TOTAL_UPLOAD_BYTES_PER_SESSION == 50 * 1024 * 1024


def test_demo_mode_limits_must_be_positive(monkeypatch) -> None:
    """Invalid demo limit values should fail settings validation."""
    monkeypatch.setenv("DEMO_MAX_QUERIES_PER_SESSION", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
