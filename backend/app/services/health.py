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
from typing import Final

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.database import get_engine
from app.schemas.health import DependencyCheck, ReadinessResponse

logger = logging.getLogger(__name__)

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
        async def probe() -> None:
            engine = get_engine()
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

        return await self._measure("postgres", probe())

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
