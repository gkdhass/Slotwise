"""Celery application configuration.

Security and reliability defaults:
- JSON-only serialisation (no pickle, no YAML).
- Late acknowledgement plus worker-lost rejection.
- Bounded retries and time limits so poison tasks cannot loop forever.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "slotwise",
    broker=settings.redis.url,
    backend=settings.redis.url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    task_default_retry_delay=10,
    task_annotations={"*": {"max_retries": 3}},
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_transport_options={"visibility_timeout": 3600},
    broker_pool_limit=10,
)

# Some tooling discovers the conventional ``app`` name.
app = celery_app
