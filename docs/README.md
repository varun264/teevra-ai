# TEEVR AI

Autonomous Machine Breakdown Rescheduler (Feature 3) + Heat Stress Guardian (Feature 4)
for a Google Cloud AI hackathon. Telangana, India factory simulation.

## Architecture

```
React Dashboard ──▶ Cloud Run FastAPI Gateway ──▶ ADK TEEVRA Orchestrator
                                              ├─ A2A ─▶ Breakdown Recovery Agent ─▶ MCP Scheduler ─▶ OR-Tools CP-SAT
                                              └─ A2A ─▶ Heat Guardian Agent ───────▶ MCP Safety Sensors
```

Pub/Sub + Eventarc trigger workflows; Firestore holds authoritative state; BigQuery stores analytics.

## Tech stack

- Python 3.11, FastAPI, Google ADK, OR-Tools CP-SAT, MCP SDK (2.x), A2A SDK (1.x)
- React + Vite + Tailwind dashboard; mobile Worker PWA (Telugu/English)
- Docker Compose (local), Cloud Run + Terraform (cloud), Firestore/Pub/Sub/BigQuery

## Quick start (local, no GCP credentials needed)

```bash
cd teevra-ai
# backend
py -3.11 -m pip install -r requirements.txt
# frontend
cd apps/dashboard && npm install && cd ../..
# run tests
py -3.11 -m pytest tests/ -q        # 21 tests pass
# run backend
PYTHONPATH="packages/shared-schemas;packages/simulation;packages/a2a;services/scheduler-engine;mcp/common" \
  py -3.11 services/api-gateway/main.py
# run frontend (another terminal)
cd apps/dashboard && npm run dev
```

Dashboard: http://localhost:5173  ·  API: http://localhost:8080  ·  API docs: http://localhost:8080/docs

Or one command: `docker compose up --build -d`

## What works (validated by tests)

- CP-SAT baseline + breakdown recovery with 2-hour frozen window (optimal/feasible, never claims optimality without solver evidence)
- Frozen-window jobs never move; broken-machine jobs stop despite freezing; only compatible replacement equipment used; no overlapping machine jobs; furnace jobs never split
- Real MCP stdio servers: factory (7 tools), safety (8 tools), scheduler (6 tools) — tools/list + tools/call with auth, timeouts, correlation IDs, machine-readable errors
- Real HTTP A2A between Recovery Agent and Heat Guardian Agent — Agent Cards + tasks/send with task IDs, correlation IDs, timeouts
- Full REST contract (/api/*), SSE event stream, WebSocket, role-based access, demo control panel
- Frontend: TypeScript-clean, production build passes, 8 pages (Overview, Live Floor, Breakdown Recovery, Heat Guardian, Worker PWA, Supervisor Alerts, Agent Observability, Demo Control)

## Safety disclaimer

Heat Guardian is a safety-support / early-warning demo, NOT a certified occupational-health instrument. All WBGT thresholds are explicitly labeled simulation policy values, not certified regulatory limits. Do not use for real-world safety decisions.

## Cloud deployment

See docs/cloud-deployment.md (Cloud Run, Terraform, Secret Manager, IAM, no service-account keys in repo).
