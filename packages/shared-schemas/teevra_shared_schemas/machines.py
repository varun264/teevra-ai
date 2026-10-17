"""Machine domain models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .base import TimestampMixin
from .common import MachineId, MachineStatus, Shift


class MachineCapability(BaseModel):
    can_cut_metal: bool = False
    can_melt_metal: bool = False
    can_paint: bool = False
    can_compress_air: bool = False
    can_chill: bool = False
    heat_emission_level: int = Field(default=1, ge=0, le=5)  # 0=none, 5=extreme
    requires_cooling: bool = False
    compatible_job_types: List[str] = Field(default_factory=list)


class Machine(BaseModel, TimestampMixin):
    machine_id: MachineId
    name: str
    status: MachineStatus = MachineStatus.AVAILABLE
    shift: Optional[Shift] = None
    location: str = "shop_floor"
    coordinates: Optional[dict] = None
    capabilities: MachineCapability = Field(default_factory=MachineCapability)
    max_concurrent_jobs: int = 1
    power_rating_kw: float = 0.0
    restart_energy_penalty_kwh: float = 0.0
    tariff_sensitive: bool = False
    heat_sensitive: bool = False
    compatible_machines: List[MachineId] = Field(default_factory=list)
    is_down_since: Optional[str] = None  # ISO timestamp

