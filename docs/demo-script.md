# TEEVR AI — Demo Script

Prereqs: backend on :8080, dashboard on :5173, recovery :8072, heat guardian :8071.

1. Open http://localhost:5173 → Dashboard shows factory overview (43 jobs, 7 machines).
2. Demo Control → "Reset Demo" (seeds baseline CP-SAT schedule).
3. Live Floor → all stations green.
4. Breakdown Recovery → "Simulate CNC-A Breakdown":
   - Pub/Sub emits MACHINE_BREAKDOWN, Eventarc routes to recovery service.
   - Solver runs CP-SAT with 2-hour frozen window; CNC-A jobs stop, CNC-B absorbs compatible work.
   - Recovery Agent calls Heat Guardian over A2A before commit.
   - Planner approves → optimistic version check → commit → Gantt refreshes.
   - Gemini explanation shows each change (verified facts only).
5. Heat Guardian → "Simulate Furnace Heat Spike":
   - WBGT crosses STOP_WORK → priority alert, heat-triggered rescheduling requested over A2A.
   - Verify missing/stale sensor → UNKNOWN (never false-safe).
6. Worker PWA → Telugu check-in:
   - Consent → OK / Too Hot / SOS.
   - SOS → immediate priority alert (no Gemini dependency).
   - Missed check-in → escalates after grace period.
7. Agent Observability → real traces: task IDs, correlation IDs, MCP calls, solver latency, safety checks, commits.
8. Supervisor Alerts → acknowledge / resolve / escalate.

Every demo button runs real backend logic; results are not hardcoded.
