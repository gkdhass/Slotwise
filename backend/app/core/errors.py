"""Typed domain errors and the single public error format.

Every error returned to a client has the shape:
``{"code": str, "message": str, "details": Any, "request_id": str}``.

Stack traces, SQL fragments, upstream URLs and secret values are never serialised.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id
from app.schemas.common import ErrorResponse, ValidationErrorDetail

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    MODULE_B_DISABLED = "MODULE_B_DISABLED"
    SELF_APPROVAL_FORBIDDEN = "SELF_APPROVAL_FORBIDDEN"
    RESPONSE_NOT_SIMULATED = "RESPONSE_NOT_SIMULATED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class DomainError(Exception):
    """Base class for expected, typed application failures."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    status_code: int = 500
    default_message = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        self.headers = headers
        super().__init__(self.message)


class BadRequestError(DomainError):
    code = ErrorCode.BAD_REQUEST
    status_code = 400
    default_message = "The request is invalid."


class UnauthorizedError(DomainError):
    code = ErrorCode.UNAUTHORIZED
    status_code = 401
    default_message = "Authentication is required."


class ForbiddenError(DomainError):
    code = ErrorCode.FORBIDDEN
    status_code = 403
    default_message = "You are not allowed to perform this action."


class NotFoundError(DomainError):
    code = ErrorCode.NOT_FOUND
    status_code = 404
    default_message = "The requested resource was not found."


class ConflictError(DomainError):
    code = ErrorCode.CONFLICT
    status_code = 409
    default_message = "The request conflicts with the current state."


class RateLimitedError(DomainError):
    code = ErrorCode.RATE_LIMITED
    status_code = 429
    default_message = "Too many requests."


class DependencyUnavailableError(DomainError):
    code = ErrorCode.DEPENDENCY_UNAVAILABLE
    status_code = 503
    default_message = "A required dependency is unavailable."


class ModuleDisabledError(DomainError):
    code = ErrorCode.MODULE_B_DISABLED
    status_code = 403
    default_message = "This module is disabled by configuration."


class SelfApprovalForbiddenError(DomainError):
    code = ErrorCode.SELF_APPROVAL_FORBIDDEN
    status_code = 403
    default_message = "A response action cannot be approved by its requester."


class ResponseNotSimulatedError(DomainError):
    code = ErrorCode.RESPONSE_NOT_SIMULATED
    status_code = 403
    default_message = "Only simulated response actions are permitted in this deployment."


_HTTP_CODE_MAP: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.DEPENDENCY_UNAVAILABLE,
}


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or get_request_id())


def build_error_response(
    *,
    status_code: int,
    code: ErrorCode | str,
    message: str,
    details: Any,
    request_id: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        code=code.value if isinstance(code, ErrorCode) else code,
        message=message,
        details=details,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=headers,
    )


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    request_id = _request_id(request)
    logger.warning(
        "domain_error",
        extra={
            "error_code": exc.code.value,
            "status_code": exc.status_code,
            "path": request.url.path,
        },
    )
    return build_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=request_id,
        headers=exc.headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only location/type/message are exposed: raw input may contain secrets.
    errors = [
        ValidationErrorDetail(
            location=[str(part) for part in error.get("loc", ())],
            message=str(error.get("msg", "Invalid value")),
            type=str(error.get("type", "value_error")),
        )
        for error in exc.errors()
    ]
    return build_error_response(
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message="The request failed validation.",
        details={"errors": [item.model_dump() for item in errors]},
        request_id=_request_id(request),
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODE_MAP.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    detail = exc.detail if isinstance(exc.detail, str) else "HTTP request failed."
    if exc.status_code >= 500:
        detail = "An unexpected error occurred."
    return build_error_response(
        status_code=exc.status_code,
        code=code,
        message=detail,
        details=None,
        request_id=_request_id(request),
        headers=exc.headers,
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the stack trace server-side only. Clients receive no internals.
    logger.exception(
        "unhandled_exception",
        extra={"path": request.url.path, "error_type": type(exc).__name__},
    )
    return build_error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred.",
        details=None,
        request_id=_request_id(request),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unexpected_error_handler)
