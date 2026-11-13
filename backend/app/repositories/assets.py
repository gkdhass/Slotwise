"""Asset and sensor repositories."""

from __future__ import annotations

from sqlalchemy import select

from app.models.assets import Asset, Sensor
from app.repositories.base import BaseRepository
from app.repositories.keyset import keyset_page
from app.repositories.pagination import Page


class AssetRepository(BaseRepository[Asset]):
    model = Asset

    async def get_by_name(self, name: str) -> Asset | None:
        result = await self.session.execute(select(Asset).where(Asset.name == name))
        return result.scalar_one_or_none()

    async def list_active(self, *, limit: int = 200, offset: int = 0) -> list[Asset]:
        statement = (
            select(Asset)
            .where(Asset.is_active.is_(True))
            .order_by(Asset.name)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        criticality: str | None = None,
        is_active: bool | None = None,
        environment: str | None = None,
    ) -> Page[Asset]:
        statement = select(Asset)
        if criticality is not None:
            statement = statement.where(Asset.criticality == criticality)
        if is_active is not None:
            statement = statement.where(Asset.is_active.is_(is_active))
        if environment is not None:
            statement = statement.where(Asset.environment == environment)
        return await keyset_page(
            self.session,
            statement,
            scope="assets",
            sort_column=Asset.created_at,
            id_column=Asset.id,
            limit=limit,
            cursor=cursor,
        )


class SensorRepository(BaseRepository[Sensor]):
    model = Sensor

    async def get_by_name(self, name: str) -> Sensor | None:
        result = await self.session.execute(select(Sensor).where(Sensor.name == name))
        return result.scalar_one_or_none()

    async def get_by_prefix(self, prefix: str) -> Sensor | None:
        result = await self.session.execute(
            select(Sensor).where(Sensor.credential_prefix == prefix)
        )
        return result.scalar_one_or_none()

    async def list_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        status: str | None = None,
        sensor_type: str | None = None,
    ) -> Page[Sensor]:
        statement = select(Sensor)
        if status is not None:
            statement = statement.where(Sensor.status == status)
        if sensor_type is not None:
            statement = statement.where(Sensor.sensor_type == sensor_type)
        return await keyset_page(
            self.session,
            statement,
            scope="sensors",
            sort_column=Sensor.created_at,
            id_column=Sensor.id,
            limit=limit,
            cursor=cursor,
        )

    async def list_active(self) -> list[Sensor]:
        statement = select(Sensor).where(Sensor.status == "ACTIVE").order_by(Sensor.name)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
