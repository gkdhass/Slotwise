"""Authentication request/response schemas.

Access tokens are returned in the body for the client to keep in memory. The
opaque refresh token is never in the body: it is delivered only as an HttpOnly
cookie.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, examples=["analyst@example.com"])
    password: str = Field(min_length=1, max_length=1024, examples=["correct horse battery staple"])


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    must_change_password: bool


class LoginResponse(BaseModel):
    access_token: str = Field(description="Short-lived JWT; keep in memory only.")
    token_type: str = "bearer"  # noqa: S105 - OAuth token type literal, not a secret
    expires_in: int = Field(description="Access-token lifetime in seconds.")
    user: UserSummary


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type literal, not a secret
    expires_in: int
    user: UserSummary


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class WsTicketResponse(BaseModel):
    ticket: str = Field(description="Single-use WebSocket ticket, valid for 30 seconds.")
    expires_in: int


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    permissions: list[str]
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None
    password_changed_at: datetime | None
