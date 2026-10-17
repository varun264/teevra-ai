"""Heat stress domain models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .base import TimestampMixin
from .common import (
    AlertId,
    AlertStatus,
    CheckInResponse,
    HeatStatus,
    Language,
    RiskLevel,
    Role,
    WorkerId,
    WorkstationId,
)
from .events import HeatReadingEvent


class SensorReading(BaseModel):
    workstation_id: WorkstationId
    temperature_c: float
    relative_humidity: float  # 0-100
    natural_wet_bulb_c: Optional[float] = None
    globe_temperature_c: Optional[float] = None
    wind_speed_ms: Optional[float] = None
    sensor_fresh_seconds: Optional[int] = None
    sensor_quality: str = "GOOD"  # GOOD, STALE, FAULTY, MISSING
    outdoor_weather: Optional[dict] = None
    recorded_at: str


class WBGTReading(BaseModel):
    workstation_id: WorkstationId
    wbgt_c: Optional[float] = None
    method: str = "indoor"  # indoor, outdoor, estimated
    confidence: str = "HIGH"  # HIGH, MEDIUM, LOW, UNKNOWN
    is_valid: bool = False
    reason: Optional[str] = None
    recorded_at: str


class WorkstationHeatStatus(BaseModel, TimestampMixin):
    workstation_id: WorkstationId
    risk_level: HeatStatus = HeatStatus.UNKNOWN
    wbgt_c: Optional[float] = None
    threshold_c: Optional[float] = None
    sensor_age_seconds: Optional[int] = None
    sensor_quality: str = "UNKNOWN"
    workers_affected: int = 0
    last_evaluated_at: str


class HeatPolicy(BaseModel):
    policy_id: str
    name: str
    version: int
    approved_by: str
    approved_at: str
    # Demo thresholds - explicitly NOT certified regulatory limits
    normal_max_wbgt_c: float = 27.0
    caution_max_wbgt_c: float = 29.0
    high_risk_max_wbgt_c: float = 31.0
    stop_work_min_wbgt_c: float = 32.0
    acclimatization_adjustment_c: float = 1.0
    clothing_adjustment_c: float = 0.0
    is_certified: bool = False
    region: str = "demo"
    disclaimer: str = (
        "Demo simulation policy values. Not certified occupational health limits."
    )


class CheckIn(BaseModel, TimestampMixin):
    checkin_id: str
    worker_id: WorkerId
    workstation_id: WorkstationId
    language: Language = Language.ENGLISH
    response: CheckInResponse = CheckInResponse.MISSED
    voice_consent: bool = False
    voice_url: Optional[str] = None
    responded_at: Optional[str] = None
    reminder_sent_at: str
    overdue: bool = False
    escalated: bool = False


class SupervisorAlert(BaseModel, TimestampMixin):
    alert_id: AlertId
    alert_type: str
    severity: str
    workstation_id: Optional[WorkstationId] = None
    worker_id: Optional[WorkerId] = None  # pseudonymous in analytics
    message: str
    status: AlertStatus = AlertStatus.OPEN
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[str] = None
    escalated_at: Optional[str] = None
    push_sent: bool = False
    correlation_id: Optional[str] = None

