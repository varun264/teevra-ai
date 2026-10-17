"""Scheduling solver result models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .base import TimestampMixin
from .common import (
    CommitResult,
    JobId,
    JobStatus,
    MachineId,
    Money,
    ScheduleVersionId,
    SolverStatus,
    WorkerId,
)
from .schedule import ScheduleEntry, ScheduleVersion


class OptimizationObjective(BaseModel):
    priority1_safety_feasibility: bool = True
    priority2_min_missed_deadlines: int = 0
    priority3_min_disruption: int = 0
    priority4_min_energy_cost: float = 0.0


class JobChangeEvidence(BaseModel):
    job_id: JobId
    change_type: str
    previous_machine: Optional[MachineId] = None
    new_machine: Optional[MachineId] = None
    previous_start_slot: Optional[int] = None
    new_start_slot: Optional[int] = None
    reason: str
    safety_validated: bool = False
    worker_id: Optional[WorkerId] = None


class SolverResult(BaseModel, TimestampMixin):
    solver_status: SolverStatus
    objective_value: Optional[float] = None
    objective_components: OptimizationObjective = Field(
        default_factory=OptimizationObjective
    )
    previous_schedule_version: ScheduleVersionId
    new_schedule_version: ScheduleVersionId
    jobs_unchanged: int = 0
    jobs_reassigned: int = 0
    jobs_delayed: int = 0
    jobs_blocked: int = 0
    expected_output_percent: float = 100.0
    electricity_cost_before_inr: float = 0.0
    electricity_cost_after_inr: float = 0.0
    restart_energy_before_kwh: float = 0.0
    restart_energy_after_kwh: float = 0.0
    validated_heat_breaches: int = 0
    recovery_duration_ms: float = 0.0
    safety_validation_result: dict = Field(default_factory=dict)
    human_approval_required: bool = False
    commit_result: CommitResult = CommitResult.COMMITTED
    change_evidence: List[JobChangeEvidence] = Field(default_factory=list)
    infeasibility_report: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)

    @property
    def is_optimal(self) -> bool:
        return self.solver_status == SolverStatus.OPTIMAL

    @property
    def is_feasible(self) -> bool:
        return self.solver_status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)


class RecoveryPlan(BaseModel):
    plan_id: str
    schedule_version: ScheduleVersion
    solver_result: SolverResult
    requires_human_approval: bool = False
    safety_breaches: List[str] = Field(default_factory=list)
    auto_commit_allowed: bool = False


class ScheduleDiff(BaseModel):
    previous_version: ScheduleVersionId
    new_version: ScheduleVersionId
    changed_jobs: List[JobChangeEvidence] = Field(default_factory=list)
    unchanged_jobs: int = 0
    summary: dict = Field(default_factory=dict)

