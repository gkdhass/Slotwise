"""Readiness contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["ok", "error"]
OverallStatus = Literal["ok", "degraded"]


class DependencyCheck(BaseModel):
    status: CheckStatus
    latency_ms: float = Field(ge=0)
    detail: str | None = Field(
        default=None,
        description="Safe, non-sensitive diagnostic code. Never contains credentials.",
    )


class ReadinessResponse(BaseModel):
    status: OverallStatus
    version: str
    environment: str
    checks: dict[str, DependencyCheck]


class LivenessResponse(BaseModel):
    status: Literal["ok"]
