"""Idempotent bootstrap data.

Everything created here is either an operational default (roles, approval-first
response policies) or explicitly named as a sample/demo record. No production
metrics, model results or licence claims are invented: demo rows use reserved
example values and are permanently labelled ``[DEMO]``.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.core.security import hash_password, is_weak_password
from app.models.alerts import Incident
from app.models.assets import Asset
from app.models.enums import (
    AlertStatus,
    AssetType,
    Criticality,
    DatasetStatus,
    Environment,
    EventStatus,
    EventType,
    IncidentStatus,
    ModelVersionStatus,
    Pipeline,
    ResponseActionType,
    Severity,
    SourceType,
    TrainingRunStatus,
)
from app.models.identity import Role, User
from app.models.responses import AllowlistEntry, ResponsePolicy
from app.repositories.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)

DEMO_PREFIX = "[DEMO]"
SAMPLE_PREFIX = "[SAMPLE]"


class SeedError(RuntimeError):
    """Configuration or policy failure that must stop seeding."""


@dataclass
class SeedResult:
    roles_created: int = 0
    admin_created: bool = False
    admin_skipped_reason: str | None = None
    assets_created: int = 0
    policies_created: int = 0
    allowlist_created: int = 0
    demo_created: bool = False
    demo_records_created: int = 0
    demo_users_created: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "roles_created": self.roles_created,
            "admin_created": self.admin_created,
            "admin_skipped_reason": self.admin_skipped_reason,
            "assets_created": self.assets_created,
            "policies_created": self.policies_created,
            "allowlist_created": self.allowlist_created,
            "demo_created": self.demo_created,
            "demo_records_created": self.demo_records_created,
            "demo_users_created": self.demo_users_created,
            "warnings": list(self.warnings),
        }


_ROLE_DESCRIPTIONS = {
    "ADMIN": "Full administrative access, including ML operator duties.",
    "ANALYST": "Triages alerts, works incidents and requests simulated response.",
    "VIEWER": "Read-only dashboard and reporting access.",
}

_SAMPLE_ASSETS = (
    (
        "Sample Analyst Workstation",
        AssetType.WORKSTATION,
        Criticality.MEDIUM,
        "IT",
        Environment.DEV,
    ),
    ("Sample Application Server", AssetType.SERVER, Criticality.HIGH, "Platform", Environment.PROD),
    (
        "Sample Cloud Gateway",
        AssetType.CLOUD_SERVICE,
        Criticality.CRITICAL,
        "Cloud",
        Environment.PROD,
    ),
)

_SAMPLE_POLICIES = (
    (
        "Sample: block malicious IP",
        ResponseActionType.BLOCK_IP,
        {"match": {"severity": ["HIGH", "CRITICAL"], "indicator": "ip"}},
    ),
    (
        "Sample: isolate compromised host",
        ResponseActionType.ISOLATE_HOST,
        {"match": {"severity": ["CRITICAL"]}},
    ),
    (
        "Sample: disable compromised account",
        ResponseActionType.DISABLE_ACCOUNT,
        {"match": {"severity": ["HIGH", "CRITICAL"], "indicator": "user"}},
    ),
)

_SAMPLE_ALLOWLIST = (
    ("IP", "198.51.100.10", "Sample: trusted vulnerability scanner (TEST-NET-2)"),
    ("DOMAIN", "partner.example.com", "Sample: approved partner domain"),
)

_DEMO_DATASET = f"{DEMO_PREFIX} Module A synthetic events"
_DEMO_RUN = f"{DEMO_PREFIX} baseline training run"
_DEMO_MODEL = f"{DEMO_PREFIX} module-a-baseline"
_DEMO_INCIDENT = f"{DEMO_PREFIX} Suspicious authentication and endpoint activity"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class SeedService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._session_factory = session_factory or get_session_factory()

    async def run(self, *, demo: bool | None = None) -> SeedResult:
        include_demo = self.settings.seed.demo if demo is None else demo
        if include_demo and not self.settings.app.is_dev_like:
            raise SeedError("Demo data is refused outside dev/test environments.")

        result = SeedResult()
        async with UnitOfWork(self._session_factory) as uow:
            roles = await self._ensure_roles(uow, result)
            admin = await self._ensure_admin(uow, roles["ADMIN"].id, result)
            await self._ensure_assets(uow, result)
            await self._ensure_policies(uow, admin, result)
            await self._ensure_allowlist(uow, admin, result)
            if include_demo:
                created = await self._ensure_demo(uow, admin)
                result.demo_created = True
                result.demo_records_created = created
                result.demo_users_created = await self._ensure_demo_users(uow, roles, result)
            await uow.commit()
        return result

    async def _ensure_roles(self, uow: UnitOfWork, result: SeedResult) -> dict[str, Role]:
        roles: dict[str, Role] = {}
        for name, description in _ROLE_DESCRIPTIONS.items():
            role = await uow.roles.get_by_name(name)
            if role is None:
                role = uow.roles.add(Role(name=name, description=description))
                await uow.flush()
                result.roles_created += 1
            roles[name] = role
        return roles

    async def _ensure_admin(
        self, uow: UnitOfWork, admin_role_id: uuid.UUID, result: SeedResult
    ) -> User | None:
        seed = self.settings.seed
        if seed.admin_password is None or not seed.admin_password.get_secret_value().strip():
            result.admin_skipped_reason = "SEED_ADMIN_PASSWORD is not set"
            result.warnings.append("admin account was not seeded because no password was supplied")
            logger.warning("seed_admin_skipped", extra={"reason": "password_missing"})
            return None

        password = seed.admin_password.get_secret_value()
        email = seed.admin_email.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise SeedError("SEED_ADMIN_EMAIL is not a valid email address")
        if not self.settings.app.is_dev_like and is_weak_password(password, email=email):
            raise SeedError(
                "SEED_ADMIN_PASSWORD is weak or a placeholder; set a strong unique password"
            )

        existing = await uow.users.get_by_email(email)
        if existing is not None:
            return existing

        user = User(
            email=email,
            password_hash=hash_password(password),
            role_id=admin_role_id,
            is_active=True,
            # The seeded administrator must replace the bootstrap credential on
            # first sign-in; permission-protected routes refuse until it does.
            must_change_password=True,
        )
        uow.users.add(user)
        await uow.flush()
        result.admin_created = True
        logger.info("seed_admin_created", extra={"user_id": str(user.id)})
        return user

    async def _ensure_demo_users(
        self, uow: UnitOfWork, roles: dict[str, Role], result: SeedResult
    ) -> int:
        """Create labelled demo principals, dev/test only.

        ``run`` already refuses demo mode outside dev/test, and a password is only
        used when the operator supplied one through the environment. A missing
        password is a warning, never a built-in default.
        """
        seed = self.settings.seed
        created = 0
        candidates = (
            ("ANALYST", seed.analyst_email, seed.analyst_password),
            ("VIEWER", seed.viewer_email, seed.viewer_password),
        )
        for role_name, email, password in candidates:
            if password is None or not password.get_secret_value().strip():
                result.warnings.append(
                    f"demo {role_name.lower()} user skipped: no password supplied"
                )
                continue
            normalised = email.strip().lower()
            if "@" not in normalised or normalised.startswith("@") or normalised.endswith("@"):
                raise SeedError(f"Demo {role_name} email is not a valid email address")
            if await uow.users.get_by_email(normalised) is not None:
                continue
            user = User(
                email=normalised,
                password_hash=hash_password(password.get_secret_value()),
                role_id=roles[role_name].id,
                is_active=True,
                must_change_password=True,
            )
            uow.users.add(user)
            created += 1
            logger.info(
                "seed_demo_user_created",
                extra={"user_id": str(user.id), "role": role_name},
            )
        await uow.flush()
        return created

    async def _ensure_assets(self, uow: UnitOfWork, result: SeedResult) -> None:
        for name, asset_type, criticality, owner, environment in _SAMPLE_ASSETS:
            if await uow.assets.get_by_name(name) is not None:
                continue
            uow.assets.add(
                Asset(
                    name=name,
                    asset_type=asset_type.value,
                    criticality=criticality.value,
                    owner_team=owner,
                    environment=environment.value,
                    is_active=True,
                )
            )
            result.assets_created += 1
        await uow.flush()

    async def _ensure_policies(
        self, uow: UnitOfWork, admin: User | None, result: SeedResult
    ) -> None:
        for name, action_type, conditions in _SAMPLE_POLICIES:
            if await uow.response_policies.get_by_name(name) is not None:
                continue
            uow.response_policies.add(
                ResponsePolicy(
                    name=name,
                    action_type=action_type.value,
                    conditions=conditions,
                    requires_approval=True,
                    enabled=True,
                    created_by=admin.id if admin else None,
                )
            )
            result.policies_created += 1
        await uow.flush()

    async def _ensure_allowlist(
        self, uow: UnitOfWork, admin: User | None, result: SeedResult
    ) -> None:
        for entry_type, value, reason in _SAMPLE_ALLOWLIST:
            if await uow.allowlist.find_active(entry_type, value) is not None:
                continue
            uow.allowlist.add(
                AllowlistEntry(
                    entry_type=entry_type,
                    value=value,
                    reason=reason,
                    created_by=admin.id if admin else None,
                    is_active=True,
                )
            )
            result.allowlist_created += 1
        await uow.flush()

    async def _ensure_demo(self, uow: UnitOfWork, admin: User | None) -> int:
        created = 0
        admin_id = admin.id if admin else None
        now = datetime.now(UTC)

        dataset = await uow.datasets.get_by_name(_DEMO_DATASET)
        if dataset is None:
            dataset = await uow.datasets.create(
                {
                    "name": _DEMO_DATASET,
                    "modality": "network_flow",
                    "source": "Generated locally by seed --demo; no third-party data",
                    "licence": "Synthetic demo data; no licence restrictions",
                    "object_uri": (f"s3://{self.settings.minio.bucket}/datasets/demo/events.jsonl"),
                    "checksum": _sha256(b"slotwise-demo-dataset-v1"),
                    "label_schema": {"classes": ["benign", "brute_force", "suspicious_process"]},
                    "status": DatasetStatus.ACTIVE.value,
                    "created_by": admin_id,
                }
            )
            created += 1

        run = await uow.training_runs.get_by_mlflow_run_id("demo-run-0001")
        if run is None:
            run = await uow.training_runs.create(
                {
                    "dataset_id": dataset.id,
                    "pipeline": Pipeline.MODULE_A.value,
                    "base_model": "demo-placeholder",
                    "hyperparameters": {"note": "demo placeholder, no training performed"},
                    "mlflow_run_id": "demo-run-0001",
                    "status": TrainingRunStatus.PENDING.value,
                    "metrics": {},
                }
            )
            created += 1

        model = await uow.model_versions.get_by_identity(
            Pipeline.MODULE_A.value, _DEMO_MODEL, "0.0-demo"
        )
        if model is None:
            model = await uow.model_versions.create(
                {
                    "pipeline": Pipeline.MODULE_A.value,
                    "model_name": _DEMO_MODEL,
                    "version": "0.0-demo",
                    "artifact_uri": (
                        f"s3://{self.settings.minio.bucket}/models/demo/module-a-baseline.onnx"
                    ),
                    "framework": "onnx",
                    "metrics": {},
                    "status": ModelVersionStatus.DRAFT.value,
                    "training_run_id": run.id,
                }
            )
            created += 1

        incident = await uow.incidents.get_by_title(_DEMO_INCIDENT)
        if incident is None:
            incident = uow.incidents.add(
                Incident(
                    title=_DEMO_INCIDENT,
                    severity=Severity.HIGH.value,
                    status=IncidentStatus.OPEN.value,
                    owner_id=admin_id,
                    opened_at=now - timedelta(hours=2),
                    summary=(
                        f"{DEMO_PREFIX} Sample incident generated by the seed command. "
                        "All events, scores and outcomes are synthetic."
                    ),
                )
            )
            await uow.flush()
            created += 1

        demo_events: tuple[dict[str, Any], ...] = (
            {
                "external_id": "demo-event-0001",
                "event_type": EventType.NETWORK_FLOW.value,
                "predicted_class": "brute_force",
                "confidence": 0.97,
                "anomaly_score": 0.91,
                "severity": Severity.HIGH.value,
                "category": "Credential attack",
                "label": "brute_force",
            },
            {
                "external_id": "demo-event-0002",
                "event_type": EventType.ENDPOINT_LOG.value,
                "predicted_class": "suspicious_process",
                "confidence": 0.81,
                "anomaly_score": 0.72,
                "severity": Severity.MEDIUM.value,
                "category": "Suspicious process",
                "label": "suspicious_process",
            },
        )

        for index, item in enumerate(demo_events, start=1):
            payload = {"demo": True, "sequence": index, "note": "synthetic demo event"}
            raw_body = f"{DEMO_PREFIX} raw event {index}".encode()
            event, event_created = await uow.events.upsert(
                {
                    "external_id": item["external_id"],
                    "source_type": SourceType.UPLOAD.value,
                    "source_id": "demo-sensor",
                    "observed_at": now - timedelta(minutes=30 * index),
                    "event_type": item["event_type"],
                    "raw_ref": (
                        f"s3://{self.settings.minio.bucket}/events/demo/"
                        f"{item['external_id']}.json"
                    ),
                    "raw_checksum": _sha256(raw_body),
                    "normalized_payload": payload,
                    "schema_version": "1.0",
                    "processing_status": EventStatus.PROCESSED.value,
                }
            )
            created += int(event_created)

            if await uow.event_labels.get_for_event(event.id, str(item["label"])) is None:
                await uow.event_labels.create(
                    {
                        "event_id": event.id,
                        "label": item["label"],
                        "source": "DEMO",
                        "confidence": item["confidence"],
                        "created_by": admin_id,
                    }
                )
                created += 1

            inference = await uow.inference_results.get_for_event_class(
                event.id, model.id, str(item["predicted_class"])
            )
            if inference is None:
                inference = await uow.inference_results.create(
                    {
                        "event_id": event.id,
                        "model_version_id": model.id,
                        "predicted_class": item["predicted_class"],
                        "probabilities": {
                            "benign": round(1.0 - float(item["confidence"]), 2),
                            str(item["predicted_class"]): item["confidence"],
                        },
                        "anomaly_score": item["anomaly_score"],
                        "severity": item["severity"],
                        "inference_ms": 12 + index,
                    }
                )
                created += 1

            alert = await uow.alert_repo.get_by_inference_result(inference.id)
            if alert is None:
                alert, alert_created = await uow.alert_repo.upsert(
                    {
                        "event_id": event.id,
                        "inference_result_id": inference.id,
                        "asset_id": None,
                        "category": item["category"],
                        "severity": item["severity"],
                        "confidence": item["confidence"],
                        "status": AlertStatus.NEW.value,
                        "severity_policy_version": "demo-v1",
                        "review_required": True,
                    }
                )
                created += int(alert_created)

            linked = await uow.incident_alerts.link(incident.id, alert.id)
            created += int(linked)

        body = (
            f"{DEMO_PREFIX} Generated by `seed --demo`. "
            "All scores and outcomes are synthetic and safe to delete."
        )
        if await uow.incident_comments.find_by_body(incident.id, body) is None:
            await uow.incident_comments.create(
                {"incident_id": incident.id, "author_id": admin_id, "body": body}
            )
            created += 1

        return created
