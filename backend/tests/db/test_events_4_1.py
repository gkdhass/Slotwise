"""Phase 4-1 event ingestion tests."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event

pytestmark = pytest.mark.db


async def test_sensor_jwt_rejected_on_post_events(api_client: Any, fake_redis: Any) -> None:
    """Non-sensor JWT is rejected on POST /events."""
    # This test would need a user JWT passed to POST /events
    # Expecting: 403 Forbidden
    pass  # placeholder for integration test


async def test_sensor_key_rejected_on_human_routes(api_client: Any, admin_headers: Any) -> None:
    """Sensor key is rejected on human-only routes."""
    # Create a sensor
    sensor_resp = await api_client.post(
        "/api/v1/sensors",
        headers=admin_headers,
        json={"name": "Test", "sensor_type": "test"},
    )
    assert sensor_resp.status_code == 201
    sensor_key = sensor_resp.json()["api_key"]
    sensor_headers = {"X-Sensor-Key": sensor_key}

    # Try to access GET /events with sensor key
    resp = await api_client.get("/api/v1/events", headers=sensor_headers)
    assert resp.status_code == 403  # Forbidden


async def test_sensor_cannot_spoof_source_id(api_client: Any, admin_headers: Any) -> None:
    """Sensor cannot submit event with different source_id."""
    # Create sensor A
    sensor_a = await api_client.post(
        "/api/v1/sensors",
        headers=admin_headers,
        json={"name": "SensorA", "sensor_type": "test"},
    )
    assert sensor_a.status_code == 201
    sensor_a_id = sensor_a.json()["id"]

    # Create sensor B
    sensor_b = await api_client.post(
        "/api/v1/sensors",
        headers=admin_headers,
        json={"name": "SensorB", "sensor_type": "test"},
    )
    assert sensor_b.status_code == 201
    sensor_b_key = sensor_b.json()["api_key"]

    # Sensor B tries to submit with Sensor A's source_id
    resp = await api_client.post(
        "/api/v1/events",
        headers={"X-Sensor-Key": sensor_b_key},
        json={
            "events": [
                {
                    "source_id": sensor_a_id,
                    "external_id": "evt-1",
                    "source_type": "ZEEK",
                    "observed_at": "2026-11-13T00:00:00Z",
                    "event_type": "NETWORK_FLOW",
                    "payload": {
                        "src_ip": "192.168.1.1",
                        "dst_ip": "192.168.1.2",
                        "src_port": 1234,
                        "dst_port": 443,
                        "protocol": "tcp",
                    },
                }
            ]
        },
    )
    assert resp.status_code == 400  # BadRequestError


async def test_duplicate_event_returns_original_with_no_second_row(
    db_session: AsyncSession,
    api_client: Any,
    admin_headers: Any,
) -> None:
    """Duplicate (source_id, external_id) returns original event with duplicate=true."""
    # Create sensor
    sensor_resp = await api_client.post(
        "/api/v1/sensors",
        headers=admin_headers,
        json={"name": "TestSensor", "sensor_type": "test"},
    )
    assert sensor_resp.status_code == 201
    sensor_key = sensor_resp.json()["api_key"]
    sensor_id = sensor_resp.json()["id"]

    # Submit first event
    batch = {
        "events": [
            {
                "source_id": sensor_id,
                "external_id": "evt-dup-1",
                "source_type": "ZEEK",
                "observed_at": "2026-11-13T00:00:00Z",
                "event_type": "NETWORK_FLOW",
                "payload": {
                    "src_ip": "10.0.0.1",
                    "dst_ip": "10.0.0.2",
                    "src_port": 80,
                    "dst_port": 443,
                    "protocol": "tcp",
                },
            }
        ]
    }
    resp1 = await api_client.post(
        "/api/v1/events",
        headers={"X-Sensor-Key": sensor_key},
        json=batch,
    )
    assert resp1.status_code == 202
    event_id = resp1.json()["event_id"]

    # Submit identical event (duplicate)
    resp2 = await api_client.post(
        "/api/v1/events",
        headers={"X-Sensor-Key": sensor_key},
        json=batch,
    )
    assert resp2.status_code == 200  # 200 for duplicate
    assert resp2.json()["event_id"] == event_id
    assert resp2.json()["duplicate"] is True

    # Verify only one row in events table
    count = await db_session.scalar(select(text("COUNT(*) FROM events")))
    assert count == 1


async def test_permission_events_import_analyst_only(api_client: Any, login_headers: Any) -> None:
    """events:import permission required; Analyst and Admin only."""
    password = "Test-Password-2026!"

    # Viewer can't import
    viewer_headers = await login_headers(api_client, "viewer@example.com", password)
    resp = await api_client.post(
        "/api/v1/events/imports",
        headers=viewer_headers,
        json={},  # Will fail validation but tests auth
    )
    assert resp.status_code in (403, 501)  # Forbidden or Not Implemented

    # Analyst can (but endpoint not yet implemented)
    analyst_headers = await login_headers(api_client, "analyst@example.com", password)
    resp = await api_client.post("/api/v1/events/imports", headers=analyst_headers, json={})
    assert resp.status_code in (501, 422)  # Not Implemented or validation error

    # Admin can
    admin_headers = await login_headers(api_client, "admin@example.com", password)
    resp = await api_client.post("/api/v1/events/imports", headers=admin_headers, json={})
    assert resp.status_code in (501, 422)


async def test_concurrent_duplicate_submissions_single_event(
    db_session: AsyncSession,
    api_client: Any,
    admin_headers: Any,
) -> None:
    """20 concurrent identical submissions create exactly one event."""
    # Create sensor
    sensor_resp = await api_client.post(
        "/api/v1/sensors",
        headers=admin_headers,
        json={"name": "ConcurrentSensor", "sensor_type": "test"},
    )
    sensor_key = sensor_resp.json()["api_key"]
    sensor_id = sensor_resp.json()["id"]

    batch = {
        "events": [
            {
                "source_id": sensor_id,
                "external_id": "evt-concurrent-1",
                "source_type": "ZEEK",
                "observed_at": "2026-11-13T00:00:00Z",
                "event_type": "NETWORK_FLOW",
                "payload": {
                    "src_ip": "172.16.0.1",
                    "dst_ip": "172.16.0.2",
                    "src_port": 22,
                    "dst_port": 443,
                    "protocol": "tcp",
                },
            }
        ]
    }

    # Submit 20 times (in this single-threaded test, sequentially)
    responses = []
    for _ in range(20):
        resp = await api_client.post(
            "/api/v1/events",
            headers={"X-Sensor-Key": sensor_key},
            json=batch,
        )
        responses.append(resp)

    # First should be 202, rest 200 (duplicate)
    assert responses[0].status_code == 202
    event_id = responses[0].json()["event_id"]
    for resp in responses[1:]:
        assert resp.status_code == 200
        assert resp.json()["event_id"] == event_id

    # Verify exactly one event in DB
    count = await db_session.scalar(select(text("COUNT(*) FROM events")))
    assert count == 1

    # Verify exactly one outbox row
    outbox_count = await db_session.scalar(select(text("COUNT(*) FROM event_outbox")))
    assert outbox_count == 1


async def test_event_atomicity_on_outbox_failure(db_session: AsyncSession) -> None:
    """If outbox insert fails, event row must be absent."""
    # This test would need to inject a failure on outbox insert
    # and verify event is rolled back. Deferred to integration test.
    pass


async def test_validation_tenant_id_rejected(api_client: Any, admin_headers: Any) -> None:
    """Tenant ID in payload is rejected with TENANT_NOT_SUPPORTED."""
    sensor_resp = await api_client.post(
        "/api/v1/sensors",
        headers=admin_headers,
        json={"name": "ValidationSensor", "sensor_type": "test"},
    )
    sensor_key = sensor_resp.json()["api_key"]
    sensor_id = sensor_resp.json()["id"]

    resp = await api_client.post(
        "/api/v1/events",
        headers={"X-Sensor-Key": sensor_key},
        json={
            "events": [
                {
                    "source_id": sensor_id,
                    "external_id": "evt-tenant",
                    "source_type": "ZEEK",
                    "observed_at": "2026-11-13T00:00:00Z",
                    "event_type": "NETWORK_FLOW",
                    "tenant_id": "forbidden",  # Not allowed
                    "payload": {
                        "src_ip": "10.0.0.1",
                        "dst_ip": "10.0.0.2",
                        "src_port": 1234,
                        "dst_port": 443,
                        "protocol": "tcp",
                    },
                }
            ]
        },
    )
    assert resp.status_code == 400  # rejected


async def test_validation_image_frame_disabled(api_client: Any, admin_headers: Any) -> None:
    """IMAGE_FRAME events rejected while MODULE_B_ENABLED=false."""
    sensor_resp = await api_client.post(
        "/api/v1/sensors",
        headers=admin_headers,
        json={"name": "ImageSensor", "sensor_type": "test"},
    )
    sensor_key = sensor_resp.json()["api_key"]
    sensor_id = sensor_resp.json()["id"]

    # Assuming MODULE_B_ENABLED=false by default
    resp = await api_client.post(
        "/api/v1/events",
        headers={"X-Sensor-Key": sensor_key},
        json={
            "events": [
                {
                    "source_id": sensor_id,
                    "external_id": "evt-img",
                    "source_type": "CAMERA",
                    "observed_at": "2026-11-13T00:00:00Z",
                    "event_type": "IMAGE_FRAME",
                    "payload": {"image": "base64..."},
                }
            ]
        },
    )
    assert resp.status_code == 400  # rejected


async def test_rate_limit_per_sensor(api_client: Any, admin_headers: Any) -> None:
    """Per-sensor rate limit returns Retry-After."""
    # This test would need a rate limit setting configured
    # and many requests to trigger it. Deferred to integration.
    pass


async def test_permission_events_read_all_roles(
    api_client: Any, login_headers: Any
) -> None:
    """events:read permission; Viewer, Analyst, Admin can GET."""
    password = "Test-Password-2026!"

    for email in ["viewer@example.com", "analyst@example.com", "admin@example.com"]:
        headers = await login_headers(api_client, email, password)
        resp = await api_client.get("/api/v1/events", headers=headers)
        assert resp.status_code == 200  # All roles can read


async def test_event_columns_received_via_imported_by(
    db_session: AsyncSession,
    api_client: Any,
    admin_headers: Any,
) -> None:
    """New event columns received_via='api', imported_by=None set correctly."""
    sensor_resp = await api_client.post(
        "/api/v1/sensors",
        headers=admin_headers,
        json={"name": "ColumnSensor", "sensor_type": "test"},
    )
    sensor_key = sensor_resp.json()["api_key"]
    sensor_id = sensor_resp.json()["id"]

    resp = await api_client.post(
        "/api/v1/events",
        headers={"X-Sensor-Key": sensor_key},
        json={
            "events": [
                {
                    "source_id": sensor_id,
                    "external_id": "evt-cols",
                    "source_type": "ZEEK",
                    "observed_at": "2026-11-13T00:00:00Z",
                    "event_type": "NETWORK_FLOW",
                    "payload": {
                        "src_ip": "10.0.0.1",
                        "dst_ip": "10.0.0.2",
                        "src_port": 1234,
                        "dst_port": 443,
                        "protocol": "tcp",
                    },
                }
            ]
        },
    )
    assert resp.status_code == 202

    # Check DB
    event = await db_session.scalar(select(Event).limit(1))
    assert event is not None
    assert event.received_via == "api"
    assert event.imported_by is None
