"""Authentication primitives: passwords, JWTs, refresh tokens and sensor keys.

Argon2id is the password default; bcrypt remains only as an import fallback for
minimal installations. All parameters are read from validated settings, so cost
factors cannot be lowered silently through an unrelated environment variable.

The JWT codec is deliberately small and dependency-free. It implements only the
HMAC algorithms on the allow-list, rejects ``alg=none``, requires a known
``kid`` and validates every claim the API relies on. Anything that fails is a
typed ``TokenValidationError``; callers translate that into the public error
envelope without echoing the token or the secret.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from types import ModuleType
from typing import Any, Final

from starlette.responses import Response

from app.core.config import Settings, get_settings
from app.models.enums import RoleName

_ARGON2_AVAILABLE = True
try:  # pragma: no cover - exercised by the fallback test through monkeypatching
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
except ImportError:  # pragma: no cover - Argon2 is a declared dependency
    _ARGON2_AVAILABLE = False
    PasswordHasher = None  # type: ignore[assignment,misc]

_bcrypt: ModuleType | None
try:  # pragma: no cover - optional fallback backend
    import bcrypt as _bcrypt_module

    _bcrypt = _bcrypt_module
except ImportError:  # pragma: no cover - bcrypt is a declared dependency
    _bcrypt = None

_WEAK_TOKENS: Final[tuple[str, ...]] = (
    "change-me",
    "changeme",
    "change_me",
    "password",
    "passw0rd",
    "secret",
    "admin123",
    "letmein",
    "example",
    "demo",
    "test-only",
)

#: The seed command keeps its own stricter-than-required placeholder scan.
MIN_SEED_PASSWORD_LENGTH: Final[int] = 12

#: Small denylist of the passwords that dominate credential-stuffing lists.
COMMON_PASSWORDS: Final[frozenset[str]] = frozenset(
    {
        "123456789012",
        "1234567890123",
        "12345678901234",
        "password1234",
        "password12345",
        "passwordpassword",
        "qwertyuiop12",
        "qwertyuiop123",
        "letmein12345",
        "welcome12345",
        "admin1234567",
        "administrator",
        "iloveyou1234",
        "monkey123456",
        "dragon123456",
        "baseball1234",
        "football1234",
        "superman1234",
        "trustno1trustno1",
        "changeme1234",
        "changeme12345",
        "slotwise1234",
        "slotwise12345",
        "slotwise-admin",
        "slotwise-password",
    }
)


class PasswordPolicyCheckError(ValueError):
    """Raised with machine-readable reasons, never with the password itself."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__(", ".join(reasons))


def _hasher_params(settings: Settings) -> tuple[int, int, int]:
    security = settings.security
    return security.argon2_time_cost, security.argon2_memory_cost, security.argon2_parallelism


@lru_cache(maxsize=8)
def _build_hasher(time_cost: int, memory_cost: int, parallelism: int) -> Any:
    if not _ARGON2_AVAILABLE:
        return None
    return PasswordHasher(
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=32,
        salt_len=16,
    )


def _hasher(settings: Settings | None = None) -> Any:
    return _build_hasher(*_hasher_params(settings or get_settings()))


def reset_password_hasher_cache() -> None:
    """Test helper: settings mutations must rebuild the Argon2 hasher."""
    _build_hasher.cache_clear()
    _dummy_hash.cache_clear()


def hash_password(password: str, *, settings: Settings | None = None) -> str:
    if not password:
        raise ValueError("Password must not be empty")
    hasher = _hasher(settings)
    if hasher is not None:
        return str(hasher.hash(password))
    if _bcrypt is not None:  # pragma: no cover - fallback path
        return str(
            _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt(rounds=12)).decode("ascii")
        )
    raise RuntimeError("No password hashing backend is installed")


def verify_password(password: str, stored_hash: str, *, settings: Settings | None = None) -> bool:
    if stored_hash.startswith("$argon2"):
        hasher = _hasher(settings)
        if hasher is None:
            return False
        try:
            return bool(hasher.verify(stored_hash, password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    if stored_hash.startswith("$2"):
        if _bcrypt is None:  # pragma: no cover - fallback path
            return False
        try:
            return bool(_bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("ascii")))
        except ValueError:
            return False
    return False


def password_needs_rehash(stored_hash: str, *, settings: Settings | None = None) -> bool:
    if stored_hash.startswith("$argon2") and _hasher(settings) is not None:
        try:
            return bool(_hasher(settings).check_needs_rehash(stored_hash))
        except InvalidHashError:
            return True
    # A bcrypt hash is upgraded on the next successful login once Argon2 exists.
    return stored_hash.startswith("$2") and _ARGON2_AVAILABLE


@lru_cache(maxsize=8)
def _dummy_hash(time_cost: int, memory_cost: int, parallelism: int) -> str:
    """A real hash of a random throwaway value.

    Login verifies against this when the email is unknown, so the response time
    does not distinguish a missing account from a wrong password.
    """
    hasher = _build_hasher(time_cost, memory_cost, parallelism)
    if hasher is not None:
        return str(hasher.hash(secrets.token_urlsafe(24)))
    if _bcrypt:
        return str(_bcrypt.hashpw(b"timing-equalizer", _bcrypt.gensalt(rounds=12)).decode())
    return "$2b$12$" + "x" * 53


def verify_dummy_password(password: str, *, settings: Settings | None = None) -> None:
    verify_password(password, _dummy_hash(*_hasher_params(settings or get_settings())))


def is_weak_password(password: str, *, email: str | None = None) -> bool:
    """Reject short, common or obviously placeholder seed passwords."""
    if len(password) < MIN_SEED_PASSWORD_LENGTH:
        return True
    lowered = password.lower()
    if any(token in lowered for token in _WEAK_TOKENS):
        return True
    if email and lowered == email.strip().lower():
        return True
    classes = sum(
        bool(pattern.search(password))
        for pattern in (
            re.compile(r"[a-z]"),
            re.compile(r"[A-Z]"),
            re.compile(r"\d"),
            re.compile(r"[^A-Za-z0-9]"),
        )
    )
    return classes < 3


def validate_new_password(
    password: str,
    *,
    email: str | None = None,
    current_hash: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Enforce length, denylist and no-reuse policy.

    Raises :class:`PasswordPolicyCheckError` with reason codes instead of a
    human message that might echo the submitted value.
    """
    resolved = settings or get_settings()
    reasons: list[str] = []
    minimum = resolved.security.password_min_length
    if len(password) < minimum:
        reasons.append("too_short")
    if len(password) > 1024:
        reasons.append("too_long")
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        reasons.append("common_password")
    if email:
        local_part = email.split("@", 1)[0].strip().lower()
        if local_part and local_part in lowered and len(local_part) >= 4:
            reasons.append("contains_email")
    classes = sum(
        bool(pattern.search(password))
        for pattern in (
            re.compile(r"[a-z]"),
            re.compile(r"[A-Z]"),
            re.compile(r"\d"),
            re.compile(r"[^A-Za-z0-9]"),
        )
    )
    if classes < 3:
        reasons.append("insufficient_character_classes")
    if current_hash and verify_password(password, current_hash, settings=resolved):
        reasons.append("same_as_current")
    if reasons:
        raise PasswordPolicyCheckError(sorted(set(reasons)))


# --------------------------------------------------------------------------- JWT

_ALLOWED_ALGORITHMS: Final[frozenset[str]] = frozenset({"HS256", "HS384", "HS512"})
_HASHERS: Final[dict[str, Any]] = {
    "HS256": hashlib.sha256,
    "HS384": hashlib.sha384,
    "HS512": hashlib.sha512,
}


class TokenValidationError(ValueError):
    """Token failed signature or claim validation."""

    def __init__(self, reason: str, *, expired: bool = False) -> None:
        self.reason = reason
        self.expired = expired
        super().__init__(reason)


@dataclass(frozen=True)
class JwtClaims:
    subject: uuid.UUID
    role: RoleName
    jti: str
    issued_at: datetime
    expires_at: datetime


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise TokenValidationError("malformed") from exc


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def create_access_token(
    user_id: uuid.UUID, role: RoleName | str, *, settings: Settings | None = None
) -> str:
    resolved = settings or get_settings()
    security = resolved.security
    if security.jwt_algorithm not in _ALLOWED_ALGORITHMS:
        raise ValueError("JWT algorithm is not on the allow-list")
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=security.access_token_expire_minutes)
    header = {"alg": security.jwt_algorithm, "typ": "JWT", "kid": security.jwt_key_id}
    payload = {
        "sub": str(user_id),
        "role": RoleName(role).value,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": security.jwt_issuer,
        "aud": security.jwt_audience,
    }
    signing_input = f"{_b64encode(_json_bytes(header))}.{_b64encode(_json_bytes(payload))}"
    digest = hmac.new(
        security.active_jwt_secret.encode("utf-8"),
        signing_input.encode("ascii"),
        _HASHERS[security.jwt_algorithm],
    ).digest()
    return f"{signing_input}.{_b64encode(digest)}"


def decode_access_token(token: str, *, settings: Settings | None = None) -> JwtClaims:
    resolved = settings or get_settings()
    security = resolved.security
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise TokenValidationError("malformed") from exc

    try:
        header = json.loads(_b64decode(header_b64))
        payload = json.loads(_b64decode(payload_b64))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TokenValidationError("malformed") from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise TokenValidationError("malformed")

    alg = header.get("alg")
    if not isinstance(alg, str) or alg.lower() == "none":
        raise TokenValidationError("algorithm_not_allowed")
    if alg not in _ALLOWED_ALGORITHMS or alg != security.jwt_algorithm:
        raise TokenValidationError("algorithm_not_allowed")
    if header.get("typ") != "JWT":
        raise TokenValidationError("invalid_type")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise TokenValidationError("unknown_kid")
    signing_key = security.jwt_signing_keys.get(kid)
    if signing_key is None:
        raise TokenValidationError("unknown_kid")

    expected = hmac.new(
        signing_key.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("ascii"),
        _HASHERS[alg],
    ).digest()
    try:
        actual = _b64decode(signature_b64)
    except TokenValidationError as exc:
        raise TokenValidationError("bad_signature") from exc
    if not hmac.compare_digest(expected, actual):
        raise TokenValidationError("bad_signature")

    now = int(datetime.now(UTC).timestamp())
    leeway = security.jwt_leeway_seconds
    exp = payload.get("exp")
    iat = payload.get("iat")
    if isinstance(exp, bool) or not isinstance(exp, int):
        raise TokenValidationError("invalid_exp")
    if isinstance(iat, bool) or not isinstance(iat, int):
        raise TokenValidationError("invalid_iat")
    if exp < now - leeway:
        raise TokenValidationError("expired", expired=True)
    if iat > now + leeway:
        raise TokenValidationError("issued_in_future")
    if exp <= iat:
        raise TokenValidationError("invalid_lifetime")
    if exp - iat > security.access_token_expire_minutes * 60 + 60:
        raise TokenValidationError("lifetime_too_long")

    not_before = payload.get("nbf")
    if not_before is not None and (
        isinstance(not_before, bool) or not isinstance(not_before, int) or not_before > now + leeway
    ):
        raise TokenValidationError("not_yet_valid")

    if payload.get("iss") != security.jwt_issuer:
        raise TokenValidationError("bad_issuer")
    audience = payload.get("aud")
    if isinstance(audience, list):
        audience_ok = security.jwt_audience in audience
    else:
        audience_ok = audience == security.jwt_audience
    if not audience_ok:
        raise TokenValidationError("bad_audience")

    subject = payload.get("sub")
    try:
        user_id = uuid.UUID(str(subject))
    except (ValueError, TypeError, AttributeError) as exc:
        raise TokenValidationError("invalid_subject") from exc
    try:
        role = RoleName(str(payload.get("role")))
    except ValueError as exc:
        raise TokenValidationError("invalid_role") from exc
    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise TokenValidationError("invalid_jti")

    return JwtClaims(
        subject=user_id,
        role=role,
        jti=jti,
        issued_at=datetime.fromtimestamp(iat, tz=UTC),
        expires_at=datetime.fromtimestamp(exp, tz=UTC),
    )


# --------------------------------------------------------- refresh and tickets


def new_refresh_token() -> tuple[str, str]:
    """Return ``(raw, sha256_hex)``; only the digest is persisted."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_ws_ticket() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


# ---------------------------------------------------------------- sensor keys


@dataclass(frozen=True)
class IssuedSensorKey:
    raw: str
    prefix: str
    hash: str


_SENSOR_KEY_PREFIX = "sk"
_SENSOR_KEY_PATTERN = re.compile(r"^(?P<prefix>[a-z0-9]{8,32})\.(?P<secret>[A-Za-z0-9_-]{32,})$")


def new_sensor_key() -> IssuedSensorKey:
    prefix = _SENSOR_KEY_PREFIX + secrets.token_hex(7)
    secret = secrets.token_urlsafe(32)
    return IssuedSensorKey(
        raw=f"{prefix}.{secret}",
        prefix=prefix,
        hash=hash_sensor_secret(secret),
    )


def hash_sensor_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def parse_sensor_key(raw: str) -> tuple[str, str] | None:
    match = _SENSOR_KEY_PATTERN.fullmatch(raw.strip())
    if match is None:
        return None
    return match.group("prefix"), match.group("secret")


def verify_sensor_key(secret: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_sensor_secret(secret), stored_hash)


# -------------------------------------------------------------------- cookies


def set_refresh_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    security = settings.security
    response.set_cookie(
        key=security.refresh_cookie_name,
        value=raw_token,
        max_age=security.refresh_token_expire_hours * 3600,
        path=security.refresh_cookie_path,
        secure=security.refresh_cookie_secure,
        httponly=True,
        samesite=security.refresh_cookie_samesite,
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    security = settings.security
    response.delete_cookie(
        key=security.refresh_cookie_name,
        path=security.refresh_cookie_path,
        secure=security.refresh_cookie_secure,
        httponly=True,
        samesite=security.refresh_cookie_samesite,
    )
