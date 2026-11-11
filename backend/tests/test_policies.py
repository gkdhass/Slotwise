"""Feature gates and simulated-response policy hooks."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import (
    ModuleDisabledError,
    ResponseNotSimulatedError,
    SelfApprovalForbiddenError,
)
from app.policies.safety import (
    Module,
    require_independent_approval,
    require_module_enabled,
    require_simulated_response,
)


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.setenv("APP_ENV", "test")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


def test_module_b_is_blocked_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    with pytest.raises(ModuleDisabledError):
        require_module_enabled(Module.B, settings)


def test_module_b_can_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, MODULE_B_ENABLED="true")
    require_module_enabled(Module.B, settings)


def test_module_a_is_always_available(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    require_module_enabled(Module.A, settings)


def test_self_approval_is_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    with pytest.raises(SelfApprovalForbiddenError):
        require_independent_approval(
            requester_id="analyst-1", approver_id="analyst-1", settings=settings
        )


def test_self_approval_flag_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, ALLOW_SELF_APPROVAL="true")
    require_independent_approval(
        requester_id="analyst-1", approver_id="analyst-1", settings=settings
    )


def test_response_must_be_simulated() -> None:
    require_simulated_response("SIMULATED")
    with pytest.raises(ResponseNotSimulatedError):
        require_simulated_response("LIVE")
