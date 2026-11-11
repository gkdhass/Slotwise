"""Operational endpoints: liveness, readiness and Prometheus metrics."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import HealthServiceDep
from app.core.errors import ErrorCode, build_error_response
from app.schemas.common import ErrorResponse
from app.schemas.health import LivenessResponse, ReadinessResponse

health_router = APIRouter(tags=["health"])
metrics_router = APIRouter(tags=["metrics"])


@health_router.get(
    "/healthz",
    response_model=LivenessResponse,
    operation_id="get_liveness",
    summary="Liveness probe",
    description="Returns 200 while the API process is able to serve requests.",
)
async def healthz() -> LivenessResponse:
    return LivenessResponse(status="ok")


@health_router.get(
    "/readyz",
    response_model=ReadinessResponse,
    operation_id="get_readiness",
    summary="Readiness probe",
    description=(
        "Checks PostgreSQL, Redis, OpenSearch, MinIO and MLflow independently. "
        "Returns 503 with the standard error envelope when any dependency is down; "
        "the per-dependency report is carried in details.checks."
    ),
    responses={503: {"model": ErrorResponse}},
)
async def readyz(request: Request, service: HealthServiceDep) -> JSONResponse:
    report = await service.readiness()
    if report.status != "ok":
        return build_error_response(
            status_code=503,
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            message="One or more dependencies are unavailable.",
            details=report.model_dump(mode="json"),
            request_id=str(getattr(request.state, "request_id", "-")),
        )
    return JSONResponse(status_code=200, content=report.model_dump(mode="json"))


@metrics_router.get(
    "/metrics",
    operation_id="get_metrics",
    summary="Prometheus metrics",
    response_class=Response,
    include_in_schema=False,
)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
