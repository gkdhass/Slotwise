"""Model registry and inference-result repositories."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from app.models.inference import InferenceResult, ModelVersion
from app.repositories.base import BaseRepository


class ModelVersionRepository(BaseRepository[ModelVersion]):
    model = ModelVersion

    async def get_by_identity(
        self, pipeline: str, model_name: str, version: str
    ) -> ModelVersion | None:
        statement = select(ModelVersion).where(
            ModelVersion.pipeline == pipeline,
            ModelVersion.model_name == model_name,
            ModelVersion.version == version,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_active(self, pipeline: str, model_name: str) -> ModelVersion | None:
        statement = select(ModelVersion).where(
            ModelVersion.pipeline == pipeline,
            ModelVersion.model_name == model_name,
            ModelVersion.status == "ACTIVE",
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_pipeline(
        self, pipeline: str, *, status: str | None = None
    ) -> list[ModelVersion]:
        statement = select(ModelVersion).where(ModelVersion.pipeline == pipeline)
        if status is not None:
            statement = statement.where(ModelVersion.status == status)
        statement = statement.order_by(ModelVersion.created_at.desc())
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def create(self, values: Mapping[str, Any]) -> ModelVersion:
        entity = ModelVersion(**dict(values))
        self.session.add(entity)
        await self.session.flush()
        return entity


class InferenceResultRepository(BaseRepository[InferenceResult]):
    model = InferenceResult

    async def list_for_event(self, event_id: uuid.UUID) -> list[InferenceResult]:
        statement = (
            select(InferenceResult)
            .where(InferenceResult.event_id == event_id)
            .order_by(InferenceResult.created_at.desc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_for_event_class(
        self, event_id: uuid.UUID, model_version_id: uuid.UUID, predicted_class: str
    ) -> InferenceResult | None:
        statement = select(InferenceResult).where(
            InferenceResult.event_id == event_id,
            InferenceResult.model_version_id == model_version_id,
            InferenceResult.predicted_class == predicted_class,
        )
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def create(self, values: Mapping[str, Any]) -> InferenceResult:
        entity = InferenceResult(**dict(values))
        self.session.add(entity)
        await self.session.flush()
        return entity
