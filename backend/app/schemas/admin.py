"""Administration request/response schemas.

No schema includes a password hash, refresh token or sensor secret. The one-time
temporary password / sensor key is returned by a dedicated creation response and
never persisted in plaintext.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

RoleNameLiteral = Literal["ADMIN", "ANALYST", "VIEWER"]
CriticalityLiteral = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
AssetTypeLiteral = Literal[
    "WORKSTATION", "SERVER", "NETWORK_DEVICE", "CLOUD_SERVICE", "APPLICATION", "OTHER"
]
EnvironmentLiteral = Literal["DEV", "STAGING", "PROD"]
SensorStatusLiteral = Literal["ACTIVE", "INACTIVE", "REVOKED"]
ResponseActionLiteral = Literal[
    "BLOCK_IP", "ISOLATE_HOST", "DISABLE_ACCOUNT", "BLOCK_DOMAIN", "QUARANTINE_FILE"
]
AllowlistLiteral = Literal["IP", "CIDR", "DOMAIN", "URL", "HASH", "USER"]


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    must_change_password: bool
    failed_login_count: int
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: RoleNameLiteral
    password: str | None = Field(
        default=None,
        min_length=12,
        max_length=1024,
        description="Omit to receive a one-time generated temporary password.",
    )

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        normalised = value.strip().lower()
        if "@" not in normalised or normalised.startswith("@") or normalised.endswith("@"):
            raise ValueError("A valid email address is required")
        return normalised


class UserCreateResponse(BaseModel):
    user: UserResponse
    temporary_password: str | None = None
    password_generated: bool


class UserUpdateRequest(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=320)
    role: RoleNameLiteral | None = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalised = value.strip().lower()
        if "@" not in normalised or normalised.startswith("@") or normalised.endswith("@"):
            raise ValueError("A valid email address is required")
        return normalised


class ResetPasswordResponse(BaseModel):
    user_id: uuid.UUID
    temporary_password: str
    must_change_password: bool


class RoleResponse(BaseModel):
    name: str
    description: str | None
    permissions: list[str]


class SensorResponse(BaseModel):
    id: uuid.UUID
    name: str
    sensor_type: str
    asset_id: uuid.UUID | None
    credential_prefix: str | None
    status: str
    last_seen_at: datetime | None
    credential_rotated_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class SensorCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sensor_type: str = Field(min_length=1, max_length=64)
    asset_id: uuid.UUID | None = None


class SensorCreatedResponse(BaseModel):
    sensor: SensorResponse
    api_key: str = Field(description="Shown exactly once; store it in the sensor's secret store.")


class SensorRotateResponse(BaseModel):
    sensor: SensorResponse
    api_key: str


class AssetResponse(BaseModel):
    id: uuid.UUID
    name: str
    asset_type: str
    criticality: str
    owner_team: str
    environment: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AssetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    asset_type: AssetTypeLiteral
    criticality: CriticalityLiteral
    owner_team: str = Field(min_length=1, max_length=120)
    environment: EnvironmentLiteral
    is_active: bool = True


class AssetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    criticality: CriticalityLiteral | None = None
    owner_team: str | None = Field(default=None, min_length=1, max_length=120)
    environment: EnvironmentLiteral | None = None
    is_active: bool | None = None


class ResponsePolicyResponse(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    supersedes_id: uuid.UUID | None
    action_type: str
    conditions: dict[str, Any]
    requires_approval: bool
    enabled: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ResponsePolicyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    action_type: ResponseActionLiteral
    conditions: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = True
    enabled: bool = True
    supersedes_id: uuid.UUID | None = None


class AllowlistResponse(BaseModel):
    id: uuid.UUID
    entry_type: str
    value: str
    reason: str
    expires_at: datetime | None
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime


class AllowlistCreateRequest(BaseModel):
    entry_type: AllowlistLiteral
    value: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=3, max_length=2000)
    expires_at: datetime | None = None


class AllowlistUpdateRequest(BaseModel):
    reason: str | None = Field(default=None, min_length=3, max_length=2000)
    expires_at: datetime | None = None


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime
