"""Route-table authorization contract.

Generates the checks from the live route table, so a new endpoint cannot ship
without either an authorization dependency or an explicit entry in the reviewed
public allow-list.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from app.api.deps import (
    PUBLIC_ROUTES,
    _dependency_calls,
    iter_api_routes,
    unprotected_routes,
)

pytestmark = pytest.mark.asyncio

#: The complete, reviewed anonymous surface. Adding a route here is a security
#: decision, not a convenience.
EXPECTED_PUBLIC = frozenset(
    {
        ("GET", "/healthz"),
        ("GET", "/readyz"),
        ("GET", "/metrics"),
        ("GET", "/api/v1/healthz"),
        ("GET", "/api/v1/readyz"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
    }
)

PLACEHOLDER = "11111111-1111-1111-1111-111111111111"


def _concrete_path(path: str) -> str:
    while "{" in path and "}" in path:
        start = path.index("{")
        end = path.index("}", start)
        path = path[:start] + PLACEHOLDER + path[end + 1 :]
    return path


def _permissions_for_route(route: Any) -> set[str]:
    found: set[str] = set()
    for call in _dependency_calls(route.dependant):
        found.update(getattr(call, "__required_permissions__", ()) or ())
    return found


def test_public_allow_list_is_exactly_reviewed() -> None:
    assert PUBLIC_ROUTES == EXPECTED_PUBLIC


def test_every_route_is_protected_or_public(app) -> None:
    assert unprotected_routes(app) == []


def test_route_table_is_non_empty(app) -> None:
    routes = iter_api_routes(app.routes)
    assert len(routes) >= 30


def test_admin_routes_declare_permissions(app) -> None:
    """Every route outside auth/health/sensor declares at least one permission."""
    allowed_without_permission = {
        "/api/v1/auth/logout-all",
        "/api/v1/auth/change-password",
        "/api/v1/auth/ws-ticket",
        "/api/v1/auth/me",
        "/api/v1/me",  # TRD contract: canonical /me path, aliased from /auth/me
        "/api/v1/sensors/heartbeat",
        "/api/v1/healthz",
        "/api/v1/readyz",
        "/healthz",
        "/readyz",
        "/metrics",
    }
    missing: list[str] = []
    for route in iter_api_routes(app.routes):
        if route.path in allowed_without_permission:
            continue
        if (str(next(iter(route.methods))), route.path) in PUBLIC_ROUTES:
            continue
        if not _permissions_for_route(route):
            missing.append(f"{sorted(route.methods)} {route.path}")
    assert missing == []


def test_expected_permission_matrix(app) -> None:
    expected = {
        ("GET", "/api/v1/users"): {"users:manage"},
        ("POST", "/api/v1/users"): {"users:manage"},
        ("GET", "/api/v1/roles"): {"roles:manage"},
        ("GET", "/api/v1/sensors"): {"sensors:manage"},
        ("POST", "/api/v1/sensors/{sensor_id}/rotate"): {"sensors:manage"},
        ("POST", "/api/v1/sensors/{sensor_id}/revoke"): {"sensors:manage"},
        ("GET", "/api/v1/assets"): {"assets:read"},
        ("POST", "/api/v1/assets"): {"assets:write"},
        ("PATCH", "/api/v1/assets/{asset_id}"): {"assets:write"},
        ("DELETE", "/api/v1/assets/{asset_id}"): {"assets:write"},
        ("GET", "/api/v1/response-policies"): {"policies:write"},
        ("POST", "/api/v1/response-policies"): {"policies:write"},
        ("GET", "/api/v1/allowlist"): {"allowlist:write"},
        ("DELETE", "/api/v1/allowlist/{entry_id}"): {"allowlist:write"},
        ("GET", "/api/v1/audit-logs"): {"audit:read"},
    }
    actual: dict[tuple[str, str], set[str]] = {}
    for route in iter_api_routes(app.routes):
        for method in route.methods or ():
            actual[(method, route.path)] = _permissions_for_route(route)
    for key, permissions in expected.items():
        assert actual.get(key) == permissions, key


async def test_anonymous_request_is_rejected_everywhere_protected(app) -> None:
    """No protected handler logic can run without a principal."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for route in iter_api_routes(app.routes):
            for method in sorted(route.methods or ()):
                if (method, route.path) in PUBLIC_ROUTES:
                    continue
                response = await client.request(method, _concrete_path(route.path))
                assert response.status_code in {
                    401,
                    403,
                }, f"{method} {route.path} returned {response.status_code}: {response.text}"
                body = response.json()
                assert body["code"] in {
                    "UNAUTHORIZED",
                    "AUTH_TOKEN_INVALID",
                    "AUTH_INVALID_CREDENTIALS",
                    "FORBIDDEN",
                    "AUTH_ACCOUNT_LOCKED",
                }
