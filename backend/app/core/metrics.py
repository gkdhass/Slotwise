"""Prometheus metrics and the Celery queue-depth reporter."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Final

import redis
from prometheus_client import Counter, Gauge, Histogram

from app.core.config import Settings

logger = logging.getLogger(__name__)

REQUEST_COUNT: Final = Counter(
    "http_requests_total",
    "Total HTTP requests processed by the API.",
    labelnames=("method", "path", "status"),
)

REQUEST_DURATION: Final = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

CELERY_QUEUE_DEPTH: Final = Gauge(
    "celery_queue_depth",
    "Approximate number of pending Celery tasks per queue.",
    labelnames=("queue",),
)

APP_INFO: Final = Gauge(
    "app_info",
    "Static application build information.",
    labelnames=("version", "environment"),
)


def refresh_queue_depth(settings: Settings) -> dict[str, int]:
    """Read queue lengths from Redis with short timeouts.

    This is intentionally best-effort: monitoring must never take the API down.
    """
    depths: dict[str, int] = {}
    client = redis.Redis.from_url(
        settings.redis.url,
        socket_connect_timeout=min(settings.redis.socket_timeout_seconds, 2.0),
        socket_timeout=min(settings.redis.socket_timeout_seconds, 2.0),
        decode_responses=True,
    )
    try:
        for queue in settings.redis.queue_names:
            depth = int(client.llen(queue))
            depths[queue] = depth
            CELERY_QUEUE_DEPTH.labels(queue=queue).set(depth)
    finally:
        client.close()
    return depths


async def queue_depth_reporter(settings: Settings) -> None:
    """Refresh the queue gauge periodically for Prometheus scrapes."""
    while True:
        try:
            await asyncio.to_thread(refresh_queue_depth, settings)
        except Exception as exc:
            logger.warning(
                "queue_depth_refresh_failed",
                extra={"error_type": type(exc).__name__},
            )
        await asyncio.sleep(settings.redis.queue_depth_refresh_seconds)


def start_queue_depth_reporter(settings: Settings) -> asyncio.Task[None]:
    return asyncio.create_task(queue_depth_reporter(settings), name="queue-depth-reporter")


async def stop_background_task(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
