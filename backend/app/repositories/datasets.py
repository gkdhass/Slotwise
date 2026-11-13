"""Dataset and training-run repositories."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from app.models.datasets import Dataset, TrainingRun
from app.repositories.base import BaseRepository


class DatasetRepository(BaseRepository[Dataset]):
    model = Dataset

    async def get_by_name(self, name: str) -> Dataset | None:
        result = await self.session.execute(select(Dataset).where(Dataset.name == name))
        return result.scalar_one_or_none()

    async def create(self, values: Mapping[str, Any]) -> Dataset:
        entity = Dataset(**dict(values))
        self.session.add(entity)
        await self.session.flush()
        return entity


class TrainingRunRepository(BaseRepository[TrainingRun]):
    model = TrainingRun

    async def get_by_mlflow_run_id(self, mlflow_run_id: str) -> TrainingRun | None:
        result = await self.session.execute(
            select(TrainingRun).where(TrainingRun.mlflow_run_id == mlflow_run_id)
        )
        return result.scalar_one_or_none()

    async def list_for_dataset(self, dataset_id: uuid.UUID) -> list[TrainingRun]:
        statement = (
            select(TrainingRun)
            .where(TrainingRun.dataset_id == dataset_id)
            .order_by(TrainingRun.created_at.desc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def create(self, values: Mapping[str, Any]) -> TrainingRun:
        entity = TrainingRun(**dict(values))
        self.session.add(entity)
        await self.session.flush()
        return entity
