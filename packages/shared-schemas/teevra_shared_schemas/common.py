"""Common ID types, enums, and shared value objects."""

from __future__ import annotations

from datetime import timedelta
from enum import Enum as PyEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

# --- Opaque ID types ---

MachineId = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
JobId = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
ScheduleVersionId = Annotated[
    str, StringConstraints(min_length=1, strip_whitespace=True)
]
WorkerId = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
WorkstationId = Annotated[
    str, StringConstraints(min_length=1, strip_whitespace=True)
]
AgentId = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
CorrelationId = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
EventId = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
AlertId = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


def _new_id() -> str:
    return uuid4().hex


# --- Enums ---


class Severity(PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskLevel(PyEnum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    HIGH_RISK = "HIGH_RISK"
    STOP_WORK = "STOP_WORK"
    UNKNOWN = "UNKNOWN"


class Role(PyEnum):
    SUPERVISOR = "SUPERVISOR"
    PLANNER = "PLANNER"
    OPERATOR = "OPERATOR"
    WORKER = "WORKER"
    ADMIN = "ADMIN"


class Shift(PyEnum):
    A = "A"
    B = "B"


SlotDurationMinutes = Literal[15]


class JobType(PyEnum):
    PRODUCTION = "PRODUCTION"
    MAINTENANCE = "MAINTENANCE"
    INTERRUPTIBLE = "INTERRUPTIBLE"
    FURNACE = "FURNACE"  # non-preemptive furnace job


class JobStatus(PyEnum):
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    DELAYED = "DELAYED"
    REASSIGNED = "REASSIGNED"
    CANCELLED = "CANCELLED"


class MachineStatus(PyEnum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    DOWN = "DOWN"
    MAINTENANCE = "MAINTENANCE"
    DEGRADED = "DEGRADED"


class SolverStatus(str, PyEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    UNKNOWN = "UNKNOWN"
    MODEL_INVALID = "MODEL_INVALID"
    NOT_SOLVED = "NOT_SOLVED"


class ScheduleChangeType(str, PyEnum):
    UNCHANGED = "UNCHANGED"
    REASSIGNED = "REASSIGNED"
    DELAYED = "DELAYED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class HeatStatus(str, PyEnum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    HIGH_RISK = "HIGH_RISK"
    STOP_WORK = "STOP_WORK"
    UNKNOWN = "UNKNOWN"


class CheckInResponse(str, PyEnum):
    OK = "OK"
    TOO_HOT = "TOO_HOT"
    SOS = "SOS"
    MISSED = "MISSED"


class AlertStatus(str, PyEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class ApprovalStatus(str, PyEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CommitResult(str, PyEnum):
    COMMITTED = "COMMITTED"
    REJECTED_CONFLICT = "REJECTED_CONFLICT"
    REJECTED_SAFETY = "REJECTED_SAFETY"
    REJECTED_APPROVAL = "REJECTED_APPROVAL"


class EventSource(str, PyEnum):
    SIMULATOR = "SIMULATOR"
    SENSOR = "SENSOR"
    OPERATOR = "OPERATOR"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class Language(str, PyEnum):
    TELUGU = "te"
    ENGLISH = "en"


# --- Value objects ---


class Money(BaseModel):
    amount_inr: float
    currency: str = "INR"


class Energy(BaseModel):
    kwh: float
    cost_inr: float


class SlotRange(BaseModel):
    start_slot: int
    end_slot: int  # inclusive

    @property
    def duration_minutes(self) -> int:
        return (self.end_slot - self.start_slot + 1) * 15


class TimeWindow(BaseModel):
    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0


class Coordinates(BaseModel):
    x: float
    y: float

