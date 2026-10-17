"""Safety MCP server (stdio / StreamableHTTP).

Tools: get_sensor_readings, get_wbgt_history, get_station_risk_status,
get_approved_heat_policy, get_worker_acclimatization_class, get_pending_checkins,
record_checkin_response, create_supervisor_alert.

All thresholds are explicitly labeled SIMULATION policy values - NOT certified
occupational health limits.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from mcp.server.mcpserver import MCPServer

from teevra_mcp_common import (
    AuthContext,
    MCPError,
    audit_log,
    enforce_tool_auth,
    now_iso,
)
from teevra_simulation import HEAT_POLICY, WORKSTATIONS, get_workstation, ist_to_slot, slot_to_ist
from teevra_simulation.state import get_state
from teevra_shared_schemas.heat import CheckIn, CheckInResponse, SupervisorAlert

server = MCPServer(name="teevra-safety-mcp", version="1.0.0")
PLANNER_ROLES = {"PLANNER", "SUPERVISOR", "ADMIN"}


def _ctx(correlation_id: Optional[str], role: Optional[str], worker_id: Optional[str]) -> AuthContext:
    return AuthContext(
        role=role or "WORKER",
        worker_id=worker_id,
        correlation_id=correlation_id or uuid.uuid4().hex,
    )


# --------------------------------------------------------------------------- #
# Deterministic simulated sensor feed
# --------------------------------------------------------------------------- #
def _deterministic_seed(workstation_id: str) -> int:
    return sum(ord(c) for c in workstation_id) % 1000


def _simulated_reading(workstation: dict, slot: int | None = None) -> dict:
    """Generate a labeled-simulated sensor reading for a workstation."""
    seed = _deterministic_seed(workstation["workstation_id"])
    rng = __import__("random").Random(seed + (slot or 0))
    base_wbgt = workstation["base_wbgt_c"]
    # introduce occasional heat spikes deterministically
    spike = 0.0
    if slot is not None and (slot % 97) == 31:
        spike = 4.0  # heat spike event
    elif slot is not None and (slot % 53) == 17:
        spike = 1.5
    wbgt = base_wbgt + rng.uniform(-1.0, 1.0) + spike
    temp = wbgt + rng.uniform(1.0, 4.0)
    rh = rng.uniform(40, 80)
    nwb = wbgt - rng.uniform(0.5, 2.0)
    globe = wbgt + rng.uniform(0.0, 3.0)
    fresh = rng.randint(1, 60)
    quality = "GOOD" if fresh < 30 else ("STALE" if fresh < 120 else "FAULTY")
    return {
        "workstation_id": workstation["workstation_id"],
        "machine_id": workstation.get("machine_id"),
        "temperature_c": round(temp, 2),
        "relative_humidity": round(rh, 2),
        "natural_wet_bulb_c": round(nwb, 2),
        "globe_temperature_c": round(globe, 2),
        "wind_speed_ms": round(rng.uniform(0.2, 1.5), 2),
        "sensor_fresh_seconds": fresh,
        "sensor_quality": quality,
        "recorded_at": slot_to_ist(slot or 0).isoformat() if slot is not None else now_iso(),
        "simulated": True,
    }


def _wbgt_indoor(nwb: float, globe: float) -> float:
    """Indoor WBGT = 0.7*NWB + 0.3*GT (no solar load). ISO 7243 screening."""
    return round(0.7 * nwb + 0.3 * globe, 2)


def _classify_risk(wbgt: Optional[float], policy: dict, quality: str, fresh_seconds: Optional[int]) -> str:
    if wbgt is None or quality == "FAULTY" or fresh_seconds is None or fresh_seconds > 300:
        return "UNKNOWN"
    if wbgt >= policy["stop_work_min_wbgt_c"]:
        return "STOP_WORK"
    if wbgt >= policy["high_risk_max_wbgt_c"]:
        return "HIGH_RISK"
    if wbgt >= policy["caution_max_wbgt_c"]:
        return "CAUTION"
    return "NORMAL"


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@server.tool()
async def get_sensor_readings(
    workstation_id: Optional[str] = None,
    slot: Optional[int] = None,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return current sensor readings. Unknown workstation IDs rejected."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_sensor_readings")
    state = get_state()
    results = []
    targets = [workstation_id] if workstation_id else [w["workstation_id"] for w in WORKSTATIONS]
    for wid in targets:
        try:
            ws = get_workstation(wid)
        except KeyError:
            raise MCPError("NOT_FOUND", f"unknown workstation_id: {wid}", 404)
        reading = _simulated_reading(ws, slot)
        results.append(reading)
        state.heat_readings.append(reading)
    audit_log("get_sensor_readings", ctx, "read_sensors", {"workstations": targets})
    return {"status": "ok", "readings": results, "count": len(results), "correlation_id": ctx.correlation_id}


@server.tool()
async def get_wbgt_history(
    workstation_id: str,
    hours: Optional[int] = 6,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return WBGT history for a workstation."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_wbgt_history")
    try:
        get_workstation(workstation_id)
    except KeyError:
        raise MCPError("NOT_FOUND", f"unknown workstation_id: {workstation_id}", 404)
    state = get_state()
    history = [r for r in state.heat_readings if r["workstation_id"] == workstation_id]
    history = sorted(history, key=lambda r: r["recorded_at"])[-max(1, hours * 4):]
    audit_log("get_wbgt_history", ctx, "read_wbgt_history", {"workstation_id": workstation_id})
    return {"status": "ok", "workstation_id": workstation_id, "history": history, "count": len(history)}


@server.tool()
async def get_station_risk_status(
    workstation_id: str,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return evaluated heat risk status for a workstation. Missing sensor => UNKNOWN."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_station_risk_status")
    try:
        ws = get_workstation(workstation_id)
    except KeyError:
        raise MCPError("NOT_FOUND", f"unknown workstation_id: {workstation_id}", 404)
    state = get_state()
    reading = _simulated_reading(ws)
    wbgt = _wbgt_indoor(reading["natural_wet_bulb_c"], reading["globe_temperature_c"])
    risk = _classify_risk(
        wbgt, HEAT_POLICY, reading["sensor_quality"], reading["sensor_fresh_seconds"]
    )
    status = {
        "workstation_id": workstation_id,
        "risk_level": risk,
        "wbgt_c": wbgt,
        "threshold_c": HEAT_POLICY["stop_work_min_wbgt_c"],
        "sensor_age_seconds": reading["sensor_fresh_seconds"],
        "sensor_quality": reading["sensor_quality"],
        "workers_affected": 0,
        "last_evaluated_at": now_iso(),
        "simulated": True,
        "policy_disclaimer": HEAT_POLICY["disclaimer"],
    }
    state.workstation_risk[workstation_id] = risk
    audit_log("get_station_risk_status", ctx, "evaluate_risk", {"workstation_id": workstation_id, "risk": risk, "wbgt": wbgt})
    return {"status": "ok", **status, "correlation_id": ctx.correlation_id}


@server.tool()
async def get_approved_heat_policy(
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return the approved heat policy (simulation values, not certified)."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_approved_heat_policy")
    audit_log("get_approved_heat_policy", ctx, "read_policy")
    return {"status": "ok", "policy": HEAT_POLICY, "correlation_id": ctx.correlation_id}


@server.tool()
async def get_worker_acclimatization_class(
    worker_id: str,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id_actor: Optional[str] = None,
) -> dict:
    """Return acclimatization class for a worker."""
    ctx = _ctx(correlation_id, role, worker_id_actor or worker_id)
    enforce_tool_auth(ctx, "get_worker_acclimatization_class")
    try:
        w = get_worker(worker_id)
    except KeyError:
        raise MCPError("NOT_FOUND", f"unknown worker_id: {worker_id}", 404)
    audit_log("get_worker_acclimatization_class", ctx, "read_acclimatization", {"worker_id": worker_id})
    return {
        "status": "ok",
        "worker_id": worker_id,
        "acclimatization_class": w["acclimatization_class"],
        "shift": w["shift"],
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def get_pending_checkins(
    correlation_id: Optional[str] = None,
    role: Optional[str] = "PLANNER",
    worker_id: Optional[str] = None,
) -> dict:
    """Return pending/overdue check-ins (planner-only)."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "get_pending_checkins")
    state = get_state()
    pending = [c for c in state.checkins if c.response == CheckInResponse.MISSED or c.overdue]
    audit_log("get_pending_checkins", ctx, "read_checkins", {"count": len(pending)})
    return {
        "status": "ok",
        "checkins": [c.model_dump() for c in pending],
        "count": len(pending),
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def record_checkin_response(
    checkin_id: str,
    response: str,
    voice_consent: Optional[bool] = False,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Record a worker check-in response. OK / Too Hot / SOS."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "record_checkin_response")
    if response not in {r.value for r in CheckInResponse}:
        raise MCPError("INVALID", f"invalid response: {response}", 400)
    state = get_state()
    target = None
    for c in state.checkins:
        if c.checkin_id == checkin_id:
            target = c
            break
    if target is None:
        raise MCPError("NOT_FOUND", f"unknown checkin_id: {checkin_id}", 404)
    target.response = CheckInResponse(response)
    target.responded_at = now_iso()
    target.voice_consent = bool(voice_consent)
    audit_log("record_checkin_response", ctx, "record_response", {"checkin_id": checkin_id, "response": response})
    # SOS -> create priority alert immediately
    if response == CheckInResponse.SOS:
        alert = SupervisorAlert(
            alert_id=f"alert-{uuid.uuid4().hex[:8]}",
            alert_type="WORKER_SOS",
            severity="CRITICAL",
            workstation_id=target.workstation_id,
            worker_id=target.worker_id,
            message=f"SOS check-in from worker {target.worker_id} at {target.workstation_id}",
            correlation_id=ctx.correlation_id,
        )
        state.alerts[alert.alert_id] = alert
        audit_log("record_checkin_response", ctx, "sos_alert_created", {"alert_id": alert.alert_id}, level="CRITICAL")
        return {"status": "ok", "recorded": True, "sos_alert": alert.alert_id, "correlation_id": ctx.correlation_id}
    return {"status": "ok", "recorded": True, "correlation_id": ctx.correlation_id}


@server.tool()
async def create_supervisor_alert(
    alert_type: str,
    severity: str,
    message: str,
    workstation_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "PLANNER",
    worker_id_actor: Optional[str] = None,
) -> dict:
    """Create a supervisor alert (planner-only)."""
    ctx = _ctx(correlation_id, role, worker_id_actor)
    enforce_tool_auth(ctx, "create_supervisor_alert")
    if workstation_id:
        try:
            get_workstation(workstation_id)
        except KeyError:
            raise MCPError("NOT_FOUND", f"unknown workstation_id: {workstation_id}", 404)
    state = get_state()
    alert = SupervisorAlert(
        alert_id=f"alert-{uuid.uuid4().hex[:8]}",
        alert_type=alert_type,
        severity=severity,
        workstation_id=workstation_id,
        worker_id=worker_id,
        message=message,
        correlation_id=ctx.correlation_id,
    )
    state.alerts[alert.alert_id] = alert
    audit_log("create_supervisor_alert", ctx, "create_alert", {"alert_id": alert.alert_id, "severity": severity}, level=severity)
    return {"status": "ok", "alert_id": alert.alert_id, "correlation_id": ctx.correlation_id}


if __name__ == "__main__":
    server.run(transport="stdio")
