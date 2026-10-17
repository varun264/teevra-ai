"""Domain event models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .base import CorrelationIdMixin, TimestampMixin
from .common import (
    EventId,
    EventSource,
    MachineId,
    Severity,
    Shift,
)
from .machines import MachineStatus


class MachineFaultEvent(BaseModel, CorrelationIdMixin, TimestampMixin):
    event_id: EventId
    machine_id: MachineId
    event_type: str = "MACHINE_BREAKDOWN"
    timestamp: str  # ISO
    estimated_repair_minutes: int = Field(gt=0)
    severity: Severity = Severity.HIGH
    source: EventSource = EventSource.SIMULATOR
    shift: Optional[Shift] = None
    description: Optional[str] = None

    @property
    def is_duplicate_key(self) -> str:
        return f"{self.event_type}:{self.machine_id}:{self.timestamp}"


class MachineRestoredEvent(BaseModel, CorrelationIdMixin, TimestampMixin):
    event_id: EventId
    machine_id: MachineId
    restored_at: str
    source: EventSource = EventSource.SYSTEM


class HeatReadingEvent(BaseModel, CorrelationIdMixin, TimestampMixin):
    event_id: EventId
    workstation_id: str
    temperature_c: float
    relative_humidity: float
    natural_wet_bulb_c: Optional[float] = None
    globe_temperature_c: Optional[float] = None
    wind_speed_ms: Optional[float] = None
    sensor_fresh_seconds: Optional[int] = None
    sensor_quality: str = "GOOD"
    timestamp: str

