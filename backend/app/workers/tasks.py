"""Celery tasks.

Phase 1 exposes only a non-destructive connectivity probe. Inference, ingestion
and simulated-response tasks arrive in later phases and must call the policy
guards in ``app.policies.safety`` before any response path.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from typing import Any

from celery import Task

from app.workers.celery_app import celery_app


@celery_app.task(  # type: ignore[misc]  # Celery decorators are untyped.
    name="app.workers.tasks.ping",
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    retry_jitter=True,
)
def ping(self: Task) -> dict[str, Any]:
    """Health probe task. Returns only non-sensitive runtime metadata."""
    return {
        "pong": True,
        "task_id": self.request.id,
        "worker": socket.gethostname(),
        "timestamp": datetime.now(UTC).isoformat(),
    }
