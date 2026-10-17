"""In-memory operational state store (local-mode Firestore equivalent).

Used by MCP servers, agents, and the API gateway in local demo mode.
Thread-safe-ish via asyncio locks; single-process demo.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from teevra_shared_schemas import (
    AlertId,
    AlertStatus,
    CheckInResponse,
    HeatStatus,
    Language,
    Role,
    UTCNow,
)
from teevra_shared_schemas.heat import CheckIn, SupervisorAlert
from teevra_shared_schemas.schedule import ScheduleVersion


class LocalState:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.schedules: dict[str, ScheduleVersion] = {}
        self.current_version_id: Optional[str] = None
        self.machine_status: dict[str, str] = {}
        self.fault_events: list[dict] = []
        self.heat_readings: list[dict] = []
        self.workstation_risk: dict[str, HeatStatus] = {}
        self.checkins: list[CheckIn] = []
        self.alerts: dict[str, SupervisorAlert] = {}
        self.event_dedup: set[str] = set()
        self.policies: dict[str, dict] = {}
        self.audit: list[dict] = []
        self.worker_roles: dict[str, str] = {}
        self.candidate_version_id: Optional[str] = None

    async def lock(self):
        return self._lock

    def new_id(self) -> str:
        return uuid.uuid4().hex

    def utc_now(self) -> str:
        return UTCNow().isoformat()


_STATE: Optional[LocalState] = None


def get_state() -> LocalState:
    global _STATE
    if _STATE is None:
        _STATE = LocalState()
    return _STATE


def reset_state() -> LocalState:
    global _STATE
    _STATE = LocalState()
    return _STATE


__all__ = ["LocalState", "get_state", "reset_state"]
