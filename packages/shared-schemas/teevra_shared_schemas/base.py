"""Base entities, timestamp handling, and mixins."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


def UTCNow() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Normalize a datetime to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_kolkata(value: datetime) -> datetime:
    """Convert a UTC datetime to Asia/Kolkata for presentation."""
    utc = as_utc(value)
    return utc.astimezone(IST)


class BaseEntity(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
        extra="forbid",
    )


class TimestampMixin:
    created_at: datetime = Field(default_factory=UTCNow)
    updated_at: Optional[datetime] = None

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _normalize(cls, v: Any) -> Any:
        if v is None:
            return v
        return as_utc(v) if isinstance(v, datetime) else v


class CorrelationIdMixin:
    correlation_id: str = Field(
        default_factory=lambda: __import__("uuid").uuid4().hex,
        description="Correlation ID for distributed tracing.",
    )


class AuditMixin:
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    audit_correlation_id: Optional[str] = None


from typing import Generic, TypeVar

T = TypeVar("T")


class Pagination(BaseModel):
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int

