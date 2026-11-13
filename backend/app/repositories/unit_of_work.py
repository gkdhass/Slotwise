"""Unit-of-work helper.

One session and one transaction per unit of work. Repositories never commit;
services call ``commit()`` exactly once after their domain change and audit row
have both been staged.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.alerts import (
    AlertRepository,
    IncidentAlertRepository,
    IncidentCommentRepository,
    IncidentRepository,
)
from app.repositories.assets import AssetRepository, SensorRepository
from app.repositories.audit import AuditRepository
from app.repositories.datasets import DatasetRepository, TrainingRunRepository
from app.repositories.events import EventLabelRepository, EventRepository
from app.repositories.identity import RefreshTokenRepository, RoleRepository, UserRepository
from app.repositories.inference import InferenceResultRepository, ModelVersionRepository
from app.repositories.responses import (
    AllowlistRepository,
    ResponseActionRepository,
    ResponsePolicyRepository,
)


class UnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession

    async def __aenter__(self) -> UnitOfWork:
        self.session = self._session_factory()
        self.roles = RoleRepository(self.session)
        self.users = UserRepository(self.session)
        self.refresh_tokens = RefreshTokenRepository(self.session)
        self.assets = AssetRepository(self.session)
        self.sensors = SensorRepository(self.session)
        self.events = EventRepository(self.session)
        self.event_labels = EventLabelRepository(self.session)
        self.alert_repo = AlertRepository(self.session)
        self.incidents = IncidentRepository(self.session)
        self.incident_alerts = IncidentAlertRepository(self.session)
        self.incident_comments = IncidentCommentRepository(self.session)
        self.model_versions = ModelVersionRepository(self.session)
        self.inference_results = InferenceResultRepository(self.session)
        self.response_policies = ResponsePolicyRepository(self.session)
        self.allowlist = AllowlistRepository(self.session)
        self.response_actions = ResponseActionRepository(self.session)
        self.audit = AuditRepository(self.session)
        self.datasets = DatasetRepository(self.session)
        self.training_runs = TrainingRunRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Closing without an explicit commit always rolls back.
        await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def flush(self) -> None:
        await self.session.flush()
