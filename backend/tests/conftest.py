"""Shared test configuration.

Integration tests use TEST_REDIS_URL when present and skip otherwise. Unit tests
never require external services.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from httpx import ASGITransport

from app.core.config import Settings, reset_settings_cache
from app.main import create_app

# Set deterministic test values before any application module reads settings.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECURITY_SECRET_KEY", "test-only-secret-key-0123456789abcdef")
os.environ.setdefault("MINIO_SECRET_KEY", "test-only-minio-secret")

# Check for TEST_* env vars first (e.g., from CI/bootstrap), fall back to localhost
test_db_url = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://slotwise_app:slotwise_app@127.0.0.1:5432/slotwise_test",
)
test_migration_url = os.getenv(
    "TEST_MIGRATION_URL",
    "postgresql+asyncpg://slotwise_migrator:slotwise_migrator@127.0.0.1:5432/slotwise_test",
)
os.environ.setdefault("DATABASE_URL", test_db_url)
os.environ.setdefault("DATABASE_MIGRATION_URL", test_migration_url)

os.environ.setdefault("REDIS_URL", os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/0"))
os.environ.setdefault("OPENSEARCH_URL", "http://localhost:9200")
os.environ.setdefault("MINIO_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("MLFLOW_TRACKING_URI", "http://localhost:5000")


@pytest.fixture
def settings() -> Iterator[Settings]:
    reset_settings_cache()
    resolved = Settings()
    yield resolved
    reset_settings_cache()


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
