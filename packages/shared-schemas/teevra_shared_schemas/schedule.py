"""Schedule domain models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .base import TimestampMixin
from .common import (
    JobId,
    JobStatus,
    MachineId,
    ScheduleVersionId,
    SlotRange,
    WorkerId,
)
from .machines import MachineStatus


class ScheduleEntry(BaseModel):
    job_id: JobId
    machine_id: MachineId
    start_slot: int
    end_slot: int  # inclusive
    worker_id: Optional[WorkerId] = None
    version_id: ScheduleVersionId
    is_frozen: bool = False


class FrozenWindow(BaseModel):
    start_slot: int
    end_slot: int  # inclusive

    def contains(self, slot: int) -> bool:
        return self.start_slot <= slot <= self.end_slot


class ScheduleVersion(BaseModel, TimestampMixin):
    version_id: ScheduleVersionId
    factory_id: str
    horizon_start_slot: int = 0
    horizon_end_slot: int = Field(default=191)  # 48h * 4 slots/hr
    slot_duration_minutes: int = 15
    frozen_window: FrozenWindow
    entries: List[ScheduleEntry] = Field(default_factory=list)
    is_committed: bool = False
    parent_version_id: Optional[ScheduleVersionId] = None
    solver_status: Optional[str] = None
    objective_value: Optional[float] = None
    commit_correlation_id: Optional[str] = None

    def entry_for_job(self, job_id: JobId) -> Optional[ScheduleEntry]:
        for e in self.entries:
            if e.job_id == job_id:
                return e
        return None

    def machine_jobs(self, machine_id: MachineId) -> List[ScheduleEntry]:
        return [e for e in self.entries if e.machine_id == machine_id]

    def validate_no_overlap(self) -> list[str]:
        errors: list[str] = []
        by_machine: dict[MachineId, list[ScheduleEntry]] = {}
        for e in self.entries:
            by_machine.setdefault(e.machine_id, []).append(e)
        for mid, jobs in by_machine.items():
            jobs.sort(key=lambda e: e.start_slot)
            for i in range(len(jobs)):
                for j in range(i + 1, len(jobs)):
                    a, b = jobs[i], jobs[j]
                    if a.start_slot <= b.end_slot and b.start_slot <= a.end_slot:
                        errors.append(
                            f"overlap on {mid}: {a.job_id} [{a.start_slot},{a.end_slot}] vs "
                            f"{b.job_id} [{b.start_slot},{b.end_slot}]"
                        )
        return errors

