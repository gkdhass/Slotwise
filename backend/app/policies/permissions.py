"""Role-to-permission mapping.

The Phase 1 schema defines a ``roles`` table with only name and description and
does not define permission or role_permission tables. Permissions therefore live
in code and are resolved by Phase 3 authorization checks; nothing is duplicated
into the database, and no migration is needed when a permission bundle changes.

The ML operator bundle is intentionally attached to ADMIN: datasets:write,
training:run, models:promote and models:retire. A future dedicated ML role can be
added without changing persisted rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from app.models.enums import RoleName

READ_PERMISSIONS: Final[frozenset[str]] = frozenset(
    {
        "events:read",
        "alerts:read",
        "incidents:read",
        "models:read",
        "assets:read",
        "dashboard:read",
    }
)

ANALYST_PERMISSIONS: Final[frozenset[str]] = READ_PERMISSIONS | frozenset(
    {
        "events:write",
        "alerts:update",
        "incidents:write",
        "incidents:comment",
        "responses:request",
        "reports:export",
    }
)

ADMIN_PERMISSIONS: Final[frozenset[str]] = ANALYST_PERMISSIONS | frozenset(
    {
        "users:manage",
        "roles:manage",
        "sensors:manage",
        "assets:write",
        "policies:write",
        "allowlist:write",
        "audit:read",
        # ML operator bundle.
        "datasets:write",
        "training:run",
        "models:promote",
        "models:retire",
        "responses:approve",
        "responses:execute",
    }
)

ROLE_PERMISSIONS: Final[Mapping[RoleName, frozenset[str]]] = MappingProxyType(
    {
        RoleName.ADMIN: ADMIN_PERMISSIONS,
        RoleName.ANALYST: ANALYST_PERMISSIONS,
        RoleName.VIEWER: READ_PERMISSIONS,
    }
)


def permissions_for(role: RoleName | str) -> frozenset[str]:
    try:
        resolved = role if isinstance(role, RoleName) else RoleName(role)
    except ValueError:
        return frozenset()
    return ROLE_PERMISSIONS[resolved]
