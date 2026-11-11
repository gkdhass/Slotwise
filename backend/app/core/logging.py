"""Structured JSON logging with request correlation and secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_SENSITIVE_KEYS = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|authorization|cookie|session[_-]?id)"
)
_REDACTED = "[REDACTED]"

# Text patterns catch secrets embedded in free-form messages.
_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Bearer tokens must be handled first: the generic key/value rule would
    # otherwise consume the "Bearer" prefix and leave the token intact.
    (re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1" + _REDACTED),
    (
        # Handles both ``key=value`` logs and quoted JSON-style ``"key": "value"``.
        re.compile(
            r"(?i)([\"']?(?:password|passwd|pwd|secret|token|api[_-]?key|"
            r"access[_-]?key|access[_-]?token|private[_-]?key|authorization|"
            r"client[_-]?secret|cookie|session[_-]?id)[\"']?\s*[=:]\s*)"
            r"(\"[^\"]*\"|'[^']*'|[^\s,;}]+)"
        ),
        r"\1" + _REDACTED,
    ),
    (re.compile(r"(://[^:/\s]+:)([^@\s]+)(@)"), r"\1" + _REDACTED + r"\3"),
)


def get_request_id() -> str:
    return _request_id_ctx.get()


def set_request_id(value: str) -> object:
    """Set the context value and return the token for later reset."""
    return _request_id_ctx.set(value)


def reset_request_id(token: object) -> None:
    _request_id_ctx.reset(token)  # type: ignore[arg-type]


def redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _TEXT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_mapping(value: Any) -> Any:
    """Recursively redact mapping values whose keys look sensitive."""
    if isinstance(value, dict):
        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SENSITIVE_KEYS.search(key):
                cleaned[key] = _REDACTED
            else:
                cleaned[key] = redact_mapping(item)
        return cleaned
    if isinstance(value, list | tuple | set):
        return [redact_mapping(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class SecretRedactingFilter(logging.Filter):
    """Redact secrets from the rendered message before any handler sees it."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive against malformed args
            message = str(record.msg)
        record.msg = redact_text(message)
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, *, service: str, environment: str) -> None:
        super().__init__()
        self.service = service
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": self.service,
            "environment": self.environment,
            "message": redact_text(record.getMessage()),
            "request_id": getattr(record, "request_id", None) or get_request_id(),
        }
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))

        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_KEYS or key.startswith("_"):
                continue
            payload[key] = redact_mapping(value)

        return json.dumps(redact_mapping(payload), default=str, ensure_ascii=False)


_RESERVED_RECORD_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "asctime",
}


def configure_logging(
    *, level: str = "INFO", service: str = "slotwise-api", environment: str = "dev"
) -> None:
    """Install a single JSON handler on the root logger.

    Idempotent so repeated ``create_app`` calls in tests do not duplicate output.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service=service, environment=environment))
    handler.addFilter(SecretRedactingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "app"):
        child = logging.getLogger(logger_name)
        child.handlers.clear()
        child.propagate = True
        child.setLevel(level.upper())
