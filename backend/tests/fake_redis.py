"""In-memory Redis double for unit and API tests.

Only the commands the authentication code uses are implemented. ``fail = True``
raises the same exception class as a real network failure so the fail-closed
policy can be tested without stopping a server.
"""

from __future__ import annotations

from typing import Any

from redis.exceptions import ConnectionError as RedisConnectionError


class FakeRedis:
    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, float]] = {}
        self.kv: dict[str, str] = {}
        self.expiry: dict[str, int] = {}
        self.fail = False

    def _guard(self) -> None:
        if self.fail:
            raise RedisConnectionError("simulated Redis outage")

    async def zremrangebyscore(self, key: str, minimum: float, maximum: float) -> int:
        self._guard()
        bucket = self.zsets.get(key, {})
        doomed = [member for member, score in bucket.items() if minimum <= score <= maximum]
        for member in doomed:
            bucket.pop(member, None)
        return len(doomed)

    async def zcard(self, key: str) -> int:
        self._guard()
        return len(self.zsets.get(key, {}))

    async def zrange(
        self, key: str, start: int, end: int, *, withscores: bool = False
    ) -> list[Any]:
        self._guard()
        ordered = sorted(self.zsets.get(key, {}).items(), key=lambda item: item[1])
        stop = None if end == -1 else end + 1
        selected = ordered[start:stop]
        if withscores:
            return [(member, score) for member, score in selected]
        return [member for member, _score in selected]

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self._guard()
        bucket = self.zsets.setdefault(key, {})
        added = sum(1 for member in mapping if member not in bucket)
        bucket.update(mapping)
        return added

    async def expire(self, key: str, seconds: int) -> bool:
        self._guard()
        self.expiry[key] = seconds
        return True

    async def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self._guard()
        self.kv[key] = value
        if ex is not None:
            self.expiry[key] = ex
        return True

    async def getdel(self, key: str) -> str | None:
        self._guard()
        self.expiry.pop(key, None)
        return self.kv.pop(key, None)

    async def ping(self) -> bool:
        self._guard()
        return True

    async def aclose(self) -> None:
        return None
