"""Opaque keyset-pagination cursors.

Cursors are base64url-encoded JSON, not signed: they carry no authority and are
validated against a sort whitelist on every use. Clients cannot inject SQL
through them because values are bound parameters.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from app.core.errors import BadRequestError

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    next_cursor: str | None


def validate_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise BadRequestError(
            "The page size is outside the supported range.",
            details={"min": 1, "max": MAX_PAGE_SIZE},
        )
    return limit


def encode_cursor(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadRequestError("The pagination cursor is invalid.") from exc
    if not isinstance(decoded, dict):
        raise BadRequestError("The pagination cursor is invalid.")
    return decoded
