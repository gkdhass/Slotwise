"""End-to-end checks against the edge Nginx proxy.

Requires a running stack: ``E2E_BASE_URL=https://localhost pytest tests/e2e -m e2e``.
Self-signed certificates are accepted only for this opt-in test.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.e2e


def test_edge_exposes_health_metrics_and_dashboard() -> None:
    base_url = os.getenv("E2E_BASE_URL", "https://localhost")
    with httpx.Client(verify=False, timeout=15) as client:
        health = client.get(f"{base_url}/api/v1/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.headers["x-request-id"]

        ready = client.get(f"{base_url}/api/v1/readyz")
        assert ready.status_code in {200, 503}
        body = ready.json()
        checks = body.get("checks") or body.get("details", {}).get("checks", {})
        assert set(checks) == {"postgres", "redis", "opensearch", "minio", "mlflow"}

        metrics = client.get(f"{base_url}/metrics")
        assert metrics.status_code == 200
        assert "http_requests_total" in metrics.text

        dashboard = client.get(f"{base_url}/")
        assert dashboard.status_code == 200
        assert "slotwise" in dashboard.text.lower()
