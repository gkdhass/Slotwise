"""HTTP middleware: correlation IDs, structured access logs, security headers, metrics."""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.core.logging import (
    get_request_id,
    reset_request_id,
    set_request_id,
)
from app.core.metrics import REQUEST_COUNT, REQUEST_DURATION

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_DOCS_PATHS = {"/api/v1/docs", "/api/v1/redoc", "/api/v1/openapi.json"}

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-site",
    "Cache-Control": "no-store",
}
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Accept a safe inbound correlation ID or generate one, then propagate it."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        inbound = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = inbound if _VALID_REQUEST_ID.fullmatch(inbound) else uuid4().hex
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise
        finally:
            reset_request_id(token)

        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.path not in _DOCS_PATHS:
            response.headers.setdefault("Content-Security-Policy", _API_CSP)
        if request.url.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            # Unknown paths collapse to a single label to bound label cardinality.
            path_label = getattr(route, "path", "unmatched")
            elapsed = time.perf_counter() - started
            REQUEST_COUNT.labels(
                method=request.method, path=path_label, status=str(status_code)
            ).inc()
            REQUEST_DURATION.labels(method=request.method, path=path_label).observe(elapsed)


def current_request_id() -> str:
    return get_request_id()
