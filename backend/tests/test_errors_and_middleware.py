"""Standard error envelope, request IDs and middleware headers."""

from __future__ import annotations

import re
from uuid import UUID

import pytest
from fastapi import FastAPI

from app.core.errors import NotFoundError
from app.schemas.health import DependencyCheck, ReadinessResponse

REQUEST_ID_HEADER = "X-Request-ID"


def _assert_error_shape(body: dict, *, code: str, request_id: str) -> None:
    assert set(body) == {"code", "message", "details", "request_id"}
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert body["request_id"] == request_id


async def test_domain_error_uses_standard_format(app, client) -> None:
    @app.get("/test/domain-error")
    async def domain_error() -> None:
        raise NotFoundError("Alert not found.", details={"alert_id": "a-1"})

    response = await client.get("/test/domain-error", headers={REQUEST_ID_HEADER: "req-domain-1"})
    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == "req-domain-1"
    _assert_error_shape(response.json(), code="NOT_FOUND", request_id="req-domain-1")
    assert response.json()["details"] == {"alert_id": "a-1"}


async def test_validation_error_uses_standard_format_and_hides_input(app, client) -> None:
    @app.get("/test/validation")
    async def validation(secret_token: int = 0) -> dict[str, int]:
        return {"secret_token": secret_token}

    response = await client.get(
        "/test/validation?secret_token=not-a-number",
        headers={REQUEST_ID_HEADER: "req-validation-1"},
    )
    assert response.status_code == 422
    body = response.json()
    _assert_error_shape(body, code="VALIDATION_ERROR", request_id="req-validation-1")
    assert body["details"]["errors"][0]["location"] == ["query", "secret_token"]
    assert "not-a-number" not in response.text


async def test_http_error_uses_standard_format(app, client) -> None:
    response = await client.get("/does-not-exist", headers={REQUEST_ID_HEADER: "req-http-1"})
    assert response.status_code == 404
    _assert_error_shape(response.json(), code="NOT_FOUND", request_id="req-http-1")


async def test_unexpected_error_hides_stack_trace(app, client) -> None:
    @app.get("/test/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("database password=super-secret")

    response = await client.get("/test/unexpected", headers={REQUEST_ID_HEADER: "req-boom-1"})
    assert response.status_code == 500
    body = response.json()
    _assert_error_shape(body, code="INTERNAL_ERROR", request_id="req-boom-1")
    assert "RuntimeError" not in response.text
    assert "super-secret" not in response.text
    assert "Traceback" not in response.text


async def test_request_id_is_propagated(app, client) -> None:
    response = await client.get("/healthz", headers={REQUEST_ID_HEADER: "client-correlation-42"})
    assert response.headers[REQUEST_ID_HEADER] == "client-correlation-42"


async def test_request_id_is_generated_when_absent(app, client) -> None:
    response = await client.get("/healthz")
    generated = response.headers[REQUEST_ID_HEADER]
    UUID(generated)  # raises if not a UUID
    assert generated == response.json().get("request_id", generated)


async def test_unsafe_request_id_is_replaced(app, client) -> None:
    response = await client.get(
        "/healthz", headers={REQUEST_ID_HEADER: "bad id\r\nX-Injected: yes"}
    )
    generated = response.headers[REQUEST_ID_HEADER]
    assert generated != "bad id"
    assert re.fullmatch(r"[0-9a-f]{32}", generated)
    assert "X-Injected" not in response.headers


async def test_security_headers_are_present(app, client) -> None:
    response = await client.get("/healthz", headers={REQUEST_ID_HEADER: "req-sec-1"})
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


async def test_readyz_ok_reports_each_dependency(app, client) -> None:
    from app.api.deps import get_health_service
    from app.services.health import DEPENDENCIES, HealthService

    class HealthyService(HealthService):
        async def readiness(self) -> ReadinessResponse:
            return ReadinessResponse(
                status="ok",
                version="0.1.0",
                environment="test",
                checks={
                    name: DependencyCheck(status="ok", latency_ms=1.0) for name in DEPENDENCIES
                },
            )

    app.dependency_overrides[get_health_service] = lambda: HealthyService()
    response = await client.get("/api/v1/readyz", headers={REQUEST_ID_HEADER: "req-ready-ok"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["checks"]) == set(DEPENDENCIES)
    assert all(check["status"] == "ok" for check in body["checks"].values())


async def test_readyz_degraded_when_dependency_down(app, client) -> None:
    from app.api.deps import get_health_service
    from app.services.health import DEPENDENCIES, HealthService

    class DegradedService(HealthService):
        async def readiness(self) -> ReadinessResponse:
            checks = {name: DependencyCheck(status="ok", latency_ms=2.0) for name in DEPENDENCIES}
            checks["redis"] = DependencyCheck(
                status="error", latency_ms=0.5, detail="connection_error"
            )
            return ReadinessResponse(
                status="degraded",
                version="0.1.0",
                environment="test",
                checks=checks,
            )

    app.dependency_overrides[get_health_service] = lambda: DegradedService()
    response = await client.get("/api/v1/readyz", headers={REQUEST_ID_HEADER: "req-ready-down"})
    assert response.status_code == 503
    body = response.json()
    _assert_error_shape(body, code="DEPENDENCY_UNAVAILABLE", request_id="req-ready-down")
    assert body["details"]["status"] == "degraded"
    assert body["details"]["checks"]["redis"]["status"] == "error"
    assert body["details"]["checks"]["postgres"]["status"] == "ok"


@pytest.mark.parametrize("path", ["/healthz", "/api/v1/healthz"])
async def test_liveness_both_paths(app, client, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_and_docs_are_versioned(app) -> None:
    assert app.openapi_url == "/api/v1/openapi.json"


def test_exception_handler_registration_is_app_local(app) -> None:
    # Guards against accidentally registering handlers on the FastAPI class.
    from app.core.errors import DomainError

    local_app = FastAPI()
    assert DomainError not in local_app.exception_handlers
    assert DomainError in app.exception_handlers
