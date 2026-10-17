"""Job domain models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .base import TimestampMixin
from .common import (
    JobId,
    JobStatus,
    JobType,
    MachineId,
    SlotRange,
    TimeWindow,
    WorkerId,
)
from .machines import MachineCapability


class MachineJobAssignment(BaseModel):
    machine_id: MachineId
    start_slot: int
    end_slot: int  # inclusive
    worker_id: Optional[WorkerId] = None


class Job(BaseModel, TimestampMixin):
    job_id: JobId
    job_type: JobType = JobType.PRODUCTION
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(gt=0)
    release_slot: int = Field(ge=0)
    deadline_slot: int = Field(ge=0)
    priority: int = Field(default=1, ge=1, le=10)
    required_machine_type: Optional[str] = None
    compatible_machines: List[MachineId] = Field(default_factory=list)
    required_worker_roles: List[str] = Field(default_factory=list)
    required_workers: int = 1
    precedence_job_ids: List[JobId] = Field(default_factory=list)
    is_interruptible: bool = False
    is_furnace: bool = False  # non-preemptive
    power_kw: float = 0.0
    energy_kwh: float = 0.0
    restart_energy_penalty_kwh: float = 0.0
    tariff_sensitive: bool = False
    heat_exposure_level: int = Field(default=1, ge=0, le=5)
    production_target_units: int = 0
    current_slot_assignment: Optional[MachineJobAssignment] = None
    status: JobStatus = JobStatus.SCHEDULED

    @property
    def time_window(self) -> TimeWindow:
        from datetime import datetime, timedelta, timezone

        base = datetime(2026, 10, 17, tzinfo=timezone.utc)
        return TimeWindow(
            start=base + timedelta(minutes=self.release_slot * 15),
            end=base + timedelta(minutes=(self.deadline_slot + 1) * 15),
        )

    @property
    def slot_range(self) -> SlotRange:
        return SlotRange(start_slot=self.release_slot, end_slot=self.deadline_slot)

