"""Unit tests for the Phase 3 authentication primitives.

Everything here runs without PostgreSQL or Redis. The Redis-dependent parts use a
small in-memory double; the real-Redis behaviour (TTL, GETDEL atomicity) is
covered in ``tests/integration/test_redis_auth.py``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings, reset_settings_cache
from app.core.rate_limit import check_sliding_window
from app.core.security import (
    COMMON_PASSWORDS,
    PasswordPolicyCheckError,
    TokenValidationError,
    create_access_token,
    decode_access_token,
    hash_password,
    new_sensor_key,
    parse_sensor_key,
    password_needs_rehash,
    reset_password_hasher_cache,
    validate_new_password,
    verify_dummy_password,
    verify_password,
    verify_sensor_key,
)
from app.core.tickets import consume_ws_ticket, issue_ws_ticket
from app.models.enums import RoleName
from tests.fake_redis import FakeRedis

STRONG = "Correct-Horse-Battery-Staple-2026!"


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> Any:
    reset_settings_cache()
    reset_password_hasher_cache()
    monkeypatch.setenv("APP_ENV", "test")
    yield
    reset_settings_cache()
    reset_password_hasher_cache()


# --------------------------------------------------------------- password policy


def test_password_policy_accepts_a_strong_password() -> None:
    validate_new_password(STRONG, email="analyst@example.com", settings=Settings())


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("Short1!", "too_short"),
        ("passwordpassword", "common_password"),
        ("alllowercase123", "insufficient_character_classes"),
        ("analyst-pass-123", "contains_email"),
    ],
)
def test_password_policy_rejects_weak_values(password: str, reason: str) -> None:
    with pytest.raises(PasswordPolicyCheckError) as excinfo:
        validate_new_password(password, email="analyst@example.com", settings=Settings())
    assert reason in excinfo.value.reasons


def test_password_policy_rejects_reuse_of_current_password() -> None:
    current = hash_password(STRONG)
    with pytest.raises(PasswordPolicyCheckError) as excinfo:
        validate_new_password(STRONG, current_hash=current, settings=Settings())
    assert "same_as_current" in excinfo.value.reasons


def test_common_password_denylist_is_lowercase() -> None:
    assert all(item == item.lower() for item in COMMON_PASSWORDS)


# ------------------------------------------------------------------- hashing


def test_argon2_hash_verifies_and_never_contains_the_password() -> None:
    stored = hash_password(STRONG)
    assert stored.startswith("$argon2id$")
    assert STRONG not in stored
    assert verify_password(STRONG, stored)
    assert not verify_password(STRONG + "x", stored)


def test_password_needs_rehash_when_cost_changes() -> None:
    settings = Settings()
    stored = hash_password(STRONG, settings=settings)
    assert not password_needs_rehash(stored, settings=settings)

    settings.security.argon2_time_cost = settings.security.argon2_time_cost + 1
    reset_password_hasher_cache()
    assert password_needs_rehash(stored, settings=settings)


def test_dummy_password_verification_is_safe_for_unknown_users() -> None:
    # Must complete without raising and must not be distinguishable by exception.
    assert verify_dummy_password("whatever-the-attacker-sent", settings=Settings()) is None


# ----------------------------------------------------------------------- JWT


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _forge(
    settings: Settings,
    *,
    exp_offset: int = 300,
    issuer: str | None = None,
    audience: str | None = None,
    algorithm: str | None = None,
    kid: str | None = None,
) -> str:
    security = settings.security
    alg = algorithm or security.jwt_algorithm
    now = datetime.now(UTC)
    payload = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "role": "ANALYST",
        "jti": "test-jti",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_offset)).timestamp()),
        "iss": issuer or security.jwt_issuer,
        "aud": audience or security.jwt_audience,
    }
    header = {"alg": alg, "typ": "JWT", "kid": kid or security.jwt_key_id}
    signing_input = (
        f"{_b64(json.dumps(header, separators=(',', ':'), sort_keys=True).encode())}."
        f"{_b64(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())}"
    )
    if alg.lower() == "none":
        return signing_input + "."
    digest = hmac.new(
        security.active_jwt_secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return signing_input + "." + _b64(digest)


def test_access_token_round_trip() -> None:
    settings = Settings()
    token = create_access_token(
        "11111111-1111-1111-1111-111111111111", RoleName.ANALYST, settings=settings
    )
    claims = decode_access_token(token, settings=settings)
    assert claims.role is RoleName.ANALYST
    assert claims.subject.int != 0
    assert claims.expires_at > claims.issued_at


def test_expired_token_is_reported_as_expired() -> None:
    settings = Settings()
    token = _forge(settings, exp_offset=-3600)
    with pytest.raises(TokenValidationError) as excinfo:
        decode_access_token(token, settings=settings)
    assert excinfo.value.expired is True


def test_wrong_audience_and_issuer_are_rejected() -> None:
    settings = Settings()
    with pytest.raises(TokenValidationError, match="bad_audience"):
        decode_access_token(_forge(settings, audience="someone-else"), settings=settings)
    with pytest.raises(TokenValidationError, match="bad_issuer"):
        decode_access_token(_forge(settings, issuer="someone-else"), settings=settings)


def test_alg_none_is_rejected() -> None:
    settings = Settings()
    with pytest.raises(TokenValidationError, match="algorithm_not_allowed"):
        decode_access_token(_forge(settings, algorithm="none"), settings=settings)


def test_tampered_signature_is_rejected() -> None:
    settings = Settings()
    token = create_access_token(
        "11111111-1111-1111-1111-111111111111", RoleName.ADMIN, settings=settings
    )
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(TokenValidationError, match="bad_signature"):
        decode_access_token(tampered, settings=settings)


def test_unknown_kid_is_rejected() -> None:
    settings = Settings()
    with pytest.raises(TokenValidationError, match="unknown_kid"):
        decode_access_token(_forge(settings, kid="retired-key"), settings=settings)


def test_rotated_previous_key_is_accepted() -> None:
    settings = Settings()
    old_secret = "old-key-secret-0123456789abcdef0123456789abcdef"
    token = _forge_with_secret(settings, kid="old-key", secret=old_secret)
    settings.security.jwt_previous_keys = {"old-key": old_secret}
    claims = decode_access_token(token, settings=settings)
    assert claims.role is RoleName.ANALYST


def _forge_with_secret(settings: Settings, *, kid: str, secret: str) -> str:
    security = settings.security
    now = datetime.now(UTC)
    header = {"alg": "HS256", "typ": "JWT", "kid": kid}
    payload = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "role": "ANALYST",
        "jti": "test-jti",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iss": security.jwt_issuer,
        "aud": security.jwt_audience,
    }
    signing_input = (
        f"{_b64(json.dumps(header, separators=(',', ':'), sort_keys=True).encode())}."
        f"{_b64(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())}"
    )
    digest = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64(digest)


# ---------------------------------------------------------------- sensor keys


def test_sensor_key_format_and_constant_time_verification() -> None:
    issued = new_sensor_key()
    parsed = parse_sensor_key(issued.raw)
    assert parsed is not None
    prefix, secret = parsed
    assert prefix == issued.prefix
    assert verify_sensor_key(secret, issued.hash)
    assert not verify_sensor_key(secret + "x", issued.hash)


@pytest.mark.parametrize("bad", ["", "no-dot", "prefix.secret", "sk123.abc", " sk1.zz"])
def test_invalid_sensor_keys_are_not_parsed(bad: str) -> None:
    assert parse_sensor_key(bad) is None


# --------------------------------------------------------------- fake redis


async def test_sliding_window_denies_after_limit() -> None:
    redis = FakeRedis()
    decisions = [
        await check_sliding_window(redis, key="rl:test", limit=3, window_seconds=60)
        for _ in range(3)
    ]
    assert all(decision.allowed for decision in decisions)
    denied = await check_sliding_window(redis, key="rl:test", limit=3, window_seconds=60)
    assert denied.allowed is False
    assert denied.retry_after >= 1


async def test_sliding_window_raises_when_redis_is_down() -> None:
    redis = FakeRedis()
    redis.fail = True
    with pytest.raises(RedisConnectionError):
        await check_sliding_window(redis, key="rl:test", limit=3, window_seconds=60)


async def test_websocket_ticket_is_single_use_and_ip_bound() -> None:
    redis = FakeRedis()
    user_id = __import__("uuid").uuid4()
    ip_good = "198.51.100.7"
    ip_bad = "203.0.113.9"
    ticket = await issue_ws_ticket(redis, user_id=user_id, ip_address=ip_good, ttl_seconds=30)

    assert await consume_ws_ticket(redis, ticket, ip_address=ip_bad) is None
    # The wrong IP consumed the ticket; issue another to prove the happy path.
    ticket = await issue_ws_ticket(redis, user_id=user_id, ip_address=ip_good, ttl_seconds=30)
    assert await consume_ws_ticket(redis, ticket, ip_address=ip_good) == user_id
    # Second use of the same ticket fails: GETDEL already removed it.
    assert await consume_ws_ticket(redis, ticket, ip_address=ip_good) is None


async def test_rate_limit_window_expires_members() -> None:
    redis = FakeRedis()
    await check_sliding_window(redis, key="rl:expire", limit=1, window_seconds=1)
    # Move the stored timestamp outside the window instead of sleeping.
    for key in redis.zsets:
        redis.zsets[key] = {member: time.time() - 10 for member in redis.zsets[key]}
    decision = await check_sliding_window(redis, key="rl:expire", limit=1, window_seconds=1)
    assert decision.allowed is True
