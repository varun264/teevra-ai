"""Factory MCP server (stdio / StreamableHTTP).

Tools: get_current_schedule, get_machine_status, get_machine_capabilities,
get_pending_jobs, get_worker_roster, get_workstation_assignments,
get_production_constraints.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from mcp.server.mcpserver import MCPServer

from teevra_mcp_common import (
    AuthContext,
    MCPError,
    audit_log,
    enforce_tool_auth,
    now_iso,
)
from teevra_simulation import (
    FROZEN_WINDOW_SLOTS,
    MACHINES,
    JOBS,
    TOTAL_SLOTS,
    WORKERS,
    WORKSTATIONS,
    get_machine,
    get_worker,
    get_workstation,
    slot_to_ist,
)
from teevra_simulation.state import get_state

server = MCPServer(name="teevra-factory-mcp", version="1.0.0")

PLANNER_ROLES = {"PLANNER", "SUPERVISOR", "ADMIN"}


def _ctx(correlation_id: Optional[str], role: Optional[str], worker_id: Optional[str]) -> AuthContext:
    return AuthContext(
        role=role or "WORKER",
        worker_id=worker_id,
        correlation_id=correlation_id or __import__("uuid").uuid4().hex,
    )


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@server.tool()
async def get_current_schedule(
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return the current committed production schedule version."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_current_schedule")
    audit_log("get_current_schedule", ctx, "read_schedule")
    state = get_state()
    vid = state.current_version_id
    version = state.schedules.get(vid) if vid else None
    if version is None:
        return {"status": "no_schedule", "version_id": None, "entries": []}
    return {
        "status": "ok",
        "version_id": version.version_id,
        "is_committed": version.is_committed,
        "frozen_window": {
            "start_slot": version.frozen_window.start_slot,
            "end_slot": version.frozen_window.end_slot,
        },
        "entries": [e.model_dump() for e in version.entries],
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def get_machine_status(
    machine_id: str,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return live status for a machine. Rejects unknown machine IDs."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_machine_status")
    try:
        machine = get_machine(machine_id)
    except KeyError:
        raise MCPError("NOT_FOUND", f"unknown machine_id: {machine_id}", 404)
    state = get_state()
    live = state.machine_status.get(machine_id, machine.status.value)
    audit_log("get_machine_status", ctx, "read_machine", {"machine_id": machine_id})
    return {
        "status": "ok",
        "machine_id": machine_id,
        "name": machine.name,
        "status": live,
        "capabilities": machine.capabilities.model_dump(),
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def get_machine_capabilities(
    machine_id: str,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return capabilities for a machine."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_machine_capabilities")
    try:
        machine = get_machine(machine_id)
    except KeyError:
        raise MCPError("NOT_FOUND", f"unknown machine_id: {machine_id}", 404)
    audit_log("get_machine_capabilities", ctx, "read_capabilities", {"machine_id": machine_id})
    return {
        "status": "ok",
        "machine_id": machine_id,
        "capabilities": machine.capabilities.model_dump(),
        "power_rating_kw": machine.power_rating_kw,
        "restart_energy_penalty_kwh": machine.restart_energy_penalty_kwh,
        "tariff_sensitive": machine.tariff_sensitive,
        "heat_sensitive": machine.heat_sensitive,
        "compatible_machines": machine.compatible_machines,
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def get_pending_jobs(
    machine_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return jobs not yet completed, optionally filtered by compatible machine."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_pending_jobs")
    state = get_state()
    vid = state.current_version_id
    scheduled_ids = set()
    version = state.schedules.get(vid) if vid else None
    if version:
        scheduled_ids = {e.job_id for e in version.entries}
    pending = [j for j in JOBS if j.job_id not in scheduled_ids and j.status != "COMPLETED"]
    if machine_id:
        try:
            get_machine(machine_id)
        except KeyError:
            raise MCPError("NOT_FOUND", f"unknown machine_id: {machine_id}", 404)
        pending = [j for j in pending if machine_id in j.compatible_machines]
    audit_log("get_pending_jobs", ctx, "read_jobs", {"machine_id": machine_id, "count": len(pending)})
    return {
        "status": "ok",
        "pending_jobs": [j.model_dump() for j in pending],
        "count": len(pending),
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def get_worker_roster(
    correlation_id: Optional[str] = None,
    role: Optional[str] = "PLANNER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return worker roster (planner-only)."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_worker_roster")
    audit_log("get_worker_roster", ctx, "read_roster", {"count": len(WORKERS)})
    return {
        "status": "ok",
        "workers": [
            {
                "worker_id": w["worker_id"],
                "name": w["name"],
                "role": w["role"],
                "shift": w["shift"],
                "skills": w["skills"],
                "acclimatization_class": w["acclimatization_class"],
                "workstation": w["workstation"],
            }
            for w in WORKERS
        ],
        "count": len(WORKERS),
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def get_workstation_assignments(
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return current workstation assignments from schedule."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_workstation_assignments")
    state = get_state()
    vid = state.current_version_id
    version = state.schedules.get(vid) if vid else None
    assignments = []
    if version:
        for e in version.entries:
            assignments.append(
                {
                    "job_id": e.job_id,
                    "machine_id": e.machine_id,
                    "start_slot": e.start_slot,
                    "end_slot": e.end_slot,
                    "worker_id": e.worker_id,
                    "start_ist": slot_to_ist(e.start_slot).isoformat(),
                }
            )
    audit_log("get_workstation_assignments", ctx, "read_assignments", {"count": len(assignments)})
    return {
        "status": "ok",
        "assignments": assignments,
        "count": len(assignments),
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def get_production_constraints(
    correlation_id: Optional[str] = None,
    role: Optional[str] = "PLANNER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return production constraints (planner-only)."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_production_constraints")
    audit_log("get_production_constraints", ctx, "read_constraints")
    return {
        "status": "ok",
        "horizon_hours": 48,
        "slot_duration_minutes": 15,
        "total_slots": TOTAL_SLOTS,
        "frozen_window_minutes": 120,
        "frozen_window_slots": FROZEN_WINDOW_SLOTS,
        "shifts": ["A", "B"],
        "machines": [m.machine_id for m in MACHINES],
        "demarcation": "Asia/Kolkata (IST)",
        "correlation_id": ctx.correlation_id,
    }


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    server.run(transport="stdio")
