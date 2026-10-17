"""TEEVRA auth helpers (Firebase in cloud; local role header in demo)."""

from __future__ import annotations

from typing import Optional

PLANNER_ROLES = {"PLANNER", "SUPERVISOR", "ADMIN"}
WORKER_ROLES = {"WORKER", "OPERATOR"}


def require_planner(role: Optional[str]) -> None:
    if role not in PLANNER_ROLES:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="planner role required")


def require_worker_or_planner(role: Optional[str]) -> None:
    if role not in (PLANNER_ROLES | WORKER_ROLES):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="worker or planner role required")
