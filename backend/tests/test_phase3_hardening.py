"""Phase 3 hardening tests: gap closure and security verification.

Tests that don't require PostgreSQL or Redis run here as unit tests.
DB-dependent tests are in tests/db/test_phase3_hardening_db.py.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.api.deps import iter_api_routes
from app.core.security import create_access_token, decode_access_token
from app.models.enums import RoleName


def test_me_endpoint_exists_at_canonical_path(app: Any) -> None:
    """TRD contract: GET /api/v1/me is the canonical path."""
    paths = [route.path for route in iter_api_routes(app.routes)]
    assert "/api/v1/me" in paths
    # Alias at /auth/me still works for backwards compatibility.
    assert "/api/v1/auth/me" in paths


def test_jwt_never_contains_permissions() -> None:
    """Permissions are resolved server-side from role, never embedded in JWT."""
    from app.core.config import Settings

    settings = Settings()
    token = create_access_token(
        "11111111-1111-1111-1111-111111111111", RoleName.ADMIN, settings=settings
    )
    # Decode manually to check raw claims without validation side-effects.
    import base64

    parts = token.split(".")
    payload_b64 = parts[1]
    # Add padding if needed
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))

    assert "permissions" not in payload
    assert "role" in payload
    assert payload["role"] == "ADMIN"


def test_jwt_rejects_alg_none() -> None:
    """alg=none bypass attempt is rejected."""
    import base64
    import json

    from app.core.config import Settings
    from app.core.security import TokenValidationError

    settings = Settings()
    header = {"alg": "none", "typ": "JWT", "kid": settings.security.jwt_key_id}
    payload = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "role": "ADMIN",
        "jti": "test",
        "iat": 1700000000,
        "exp": 1700003600,
        "iss": settings.security.jwt_issuer,
        "aud": settings.security.jwt_audience,
    }

    def b64(data: dict[str, Any]) -> str:
        return (
            base64.urlsafe_b64encode(
                json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
            )
            .decode()
            .rstrip("=")
        )

    fake_token = f"{b64(header)}.{b64(payload)}."
    with pytest.raises(TokenValidationError, match="algorithm_not_allowed"):
        decode_access_token(fake_token, settings=settings)


def test_jwt_rejects_unknown_kid() -> None:
    """Tokens with unknown kid are rejected."""
    from app.core.config import Settings
    from app.core.security import TokenValidationError, create_access_token

    settings = Settings()
    # Create a valid token then tamper with kid in header
    token = create_access_token(
        "11111111-1111-1111-1111-111111111111", RoleName.VIEWER, settings=settings
    )
    parts = token.split(".")
    import base64
    import json

    header = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4)))
    header["kid"] = "unknown-kid-999"

    def b64(data: dict[str, Any]) -> str:
        return (
            base64.urlsafe_b64encode(
                json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
            )
            .decode()
            .rstrip("=")
        )

    tampered = f"{b64(header)}.{parts[1]}.{parts[2]}"
    with pytest.raises(TokenValidationError, match="unknown_kid"):
        decode_access_token(tampered, settings=settings)


def test_jwt_rejects_wrong_issuer() -> None:
    """Tokens from wrong issuer are rejected."""
    import base64
    import hashlib
    import hmac
    import json
    from datetime import UTC, datetime, timedelta

    from app.core.config import Settings
    from app.core.security import TokenValidationError

    settings = Settings()
    now = datetime.now(UTC)
    header = {"alg": "HS256", "typ": "JWT", "kid": settings.security.jwt_key_id}
    payload = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "role": "ANALYST",
        "jti": "test",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "iss": "evil-issuer",  # Wrong!
        "aud": settings.security.jwt_audience,
    }

    def b64(data: dict[str, Any]) -> str:
        raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    signing_input = f"{b64(header)}.{b64(payload)}"
    sig = hmac.new(
        settings.security.active_jwt_secret.encode(),
        signing_input.encode(),
        hashlib.sha256,
    ).digest()
    token = f"{signing_input}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"

    with pytest.raises(TokenValidationError, match="bad_issuer"):
        decode_access_token(token, settings=settings)


def test_jwt_rejects_wrong_audience() -> None:
    """Tokens for wrong audience are rejected."""
    import base64
    import hashlib
    import hmac
    import json
    from datetime import UTC, datetime, timedelta

    from app.core.config import Settings
    from app.core.security import TokenValidationError

    settings = Settings()
    now = datetime.now(UTC)
    header = {"alg": "HS256", "typ": "JWT", "kid": settings.security.jwt_key_id}
    payload = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "role": "VIEWER",
        "jti": "test",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "iss": settings.security.jwt_issuer,
        "aud": "wrong-audience",  # Wrong!
    }

    def b64(data: dict[str, Any]) -> str:
        raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    signing_input = f"{b64(header)}.{b64(payload)}"
    sig = hmac.new(
        settings.security.active_jwt_secret.encode(),
        signing_input.encode(),
        hashlib.sha256,
    ).digest()
    token = f"{signing_input}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"

    with pytest.raises(TokenValidationError, match="bad_audience"):
        decode_access_token(token, settings=settings)
