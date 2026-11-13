"""Redis sliding-window throttling for authentication surfaces.

Design decision (recorded here and covered by tests): authentication endpoints
fail closed when Redis is unavailable. A login attempt that cannot be counted
must not be allowed to proceed unthrottled, so callers translate a Redis error
into ``DEPENDENCY_UNAVAILABLE`` (503) rather than guessing. Durable lockout is
kept in PostgreSQL, so a Redis outage cannot reset an account's lock state and
the API never crashes on a cache failure.

The window is a sorted set of request timestamps. It is pruned on every call and
the member includes a random suffix so two requests in the same clock tick do
not collide. A small race between prune/count/insert is acceptable for abuse
throttling; correctness never depends on Redis.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from app.core.redis import RedisClient
from app.core.security import hash_token


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    retry_after: int = 0


async def check_sliding_window(
    redis: RedisClient,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> LimitDecision:
    now = time.time()
    threshold = now - window_seconds
    await redis.zremrangebyscore(key, 0, threshold)
    current = int(await redis.zcard(key))
    if current >= limit:
        oldest = await redis.zrange(key, 0, 0, withscores=True)
        retry_after = window_seconds
        if oldest:
            score = float(oldest[0][1])
            retry_after = max(1, int(window_seconds - (now - score)) + 1)
        return LimitDecision(allowed=False, retry_after=retry_after)
    member = f"{now:.6f}:{uuid.uuid4().hex}"
    await redis.zadd(key, {member: now})
    await redis.expire(key, window_seconds + 1)
    return LimitDecision(allowed=True)


def login_ip_key(ip: str) -> str:
    return f"rl:auth:login:ip:{ip}"


def login_account_key(email: str) -> str:
    # Hashing keeps email addresses out of Redis keys and slow-log output.
    return f"rl:auth:login:account:{hash_token(email.strip().lower())}"


def refresh_key(ip: str) -> str:
    return f"rl:auth:refresh:ip:{ip}"


def ticket_key(user_id: str) -> str:
    return f"rl:auth:ticket:user:{user_id}"


def sensor_key(prefix: str, ip: str) -> str:
    return f"rl:auth:sensor:{prefix}:{ip}"
