"""API dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.health import HealthService

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_health_service(settings: SettingsDep) -> HealthService:
    return HealthService(settings)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
