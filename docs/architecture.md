# TEEVR AI — Architecture

## Primary flow

React Production Dashboard → Cloud Run FastAPI Gateway → ADK TEEVRA Orchestrator
  ├─ A2A ─▶ Breakdown Recovery Agent ─▶ Factory MCP ─▶ OR-Tools CP-SAT
  │                    │                  ├─ Scheduling MCP ─▶ CP-SAT
  │                    └─ A2A ◀─ Heat Guardian Agent ◀─ Safety MCP (sensors)
  │                                               └─ Worker check-in / alert tools
Pub/Sub + Eventarc → operational workflows
Firestore → current authoritative state
BigQuery → analytics & KPIs

## Agents

1. TeevraOrchestratorAgent — coordinates safety + breakdown, routes over A2A, unified status. Never modifies safety thresholds.
2. BreakdownRecoveryAgent — receives faults, reads committed schedule, builds CP-SAT, applies 2-hour frozen window, calls HeatGuardianAgent over real A2A before committing, returns structured explanation inputs.
3. HeatGuardianAgent — reads sensors/roles, evaluates deterministic heat rules, maintains workstation statuses, initiates safety actions, requests replanning over A2A, manages check-ins + escalation.
4. RecoveryExplanationAgent — Gemini explains deterministic changes from verified before/after facts only. Cannot alter solver values.
5. WorkerCommunicationAgent — Telugu/English check-ins, speech, approved templates only. No medical diagnosis.

## MCP servers (official SDK, stdio)

Factory MCP: get_current_schedule, get_machine_status, get_machine_capabilities, get_pending_jobs, get_worker_roster, get_workstation_assignments, get_production_constraints
Safety MCP: get_sensor_readings, get_wbgt_history, get_station_risk_status, get_approved_heat_policy, get_worker_acclimatization_class, get_pending_checkins, record_checkin_response, create_supervisor_alert
Scheduler MCP: validate_schedule, solve_recovery_plan, evaluate_plan_safety, compare_schedule_versions, commit_schedule_with_version_check, rollback_schedule

All tools: typed schemas, authz, explicit timeouts, audit + correlation IDs, reject unknown IDs, worker→planner gating, approval to commit non-emergency changes.

## Determinism

Safety-critical execution is deterministic and policy-controlled. LLMs never authorize exceptions to hard safety constraints and never touch solver values.
