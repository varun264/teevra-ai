"""TEEVRA AI event contracts for Pub/Sub / Eventarc."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from teevra_shared_schemas import (
    CorrelationId,
    EventId,
    EventSource,
    MachineId,
    Severity,
    UTCNow,
)


class EventEnvelope(BaseModel):
    event_id: EventId = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    event_type: str
    source: EventSource = EventSource.SYSTEM
    timestamp: str = Field(default_factory=UTCNow)
    correlation_id: Optional[CorrelationId] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None


class MachineFaultEnvelope(EventEnvelope):
    event_type: str = "MACHINE_FAULT"


class HeatRiskEnvelope(EventEnvelope):
    event_type: str = "HEAT_RISK"


class ScheduleUpdateEnvelope(EventEnvelope):
    event_type: str = "SCHEDULE_UPDATE"


class WorkerCheckInEnvelope(EventEnvelope):
    event_type: str = "WORKER_CHECK_IN"


__all__ = [
    "EventEnvelope",
    "MachineFaultEnvelope",
    "HeatRiskEnvelope",
    "ScheduleUpdateEnvelope",
    "WorkerCheckInEnvelope",
]
