"""Celery task behaviour and worker configuration."""

from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.tasks import ping


def test_celery_uses_json_only_and_safe_defaults() -> None:
    conf = celery_app.conf
    assert conf.task_serializer == "json"
    assert conf.result_serializer == "json"
    assert list(conf.accept_content) == ["json"]
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_time_limit and conf.task_time_limit <= 600
    assert conf.task_annotations["*"]["max_retries"] == 3


def test_ping_runs_eagerly() -> None:
    previous = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    try:
        result = ping.delay()
        payload = result.get(timeout=5)
    finally:
        celery_app.conf.task_always_eager = previous

    assert payload["pong"] is True
    assert payload["timestamp"].endswith("+00:00")
    assert isinstance(payload["worker"], str) and payload["worker"]
