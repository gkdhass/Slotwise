"""Permission matrix invariants.

The matrix lives in code (no role_permission tables), so these assertions are the
contract that the admin UI, the route guards and the tests all share.
"""

from __future__ import annotations

import pytest

from app.models.enums import RoleName
from app.policies.permissions import (
    ADMIN_PERMISSIONS,
    ANALYST_PERMISSIONS,
    READ_PERMISSIONS,
    ROLE_PERMISSIONS,
    permissions_for,
)

ML_OPERATOR_PERMISSIONS = {
    "datasets:write",
    "training:run",
    "models:promote",
    "models:retire",
}

ALL_PERMISSIONS = ADMIN_PERMISSIONS | ANALYST_PERMISSIONS | READ_PERMISSIONS


def test_exactly_the_three_locked_roles_exist() -> None:
    assert {role.value for role in RoleName} == {"ADMIN", "ANALYST", "VIEWER"}
    assert set(ROLE_PERMISSIONS) == set(RoleName)


def test_roles_are_nested_viewer_subset_analyst_subset_admin() -> None:
    assert READ_PERMISSIONS <= ANALYST_PERMISSIONS
    assert ANALYST_PERMISSIONS <= ADMIN_PERMISSIONS


def test_ml_operator_bundle_is_admin_only() -> None:
    assert ML_OPERATOR_PERMISSIONS <= ADMIN_PERMISSIONS
    assert not ML_OPERATOR_PERMISSIONS & ANALYST_PERMISSIONS
    assert not ML_OPERATOR_PERMISSIONS & READ_PERMISSIONS
    for permission in ML_OPERATOR_PERMISSIONS:
        assert permissions_for(RoleName.ADMIN) >= {permission}
        assert permission not in permissions_for(RoleName.ANALYST)
        assert permission not in permissions_for(RoleName.VIEWER)


def test_high_impact_response_controls_are_admin_only() -> None:
    for permission in {"responses:approve", "responses:execute"}:
        assert permission in ADMIN_PERMISSIONS
        assert permission not in ANALYST_PERMISSIONS
        assert permission not in READ_PERMISSIONS


@pytest.mark.parametrize("permission", sorted(ALL_PERMISSIONS))
def test_permission_names_are_well_formed(permission: str) -> None:
    resource, separator, action = permission.partition(":")
    assert separator == ":", permission
    assert resource and action, permission
    assert permission == permission.lower(), permission


def test_admin_can_manage_every_admin_surface() -> None:
    assert {
        "users:manage",
        "roles:manage",
        "sensors:manage",
        "assets:read",
        "assets:write",
        "policies:write",
        "allowlist:write",
        "audit:read",
    } <= permissions_for(RoleName.ADMIN)


def test_viewer_has_read_access_but_no_writes() -> None:
    viewer = permissions_for(RoleName.VIEWER)
    assert "events:read" in viewer
    assert "assets:read" in viewer
    write_ops = (":write", ":manage", ":run", ":approve")
    assert not any(permission.endswith(write_ops) for permission in viewer)


def test_unknown_role_or_string_has_no_permissions() -> None:
    assert permissions_for("SUPERUSER") == frozenset()
    # Lowercase role names are invalid enum values and return empty set.
    assert permissions_for("admin") == frozenset()
