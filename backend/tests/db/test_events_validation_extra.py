"""Extra validation cases for POST /events (one test per case)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytestmark = pytest.mark.db


async def _post(api_client: Any, sensor_key: str, envelope: dict) -> Any:
    return await api_client.post(
        "/api/v1/events", headers={"X-Sensor-Key": sensor_key}, json=envelope
    )


def _base_payload() -> dict:
    return {
        "type": "network_flow",
        "src_ip": "1.1.1.1",
        "dst_ip": "2.2.2.2",
        "src_port": 80,
        "dst_port": 443,
        "protocol": 6,
        "flow_duration": 1.0,
        "flow_bytes_s": 1.0,
        "flow_bytes_d": 1.0,
        "flow_packets_s": 1.0,
        "flow_packets_d": 1.0,
        "fwd_packet_length_max": 1.0,
        "fwd_packet_length_min": 1.0,
        "fwd_packet_length_mean": 1.0,
        "fwd_packet_length_std": 1.0,
        "bwd_packet_length_max": 1.0,
        "bwd_packet_length_min": 1.0,
        "bwd_packet_length_mean": 1.0,
        "bwd_packet_length_std": 1.0,
    }


async def test_validation_nan_rejected(api_client: Any, make_user: Any, login_headers: Any) -> None:
    from tests.db.test_events_behaviour import get_sensor_key

    sensor_key = await get_sensor_key(api_client, make_user, login_headers)
    import json as _json

    body = {
        "source_id": "s",
        "source_type": "ZEEK",
        "event_type": "NETWORK_FLOW",
        "observed_at": datetime.now(UTC).isoformat(),
        "external_id": "e-nan",
        "normalized_payload": {**_base_payload(), "flow_duration": float("nan")},
    }
    raw = _json.dumps(body, allow_nan=True)
    r = await api_client.post(
        "/api/v1/events",
        headers={"X-Sensor-Key": sensor_key, "Content-Type": "application/json"},
        content=raw.encode(),
    )
    assert r.status_code == 400


async def test_validation_infinity_rejected(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    from tests.db.test_events_behaviour import get_sensor_key

    sensor_key = await get_sensor_key(api_client, make_user, login_headers)
    import json as _json

    body = {
        "source_id": "s",
        "source_type": "ZEEK",
        "event_type": "NETWORK_FLOW",
        "observed_at": datetime.now(UTC).isoformat(),
        "external_id": "e-inf",
        "normalized_payload": {**_base_payload(), "flow_duration": float("inf")},
    }
    raw = _json.dumps(body, allow_nan=True)
    r = await api_client.post(
        "/api/v1/events",
        headers={"X-Sensor-Key": sensor_key, "Content-Type": "application/json"},
        content=raw.encode(),
    )
    assert r.status_code == 400


async def test_validation_huge_number_rejected(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    from tests.db.test_events_behaviour import get_sensor_key

    sensor_key = await get_sensor_key(api_client, make_user, login_headers)
    import json as _json

    body = {
        "source_id": "s",
        "source_type": "ZEEK",
        "event_type": "NETWORK_FLOW",
        "observed_at": datetime.now(UTC).isoformat(),
        "external_id": "e-huge",
        "normalized_payload": {**_base_payload(), "flow_duration": 1e309},
    }
    raw = _json.dumps(body, allow_nan=True)
    r = await api_client.post(
        "/api/v1/events",
        headers={"X-Sensor-Key": sensor_key, "Content-Type": "application/json"},
        content=raw.encode(),
    )
    assert r.status_code == 400


async def test_validation_control_chars_rejected(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    from tests.db.test_events_behaviour import get_sensor_key

    sensor_key = await get_sensor_key(api_client, make_user, login_headers)
    env = {
        "source_id": "s\x00x",
        "source_type": "ZEEK",
        "event_type": "NETWORK_FLOW",
        "observed_at": datetime.now(UTC).isoformat(),
        "external_id": "e-ctrl",
        "normalized_payload": _base_payload(),
    }
    r = await _post(api_client, sensor_key, env)
    assert r.status_code == 400


async def test_validation_future_observed_at_rejected(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    from tests.db.test_events_behaviour import get_sensor_key

    sensor_key = await get_sensor_key(api_client, make_user, login_headers)
    future = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    env = {
        "source_id": "s",
        "source_type": "ZEEK",
        "event_type": "NETWORK_FLOW",
        "observed_at": future,
        "external_id": "e-future",
        "normalized_payload": _base_payload(),
    }
    r = await _post(api_client, sensor_key, env)
    assert r.status_code == 400


async def test_validation_too_old_observed_at_rejected(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    from tests.db.test_events_behaviour import get_sensor_key

    sensor_key = await get_sensor_key(api_client, make_user, login_headers)
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    env = {
        "source_id": "s",
        "source_type": "ZEEK",
        "event_type": "NETWORK_FLOW",
        "observed_at": old,
        "external_id": "e-old",
        "normalized_payload": _base_payload(),
    }
    r = await _post(api_client, sensor_key, env)
    assert r.status_code == 400


async def test_validation_oversize_string_rejected(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    from tests.db.test_events_behaviour import get_sensor_key

    sensor_key = await get_sensor_key(api_client, make_user, login_headers)
    env = {
        "source_id": "x" * 300,
        "source_type": "ZEEK",
        "event_type": "NETWORK_FLOW",
        "observed_at": datetime.now(UTC).isoformat(),
        "external_id": "e-big",
        "normalized_payload": _base_payload(),
    }
    r = await _post(api_client, sensor_key, env)
    assert r.status_code == 400


async def test_validation_image_frame_rejected(
    api_client: Any, make_user: Any, login_headers: Any
) -> None:
    from tests.db.test_events_behaviour import get_sensor_key

    sensor_key = await get_sensor_key(api_client, make_user, login_headers)
    env = {
        "source_id": "s",
        "source_type": "CAMERA",
        "event_type": "IMAGE_FRAME",
        "observed_at": datetime.now(UTC).isoformat(),
        "external_id": "e-img",
        "normalized_payload": {
            "type": "image_frame",
            "width": 10,
            "height": 10,
            "format": "png",
            "s3_key": "k",
            "size_bytes": 1,
        },
    }
    r = await _post(api_client, sensor_key, env)
    assert r.status_code == 400
