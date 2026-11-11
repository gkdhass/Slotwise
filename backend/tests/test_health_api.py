"""Health endpoint and metrics contract (unit level)."""

from __future__ import annotations

import pytest

from app.core.metrics import CELERY_QUEUE_DEPTH


async def test_healthz_returns_ok(app, client) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_metrics_exposes_required_families(app, client) -> None:
    CELERY_QUEUE_DEPTH.labels(queue="celery").set(0)
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "http_request_duration_seconds" in body
    assert "http_requests_total" in body
    assert "celery_queue_depth" in body
    assert "app_info" in body


@pytest.mark.parametrize(
    "path",
    ["/docs-not-configured"],
)
async def test_unknown_path_uses_standard_error(app, client, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message", "details", "request_id"}
