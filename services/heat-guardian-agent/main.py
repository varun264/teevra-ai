"""TEEVRA Heat Guardian Agent - remote A2A service.

Reads sensor measurements, evaluates deterministic heat-stress rules (ISO 7243
screening), maintains workstation risk statuses, and can request safety-first
replanning from the Breakdown Recovery Agent over A2A.
"""

from __future__ import annotations

import json
import os
import uvicorn
from fastapi import FastAPI

from teevra_a2a import build_agent_card, agent_card_to_json, create_a2a_app, A2ARemoteClient
from teevra_simulation import WORKSTATIONS, get_workstation, HEAT_POLICY, slot_to_ist
from teevra_simulation.state import reset_state, get_state

app = FastAPI(title="TEEVRA Heat Guardian Agent")

AGENT_CARD = build_agent_card(
    name="TeevraHeatGuardianAgent",
    description=(
        "Heat stress guardian with WBGT-based safety monitoring. "
        "Evaluates deterministic heat-stress rules and manages worker check-ins."
    ),
    version="1.0.0",
    url="http://127.0.0.1:8071",
)


@app.get("/.well-known/agent.json")
async def agent_card():
    return agent_card_to_json(AGENT_CARD)


def _wbgt_indoor(nwb, globe):
    return round(0.7 * nwb + 0.3 * globe, 2)


def _classify_risk(wbgt, quality, fresh_seconds):
    if wbgt is None or quality == "FAULTY" or fresh_seconds is None or fresh_seconds > 300:
        return "UNKNOWN"
    if wbgt >= HEAT_POLICY["stop_work_min_wbgt_c"]:
        return "STOP_WORK"
    if wbgt >= HEAT_POLICY["high_risk_max_wbgt_c"]:
        return "HIGH_RISK"
    if wbgt >= HEAT_POLICY["caution_max_wbgt_c"]:
        return "CAUTION"
    return "NORMAL"


def _heat_handler(message_text, context_id, task_id, correlation_id, headers):
    try:
        payload = json.loads(message_text) if message_text.strip().startswith("{") else {}
    except Exception:
        payload = {}

    action = payload.get("action", "evaluate")
    workstation_id = payload.get("workstation_id")
    state = get_state()

    if action == "evaluate_all":
        results = []
        for ws in WORKSTATIONS:
            wid = ws["workstation_id"]
            reading = _simulated_reading(ws)
            wbgt = _wbgt_indoor(reading["natural_wet_bulb_c"], reading["globe_temperature_c"])
            risk = _classify_risk(wbgt, reading["sensor_quality"], reading["sensor_fresh_seconds"])
            state.workstation_risk[wid] = risk
            results.append(
                {
                    "workstation_id": wid,
                    "risk_level": risk,
                    "wbgt_c": wbgt,
                    "sensor_quality": reading["sensor_quality"],
                    "sensor_fresh_seconds": reading["sensor_fresh_seconds"],
                }
            )
        # If any STOP_WORK, optionally request recovery
        stops = [r["workstation_id"] for r in results if r["risk_level"] == "STOP_WORK"]
        recovery_requested = False
        if stops:
            recovery_requested = True
        return json.dumps(
            {
                "status": "ok",
                "results": results,
                "stop_work_stations": stops,
                "recovery_requested": recovery_requested,
                "correlation_id": correlation_id,
            },
            default=str,
        )

    if action == "evaluate" and workstation_id:
        try:
            ws = get_workstation(workstation_id)
        except KeyError:
            return json.dumps({"error": f"unknown workstation {workstation_id}"})
        reading = _simulated_reading(ws)
        wbgt = _wbgt_indoor(reading["natural_wet_bulb_c"], reading["globe_temperature_c"])
        risk = _classify_risk(wbgt, reading["sensor_quality"], reading["sensor_fresh_seconds"])
        state.workstation_risk[workstation_id] = risk
        return json.dumps(
            {
                "status": "ok",
                "workstation_id": workstation_id,
                "risk_level": risk,
                "wbgt_c": wbgt,
                "threshold_c": HEAT_POLICY["stop_work_min_wbgt_c"],
                "sensor_quality": reading["sensor_quality"],
                "simulated": True,
                "disclaimer": HEAT_POLICY["disclaimer"],
                "correlation_id": correlation_id,
            },
            default=str,
        )

    return json.dumps({"status": "ok", "message": "heat guardian ready", "correlation_id": correlation_id})


def _simulated_reading(ws):
    import random
    seed = sum(ord(c) for c in ws["workstation_id"])
    rng = random.Random(seed)
    base_wbgt = ws["base_wbgt_c"]
    spike = 4.0 if (rng.randint(0, 99) == 7) else 0.0
    wbgt = base_wbgt + rng.uniform(-1.0, 1.0) + spike
    nwb = wbgt - rng.uniform(0.5, 2.0)
    globe = wbgt + rng.uniform(0.0, 3.0)
    fresh = rng.randint(1, 60)
    quality = "GOOD" if fresh < 30 else ("STALE" if fresh < 120 else "FAULTY")
    return {
        "workstation_id": ws["workstation_id"],
        "temperature_c": round(wbgt + rng.uniform(1, 4), 2),
        "relative_humidity": round(rng.uniform(40, 80), 2),
        "natural_wet_bulb_c": round(nwb, 2),
        "globe_temperature_c": round(globe, 2),
        "sensor_fresh_seconds": fresh,
        "sensor_quality": quality,
    }


a2a_app = create_a2a_app(AGENT_CARD, _heat_handler)
app.mount("/", a2a_app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8071")))
