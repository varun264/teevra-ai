# TEEVR AI — MCP

Three official-MCP-SDK servers (stdio), each a standalone process:

- mcp/factory-server (teevra-factory-mcp)
- mcp/safety-server (teevra-safety-mcp)
- mcp/scheduler-server (teevra-scheduler-mcp)

Every tool: typed JSON-schema input, authorization (worker vs planner), explicit timeouts, audit + correlation IDs logged to stderr, rejects unknown machine/worker/schedule IDs, worker clients cannot call planner-only tools, non-emergency commits require approval.

Real protocol flow demonstrated: tools/list → tools/call (tests/mcp/test_*_mcp.py). ADK McpToolset (StdioConnectionParams) can connect to each server; the gateway also invokes scheduler logic directly and via A2A.

Agent cards / tool schemas are machine-readable; errors return {error:{code,message,status}}.
