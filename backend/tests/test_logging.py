"""JSON logging, correlation IDs and secret redaction."""

from __future__ import annotations

import json
import logging

from app.core.logging import (
    JsonFormatter,
    SecretRedactingFilter,
    get_request_id,
    redact_mapping,
    redact_text,
    reset_request_id,
    set_request_id,
)


def _record(message: str, args: tuple[object, ...] = (), **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="slotwise.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg=message,
        args=args,
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_filter_redacts_key_value_secrets() -> None:
    record = _record("login password=%s token=%s", ("hunter2", "abc123"))
    assert SecretRedactingFilter().filter(record) is True
    message = record.getMessage()
    assert "hunter2" not in message
    assert "abc123" not in message
    assert "[REDACTED]" in message


def test_redact_text_handles_json_urls_and_bearer() -> None:
    text = (
        '{"password": "p@ssw0rd", "access_token": "tok-123"} '
        "postgresql://user:db-secret@db:5432/slotwise "
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature "
        "x-sensor-key: sensor-secret-value cookie=refresh-cookie-value "
        "refresh_token=refresh-secret-value"
    )
    redacted = redact_text(text)
    assert "p@ssw0rd" not in redacted
    assert "tok-123" not in redacted
    assert "db-secret" not in redacted
    assert "eyJhbGciOiJIUzI1NiJ9" not in redacted
    assert "sensor-secret-value" not in redacted
    assert "refresh-cookie-value" not in redacted
    assert "refresh-secret-value" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_mapping_is_recursive() -> None:
    payload = {
        "request": {
            "headers": {
                "Authorization": "Bearer abc.def.ghi",
                "X-Sensor-Key": "sensor-header-secret",
                "Cookie": "slotwise_refresh=refresh-header-secret",
            }
        },
        "credentials": [{"password": "x"}, {"safe": "visible"}],
    }
    redacted = redact_mapping(payload)
    assert redacted["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert redacted["request"]["headers"]["X-Sensor-Key"] == "[REDACTED]"
    assert redacted["request"]["headers"]["Cookie"] == "[REDACTED]"
    assert redacted["credentials"][0]["password"] == "[REDACTED]"
    assert redacted["credentials"][1]["safe"] == "visible"


def test_json_formatter_emits_json_with_request_id_and_no_secrets() -> None:
    token = set_request_id("req-log-1")
    try:
        record = _record(
            "connecting with password=%s",
            ("top-secret",),
            credentials={"password": "nested-secret", "user": "analyst"},
            duration_ms=12.5,
        )
        output = JsonFormatter(service="slotwise-api", environment="test").format(record)
    finally:
        reset_request_id(token)

    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["service"] == "slotwise-api"
    assert parsed["request_id"] == "req-log-1"
    assert parsed["duration_ms"] == 12.5
    assert parsed["credentials"]["password"] == "[REDACTED]"
    assert parsed["credentials"]["user"] == "analyst"
    assert "top-secret" not in output
    assert "nested-secret" not in output


def test_request_id_context_defaults_and_resets() -> None:
    assert get_request_id() == "-"
    token = set_request_id("corr-1")
    assert get_request_id() == "corr-1"
    reset_request_id(token)
    assert get_request_id() == "-"
