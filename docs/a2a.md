# TEEVR AI — A2A (Agent2Agent)

Recovery Agent (:8072) and Heat Guardian Agent (:8071) are independently hosted ADK services, each exposing a standards-compatible Agent Card at `/.well-known/agent.json` (a2a-sdk protobuf).

Inter-agent communication is real HTTP JSON-RPC `tasks/send`:
- task IDs, context IDs, correlation IDs (X-Correlation-ID header)
- per-request timeouts (httpx), auth token support
- failures returned as JSON-RPC error objects; client raises on error

Evidence: tests/a2a/test_recovery_heat_a2a.py starts both services over HTTP, fetches Agent Cards, and exchanges tasks/send — including the Recovery Agent consulting the Heat Guardian over A2A before committing a plan.

The Orchestrator calls both agents over A2A via /api/a2a/recovery and /api/a2a/heat on the gateway.
