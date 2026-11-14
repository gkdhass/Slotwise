"""Dependency readiness probes.

Each dependency is checked independently and reported independently. Probes only
return safe error codes (connection/timeout/status) and never echo URLs, headers
or credentials.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from functools import lru_cache
from pathlib import Path
from typing import Final

import httpx
import redis.asyncio as aioredis
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings, get_settings
from app.schemas.health import DependencyCheck, ReadinessResponse

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def expected_migration_heads() -> frozenset[str]:
    """Read the head revision(s) from the checked-in migration scripts.

    The API image ships ``alembic`` and ``alembic.ini``, so readiness compares
    the live ``alembic_version`` row with the code that is actually deployed.
    """
    config = AlembicConfig(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    return frozenset(script.get_heads())


DEPENDENCIES: Final[tuple[str, ...]] = (
    "postgres",
    "redis",
    "opensearch",
    "minio",
    "mlflow",
)


class HealthService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def _measure(self, name: str, probe: Awaitable[None]) -> DependencyCheck:
        started = time.perf_counter()
        try:
            await asyncio.wait_for(probe, timeout=self.settings.app.dependency_timeout_seconds)
        except TimeoutError:
            return DependencyCheck(
                status="error",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail="timeout",
            )
        except Exception as exc:
            logger.warning(
                "dependency_check_failed",
                extra={"dependency": name, "error_type": type(exc).__name__},
            )
            return DependencyCheck(
                status="error",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail="connection_error",
            )
        return DependencyCheck(
            status="ok",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    async def check_postgres(self) -> DependencyCheck:
        """Check connectivity and that the schema revision matches the code."""

        async def probe() -> str:
            # Use NullPool to avoid connection pool state issues across event loops
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy.pool import NullPool

            # Create temporary engine for this check
            engine = create_async_engine(
                self.settings.database.url,
                poolclass=NullPool,
                echo=False,
            )
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                    try:
                        result = await connection.execute(
                            text("SELECT version_num FROM alembic_version")
                        )
                    except DBAPIError as exc:
                        if (getattr(exc.orig, "sqlstate", None) or "") == "42P01":
                            return "migration_state_missing"
                        raise
                    current = {str(row[0]) for row in result}
                if current != expected_migration_heads():
                    return "migration_mismatch"
                return "migrations_current"
            finally:
                await engine.dispose()

        started = time.perf_counter()
        try:
            detail = await asyncio.wait_for(
                probe(), timeout=self.settings.app.dependency_timeout_seconds
            )
        except TimeoutError:
            return DependencyCheck(
                status="error",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail="timeout",
            )
        except Exception as exc:
            logger.warning(
                "dependency_check_failed",
                extra={"dependency": "postgres", "error_type": type(exc).__name__},
            )
            return DependencyCheck(
                status="error",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail="connection_error",
            )
        return DependencyCheck(
            status="ok" if detail == "migrations_current" else "error",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            detail=detail,
        )

    async def check_redis(self) -> DependencyCheck:
        async def probe() -> None:
            redis_settings = self.settings.redis
            client = aioredis.Redis.from_url(
                redis_settings.url,
                socket_connect_timeout=redis_settings.socket_timeout_seconds,
                socket_timeout=redis_settings.socket_timeout_seconds,
            )
            try:
                if not await client.ping():
                    raise ConnectionError("redis ping returned false")
            finally:
                # types-redis 4.6 lags the runtime; redis-py 5 exposes aclose().
                await client.aclose()  # type: ignore[attr-defined]

        return await self._measure("redis", probe())

    def _http_client(self, *, verify: bool = True) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.app.dependency_timeout_seconds),
            follow_redirects=False,
            verify=verify,
        )

    async def check_opensearch(self) -> DependencyCheck:
        async def probe() -> None:
            opensearch = self.settings.opensearch
            auth: tuple[str, str] | None = None
            if opensearch.username and opensearch.password:
                auth = (opensearch.username, opensearch.password.get_secret_value())
            async with self._http_client(verify=opensearch.verify_certs) as client:
                response = await client.get(
                    f"{opensearch.url.rstrip('/')}/_cluster/health",
                    auth=auth,
                )
                response.raise_for_status()

        return await self._measure("opensearch", probe())

    async def check_minio(self) -> DependencyCheck:
        async def probe() -> None:
            endpoint = self.settings.minio.endpoint.rstrip("/")
            async with self._http_client() as client:
                response = await client.get(f"{endpoint}/minio/health/live")
                response.raise_for_status()

        return await self._measure("minio", probe())

    async def check_mlflow(self) -> DependencyCheck:
        async def probe() -> None:
            mlflow = self.settings.mlflow
            url = f"{mlflow.tracking_uri.rstrip('/')}/{mlflow.health_path.lstrip('/')}"
            async with self._http_client() as client:
                response = await client.get(url)
                response.raise_for_status()

        return await self._measure("mlflow", probe())

    async def readiness(self) -> ReadinessResponse:
        checks = await asyncio.gather(
            self.check_postgres(),
            self.check_redis(),
            self.check_opensearch(),
            self.check_minio(),
            self.check_mlflow(),
        )
        report = dict(zip(DEPENDENCIES, checks, strict=True))
        overall = "ok" if all(check.status == "ok" for check in checks) else "degraded"
        return ReadinessResponse(
            status=overall,
            version=self.settings.app.version,
            environment=self.settings.app.env,
            checks=report,
        )
