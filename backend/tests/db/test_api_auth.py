"""Authentication API behaviour against real PostgreSQL.

Redis is an in-memory double here because no Redis server is available on the
developer workstation. The throttling/ticket contract is exercised against a real
Redis in ``tests/integration/test_redis_auth.py`` (CI only).

Access tokens, refresh rotation, reuse detection, CSRF, lockout, fail-closed
behaviour and the ``must_change_password`` gate are all asserted through HTTP so
the middleware, dependency and service layers are tested together.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.core.security import hash_token
from app.core.tickets import consume_ws_ticket
from app.models.audit import AuditLog
from app.models.identity import RefreshToken, Role, User
from tests.db.conftest import CSRF_HEADERS

pytestmark = pytest.mark.db

PASSWORD = "Correct-Horse-Battery-2026!"
NEW_PASSWORD = "New-Correct-Horse-Battery-2027!"
COOKIE_NAME = "__Secure-slotwise_refresh"


def _cookie_header(raw_token: str) -> dict[str, str]:
    """Send an explicit cookie so a rotated token can be replayed deterministically."""
    return {"Cookie": f"{COOKIE_NAME}={raw_token}"}


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _claims(token: str) -> dict[str, Any]:
    _header, payload, _signature = token.split(".")
    return json.loads(_b64decode(payload))


# ------------------------------------------------------------------- sign-in


async def test_login_returns_access_token_and_secure_refresh_cookie(
    api_client: Any, make_user: Any, settings: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)

    response = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.security.access_token_expire_minutes * 60
    assert body["user"]["role"] == "ANALYST"
    assert body["user"]["must_change_password"] is False
    assert "refresh_token" not in body

    cookie = response.headers["set-cookie"]
    assert COOKIE_NAME in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert f"Path={settings.security.refresh_cookie_path}" in cookie

    # The token carries identity only; permissions are resolved server-side.
    claims = _claims(body["access_token"])
    assert set(claims) == {"sub", "role", "jti", "iat", "exp", "iss", "aud"}
    assert "permissions" not in claims
    assert claims["role"] == "ANALYST"
    assert claims["exp"] - claims["iat"] == 15 * 60


async def test_access_token_is_accepted_and_me_reports_permissions(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD, role="ANALYST")
    headers = await login_headers(api_client, "analyst@example.com", PASSWORD)

    response = await api_client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["role"] == "ANALYST"
    assert "events:read" in body["permissions"]
    assert "users:manage" not in body["permissions"]


async def test_unknown_email_and_wrong_password_are_indistinguishable(
    api_client: Any, make_user: Any, api_session_factory: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)

    unknown = await api_client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    wrong = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": "incorrect-pass"}
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["code"] == wrong.json()["code"] == "AUTH_INVALID_CREDENTIALS"
    assert unknown.json()["message"] == wrong.json()["message"]
    assert "set-cookie" not in {key.lower() for key in unknown.headers}

    async with api_session_factory() as session:
        failures = (
            (await session.execute(select(AuditLog).where(AuditLog.action == "AUTH_LOGIN_FAILURE")))
            .scalars()
            .all()
        )
    assert len(failures) == 2
    for entry in failures:
        rendered = json.dumps(entry.after or {})
        assert "nobody@example.com" not in rendered
        assert "analyst@example.com" not in rendered
        assert "incorrect-pass" not in rendered


async def test_durable_lockout_then_admin_unlock(
    api_client: Any, make_user: Any, login_headers: Any, settings: Any
) -> None:
    settings.security.lockout_threshold = 3
    analyst_id = await make_user(email="analyst@example.com", password=PASSWORD)
    await make_user(email="admin@example.com", password=PASSWORD, role="ADMIN")

    for _ in range(3):
        response = await api_client.post(
            "/api/v1/auth/login",
            json={"email": "analyst@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401

    blocked = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "AUTH_ACCOUNT_LOCKED"

    admin_headers = await login_headers(api_client, "admin@example.com", PASSWORD)
    unlock = await api_client.post(f"/api/v1/users/{analyst_id}/unlock", headers=admin_headers)
    assert unlock.status_code == 200, unlock.text
    assert unlock.json()["locked_until"] is None

    recovered = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )
    assert recovered.status_code == 200, recovered.text


# -------------------------------------------------------------------- refresh


async def test_refresh_rotates_the_token(api_client: Any, make_user: Any) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    login = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )
    first = login.cookies.get(COOKIE_NAME)
    assert first

    refreshed = await api_client.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)

    assert refreshed.status_code == 200, refreshed.text
    second = refreshed.cookies.get(COOKIE_NAME)
    assert second and second != first
    assert refreshed.json()["access_token"]


async def test_replayed_refresh_token_revokes_the_whole_family(
    api_client: Any, make_user: Any, api_session_factory: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    login = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )
    first = login.cookies.get(COOKIE_NAME)
    assert first

    rotated = await api_client.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)
    assert rotated.status_code == 200
    second = rotated.cookies.get(COOKIE_NAME)
    assert second

    replay = await api_client.post(
        "/api/v1/auth/refresh",
        headers={**CSRF_HEADERS, **_cookie_header(first)},
    )
    assert replay.status_code == 401
    assert replay.json()["code"] == "AUTH_REFRESH_REUSE_DETECTED"

    # Reuse detection revokes the family, so the replacement is dead too.
    family_use = await api_client.post(
        "/api/v1/auth/refresh",
        headers={**CSRF_HEADERS, **_cookie_header(second)},
    )
    assert family_use.status_code == 401
    assert family_use.json()["code"] == "AUTH_REFRESH_REJECTED_REVOKED_FAMILY"

    async with api_session_factory() as session:
        rows = (await session.execute(select(RefreshToken))).scalars().all()
        assert rows
        assert all(row.revoked_at is not None for row in rows)

        # Exactly ONE reuse detection (replay of first token)
        reuse_audit = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "AUTH_REFRESH_REUSE_DETECTED")
                )
            )
            .scalars()
            .all()
        )
        assert len(reuse_audit) == 1

        # Exactly ONE revoked family rejection (use of second after family revocation)
        revoked_family_audit = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "AUTH_REFRESH_REJECTED_REVOKED_FAMILY"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(revoked_family_audit) == 1

        # Token values are redacted but metadata like token_id is allowed
        for entry in reuse_audit + revoked_family_audit:
            after_json = json.dumps(entry.after or {})
            # No actual token secrets
            assert "sk_" not in after_json and len(after_json) < 500


@pytest.mark.parametrize(
    ("headers", "reason"),
    [
        ({}, "csrf_header_invalid"),
        ({"X-Requested-With": "wrong"}, "csrf_header_invalid"),
        ({**CSRF_HEADERS, "Origin": "https://evil.example"}, "origin_not_allowed"),
    ],
)
async def test_refresh_rejects_missing_csrf_or_foreign_origin(
    api_client: Any, make_user: Any, headers: dict[str, str], reason: str
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )

    response = await api_client.post("/api/v1/auth/refresh", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    assert response.json()["details"]["reason"] == reason


async def test_refresh_accepts_an_allow_listed_origin(
    api_client: Any, make_user: Any, settings: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )

    response = await api_client.post(
        "/api/v1/auth/refresh",
        headers={**CSRF_HEADERS, "Origin": settings.app.cors_origins[0]},
    )

    assert response.status_code == 200, response.text


async def test_logout_revokes_the_family_and_clears_the_cookie(
    api_client: Any, make_user: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    login = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )
    token = login.cookies.get(COOKIE_NAME)
    assert token

    logout = await api_client.post("/api/v1/auth/logout", headers=CSRF_HEADERS)
    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]

    replay = await api_client.post(
        "/api/v1/auth/refresh", headers={**CSRF_HEADERS, **_cookie_header(token)}
    )
    assert replay.status_code == 401
    assert replay.json()["code"] == "AUTH_REFRESH_REJECTED_REVOKED_FAMILY"


async def test_logout_all_revokes_every_session(
    api_client: Any, make_user: Any, login_headers: Any, api_session_factory: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    first = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )
    first_token = first.cookies.get(COOKIE_NAME)
    second = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )
    second_token = second.cookies.get(COOKIE_NAME)
    assert first_token and second_token and first_token != second_token

    headers = await login_headers(api_client, "analyst@example.com", PASSWORD)
    response = await api_client.post("/api/v1/auth/logout-all", headers=headers)
    assert response.status_code == 204

    for token in (first_token, second_token):
        replay = await api_client.post(
            "/api/v1/auth/refresh", headers={**CSRF_HEADERS, **_cookie_header(token)}
        )
        assert replay.status_code == 401

    async with api_session_factory() as session:
        rows = (await session.execute(select(RefreshToken))).scalars().all()
        assert all(row.revoked_at is not None for row in rows)


# --------------------------------------------------------------- throttling


async def test_rate_limit_returns_retry_after(
    api_client: Any, make_user: Any, settings: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    settings.security.rate_limit_login_account_per_minute = 2

    for _ in range(2):
        await api_client.post(
            "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
        )
    limited = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )

    assert limited.status_code == 429
    assert limited.json()["code"] == "AUTH_RATE_LIMITED"
    assert int(limited.headers["retry-after"]) >= 1


async def test_redis_outage_fails_closed(api_client: Any, make_user: Any, fake_redis: Any) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    fake_redis.fail = True

    response = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )

    # Documented decision: uncounted authentication fails closed, never open.
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


# ---------------------------------------------------------- WebSocket ticket


async def test_ws_ticket_is_single_use_and_ip_bound(
    api_client: Any, make_user: Any, login_headers: Any, fake_redis: Any
) -> None:
    user_id = await make_user(email="analyst@example.com", password=PASSWORD)
    headers = await login_headers(api_client, "analyst@example.com", PASSWORD)

    issued = await api_client.post("/api/v1/auth/ws-ticket", headers=headers)
    assert issued.status_code == 200, issued.text
    ticket = issued.json()["ticket"]
    assert issued.json()["expires_in"] == 30

    # A request from another address must not redeem the ticket, and must not
    # burn it either: the client that owns the address can still use it once.
    assert await consume_ws_ticket(fake_redis, ticket, ip_address="203.0.113.9") is None
    assert await consume_ws_ticket(fake_redis, ticket, ip_address="127.0.0.1") == user_id
    assert await consume_ws_ticket(fake_redis, ticket, ip_address="127.0.0.1") is None


async def test_ws_ticket_happy_path(
    api_client: Any, make_user: Any, login_headers: Any, fake_redis: Any
) -> None:
    user_id = await make_user(email="analyst@example.com", password=PASSWORD)
    headers = await login_headers(api_client, "analyst@example.com", PASSWORD)

    issued = await api_client.post("/api/v1/auth/ws-ticket", headers=headers)
    ticket = issued.json()["ticket"]

    assert await consume_ws_ticket(fake_redis, ticket, ip_address="127.0.0.1") == user_id
    assert await consume_ws_ticket(fake_redis, ticket, ip_address="127.0.0.1") is None


# ------------------------------------------------------- password lifecycle


async def test_must_change_password_blocks_protected_routes(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD, must_change_password=True)
    headers = await login_headers(api_client, "analyst@example.com", PASSWORD)

    me = await api_client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True

    blocked = await api_client.get("/api/v1/users", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["details"]["reason"] == "password_change_required"

    ticket = await api_client.post("/api/v1/auth/ws-ticket", headers=headers)
    assert ticket.status_code == 403
    assert ticket.json()["details"]["reason"] == "password_change_required"


async def test_change_password_clears_flag_and_revokes_sessions(
    api_client: Any, make_user: Any, login_headers: Any, api_session_factory: Any
) -> None:
    user_id = await make_user(
        email="analyst@example.com", password=PASSWORD, must_change_password=True
    )
    headers = await login_headers(api_client, "analyst@example.com", PASSWORD)

    response = await api_client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 204, response.text

    async with api_session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert user.must_change_password is False
        tokens = (await session.execute(select(RefreshToken))).scalars().all()
        assert all(token.revoked_at is not None for token in tokens)

    unlocked = await api_client.get("/api/v1/auth/me", headers=headers)
    assert unlocked.status_code == 200
    assert unlocked.json()["must_change_password"] is False

    relogin = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": NEW_PASSWORD}
    )
    assert relogin.status_code == 200


async def test_change_password_enforces_the_policy(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    headers = await login_headers(api_client, "analyst@example.com", PASSWORD)

    response = await api_client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "passwordpassword"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "PASSWORD_POLICY_VIOLATION"
    assert "common_password" in response.json()["details"]["reasons"]


async def test_change_password_rejects_a_wrong_current_password(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    headers = await login_headers(api_client, "analyst@example.com", PASSWORD)

    response = await api_client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "not-the-real-one", "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID_CREDENTIALS"


# ------------------------------------------------------------ token handling


async def test_expired_and_forged_tokens_are_typed_errors(
    api_client: Any, make_user: Any, settings: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    login = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )
    token = login.json()["access_token"]
    header_b64, payload_b64, signature_b64 = token.split(".")

    # Forge a token with a valid signature but an expiry in the past.
    payload = json.loads(_b64decode(payload_b64))
    payload["iat"] = int((datetime.now(UTC) - timedelta(hours=2)).timestamp())
    payload["exp"] = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())
    forged_payload = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    signing_input = f"{header_b64}.{forged_payload}"
    secret = settings.security.active_jwt_secret
    digest = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    expired = f"{signing_input}.{signature}"

    expired_response = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}
    )
    assert expired_response.status_code == 401
    assert expired_response.json()["code"] == "AUTH_TOKEN_EXPIRED"

    # Flip one character so the signature cannot accidentally stay valid.
    flipped = ("A" if signature_b64[0] != "A" else "B") + signature_b64[1:]
    forged = f"{header_b64}.{payload_b64}.{flipped}"
    forged_response = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}
    )
    assert forged_response.status_code == 401
    assert forged_response.json()["code"] == "AUTH_TOKEN_INVALID"


async def test_access_token_for_a_deactivated_account_is_rejected(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    analyst_id = await make_user(email="analyst@example.com", password=PASSWORD)
    await make_user(email="admin@example.com", password=PASSWORD, role="ADMIN")
    admin_headers = await login_headers(api_client, "admin@example.com", PASSWORD)

    headers = await login_headers(api_client, "analyst@example.com", PASSWORD)
    assert (await api_client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    deactivate = await api_client.post(
        f"/api/v1/users/{analyst_id}/deactivate", headers=admin_headers
    )
    assert deactivate.status_code == 200, deactivate.text

    refused = await api_client.get("/api/v1/auth/me", headers=headers)
    assert refused.status_code == 401
    assert refused.json()["code"] == "AUTH_TOKEN_INVALID"


async def test_refresh_token_is_stored_only_as_a_digest(
    api_client: Any, make_user: Any, api_session_factory: Any
) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    login = await api_client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": PASSWORD}
    )
    raw = login.cookies.get(COOKIE_NAME)
    assert raw

    async with api_session_factory() as session:
        row = await session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
        )
        assert row is not None
        stored = await session.scalar(select(RefreshToken))
        assert stored is not None
        assert stored.token_hash != raw
        assert len(stored.token_hash) == 64


async def test_role_claim_comes_from_the_database_not_the_token(
    api_client: Any, make_user: Any, login_headers: Any, api_session_factory: Any
) -> None:
    """A promoted role takes effect immediately even though the JWT is unchanged."""
    analyst_id = await make_user(email="analyst@example.com", password=PASSWORD, role="ANALYST")
    await make_user(email="admin@example.com", password=PASSWORD, role="ADMIN")
    analyst_headers = await login_headers(api_client, "analyst@example.com", PASSWORD)
    admin_headers = await login_headers(api_client, "admin@example.com", PASSWORD)

    # The token still says ANALYST; the effective role is read from PostgreSQL.
    assert _claims(analyst_headers["Authorization"].split()[1])["role"] == "ANALYST"

    promoted = await api_client.patch(
        f"/api/v1/users/{analyst_id}", headers=admin_headers, json={"role": "ADMIN"}
    )
    assert promoted.status_code == 200, promoted.text

    # Same bearer token, new effective role read from PostgreSQL.
    me = await api_client.get("/api/v1/auth/me", headers=analyst_headers)
    assert me.status_code == 200
    assert me.json()["role"] == "ADMIN"
    assert "users:manage" in me.json()["permissions"]

    # Verify in the database - fetch admin role ID to compare
    async with api_session_factory() as session:
        admin_role = (await session.execute(select(Role).where(Role.name == "ADMIN"))).scalar_one()
        user = await session.get(User, analyst_id)
        assert user is not None
        assert user.role_id == admin_role.id


async def test_missing_bearer_token_is_unauthorized(api_client: Any, make_user: Any) -> None:
    await make_user(email="analyst@example.com", password=PASSWORD)
    response = await api_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
