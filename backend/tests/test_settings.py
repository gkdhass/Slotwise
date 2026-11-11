"""Settings validation and feature-flag contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    DEV_MINIO_SECRET_KEY,
    DEV_SECRET_KEY,
    Settings,
    reset_settings_cache,
)

STRONG_SECRET = "a" * 64
STRONG_MINIO_SECRET = "b" * 40


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_defaults_are_safe_for_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    settings = Settings()
    assert settings.app.env == "dev"
    assert settings.features.module_b_enabled is False
    assert settings.features.allow_self_approval is False
    assert settings.app.api_v1_prefix == "/api/v1"


def test_module_b_and_self_approval_flags_are_flat_env_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MODULE_B_ENABLED", "true")
    monkeypatch.setenv("ALLOW_SELF_APPROVAL", "true")
    settings = Settings()
    assert settings.features.module_b_enabled is True
    assert settings.features.allow_self_approval is True


def test_non_dev_rejects_development_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SECURITY_SECRET_KEY", DEV_SECRET_KEY)
    monkeypatch.setenv("MINIO_SECRET_KEY", STRONG_MINIO_SECRET)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://slotwise:strong-password@db:5432/slotwise"
    )
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "SECURITY_SECRET_KEY" in str(exc_info.value)


def test_non_dev_rejects_development_minio_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("SECURITY_SECRET_KEY", STRONG_SECRET)
    monkeypatch.setenv("MINIO_SECRET_KEY", DEV_MINIO_SECRET_KEY)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://slotwise:strong-password@db:5432/slotwise"
    )
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "MINIO_SECRET_KEY" in str(exc_info.value)


def test_non_dev_rejects_placeholder_database_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SECURITY_SECRET_KEY", STRONG_SECRET)
    monkeypatch.setenv("MINIO_SECRET_KEY", STRONG_MINIO_SECRET)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://slotwise:change-me@db:5432/slotwise")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "DATABASE_URL" in str(exc_info.value)


def test_non_dev_accepts_strong_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SECURITY_SECRET_KEY", STRONG_SECRET)
    monkeypatch.setenv("MINIO_SECRET_KEY", STRONG_MINIO_SECRET)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://slotwise:strong-password@db:5432/slotwise"
    )
    settings = Settings()
    assert settings.app.env == "prod"


def test_blank_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SECURITY_SECRET_KEY", "   ")
    with pytest.raises(ValidationError):
        Settings()


def test_database_url_must_use_async_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", "postgresql://slotwise:test@db:5432/slotwise")
    with pytest.raises(ValidationError):
        Settings()


def test_csv_lists_are_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_ALLOWED_HOSTS", "localhost, api ,nginx")
    monkeypatch.setenv("REDIS_QUEUE_NAMES", "celery,priority")
    settings = Settings()
    assert settings.app.allowed_hosts == ["localhost", "api", "nginx"]
    assert settings.redis.queue_names == ["celery", "priority"]


def test_secrets_are_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECURITY_SECRET_KEY", "super-secret-value")
    settings = Settings()
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.security.secret_key)
