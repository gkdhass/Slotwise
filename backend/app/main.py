"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints.health import metrics_router
from app.api.v1.router import router as v1_router
from app.core.config import Settings, get_settings
from app.core.database import dispose_engine, init_engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.metrics import (
    APP_INFO,
    start_queue_depth_reporter,
    stop_background_task,
)
from app.core.middleware import (
    PrometheusMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)

logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness, readiness and dependency status."},
    {"name": "metrics", "description": "Prometheus exposition endpoint."},
    {"name": "events", "description": "Module A event ingestion (Phase 2+)."},
    {"name": "alerts", "description": "Unified alert triage (Phase 2+)."},
    {"name": "incidents", "description": "Incident workflow (Phase 2+)."},
    {"name": "response", "description": "Human-approved simulated response (Phase 4)."},
    {"name": "models", "description": "Model registry and evaluation evidence (Phase 2+)."},
    {"name": "admin", "description": "Users, roles, sensors and audit (Phase 2+)."},
]


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(
        level=resolved.app.log_level,
        service=f"{resolved.app.name.lower()}-api",
        environment=resolved.app.env,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        init_engine(resolved)
        APP_INFO.labels(version=resolved.app.version, environment=resolved.app.env).set(1)
        reporter = start_queue_depth_reporter(resolved)
        logger.info(
            "application_started",
            extra={
                "version": resolved.app.version,
                "environment": resolved.app.env,
                "module_b_enabled": resolved.features.module_b_enabled,
            },
        )
        try:
            yield
        finally:
            await stop_background_task(reporter)
            await dispose_engine()
            logger.info("application_stopped")

    app = FastAPI(
        title="Slotwise — Organizational Threat Identification API",
        description=(
            "Hybrid security operations API. Module A (cyber events) is the core pipeline; "
            "Module B (visual threats) is feature-gated. All response actions are simulated "
            "and require human approval."
        ),
        version=resolved.app.version,
        openapi_tags=OPENAPI_TAGS,
        docs_url="/api/v1/docs" if resolved.app.docs_enabled else None,
        redoc_url="/api/v1/redoc" if resolved.app.docs_enabled else None,
        openapi_url="/api/v1/openapi.json" if resolved.app.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = resolved

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.app.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    # Operational endpoints stay unversioned for orchestrators; the same health
    # contract is also available under /api/v1 for the dashboard and proxies.
    from app.api.v1.endpoints.health import health_router

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(v1_router, prefix=resolved.app.api_v1_prefix)

    return app


app = create_app()
