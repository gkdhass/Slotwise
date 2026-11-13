"""Shared response schemas."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for the next page; null at the end."
    )


class ErrorResponse(BaseModel):
    """The only error body shape returned by the API."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable, non-sensitive summary.")
    details: Any = Field(default=None, description="Optional structured context.")
    request_id: str = Field(description="Correlation ID also returned as X-Request-ID.")


class ValidationErrorDetail(BaseModel):
    location: list[str]
    message: str
    type: str
