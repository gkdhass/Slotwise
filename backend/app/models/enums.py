"""Shared lifecycle and classification vocabularies.

Status columns are stored as ``text`` with named CHECK constraints rather than
native PostgreSQL enums. Rationale: changing a native enum requires
``ALTER TYPE ... ADD VALUE`` (which cannot run inside a transaction in older
servers) and removing a value requires recreating the type and every dependent
column, which makes the downgrade path fragile. CHECK-constrained text keeps
every migration reversible with plain DDL while still rejecting invalid values
inside the database. This choice is applied consistently to every lifecycle
status in the schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypeVar

_E = TypeVar("_E", bound=StrEnum)


class RoleName(StrEnum):
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class Criticality(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AssetType(StrEnum):
    WORKSTATION = "WORKSTATION"
    SERVER = "SERVER"
    NETWORK_DEVICE = "NETWORK_DEVICE"
    CLOUD_SERVICE = "CLOUD_SERVICE"
    APPLICATION = "APPLICATION"
    OTHER = "OTHER"


class Environment(StrEnum):
    DEV = "DEV"
    STAGING = "STAGING"
    PROD = "PROD"


class SensorStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    REVOKED = "REVOKED"


class SourceType(StrEnum):
    ZEEK = "ZEEK"
    SURICATA = "SURICATA"
    WAZUH = "WAZUH"
    UPLOAD = "UPLOAD"
    CAMERA = "CAMERA"
    OTHER = "OTHER"


class EventType(StrEnum):
    NETWORK_FLOW = "NETWORK_FLOW"
    ENDPOINT_LOG = "ENDPOINT_LOG"
    PHISHING_ITEM = "PHISHING_ITEM"
    IMAGE_FRAME = "IMAGE_FRAME"
    OTHER = "OTHER"


class EventStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(StrEnum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ASSIGNED = "ASSIGNED"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    SUPPRESSED = "SUPPRESSED"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Pipeline(StrEnum):
    MODULE_A = "MODULE_A"
    MODULE_B = "MODULE_B"


class ModelVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    TRAINED = "TRAINED"
    EVALUATED = "EVALUATED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class ResponseActionStatus(StrEnum):
    REQUESTED = "REQUESTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class ResponseActionType(StrEnum):
    BLOCK_IP = "BLOCK_IP"
    ISOLATE_HOST = "ISOLATE_HOST"
    DISABLE_ACCOUNT = "DISABLE_ACCOUNT"
    BLOCK_DOMAIN = "BLOCK_DOMAIN"
    QUARANTINE_FILE = "QUARANTINE_FILE"


class AllowlistEntryType(StrEnum):
    IP = "IP"
    CIDR = "CIDR"
    DOMAIN = "DOMAIN"
    URL = "URL"
    HASH = "HASH"
    USER = "USER"


class DatasetStatus(StrEnum):
    REGISTERED = "REGISTERED"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class TrainingRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


#: Actions that change the security posture of a real (if simulated) target.
#: The database refuses self-approval for these regardless of feature flags.
HIGH_IMPACT_ACTION_TYPES: frozenset[ResponseActionType] = frozenset(
    {
        ResponseActionType.BLOCK_IP,
        ResponseActionType.ISOLATE_HOST,
        ResponseActionType.DISABLE_ACCOUNT,
        ResponseActionType.QUARANTINE_FILE,
    }
)


def sql_values(enum_cls: type[_E]) -> str:
    """Render an enum's values as a SQL ``IN`` list.

    The input is always a trusted Python enum, never request data, so building a
    CHECK snippet this way cannot introduce user-controlled SQL.
    """
    return ", ".join(f"'{member.value}'" for member in enum_cls)


def sql_high_impact_values() -> str:
    return ", ".join(f"'{member.value}'" for member in sorted(HIGH_IMPACT_ACTION_TYPES))
