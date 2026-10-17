"""TEEVRA AI API Gateway - FastAPI backend.

Exposes the full REST contract, SSE event stream, WebSocket dashboard updates,
and coordinates the ADK agents over real A2A HTTP. Local mode uses the in-memory
operational state store (Firestore equivalent) and simulated Pub/Sub bus.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx

from teevra_shared_schemas import Severity
from teevra_simulation import (
    MACHINES, JOBS, WORKERS, TOTAL_SLOTS, FROZEN_WINDOW_SLOTS, DEMO_START,
    slot_to_ist, ist_to_slot, HEAT_POLICY, WORKSTATIONS, tariff_rate_at_ist,
)
from teevra_simulation.state import get_state, reset_state
from teevra_scheduler_engine import CPSatSchedulingEngine
from teevra_a2a import A2ARemoteClient

app = FastAPI(title="TEEVRA AI API Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ENGINE = CPSatSchedulingEngine(total_slots=TOTAL_SLOTS)
RECOVERY_URL = "http://127.0.0.1:8072"
HEAT_URL = "http://127.0.0.1:8071"

# --------------------------------------------------------------------------- #
# Auth (local demo: bearer role header; Firebase in cloud mode)
# --------------------------------------------------------------------------- #
def current_role(authorization: Optional[str] = Header(None)) -> str:
    if not authorization:
        return "PLANNER"  # local demo default
    parts = authorization.split()
    if len(parts) == 2 and parts[0] == "Bearer":
        token = parts[1]
        if token.startswith("role:"):
            return token[5:]
        if token == "demo-supervisor":
            return "SUPERVISOR"
        if token == "demo-planner":
            return "PLANNER"
        if token == "demo-worker":
            return "WORKER"
    return "PLANNER"


def require_planner(role: str = Depends(current_role)):
    if role not in ("PLANNER", "SUPERVISOR", "ADMIN"):
        raise HTTPException(status_code=403, detail="planner role required")
    return role


# --------------------------------------------------------------------------- #
# SSE subscribers
# --------------------------------------------------------------------------- #
class Hub:
    def __init__(self):
        self.subscribers: list[asyncio.Queue] = []

    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        if q in self.subscribers:
            self.subscribers.remove(q)

    async def publish(self, event: dict):
        data = json.dumps(event, default=str)
        dead = []
        for q in self.subscribers:
            try:
                q.put_nowait(data)
            except Exception:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)


HUB = Hub()


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "teevra-api-gateway", "mode": "local"}


@app.get("/api/readiness")
async def readiness():
    return {"ready": True}


# --------------------------------------------------------------------------- #
# Demo control
# --------------------------------------------------------------------------- #
@app.post("/api/demo/reset")
async def demo_reset(role: str = Depends(require_planner)):
    reset_state()
    state = get_state()
    # seed baseline schedule
    base = ENGINE.build_baseline_schedule(
        {"machines": MACHINES, "jobs": JOBS, "now_slot": 0}
    )
    state.schedules[base.version_id] = base
    state.current_version_id = base.version_id
    for m in MACHINES:
        state.machine_status[m.machine_id] = m.status.value
    await HUB.publish({
        "type": "demo.reset",
        "payload": {"version_id": base.version_id, "entries": len(base.entries)},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "reset", "version_id": base.version_id, "entries": len(base.entries)}


@app.post("/api/demo/seed")
async def demo_seed(role: str = Depends(require_planner)):
    return await demo_reset(role)


# --------------------------------------------------------------------------- #
# Machine fault events (Pub/Sub adapter)
# --------------------------------------------------------------------------- #
@app.post("/api/events/machine-fault")
async def machine_fault(payload: dict, role: str = Depends(current_role)):
    state = get_state()
    event_id = payload.get("event_id") or f"fault-{uuid.uuid4().hex[:8]}"
    machine_id = payload["machine_id"]
    ts = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
    dedup_key = f"MACHINE_BREAKDOWN:{machine_id}:{ts}"
    if dedup_key in state.event_dedup:
        return {"status": "duplicate", "event_id": event_id}
    state.event_dedup.add(dedup_key)

    now_slot = ist_to_slot(datetime.fromisoformat(ts))
    repair = int(payload.get("estimated_repair_minutes", 180))
    fault_end = now_slot + max(1, repair // 15)

    # mark machine down
    state.machine_status[machine_id] = "DOWN"

    event = {
        "event_id": event_id,
        "machine_id": machine_id,
        "event_type": "MACHINE_BREAKDOWN",
        "timestamp": ts,
        "estimated_repair_minutes": repair,
        "severity": payload.get("severity", "HIGH"),
        "source": payload.get("source", "OPERATOR"),
        "now_slot": now_slot,
        "fault_end_slot": fault_end,
    }
    state.fault_events.append(event)

    await HUB.publish({
        "type": "machine.fault",
        "payload": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "accepted", "event_id": event_id, "fault_end_slot": fault_end}


@app.post("/api/events/machine-restored")
async def machine_restored(payload: dict, role: str = Depends(current_role)):
    state = get_state()
    machine_id = payload["machine_id"]
    state.machine_status[machine_id] = "AVAILABLE"
    await HUB.publish({
        "type": "machine.restored",
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Schedule
# --------------------------------------------------------------------------- #
@app.get("/api/schedule/current")
async def schedule_current(role: str = Depends(current_role)):
    state = get_state()
    vid = state.current_version_id
    v = state.schedules.get(vid) if vid else None
    if v is None:
        return {"status": "no_schedule"}
    return {
        "status": "ok",
        "version_id": v.version_id,
        "is_committed": v.is_committed,
        "frozen_window": {
            "start_slot": v.frozen_window.start_slot,
            "end_slot": v.frozen_window.end_slot,
        },
        "entries": [e.model_dump() for e in v.entries],
        "machines": {m.machine_id: state.machine_status.get(m.machine_id, m.status.value) for m in MACHINES},
    }


@app.get("/api/schedule/history")
async def schedule_history(role: str = Depends(current_role)):
    state = get_state()
    return {
        "versions": [
            {"version_id": v.version_id, "created_at": v.created_at.isoformat(), "committed": v.is_committed}
            for v in state.schedules.values()
        ]
    }


@app.get("/api/schedule/diff")
async def schedule_diff(previous: str = Query(...), new: str = Query(...), role: str = Depends(current_role)):
    state = get_state()
    prev = state.schedules.get(previous)
    newv = state.schedules.get(new)
    if not prev or not newv:
        raise HTTPException(status_code=404, detail="version not found")
    ev = ENGINE.compare_schedules(prev, newv)
    return {"previous_version": previous, "new_version": new, "change_evidence": [e.model_dump() for e in ev]}


@app.post("/api/schedule/recover")
async def schedule_recover(payload: dict, role: str = Depends(require_planner)):
    state = get_state()
    current = state.schedules.get(state.current_version_id) if state.current_version_id else None
    if current is None:
        raise HTTPException(status_code=400, detail="no current schedule")
    fault_machine = payload.get("fault_machine", "CNC-A")
    start = int(payload.get("fault_start_slot", 20))
    end = int(payload.get("fault_end_slot", 31))
    now_slot = int(payload.get("now_slot", start))
    heat_blocked = [w for w, risk in state.workstation_risk.items() if risk == "STOP_WORK"]
    plan = ENGINE.recover_after_breakdown(
        current_version=current,
        fault_machine=fault_machine,
        fault_start_slot=start,
        fault_end_slot=end,
        now_slot=now_slot,
        heat_blocked_stations=heat_blocked,
        time_limit_seconds=30.0,
    )
    r = plan.solver_result
    result = r.model_dump()
    result["is_feasible"] = r.is_feasible
    result["is_optimal"] = r.is_optimal
    state.schedules[plan.schedule_version.version_id] = plan.schedule_version
    state.candidate_version_id = plan.schedule_version.version_id
    await HUB.publish({
        "type": "schedule.recovery",
        "payload": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "ok", "plan": result, "version_id": plan.schedule_version.version_id}


@app.post("/api/schedule/approve")
async def schedule_approve(payload: dict, role: str = Depends(require_planner)):
    state = get_state()
    vid = payload.get("version_id") or state.candidate_version_id
    if not vid or vid not in state.schedules:
        raise HTTPException(status_code=404, detail="no candidate version")
    v = state.schedules[vid]
    v.is_committed = True
    v.commit_correlation_id = str(uuid.uuid4())
    state.current_version_id = vid
    await HUB.publish({"type": "schedule.approved", "payload": {"version_id": vid}})
    return {"status": "approved", "version_id": vid}


@app.post("/api/schedule/reject")
async def schedule_reject(payload: dict, role: str = Depends(require_planner)):
    state = get_state()
    vid = payload.get("version_id") or state.candidate_version_id
    if vid in state.schedules:
        del state.schedules[vid]
    if state.candidate_version_id == vid:
        state.candidate_version_id = None
    await HUB.publish({"type": "schedule.rejected", "payload": {"version_id": vid}})
    return {"status": "rejected", "version_id": vid}


@app.post("/api/schedule/rollback")
async def schedule_rollback(role: str = Depends(require_planner)):
    state = get_state()
    committed = [v for v in state.schedules.values() if v.is_committed]
    if not committed:
        raise HTTPException(status_code=404, detail="nothing to rollback")
    v = sorted(committed, key=lambda x: x.created_at or "")[-1]
    state.current_version_id = v.version_id
    await HUB.publish({"type": "schedule.rollback", "payload": {"version_id": v.version_id}})
    return {"status": "rolled_back", "version_id": v.version_id}


# --------------------------------------------------------------------------- #
# Heat Guardian
# --------------------------------------------------------------------------- #
@app.get("/api/heat/workstations")
async def heat_workstations(role: str = Depends(current_role)):
    state = get_state()
    results = []
    for ws in WORKSTATIONS:
        wid = ws["workstation_id"]
        risk = state.workstation_risk.get(wid, "UNKNOWN")
        results.append({
            "workstation_id": wid,
            "name": ws["name"],
            "machine_id": ws.get("machine_id"),
            "risk_level": risk,
            "base_wbgt_c": ws["base_wbgt_c"],
        })
    return {"status": "ok", "workstations": results}


@app.get("/api/heat/measurements")
async def heat_measurements(role: str = Depends(current_role)):
    state = get_state()
    return {"status": "ok", "readings": state.heat_readings[-50:], "count": len(state.heat_readings)}


@app.post("/api/events/heat-reading")
async def heat_reading(payload: dict, role: str = Depends(current_role)):
    state = get_state()
    reading = {
        "workstation_id": payload.get("workstation_id", "WS-F1"),
        "temperature_c": payload.get("temperature_c", 35.0),
        "relative_humidity": payload.get("relative_humidity", 70.0),
        "natural_wet_bulb_c": payload.get("natural_wet_bulb_c", 30.0),
        "globe_temperature_c": payload.get("globe_temperature_c", 34.0),
        "sensor_fresh_seconds": payload.get("sensor_fresh_seconds", 10),
        "sensor_quality": payload.get("sensor_quality", "GOOD"),
        "recorded_at": payload.get("timestamp") or datetime.now(timezone.utc).isoformat(),
    }
    state.heat_readings.append(reading)
    # evaluate risk
    nwb = reading.get("natural_wet_bulb_c"); globe = reading.get("globe_temperature_c")
    wbgt = round(0.7 * nwb + 0.3 * globe, 2) if nwb is not None and globe is not None else None
    quality = reading.get("sensor_quality", "GOOD"); fresh = reading.get("sensor_fresh_seconds")
    risk = "UNKNOWN"
    if wbgt is not None and quality != "FAULTY" and (fresh is None or fresh <= 300):
        if wbgt >= HEAT_POLICY["stop_work_min_wbgt_c"]:
            risk = "STOP_WORK"
        elif wbgt >= HEAT_POLICY["high_risk_max_wbgt_c"]:
            risk = "HIGH_RISK"
        elif wbgt >= HEAT_POLICY["caution_max_wbgt_c"]:
            risk = "CAUTION"
        else:
            risk = "NORMAL"
    wid = reading["workstation_id"]
    state.workstation_risk[wid] = risk
    await HUB.publish({
        "type": "heat.reading",
        "payload": {"workstation_id": wid, "wbgt_c": wbgt, "risk": risk},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "ok", "workstation_id": wid, "wbgt_c": wbgt, "risk_level": risk}


# --------------------------------------------------------------------------- #
# Worker check-ins
# --------------------------------------------------------------------------- #
@app.post("/api/worker/checkin")
async def worker_checkin(payload: dict, role: str = Depends(current_role)):
    state = get_state()
    from teevra_shared_schemas.heat import CheckIn, CheckInResponse
    checkin = CheckIn(
        checkin_id=f"ci-{uuid.uuid4().hex[:8]}",
        worker_id=payload.get("worker_id", "WRK-01"),
        workstation_id=payload.get("workstation_id", "WS-CNC-A"),
        language=payload.get("language", "en"),
        response=CheckInResponse(payload.get("response", "OK")),
        voice_consent=bool(payload.get("voice_consent", False)),
        responded_at=datetime.now(timezone.utc).isoformat(),
        reminder_sent_at=datetime.now(timezone.utc).isoformat(),
    )
    state.checkins.append(checkin)
    if checkin.response == CheckInResponse.SOS:
        from teevra_shared_schemas.heat import SupervisorAlert
        alert = SupervisorAlert(
            alert_id=f"alert-{uuid.uuid4().hex[:8]}",
            alert_type="WORKER_SOS",
            severity="CRITICAL",
            workstation_id=checkin.workstation_id,
            worker_id=checkin.worker_id,
            message=f"SOS check-in from worker {checkin.worker_id}",
        )
        state.alerts[alert.alert_id] = alert
        await HUB.publish({"type": "worker.sos", "payload": alert.model_dump(), "timestamp": datetime.now(timezone.utc).isoformat()})
        return {"status": "ok", "alert_id": alert.alert_id, "escalated": True}
    await HUB.publish({"type": "worker.checkin", "payload": checkin.model_dump(), "timestamp": datetime.now(timezone.utc).isoformat()})
    return {"status": "ok", "checkin_id": checkin.checkin_id, "response": checkin.response.value}


@app.get("/api/worker/checkin/status")
async def checkin_status(worker_id: Optional[str] = None, role: str = Depends(current_role)):
    state = get_state()
    items = [c for c in state.checkins if not worker_id or c.worker_id == worker_id]
    return {"status": "ok", "checkins": [c.model_dump() for c in items], "count": len(items)}


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
@app.get("/api/alerts")
async def alerts(role: str = Depends(current_role)):
    state = get_state()
    return {"status": "ok", "alerts": [a.model_dump() for a in state.alerts.values()], "count": len(state.alerts)}


@app.post("/api/alerts/{alert_id}/acknowledge")
async def ack_alert(alert_id: str, role: str = Depends(current_role)):
    state = get_state()
    a = state.alerts.get(alert_id)
    if not a:
        raise HTTPException(status_code=404, detail="alert not found")
    a.status = "ACKNOWLEDGED"
    a.acknowledged_at = datetime.now(timezone.utc).isoformat()
    a.acknowledged_by = role
    return {"status": "acknowledged", "alert_id": alert_id}


@app.post("/api/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, role: str = Depends(current_role)):
    state = get_state()
    a = state.alerts.get(alert_id)
    if not a:
        raise HTTPException(status_code=404, detail="alert not found")
    a.status = "RESOLVED"
    a.resolved_at = datetime.now(timezone.utc).isoformat()
    return {"status": "resolved", "alert_id": alert_id}


# --------------------------------------------------------------------------- #
# Agent observability traces
# --------------------------------------------------------------------------- #
@app.get("/api/agents/traces")
async def agent_traces(role: str = Depends(current_role)):
    state = get_state()
    return {"status": "ok", "traces": state.audit[-100:], "count": len(state.audit)}


# --------------------------------------------------------------------------- #
# SSE event stream
# --------------------------------------------------------------------------- #
@app.get("/api/events/stream")
async def events_stream(role: str = Depends(current_role)):
    q = await HUB.subscribe()

    async def event_generator():
        try:
            while True:
                data = await q.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            HUB.unsubscribe(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --------------------------------------------------------------------------- #
# WebSocket dashboard updates
# --------------------------------------------------------------------------- #
@app.websocket("/api/events/ws")
async def events_ws(websocket: WebSocket):
    await websocket.accept()
    q = await HUB.subscribe()
    try:
        while True:
            data = await q.get()
            await websocket.send_text(data)
    except WebSocketDisconnect:
        pass
    finally:
        HUB.unsubscribe(q)


# --------------------------------------------------------------------------- #
# A2A agent calls (orchestrator -> recovery / heat guardian)
# --------------------------------------------------------------------------- #
@app.post("/api/a2a/recovery")
async def a2a_recovery(payload: dict, role: str = Depends(require_planner)):
    async with A2ARemoteClient(RECOVERY_URL, timeout_seconds=60.0) as client:
        try:
            card = await client.get_agent_card()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"recovery agent unreachable: {exc}")
        result = await client.send_task(json.dumps(payload), correlation_id=str(uuid.uuid4()))
    return {"status": "ok", "agent_card": card.get("name"), "result": result}


@app.post("/api/a2a/heat")
async def a2a_heat(payload: dict, role: str = Depends(current_role)):
    async with A2ARemoteClient(HEAT_URL, timeout_seconds=30.0) as client:
        try:
            await client.get_agent_card()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"heat guardian unreachable: {exc}")
        result = await client.send_task(json.dumps(payload), correlation_id=str(uuid.uuid4()))
    return {"status": "ok", "result": result}


# seed baseline on startup if empty
@app.on_event("startup")
async def _startup():
    state = get_state()
    if not state.schedules:
        base = ENGINE.build_baseline_schedule({"machines": MACHINES, "jobs": JOBS, "now_slot": 0})
        state.schedules[base.version_id] = base
        state.current_version_id = base.version_id


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
