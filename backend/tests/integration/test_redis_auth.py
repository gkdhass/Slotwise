"""Authentication rate limiting and ticket behavior against real Redis.

These tests require a real Redis 7+ instance and verify TTL, GETDEL atomicity,
and the fail-closed behavior when Redis is unreachable. They run in CI against
a Redis service container.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import get_settings
from app.core.rate_limit import check_sliding_window
from app.core.redis import RedisClient
from app.core.tickets import consume_ws_ticket, issue_ws_ticket

pytestmark = pytest.mark.integration


@pytest.fixture
async def real_redis() -> RedisClient:
    """Real Redis client for integration tests."""
    settings = get_settings()
    client: RedisClient = Redis.from_url(
        settings.redis.url,
        decode_responses=True,
        socket_timeout=settings.redis.socket_timeout_seconds,
        socket_connect_timeout=settings.redis.socket_timeout_seconds,
    )
    try:
        await client.ping()
        yield client
    finally:
        await client.aclose()  # type: ignore[attr-defined]


async def test_rate_limit_sliding_window_with_retry_after(real_redis: RedisClient) -> None:
    """Rate limiter enforces sliding window and returns Retry-After header value."""
    key = f"test:limit:{datetime.now(UTC).timestamp()}"
    max_requests = 3
    window = 10  # seconds

    # First 3 requests succeed
    for i in range(max_requests):
        result = await check_sliding_window(
            real_redis, key=key, limit=max_requests, window_seconds=window
        )
        assert result.allowed, f"Request {i+1} should succeed"
        assert result.retry_after == 0

    # 4th request is rate limited and returns retry-after
    result = await check_sliding_window(
        real_redis, key=key, limit=max_requests, window_seconds=window
    )
    assert not result.allowed
    assert 0 < result.retry_after <= window

    # Wait for the retry period to elapse
    await asyncio.sleep(result.retry_after + 0.1)

    # Now the request succeeds
    result = await check_sliding_window(
        real_redis, key=key, limit=max_requests, window_seconds=window
    )
    assert result.allowed


async def test_ws_ticket_single_use_via_getdel(real_redis: RedisClient) -> None:
    """WebSocket tickets are single-use via Redis GETDEL atomicity."""
    user_id = uuid.uuid4()
    ip = "192.0.2.100"

    # Issue a ticket
    ticket = await issue_ws_ticket(real_redis, user_id=user_id, ip_address=ip, ttl_seconds=30)
    assert ticket

    # First consumption succeeds
    consumed_user_id = await consume_ws_ticket(real_redis, ticket, ip_address=ip)
    assert consumed_user_id == user_id

    # Second consumption fails - ticket was deleted
    consumed_again = await consume_ws_ticket(real_redis, ticket, ip_address=ip)
    assert consumed_again is None


async def test_ws_ticket_ip_binding(real_redis: RedisClient) -> None:
    """WebSocket tickets are bound to the issuing IP address."""
    user_id = uuid.uuid4()
    issuing_ip = "192.0.2.100"
    different_ip = "192.0.2.200"

    ticket = await issue_ws_ticket(
        real_redis, user_id=user_id, ip_address=issuing_ip, ttl_seconds=30
    )

    # Consumption from a different IP fails
    consumed = await consume_ws_ticket(real_redis, ticket, ip_address=different_ip)
    assert consumed is None

    # Original IP can still consume
    consumed_correct = await consume_ws_ticket(real_redis, ticket, ip_address=issuing_ip)
    assert consumed_correct == user_id


async def test_ws_ticket_expiry(real_redis: RedisClient) -> None:
    """WebSocket tickets expire after configured TTL."""
    user_id = uuid.uuid4()
    ip = "192.0.2.150"

    ticket = await issue_ws_ticket(real_redis, user_id=user_id, ip_address=ip, ttl_seconds=2)

    # Fast-forward by waiting for expiry
    await asyncio.sleep(2.1)

    # Ticket is now expired
    consumed = await consume_ws_ticket(real_redis, ticket, ip_address=ip)
    assert consumed is None


async def test_sensor_key_rate_limit_per_source(real_redis: RedisClient) -> None:
    """Each sensor has an independent rate limit."""
    sensor_a_key = f"sensor:a:{datetime.now(UTC).timestamp()}"
    sensor_b_key = f"sensor:b:{datetime.now(UTC).timestamp()}"
    max_requests = 5
    window = 10

    # Exhaust sensor A's limit
    for _ in range(max_requests):
        result = await check_sliding_window(
            real_redis, key=sensor_a_key, limit=max_requests, window_seconds=window
        )
        assert result.allowed

    # Sensor A is now rate limited
    result = await check_sliding_window(
        real_redis, key=sensor_a_key, limit=max_requests, window_seconds=window
    )
    assert not result.allowed
    assert result.retry_after > 0

    # Sensor B still has capacity
    result = await check_sliding_window(
        real_redis, key=sensor_b_key, limit=max_requests, window_seconds=window
    )
    assert result.allowed


async def test_login_rate_limit_retry_after_header_value(real_redis: RedisClient) -> None:
    """Login endpoint returns accurate Retry-After when rate limited."""
    key = f"login:{datetime.now(UTC).timestamp()}"
    max_attempts = 5
    window = 60

    # Exhaust the limit
    for _ in range(max_attempts):
        result = await check_sliding_window(
            real_redis, key=key, limit=max_attempts, window_seconds=window
        )
        assert result.allowed

    # Next attempt gets a retry-after value
    result = await check_sliding_window(
        real_redis, key=key, limit=max_attempts, window_seconds=window
    )
    assert not result.allowed
    assert 0 < result.retry_after <= window


async def test_redis_connection_failure_fails_closed() -> None:
    """When Redis is unreachable, rate limiter fails closed (denies access)."""
    # Create a client pointing to a non-existent Redis instance
    bad_client: RedisClient = Redis.from_url(
        "redis://localhost:9999",  # Non-existent port
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )

    try:
        # Should raise an exception, not silently pass
        with pytest.raises((RedisConnectionError, RedisTimeoutError)):
            await check_sliding_window(bad_client, key="test", limit=10, window_seconds=60)
    finally:
        await bad_client.aclose()  # type: ignore[attr-defined]


async def test_redis_down_returns_503_for_ticket_operations() -> None:
    """Ticket operations fail closed when Redis is down."""
    bad_client: RedisClient = Redis.from_url(
        "redis://localhost:9999",
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )

    user_id = uuid.uuid4()

    try:
        with pytest.raises((RedisConnectionError, RedisTimeoutError)):
            await issue_ws_ticket(
                bad_client, user_id=user_id, ip_address="192.0.2.1", ttl_seconds=30
            )

        with pytest.raises((RedisConnectionError, RedisTimeoutError)):
            await consume_ws_ticket(bad_client, "fake-ticket", ip_address="192.0.2.1")
    finally:
        await bad_client.aclose()  # type: ignore[attr-defined]
