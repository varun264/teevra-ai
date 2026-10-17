# TEEVR AI — API Contract (FastAPI gateway, :8080)

Auth: `Authorization: Bearer role:PLANNER|SUPERVISOR|WORKER` (local demo); Firebase in cloud.

Demo / control
- POST /api/demo/reset — seed baseline schedule
- POST /api/demo/seed

Events (Pub/Sub adapter, local in-memory bus)
- POST /api/events/machine-fault (idempotent via dedup key)
- POST /api/events/machine-restored
- POST /api/events/heat-reading

Schedule
- GET /api/schedule/current — committed schedule + frozen window
- GET /api/schedule/history — version list
- GET /api/schedule/diff?previous=&new= — per-job change evidence
- POST /api/schedule/recover — CP-SAT breakdown recovery
- POST /api/schedule/approve — optimistic commit + approval gate
- POST /api/schedule/reject
- POST /api/schedule/rollback

Heat Guardian
- GET /api/heat/workstations — risk per workstation
- GET /api/heat/measurements — recent sensor readings
- POST /api/events/heat-reading

Worker
- POST /api/worker/checkin — OK / Too Hot / SOS (SOS → immediate priority alert)
- GET /api/worker/checkin/status

Alerts
- GET /api/alerts
- POST /api/alerts/{id}/acknowledge
- POST /api/alerts/{id}/resolve

Agents / observability
- GET /api/agents/traces — audit + A2A/MCP traces
- GET /api/health, GET /api/readiness
- GET /api/events/stream — SSE
- WS /api/events/ws — WebSocket dashboard updates

A2A agent calls
- POST /api/a2a/recovery — call Breakdown Recovery Agent
- POST /api/a2a/heat — call Heat Guardian Agent

Role enforcement: planner-only tools return 403 for workers.
