"""Seed command: idempotency, credential policy and demo isolation."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import Settings, reset_settings_cache
from app.core.security import verify_password
from app.models.alerts import Alert, Incident, IncidentComment
from app.models.assets import Asset
from app.models.audit import AuditLog
from app.models.datasets import Dataset, TrainingRun
from app.models.events import Event
from app.models.identity import Role, User
from app.models.inference import ModelVersion
from app.models.responses import AllowlistEntry, ResponsePolicy
from app.services.seed import DEMO_PREFIX, SeedError, SeedService

pytestmark = pytest.mark.db

STRONG_PASSWORD = "Seed-Only-Admin-Password-2026!"


@pytest.fixture
def seed_settings() -> Settings:
    reset_settings_cache()
    settings = Settings()
    settings.seed.admin_email = f"admin-{id(settings)}@example.com"
    settings.seed.admin_password = SecretStr(STRONG_PASSWORD)
    settings.seed.demo = False
    return settings


async def _counts(session_factory) -> dict[str, int]:
    models = {
        "roles": Role,
        "users": User,
        "assets": Asset,
        "policies": ResponsePolicy,
        "allowlist": AllowlistEntry,
        "audit": AuditLog,
        "datasets": Dataset,
        "training_runs": TrainingRun,
        "models": ModelVersion,
        "events": Event,
        "alerts": Alert,
        "incidents": Incident,
        "comments": IncidentComment,
    }
    async with session_factory() as session:
        return {
            name: int(await session.scalar(select(func.count()).select_from(model)) or 0)
            for name, model in models.items()
        }


async def test_seed_is_idempotent(seed_settings: Settings, session_factory) -> None:
    service = SeedService(seed_settings, session_factory=session_factory)
    first = await service.run()
    assert first.roles_created == 3
    assert first.admin_created is True
    assert first.assets_created == 3
    assert first.policies_created == 3
    assert first.allowlist_created == 2
    assert first.demo_created is False

    async with session_factory() as session:
        user = await session.scalar(
            select(User).where(User.email == seed_settings.seed.admin_email)
        )
        assert user is not None
        assert user.password_hash.startswith("$argon2")
        assert verify_password(STRONG_PASSWORD, user.password_hash)
        assert user.must_change_password is True
        assert seed_settings.seed.admin_password is not None
        assert STRONG_PASSWORD not in user.password_hash

    before = await _counts(session_factory)
    second = await service.run()
    assert second.roles_created == 0
    assert second.admin_created is False
    assert second.assets_created == 0
    assert second.policies_created == 0
    assert second.allowlist_created == 0
    assert second.demo_records_created == 0
    after = await _counts(session_factory)
    assert after == before


async def test_seed_creates_approval_first_policies(
    seed_settings: Settings, session_factory
) -> None:
    await SeedService(seed_settings, session_factory=session_factory).run()
    async with session_factory() as session:
        policies = list((await session.execute(select(ResponsePolicy))).scalars().all())
        assert policies
        assert all(policy.requires_approval for policy in policies)
        assert {policy.action_type for policy in policies} == {
            "BLOCK_IP",
            "ISOLATE_HOST",
            "DISABLE_ACCOUNT",
        }


async def test_seed_refuses_weak_password_outside_dev(session_factory) -> None:
    reset_settings_cache()
    settings = Settings()
    # Mutating the resolved settings models the staging/production deployment
    # without tripping the production secret validator at construction time.
    settings.app.env = "staging"  # type: ignore[assignment]
    settings.seed.admin_password = SecretStr("change-me")
    before = await _counts(session_factory)

    with pytest.raises(SeedError, match="weak or a placeholder"):
        await SeedService(settings, session_factory=session_factory).run()

    assert await _counts(session_factory) == before


async def test_seed_refuses_missing_password(seed_settings: Settings, session_factory) -> None:
    seed_settings.seed.admin_password = None
    result = await SeedService(seed_settings, session_factory=session_factory).run()
    assert result.admin_created is False
    assert result.admin_skipped_reason == "SEED_ADMIN_PASSWORD is not set"
    assert any("not seeded" in warning for warning in result.warnings)


async def test_demo_users_are_created_only_with_explicit_passwords(
    seed_settings: Settings, session_factory
) -> None:
    seed_settings.seed.analyst_email = "demo-analyst@example.com"
    seed_settings.seed.analyst_password = SecretStr("Demo-Analyst-Password-2026!")
    seed_settings.seed.viewer_email = "demo-viewer@example.com"
    seed_settings.seed.viewer_password = SecretStr("Demo-Viewer-Password-2026!")

    service = SeedService(seed_settings, session_factory=session_factory)
    first = await service.run(demo=True)
    assert first.demo_users_created == 2

    second = await service.run(demo=True)
    assert second.demo_users_created == 0

    async with session_factory() as session:
        analyst = await session.scalar(select(User).where(User.email == "demo-analyst@example.com"))
        viewer = await session.scalar(select(User).where(User.email == "demo-viewer@example.com"))
        assert analyst is not None and viewer is not None
        assert analyst.role_id != viewer.role_id
        assert analyst.must_change_password is True
        assert viewer.must_change_password is True


async def test_demo_users_are_skipped_without_passwords(
    seed_settings: Settings, session_factory
) -> None:
    seed_settings.seed.analyst_password = None
    seed_settings.seed.viewer_password = None
    result = await SeedService(seed_settings, session_factory=session_factory).run(demo=True)
    assert result.demo_users_created == 0
    assert any("demo analyst user skipped" in warning for warning in result.warnings)


async def test_demo_data_is_refused_outside_dev(seed_settings: Settings, session_factory) -> None:
    seed_settings.app.env = "staging"  # type: ignore[assignment]
    with pytest.raises(SeedError, match="Demo data is refused"):
        await SeedService(seed_settings, session_factory=session_factory).run(demo=True)


async def test_demo_data_is_labelled_and_idempotent(
    seed_settings: Settings, session_factory
) -> None:
    service = SeedService(seed_settings, session_factory=session_factory)
    first = await service.run(demo=True)
    assert first.demo_created is True
    assert first.demo_records_created > 0

    second = await service.run(demo=True)
    assert second.demo_records_created == 0

    async with session_factory() as session:
        incidents = list((await session.execute(select(Incident))).scalars().all())
        assert incidents and all(incident.title.startswith(DEMO_PREFIX) for incident in incidents)

        datasets = list((await session.execute(select(Dataset))).scalars().all())
        assert datasets and all(dataset.name.startswith(DEMO_PREFIX) for dataset in datasets)

        models = list((await session.execute(select(ModelVersion))).scalars().all())
        assert models
        # Demo models must never be ACTIVE and never carry fabricated metrics.
        assert all(model.status == "DRAFT" for model in models)
        assert all(model.metrics == {} for model in models)

        events = list(
            (await session.execute(select(Event).where(Event.source_id == "demo-sensor")))
            .scalars()
            .all()
        )
        assert len(events) == 2
        assert all(event.normalized_payload.get("demo") is True for event in events)

        alerts = list((await session.execute(select(Alert))).scalars().all())
        assert len(alerts) == 2
        assert all(alert.review_required for alert in alerts)
        assert all(alert.severity_policy_version == "demo-v1" for alert in alerts)

        comments = list((await session.execute(select(IncidentComment))).scalars().all())
        assert comments and all(comment.body.startswith(DEMO_PREFIX) for comment in comments)
