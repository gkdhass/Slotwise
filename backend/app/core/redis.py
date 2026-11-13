"""Shared async Redis client.

Redis is intentionally non-durable here: it carries throttling counters and
single-use WebSocket tickets only. Nothing whose loss would corrupt state lives
in it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from redis.asyncio import Redis

from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    # ``redis.asyncio.Redis`` is generic in the type stubs but not at runtime, and
    # FastAPI evaluates dependency annotations. This alias keeps mypy strict while
    # resolving to the plain class when Python imports the module.
    RedisClient = Redis[str]
else:
    RedisClient = Redis

# ``decode_responses=True`` means every value is ``str``.
_client: RedisClient | None = None


def init_redis(settings: Settings | None = None) -> RedisClient:
    global _client
    if _client is None:
        resolved = settings or get_settings()
        _client = Redis.from_url(
            resolved.redis.url,
            decode_responses=True,
            socket_timeout=resolved.redis.socket_timeout_seconds,
            socket_connect_timeout=resolved.redis.socket_timeout_seconds,
        )
    return _client


def get_redis_client() -> RedisClient:
    """FastAPI dependency. Tests override this with an in-memory double."""
    return init_redis()


async def close_redis() -> None:
    global _client
    if _client is not None:
        # ``aclose`` exists at runtime in redis-py 5.x; the shipped type stubs
        # still expose only the synchronous ``close`` alias.
        await _client.aclose()  # type: ignore[attr-defined]
        _client = None
