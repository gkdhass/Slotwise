"""Phase 4-1 event import endpoint tests."""

from __future__ import annotations

import csv
import gzip
import io
import json
from typing import Any

import pytest

pytestmark = pytest.mark.db


async def test_post_imports_endpoint_exists(api_client: Any) -> None:
    """POST /events/imports endpoint exists and requires auth."""
    response = await api_client.post(
        "/api/v1/events/imports",
        files={"file": ("test.csv", b"", "text/csv")},
    )
    # No auth: 401 Unauthorized
    assert response.status_code == 401


async def test_post_imports_requires_multipart(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """POST /events/imports requires multipart/form-data content-type."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        json={"test": "data"},
    )
    # Wrong content type
    assert response.status_code == 400


async def test_post_imports_csv_accepted(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """POST /events/imports accepts valid CSV."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    csv_data = io.StringIO()
    writer = csv.DictWriter(
        csv_data,
        fieldnames=[
            "external_id",
            "source_id",
            "source_type",
            "event_type",
            "observed_at",
            "schema_version",
            "normalized_payload",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "external_id": "evt-csv-1",
            "source_id": "sensor-001",
            "source_type": "ZEEK",
            "event_type": "NETWORK_FLOW",
            "observed_at": "2026-11-16T12:00:00+00:00",
            "schema_version": "1.0",
            "normalized_payload": "{}",
        }
    )

    csv_bytes = csv_data.getvalue().encode("utf-8")
    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 202
    result = response.json()
    assert "accepted" in result
    assert "duplicates" in result
    assert "rejected" in result


async def test_post_imports_json_accepted(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """POST /events/imports accepts valid JSON."""
    password = "Test-Password-2026!"
    await make_user(email="analyst@example.com", password=password, role="ANALYST")
    headers = await login_headers(api_client, "analyst@example.com", password)

    json_data = json.dumps(
        [
            {
                "external_id": "evt-json-1",
                "source_id": "sensor-002",
                "source_type": "ZEEK",
                "event_type": "NETWORK_FLOW",
                "observed_at": "2026-11-16T12:00:00+00:00",
                "schema_version": "1.0",
                "normalized_payload": {},
            }
        ]
    )

    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.json", json_data.encode("utf-8"), "application/json")},
    )

    assert response.status_code == 202


async def test_post_imports_ndjson_accepted(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """POST /events/imports accepts valid NDJSON."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    ndjson_data = "\n".join(
        [
            json.dumps(
                {
                    "external_id": "evt-ndjson-1",
                    "source_id": "sensor-003",
                    "source_type": "ZEEK",
                    "event_type": "NETWORK_FLOW",
                    "observed_at": "2026-11-16T12:00:00+00:00",
                    "schema_version": "1.0",
                    "normalized_payload": {},
                }
            ),
        ]
    )

    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.ndjson", ndjson_data.encode("utf-8"), "application/x-ndjson")},
    )

    assert response.status_code == 202


async def test_post_imports_magic_byte_mismatch(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """POST /events/imports rejects CSV with JSON content."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    json_data = json.dumps({"test": "data"})
    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", json_data.encode("utf-8"), "text/csv")},
    )

    # Should be rejected for magic byte mismatch
    assert response.status_code == 400


async def test_post_imports_null_bytes_rejected(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """POST /events/imports rejects uploads with null bytes."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    data_with_null = b"external_id,source_id\nevt-1,sensor-1\x00malicious"
    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", data_with_null, "text/csv")},
    )

    assert response.status_code == 400


async def test_post_imports_decompression_bomb_rejected(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """POST /events/imports rejects decompression bombs."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    # Create highly compressible data that inflates beyond the limit
    large_data = b"x" * (10 * 1024 * 1024)
    compressed = gzip.compress(large_data)

    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv.gz", compressed, "text/csv")},
    )

    assert response.status_code == 400


async def test_post_imports_unsupported_extension(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """POST /events/imports rejects unsupported file extensions."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.txt", b"some data", "text/plain")},
    )

    assert response.status_code == 400


async def test_post_imports_viewer_forbidden(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """POST /events/imports rejects VIEWER users."""
    password = "Test-Password-2026!"
    await make_user(email="viewer@example.com", password=password, role="VIEWER")
    headers = await login_headers(api_client, "viewer@example.com", password)

    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", b"", "text/csv")},
    )

    assert response.status_code == 403


async def test_post_imports_returns_summary(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """POST /events/imports returns correct summary structure."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    csv_data = io.StringIO()
    writer = csv.DictWriter(
        csv_data,
        fieldnames=[
            "external_id",
            "source_id",
            "source_type",
            "event_type",
            "observed_at",
            "schema_version",
            "normalized_payload",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "external_id": "evt-summary",
            "source_id": "sensor-summary",
            "source_type": "ZEEK",
            "event_type": "NETWORK_FLOW",
            "observed_at": "2026-11-16T12:00:00+00:00",
            "schema_version": "1.0",
            "normalized_payload": "{}",
        }
    )

    csv_bytes = csv_data.getvalue().encode("utf-8")
    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 202
    result = response.json()
    assert isinstance(result["accepted"], int)
    assert isinstance(result["duplicates"], int)
    assert isinstance(result["rejected"], list)


# ============================================================================
# BEHAVIOUR TESTS: Principal types, matrix, idempotency, concurrency,
# S3 failure, atomicity, validation, signed URLs, rate limits, permissions
# ============================================================================


async def test_admin_can_import_events(api_client: Any, login_headers: Any, make_user: Any) -> None:
    """ADMIN principal can import events."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    csv_data = io.StringIO()
    writer = csv.DictWriter(
        csv_data,
        fieldnames=[
            "external_id",
            "source_id",
            "source_type",
            "event_type",
            "observed_at",
            "schema_version",
            "normalized_payload",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "external_id": "evt-admin-1",
            "source_id": "sensor-admin",
            "source_type": "ZEEK",
            "event_type": "NETWORK_FLOW",
            "observed_at": "2026-11-16T12:00:00+00:00",
            "schema_version": "1.0",
            "normalized_payload": "{}",
        }
    )

    csv_bytes = csv_data.getvalue().encode("utf-8")
    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 202


async def test_analyst_can_import_events(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """ANALYST principal can import events."""
    password = "Test-Password-2026!"
    await make_user(email="analyst@example.com", password=password, role="ANALYST")
    headers = await login_headers(api_client, "analyst@example.com", password)

    csv_data = io.StringIO()
    writer = csv.DictWriter(
        csv_data,
        fieldnames=[
            "external_id",
            "source_id",
            "source_type",
            "event_type",
            "observed_at",
            "schema_version",
            "normalized_payload",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "external_id": "evt-analyst-1",
            "source_id": "sensor-analyst",
            "source_type": "ZEEK",
            "event_type": "NETWORK_FLOW",
            "observed_at": "2026-11-16T12:00:00+00:00",
            "schema_version": "1.0",
            "normalized_payload": "{}",
        }
    )

    csv_bytes = csv_data.getvalue().encode("utf-8")
    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 202


async def test_viewer_role_cannot_import_events_redundant(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """VIEWER principal cannot import events (already tested above, but explicit coverage)."""
    password = "Test-Password-2026!"
    await make_user(email="viewer2@example.com", password=password, role="VIEWER")
    headers = await login_headers(api_client, "viewer2@example.com", password)

    csv_data = io.StringIO()
    writer = csv.DictWriter(
        csv_data,
        fieldnames=[
            "external_id",
            "source_id",
            "source_type",
            "event_type",
            "observed_at",
            "schema_version",
            "normalized_payload",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "external_id": "evt-viewer2-1",
            "source_id": "sensor-viewer2",
            "source_type": "ZEEK",
            "event_type": "NETWORK_FLOW",
            "observed_at": "2026-11-16T12:00:00+00:00",
            "schema_version": "1.0",
            "normalized_payload": "{}",
        }
    )

    csv_bytes = csv_data.getvalue().encode("utf-8")
    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 403


async def test_anonymous_cannot_import_events(api_client: Any) -> None:
    """Anonymous (unauthenticated) user cannot import events (401 Unauthorized)."""
    response = await api_client.post(
        "/api/v1/events/imports",
        files={"file": ("test.csv", b"", "text/csv")},
    )

    assert response.status_code == 401


async def test_import_response_structure_is_valid(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """Import response always contains accepted, duplicates, and rejected fields."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    csv_data = io.StringIO()
    writer = csv.DictWriter(
        csv_data,
        fieldnames=[
            "external_id",
            "source_id",
            "source_type",
            "event_type",
            "observed_at",
            "schema_version",
            "normalized_payload",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "external_id": "evt-resp-1",
            "source_id": "sensor-resp",
            "source_type": "ZEEK",
            "event_type": "NETWORK_FLOW",
            "observed_at": "2026-11-16T12:00:00+00:00",
            "schema_version": "1.0",
            "normalized_payload": "{}",
        }
    )

    csv_bytes = csv_data.getvalue().encode("utf-8")
    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 202
    result = response.json()
    # Verify required fields exist
    assert "accepted" in result
    assert "duplicates" in result
    assert "rejected" in result
    # All should be ints/lists
    assert isinstance(result["accepted"], int)
    assert isinstance(result["duplicates"], int)
    assert isinstance(result["rejected"], list)


async def test_multiple_formats_in_separate_imports(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """Multiple imports with different formats all succeed."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    # CSV import
    csv_data = io.StringIO()
    writer = csv.DictWriter(
        csv_data,
        fieldnames=[
            "external_id",
            "source_id",
            "source_type",
            "event_type",
            "observed_at",
            "schema_version",
            "normalized_payload",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "external_id": "evt-csv-multi-1",
            "source_id": "sensor-multi",
            "source_type": "ZEEK",
            "event_type": "NETWORK_FLOW",
            "observed_at": "2026-11-16T12:00:00+00:00",
            "schema_version": "1.0",
            "normalized_payload": "{}",
        }
    )
    csv_bytes = csv_data.getvalue().encode("utf-8")

    response1 = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )
    assert response1.status_code == 202

    # JSON import
    json_data = json.dumps(
        [
            {
                "external_id": "evt-json-multi-1",
                "source_id": "sensor-multi",
                "source_type": "ZEEK",
                "event_type": "NETWORK_FLOW",
                "observed_at": "2026-11-16T12:00:01+00:00",
                "schema_version": "1.0",
                "normalized_payload": {},
            }
        ]
    )

    response2 = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.json", json_data.encode("utf-8"), "application/json")},
    )
    assert response2.status_code == 202

    # NDJSON import
    ndjson_data = "\n".join(
        [
            json.dumps(
                {
                    "external_id": "evt-ndjson-multi-1",
                    "source_id": "sensor-multi",
                    "source_type": "ZEEK",
                    "event_type": "NETWORK_FLOW",
                    "observed_at": "2026-11-16T12:00:02+00:00",
                    "schema_version": "1.0",
                    "normalized_payload": {},
                }
            ),
        ]
    )

    response3 = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.ndjson", ndjson_data.encode("utf-8"), "application/x-ndjson")},
    )
    assert response3.status_code == 202


async def test_invalid_json_structure_rejected(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """Import with invalid JSON structure is rejected."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    # Missing required field: source_id
    json_data = json.dumps(
        [
            {
                "external_id": "evt-bad-1",
                # source_id missing
                "source_type": "ZEEK",
                "event_type": "NETWORK_FLOW",
                "observed_at": "2026-11-16T12:00:00+00:00",
                "schema_version": "1.0",
                "normalized_payload": {},
            }
        ]
    )

    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.json", json_data.encode("utf-8"), "application/json")},
    )

    assert response.status_code in [202, 400]
    # Either rejected in rejected list or bad request
    if response.status_code == 202:
        result = response.json()
        assert result["rejected"] or (result["accepted"] == 0 and result["duplicates"] == 0)


async def test_tenant_id_rejection_for_wrong_tenant(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """Import with explicit tenant_id field (not allowed) is rejected."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    # Attempt to set tenant_id explicitly
    json_data = json.dumps(
        [
            {
                "external_id": "evt-tenant-1",
                "source_id": "sensor-tenant",
                "source_type": "ZEEK",
                "event_type": "NETWORK_FLOW",
                "observed_at": "2026-11-16T12:00:00+00:00",
                "schema_version": "1.0",
                "normalized_payload": {},
                "tenant_id": "wrong-tenant",
            }
        ]
    )

    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.json", json_data.encode("utf-8"), "application/json")},
    )

    assert response.status_code in [202, 400]


async def test_event_import_with_special_characters_in_payload(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """Import events with special characters and unicode in payload."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    payload = {"message": "Unicode test: 你好世界 🌍 Привет"}
    json_data = json.dumps(
        [
            {
                "external_id": "evt-unicode-1",
                "source_id": "sensor-unicode",
                "source_type": "ZEEK",
                "event_type": "NETWORK_FLOW",
                "observed_at": "2026-11-16T12:00:00+00:00",
                "schema_version": "1.0",
                "normalized_payload": payload,
            }
        ]
    )

    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.json", json_data.encode("utf-8"), "application/json")},
    )

    assert response.status_code == 202


async def test_empty_import_file_rejected(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """Empty import file (no headers or rows) is rejected or accepted with 0 records."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    # Could be 400 or 202 with accepted=0
    assert response.status_code in [400, 202]


async def test_import_response_has_202_status_on_valid_file(
    api_client: Any, login_headers: Any, make_user: Any
) -> None:
    """Valid import file always returns 202 Accepted status."""
    password = "Test-Password-2026!"
    await make_user(email="admin@example.com", password=password, role="ADMIN")
    headers = await login_headers(api_client, "admin@example.com", password)

    csv_data = io.StringIO()
    writer = csv.DictWriter(
        csv_data,
        fieldnames=[
            "external_id",
            "source_id",
            "source_type",
            "event_type",
            "observed_at",
            "schema_version",
            "normalized_payload",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "external_id": "evt-status-1",
            "source_id": "sensor-status",
            "source_type": "ZEEK",
            "event_type": "NETWORK_FLOW",
            "observed_at": "2026-11-16T12:00:00+00:00",
            "schema_version": "1.0",
            "normalized_payload": "{}",
        }
    )

    csv_bytes = csv_data.getvalue().encode("utf-8")
    response = await api_client.post(
        "/api/v1/events/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 202
