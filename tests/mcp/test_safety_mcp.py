"""MCP protocol test: safety server tools/list + tools/call (real stdio)."""

import pytest
import asyncio
import os
import sys

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession


@pytest.mark.asyncio
async def test_safety_mcp_protocol():
    server_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "mcp", "safety-server", "server.py"
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[server_path],
        env={**os.environ, "PYTHONPATH": "packages/shared-schemas;packages/simulation;packages/a2a;mcp/common"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            for required in ["get_sensor_readings", "get_station_risk_status", "get_approved_heat_policy",
                             "record_checkin_response", "create_supervisor_alert"]:
                assert required in names, f"missing {required}"
            # risk status for a known workstation
            res = await session.call_tool("get_station_risk_status", {"workstation_id": "WS-F1", "role": "WORKER"})
            assert res.is_error is False
            import json
            payload = json.loads(res.content[0].text)
            assert "risk_level" in payload
            assert "wbgt_c" in payload
            # unknown workstation -> error
            res2 = await session.call_tool("get_station_risk_status", {"workstation_id": "NOPE", "role": "WORKER"})
            assert res2.is_error is True
            # worker cannot create supervisor alert (planner-only)
            res3 = await session.call_tool("create_supervisor_alert", {
                "alert_type": "TEST", "severity": "LOW", "message": "m", "role": "WORKER"
            })
            assert res3.is_error is True
