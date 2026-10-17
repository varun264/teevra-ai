"""A2A protocol test: real HTTP tasks/send between Recovery and Heat Guardian agents."""

import json
import os
import subprocess
import sys
import time
import urllib.request

import pytest
import httpx

HEAT_PORT = 8071
RECOVERY_PORT = 8072
HEAT_URL = f"http://127.0.0.1:{HEAT_PORT}"
REC_URL = f"http://127.0.0.1:{RECOVERY_PORT}"


def _start(script_rel, port):
    script = os.path.join(os.path.dirname(__file__), "..", "..", script_rel)
    env = {**os.environ, "PORT": str(port),
           "PYTHONPATH": "packages/shared-schemas;packages/simulation;packages/a2a;services/scheduler-engine;mcp/common"}
    proc = subprocess.Popen([sys.executable, script], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # wait for health
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/.well-known/agent.json", timeout=1)
            return proc
        except Exception:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"service on port {port} did not start")


@pytest.mark.asyncio
async def test_a2a_agent_cards_and_tasks_send():
    heat_proc = _start("services/heat-guardian-agent/main.py", HEAT_PORT)
    rec_proc = _start("services/recovery-agent/main.py", RECOVERY_PORT)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Agent cards
            hc = await client.get(f"{HEAT_URL}/.well-known/agent.json")
            rc = await client.get(f"{REC_URL}/.well-known/agent.json")
            assert hc.status_code == 200
            assert rc.status_code == 200
            assert hc.json()["name"] == "TeevraHeatGuardianAgent"
            assert rc.json()["name"] == "TeevraBreakdownRecoveryAgent"

            # Real HTTP tasks/send to Heat Guardian
            hresp = await client.post(f"{HEAT_URL}/", json={
                "jsonrpc": "2.0", "id": "1", "method": "tasks/send",
                "params": {"id": "t1", "context_id": "c1",
                           "message": {"message_id": "m1", "context_id": "c1", "task_id": "t1",
                                       "role": "user", "parts": [{"text": json.dumps({"action": "evaluate_all"})}]},
                           "metadata": {"correlation_id": "corr-001"}}})
            assert hresp.status_code == 200
            hbody = hresp.json()
            assert "result" in hbody
            result = json.loads(hbody["result"]["artifacts"][0]["parts"][0]["text"]) if "artifacts" in hbody["result"] else hbody["result"]
            # result may be text content
            assert "status" in result or "results" in result or "message" in result

            # Real HTTP tasks/send to Recovery Agent (which consults Heat Guardian over A2A)
            rresp = await client.post(f"{REC_URL}/", json={
                "jsonrpc": "2.0", "id": "2", "method": "tasks/send",
                "params": {"id": "t2", "context_id": "c2",
                           "message": {"message_id": "m2", "context_id": "c2", "task_id": "t2",
                                       "role": "user", "parts": [{"text": json.dumps({
                                           "fault_machine": "CNC-A", "fault_start_slot": 20,
                                           "fault_end_slot": 31, "now_slot": 20,
                                           "time_limit_seconds": 20.0})}]},
                           "metadata": {"correlation_id": "corr-002"}}})
            assert rresp.status_code == 200
            rbody = rresp.json()
            assert "result" in rbody
    finally:
        heat_proc.kill()
        rec_proc.kill()
