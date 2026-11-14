"""Versioned API router.

Every router below is mounted under ``/api/v1``. The only unauthenticated routes
are the three health probes, metrics and the auth entry points listed in
``app.api.deps.PUBLIC_ROUTES``; a startup assertion enforces that no other route
can be added without an authorization dependency.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    allowlist,
    assets,
    audit,
    auth,
    health,
    policies,
    roles,
    sensors,
    users,
)
from app.api.v1.endpoints.auth import me as me_handler

router = APIRouter()
router.include_router(health.health_router)
router.include_router(auth.auth_router)
router.include_router(users.users_router)
router.include_router(roles.roles_router)
router.include_router(sensors.sensors_router)
router.include_router(assets.assets_router)
router.include_router(policies.policies_router)
router.include_router(allowlist.allowlist_router)
router.include_router(audit.audit_router)

# TRD contract: /api/v1/me is the canonical path; /auth/me kept as an alias for
# backwards compatibility. Both resolve to the same handler.
router.add_api_route("/me", me_handler, methods=["GET"], include_in_schema=False)
