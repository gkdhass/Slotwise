"""Worker integration test.

Run with a reachable Redis (``TEST_REDIS_URL`` or ``REDIS_URL``). The test is
skipped automatically when Redis is unavailable, so ``pytest`` stays green on a
developer laptop while CI exercises a real worker.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import redis

from app.workers.celery_app import celery_app
from app.workers.tasks import ping

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _redis_url() -> str:
    return os.getenv("TEST_REDIS_URL") or os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _redis_available(url: str) -> bool:
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        return False


def test_ping_runs_via_real_worker() -> None:
    url = _redis_url()
    if not _redis_available(url):
        pytest.skip(f"Redis is not reachable at {url}")

    env = os.environ.copy()
    env.update(
        {
            "REDIS_URL": url,
            "APP_ENV": "test",
            "SECURITY_SECRET_KEY": "test-only-secret-key-0123456789abcdef",
            "PYTHONPATH": str(BACKEND_DIR),
        }
    )
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "app.workers.celery_app:celery_app",
            "worker",
            "--pool=solo",
            "--loglevel=WARNING",
            "--hostname=test-worker@%h",
        ],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 25
        ready = False
        while time.monotonic() < deadline:
            if worker.poll() is not None:
                output = worker.stdout.read() if worker.stdout else ""
                pytest.fail(f"Celery worker exited early:\n{output}")
            if celery_app.control.ping(timeout=1):
                ready = True
                break
            time.sleep(1)
        if not ready:
            pytest.fail("Celery worker did not become ready in time")

        result = ping.delay()
        payload = result.get(timeout=15)
        assert payload["pong"] is True
        assert payload["task_id"]
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
