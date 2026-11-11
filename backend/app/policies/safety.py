"""Feature gating and safe-response policy hooks.

These guards are intentionally implemented before the modules they protect.
Later phases must call them rather than re-implementing policy checks.
"""

from __future__ import annotations

from enum import Enum

from app.core.config import Settings
from app.core.errors import (
    ModuleDisabledError,
    ResponseNotSimulatedError,
    SelfApprovalForbiddenError,
)


class Module(str, Enum):
    A = "A"
    B = "B"


def require_module_enabled(module: Module, settings: Settings) -> None:
    """Reject Module B traffic unless the feature flag is explicitly enabled."""
    if module is Module.B and not settings.features.module_b_enabled:
        raise ModuleDisabledError(
            "Module B (visual threats) is disabled.",
            details={"module": Module.B.value, "flag": "MODULE_B_ENABLED"},
        )


def require_independent_approval(
    *, requester_id: str, approver_id: str, settings: Settings
) -> None:
    """Enforce separation of duties for response approvals."""
    if requester_id == approver_id and not settings.features.allow_self_approval:
        raise SelfApprovalForbiddenError(
            details={"flag": "ALLOW_SELF_APPROVAL"},
        )


class ResponseMode(str, Enum):
    SIMULATED = "SIMULATED"


def require_simulated_response(mode: str) -> None:
    """No response path may execute real commands in this project.

    Callers must still persist an approval and audit record; this guard only
    ensures the execution mode can never be a live/real action.
    """
    if mode != ResponseMode.SIMULATED.value:
        raise ResponseNotSimulatedError(details={"mode": mode, "executed": False})
