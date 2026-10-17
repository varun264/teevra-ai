"""Real MCP protocol test: stdio client lists + calls factory tools."""

import pytest
import asyncio
import os
import sys

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession


@pytest.mark.asyncio
async def test_factory_mcp_protocol():
    server_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "mcp", "factory-server", "server.py"
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[server_path],
        env={**os.environ, "PYTHONPATH": "packages/shared-schemas;packages/simulation;mcp/common"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])
            # call get_machine_status
            result = await session.call_tool(
                "get_machine_status",
                {"machine_id": "CNC-A", "role": "WORKER"},
            )
            print("CALL RESULT:", result)
            # call unknown machine -> expect MCP error content
            res2 = await session.call_tool(
                "get_machine_status", {"machine_id": "NOPE", "role": "WORKER"}
            )
            print("UNKNOWN MACHINE is_error:", res2.is_error)
            assert res2.is_error is True


