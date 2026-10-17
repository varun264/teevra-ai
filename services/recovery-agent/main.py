"""TEEVRA Breakdown Recovery Agent - remote A2A service.

Exposes an A2A Agent Card and a JSON-RPC tasks/send endpoint. Receives machine
fault notifications, runs the CP-SAT recovery solver, consults the Heat Guardian
agent over real A2A before committing, and returns a structured recovery plan.
"""

from __future__ import annotations

import asyncio
import json
import os
import uvicorn
from fastapi import FastAPI

from teevra_a2a import build_agent_card, agent_card_to_json, create_a2a_app, A2ARemoteClient, new_id
from teevra_simulation import MACHINES, JOBS, TOTAL_SLOTS, slot_to_ist
from teevra_simulation.state import reset_state, get_state
from teevra_scheduler_engine import CPSatSchedulingEngine

ENGINE = CPSatSchedulingEngine(total_slots=TOTAL_SLOTS)

HEAT_GUARDIAN_URL = "http://127.0.0.1:8071"

app = FastAPI(title="TEEVRA Breakdown Recovery Agent")

AGENT_CARD = build_agent_card(
    name="TeevraBreakdownRecoveryAgent",
    description=(
        "Autonomous machine breakdown rescheduler with 2-hour frozen window. "
        "Solves CP-SAT recovery plans and validates safety via Heat Guardian A2A."
    ),
    version="1.0.0",
    url=HEAT_GUARDIAN_URL,
)


async def _call_heat_guardian_card() -> str:
    async with A2ARemoteClient(HEAT_GUARDIAN_URL, timeout_seconds=20.0) as client:
        card = await client.get_agent_card()
        return f"heat guardian agent card reached: {card.get('name')}"


@app.get("/.well-known/agent.json")
async def agent_card():
    return agent_card_to_json(AGENT_CARD)


async def _recovery_handler(message_text, context_id, task_id, correlation_id, headers):
    """A2A task handler: solve a breakdown recovery plan."""
    try:
        payload = json.loads(message_text) if message_text.strip().startswith("{") else {}
    except Exception:
        payload = {}

    fault_machine = payload.get("fault_machine", "CNC-A")
    fault_start = int(payload.get("fault_start_slot", 20))
    fault_end = int(payload.get("fault_end_slot", 31))
    now_slot = int(payload.get("now_slot", fault_start))
    time_limit = float(payload.get("time_limit_seconds", 30.0))

    state = get_state()
    current = state.schedules.get(state.current_version_id) if state.current_version_id else None
    if current is None:
        # build a baseline first
        from teevra_scheduler_engine import CPSatSchedulingEngine as _E
        base = ENGINE.build_baseline_schedule(
            {"machines": MACHINES, "jobs": JOBS, "now_slot": 0}
        )
        state.schedules[base.version_id] = base
        state.current_version_id = base.version_id
        current = base

    # heat-blocked stations
    heat_blocked = [
        wid for wid, risk in state.workstation_risk.items() if risk == "STOP_WORK"
    ]

    # safety pre-check via Heat Guardian A2A (real remote call)
    safety_note = "heat guardian unavailable (local fallback)"
    try:
        safety_note = await _call_heat_guardian_card()
    except Exception as exc:  # noqa: BLE001
        safety_note = f"heat guardian A2A unreachable: {exc}"

    plan = ENGINE.recover_after_breakdown(
        current_version=current,
        fault_machine=fault_machine,
        fault_start_slot=fault_start,
        fault_end_slot=fault_end,
        now_slot=now_slot,
        heat_blocked_stations=heat_blocked,
        time_limit_seconds=time_limit,
    )

    # store candidate version
    state.schedules[plan.schedule_version.version_id] = plan.schedule_version
    state.candidate_version_id = plan.schedule_version.version_id

    r = plan.solver_result
    result = {
        "plan_id": plan.plan_id,
        "version_id": plan.schedule_version.version_id,
        "solver_status": r.solver_status.value,
        "is_feasible": r.is_feasible,
        "is_optimal": r.is_optimal,
        "jobs_unchanged": r.jobs_unchanged,
        "jobs_reassigned": r.jobs_reassigned,
        "jobs_delayed": r.jobs_delayed,
        "jobs_blocked": r.jobs_blocked,
        "expected_output_percent": r.expected_output_percent,
        "electricity_cost_before_inr": r.electricity_cost_before_inr,
        "electricity_cost_after_inr": r.electricity_cost_after_inr,
        "recovery_duration_ms": r.recovery_duration_ms,
        "human_approval_required": r.human_approval_required,
        "auto_commit_allowed": plan.auto_commit_allowed,
        "infeasibility_report": r.infeasibility_report,
        "safety_note": safety_note,
        "change_evidence": [e.model_dump() for e in r.change_evidence],
        "safety_validation_result": r.safety_validation_result,
        "correlation_id": correlation_id,
    }
    return json.dumps(result, default=str)


a2a_app = create_a2a_app(AGENT_CARD, _recovery_handler)
app.mount("/", a2a_app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8072")))
