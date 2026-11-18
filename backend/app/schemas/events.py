"""Event envelope and payload schemas for Phase 4-1.

Versioned envelope with strict validation, bounded sizes, and tenant rejection.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import unicodedata
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from app.core.config import get_settings
from app.models.enums import EventType, SourceType

# LOCKED DECISION: Single-tenant - any tenant_id in a payload is rejected
# LOCKED DECISION: Telemetry is untrusted input - validate, size-limit, never execute
# LOCKED DECISION: No scalers or encoders are fitted in Phase 4
# LOCKED DECISION: Module B: image_frame events are rejected while MODULE_B_ENABLED=false


class SchemaVersion(StrEnum):
    """Supported envelope schema versions."""

    V1_0 = "1.0"


class LabelSource(StrEnum):
    """Provenance of an event label."""

    SENSOR_SUPPLIED = "SENSOR_SUPPLIED"
    ANALYST = "ANALYST"
    ML = "ML"


class NetworkFlowPayload(BaseModel):
    """CIC-IDS-style network flow features plus 5-tuple."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    type: Literal["network_flow"] = "network_flow"

    # 5-tuple
    src_ip: str = Field(..., description="Source IP address")
    dst_ip: str = Field(..., description="Destination IP address")
    src_port: int = Field(..., ge=0, le=65535, description="Source port (0-65535)")
    dst_port: int = Field(..., ge=0, le=65535, description="Destination port (0-65535)")
    protocol: int = Field(..., ge=0, le=255, description="IP protocol number (0-255)")

    # CIC-IDS features
    flow_duration: float = Field(..., ge=0, description="Flow duration in seconds")
    flow_bytes_s: float = Field(..., ge=0, description="Bytes per second source→destination")
    flow_bytes_d: float = Field(..., ge=0, description="Bytes per second destination→source")
    flow_packets_s: float = Field(..., ge=0, description="Packets per second source→destination")
    flow_packets_d: float = Field(..., ge=0, description="Packets per second destination→source")
    fwd_packet_length_max: float = Field(..., ge=0, description="Max forward packet length")
    fwd_packet_length_min: float = Field(..., ge=0, description="Min forward packet length")
    fwd_packet_length_mean: float = Field(..., ge=0, description="Mean forward packet length")
    fwd_packet_length_std: float = Field(..., ge=0, description="Std forward packet length")
    bwd_packet_length_max: float = Field(..., ge=0, description="Max backward packet length")
    bwd_packet_length_min: float = Field(..., ge=0, description="Min backward packet length")
    bwd_packet_length_mean: float = Field(..., ge=0, description="Mean backward packet length")
    bwd_packet_length_std: float = Field(..., ge=0, description="Std backward packet length")

    @field_validator("src_ip", "dst_ip")
    @classmethod
    def validate_ip_address(cls, value: str) -> str:
        """Validate IP addresses with ipaddress module."""
        try:
            ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError(f"Invalid IP address: {value}") from exc
        return value


class EndpointLogPayload(BaseModel):
    """Endpoint log with capped message and structured fields."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    type: Literal["endpoint_log"] = "endpoint_log"

    host: Annotated[str, StringConstraints(max_length=255)] = Field(
        ..., description="Hostname or IP"
    )
    timestamp: AwareDatetime = Field(..., description="Log timestamp (timezone-aware)")
    category: Annotated[str, StringConstraints(max_length=100)] = Field(
        ..., description="Log category"
    )
    message: Annotated[str, StringConstraints(max_length=10_000)] = Field(
        ..., description="Log message"
    )
    structured_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured fields",
    )

    @field_validator("structured_fields")
    @classmethod
    def cap_structured_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Limit depth and size of structured fields."""
        # Cap total size
        serialized = json.dumps(value, sort_keys=True)
        if len(serialized) > 10_000:  # 10KB max for structured fields
            raise ValueError("Structured fields exceed size limit")

        # Cap depth
        def check_depth(obj: Any, depth: int = 0) -> None:
            if depth > 5:
                raise ValueError("Structured fields exceed maximum depth")
            if isinstance(obj, dict):
                for v in obj.values():
                    check_depth(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    check_depth(item, depth + 1)

        check_depth(value)
        return value


class PhishingItemPayload(BaseModel):
    """Phishing item with URL and/or text."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    type: Literal["phishing_item"] = "phishing_item"

    url: Annotated[str | None, StringConstraints(max_length=2000)] = Field(
        None,
        description="URL (parsed only, never fetched)",
    )
    text: Annotated[str | None, StringConstraints(max_length=50_000)] = Field(
        None,
        description="Text content",
    )

    @model_validator(mode="after")
    def require_url_or_text(self) -> PhishingItemPayload:
        """At least one of URL or text must be provided."""
        if not self.url and not self.text:
            raise ValueError("Either url or text must be provided")
        return self

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        """Parse URL to ensure it's valid syntax."""
        if value is None:
            return None
        try:
            parsed = urlparse(value)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("URL must have scheme and netloc")
        except Exception as exc:
            raise ValueError(f"Invalid URL: {value}") from exc
        return value


class ImageFramePayload(BaseModel):
    """Image frame metadata with S3 reference (disabled in Phase 4)."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    type: Literal["image_frame"] = "image_frame"

    width: int = Field(..., ge=1, description="Image width in pixels")
    height: int = Field(..., ge=1, description="Image height in pixels")
    format: Annotated[str, StringConstraints(max_length=10)] = Field(
        ..., description="Image format"
    )
    s3_key: Annotated[str, StringConstraints(max_length=1000)] = Field(
        ..., description="S3 object key"
    )
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    capture_time: AwareDatetime | None = Field(None, description="Image capture time")


class EventLabel(BaseModel):
    """Optional label with provenance."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    label: Annotated[str, StringConstraints(max_length=200)] = Field(..., description="Label value")
    source: LabelSource = Field(
        default=LabelSource.SENSOR_SUPPLIED,
        description="Provenance of the label",
    )
    confidence: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Confidence score (0-1) if applicable",
    )


class EventEnvelope(BaseModel):
    """Version 1.0 event envelope."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    # Client-supplied fields
    external_id: Annotated[str | None, StringConstraints(max_length=200)] = Field(
        None,
        description="Client's identifier for this event",
    )
    source_type: SourceType = Field(..., description="Event source type")
    source_id: Annotated[str, StringConstraints(max_length=200)] = Field(
        ...,
        description="Identifier of the source within its type",
    )
    observed_at: AwareDatetime = Field(..., description="When the event occurred (timezone-aware)")
    asset_id: str | None = Field(None, description="Asset UUID if known")
    event_type: EventType = Field(..., description="Type of event payload")
    raw_reference: Annotated[str | None, StringConstraints(max_length=500)] = Field(
        None,
        description="Optional reference to raw data location",
    )
    normalized_payload: Annotated[
        NetworkFlowPayload | EndpointLogPayload | PhishingItemPayload | ImageFramePayload,
        Field(discriminator="type"),
    ] = Field(
        ...,
        description="Normalized event payload",
    )
    label: EventLabel | None = Field(None, description="Optional label")
    schema_version: Literal[SchemaVersion.V1_0] = Field(
        default=SchemaVersion.V1_0,
        description="Envelope schema version",
    )

    # Server-assigned fields (reject client-supplied)
    event_id: str | None = Field(None, description="Server-assigned UUID (reject client-supplied)")

    @field_validator("event_id", mode="before")
    @classmethod
    def reject_client_event_id(cls, value: Any) -> None:
        """Reject any client-supplied event_id."""
        if value is not None:
            raise ValueError("event_id is assigned by server")
        return None

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at_timestamp(cls, value: AwareDatetime) -> AwareDatetime:
        """Reject timestamps beyond configurable future skew or older than configurable age."""
        settings = get_settings()
        # Convert to UTC for comparison
        utc_now = datetime.now(UTC)
        observed_utc = value.astimezone(UTC)

        future_skew_seconds = settings.security.event_future_skew_seconds
        max_age_days = settings.security.event_max_age_days

        if observed_utc > utc_now + timedelta(seconds=future_skew_seconds):
            raise ValueError(
                f"Observed timestamp is too far in the future (max {future_skew_seconds}s)"
            )

        if observed_utc < utc_now - timedelta(days=max_age_days):
            raise ValueError(f"Observed timestamp is too old (max {max_age_days} days)")

        return value

    @model_validator(mode="after")
    def reject_tenant_id(self) -> EventEnvelope:
        """Reject any tenant_id in the payload."""
        # LOCKED DECISION: Single-tenant - any tenant_id is rejected
        payload_dict = self.normalized_payload.model_dump()
        if "tenant_id" in payload_dict or "tenantId" in payload_dict:
            raise ValueError("tenant_id is not supported in single-tenant deployment")
        return self

    @model_validator(mode="after")
    def reject_image_frame_if_disabled(self) -> EventEnvelope:
        """Reject image_frame events when Module B is disabled."""
        settings = get_settings()
        if self.event_type == EventType.IMAGE_FRAME and not settings.features.module_b_enabled:
            raise ValueError("image_frame events are disabled (MODULE_B_ENABLED=false)")
        return self

    @model_validator(mode="after")
    def reject_control_characters(self) -> EventEnvelope:
        """Reject unicode control/format characters in any string field."""

        def _check(obj: Any) -> None:
            if isinstance(obj, str):
                for ch in obj:
                    if unicodedata.category(ch).startswith("C"):
                        raise ValueError("Control characters are not allowed")
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    _check(key)
                    _check(value)
            elif isinstance(obj, list | tuple | set):
                for item in obj:
                    _check(item)
            elif hasattr(obj, "__dict__"):
                for value in obj.__dict__.values():
                    _check(value)

        _check(self)
        return self

    def canonical_bytes(self) -> bytes:
        """Return canonical JSON bytes for checksum computation."""
        # Convert to dict with camelCase keys
        data = self.model_dump(
            mode="json",
            by_alias=True,
            exclude={"event_id", "label"},  # Exclude server-assigned and optional fields
        )
        # Ensure stable key order
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def compute_checksum(self) -> str:
        """Compute SHA-256 of canonical bytes."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class BatchEventRequest(BaseModel):
    """Batch event submission request."""

    model_config = ConfigDict(extra="forbid", strict=True)

    events: list[EventEnvelope] = Field(
        ...,
        max_length=100,  # Configurable batch size limit
        description="Batch of events to ingest",
    )


# Canonical feature list version constant
NETWORK_FLOW_FEATURE_SCHEMA_VERSION = "1.0"
