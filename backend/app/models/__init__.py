"""SQLAlchemy models for the Slotwise operational schema.

Importing this package registers every table on ``Base.metadata`` so Alembic
autogenerate and drift checks see the complete schema.
"""

from app.models.alerts import Alert, Incident, IncidentAlert, IncidentComment
from app.models.assets import Asset, Sensor
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.datasets import Dataset, TrainingRun
from app.models.events import Event, EventLabel
from app.models.identity import RefreshToken, Role, User
from app.models.inference import InferenceResult, ModelVersion
from app.models.responses import AllowlistEntry, ResponseAction, ResponsePolicy

__all__ = [
    "Alert",
    "AllowlistEntry",
    "Asset",
    "AuditLog",
    "Base",
    "Dataset",
    "Event",
    "EventLabel",
    "Incident",
    "IncidentAlert",
    "IncidentComment",
    "InferenceResult",
    "ModelVersion",
    "RefreshToken",
    "ResponseAction",
    "ResponsePolicy",
    "Role",
    "Sensor",
    "TrainingRun",
    "User",
]
