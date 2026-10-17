"""Scheduler MCP server (stdio / StreamableHTTP).

Tools: validate_schedule, solve_recovery_plan, evaluate_plan_safety,
compare_schedule_versions, commit_schedule_with_version_check, rollback_schedule.

Deterministic policy-controlled scheduling via CP-SAT. LLM never touches
solver values.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from mcp.server.mcpserver import MCPServer

from teevra_mcp_common import (
    AuthContext,
    MCPError,
    audit_log,
    enforce_tool_auth,
    now_iso,
)
from teevra_shared_schemas import CommitResult, SolverStatus
from teevra_simulation import JOBS, MACHINES, TOTAL_SLOTS, get_machine, get_worker
from teevra_simulation.state import get_state
from teevra_shared_schemas.jobs import Job, MachineJobAssignment
from teevra_shared_schemas.schedule import FrozenWindow, ScheduleEntry, ScheduleVersion
from teevra_shared_schemas.scheduling import RecoveryPlan, SolverResult

try:
    from teevra_scheduler_engine import CPSatSchedulingEngine
except Exception:  # local fallback import path
    from teevra_scheduler_engine import CPSatSchedulingEngine  # type: ignore

server = MCPServer(name="teevra-scheduler-mcp", version="1.0.0")
PLANNER_ROLES = {"PLANNER", "SUPERVISOR", "ADMIN"}
_ENGINE = CPSatSchedulingEngine(total_slots=TOTAL_SLOTS)


def _ctx(correlation_id: Optional[str], role: Optional[str], worker_id: Optional[str]) -> AuthContext:
    return AuthContext(
        role=role or "PLANNER",
        worker_id=worker_id,
        correlation_id=correlation_id or uuid.uuid4().hex,
    )


def _load_current_version(state) -> Optional[ScheduleVersion]:
    vid = state.current_version_id
    return state.schedules.get(vid) if vid else None


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@server.tool()
async def validate_schedule(
    version_id: str,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "PLANNER",
    worker_id: Optional[str] = None,
) -> dict:
    """Validate a schedule version for overlaps and feasibility."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "validate_schedule")
    state = get_state()
    version = state.schedules.get(version_id)
    if version is None:
        raise MCPError("NOT_FOUND", f"unknown schedule version: {version_id}", 404)
    errors = _ENGINE.validate_schedule(version)
    audit_log("validate_schedule", ctx, "validate", {"version_id": version_id, "errors": len(errors)})
    return {
        "status": "ok",
        "version_id": version_id,
        "valid": len(errors) == 0,
        "errors": errors,
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def solve_recovery_plan(
    fault_machine: str,
    fault_start_slot: int,
    fault_end_slot: int,
    now_slot: Optional[int] = None,
    time_limit_seconds: Optional[float] = 30.0,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "PLANNER",
    worker_id: Optional[str] = None,
) -> dict:
    """Solve a CP-SAT recovery plan after a machine breakdown."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "solve_recovery_plan")
    state = get_state()
    current = _load_current_version(state)
    if current is None:
        raise MCPError("NOT_FOUND", "no current schedule version to recover from", 404)
    try:
        get_machine(fault_machine)
    except KeyError:
        raise MCPError("NOT_FOUND", f"unknown machine_id: {fault_machine}", 404)
    if now_slot is None:
        now_slot = fault_start_slot

    heat_blocked = [
        wid for wid, risk in state.workstation_risk.items() if risk == "STOP_WORK"
    ]

    plan = _ENGINE.recover_after_breakdown(
        current_version=current,
        fault_machine=fault_machine,
        fault_start_slot=fault_start_slot,
        fault_end_slot=fault_end_slot,
        now_slot=now_slot,
        heat_blocked_stations=heat_blocked,
        time_limit_seconds=float(time_limit_seconds or 30.0),
    )

    # store candidate version (not committed)
    state.schedules[plan.schedule_version.version_id] = plan.schedule_version
    state.candidate_version_id = plan.schedule_version.version_id
    r = plan.solver_result
    audit_log("solve_recovery_plan", ctx, "solve", {
        "fault_machine": fault_machine, "status": r.solver_status.value,
        "reassigned": r.jobs_reassigned, "blocked": r.jobs_blocked,
    })
    return {
        "status": "ok",
        "plan_id": plan.plan_id,
        "version_id": plan.schedule_version.version_id,
        "solver_status": r.solver_status.value,
        "is_feasible": r.is_feasible,
        "is_optimal": r.is_optimal,
        "jobs_unchanged": r.jobs_unchanged,
        "jobs_reassigned": r.jobs_reassigned,
        "jobs_delayed": r.jobs_delayed,
        "jobs_blocked": r.jobs_blocked,
        "expected_output_percent": r.expected_output_percent,
        "electricity_cost_before_inr": r.electricity_cost_before_inr,
        "electricity_cost_after_inr": r.electricity_cost_after_inr,
        "recovery_duration_ms": r.recovery_duration_ms,
        "human_approval_required": r.human_approval_required,
        "auto_commit_allowed": plan.auto_commit_allowed,
        "infeasibility_report": r.infeasibility_report,
        "change_evidence": [e.model_dump() for e in r.change_evidence],
        "safety_validation_result": r.safety_validation_result,
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def evaluate_plan_safety(
    version_id: str,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Evaluate whether a candidate schedule violates heat-safety constraints."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "evaluate_plan_safety")
    state = get_state()
    version = state.schedules.get(version_id)
    if version is None:
        raise MCPError("NOT_FOUND", f"unknown schedule version: {version_id}", 404)
    breaches = []
    for e in version.entries:
        try:
            m = get_machine(e.machine_id)
        except KeyError:
            raise MCPError("NOT_FOUND", f"unknown machine_id in schedule: {e.machine_id}", 404)
        if m.heat_sensitive and state.workstation_risk.get(e.machine_id) == "STOP_WORK":
            breaches.append({
                "job_id": e.job_id,
                "machine_id": e.machine_id,
                "reason": "workstation STOP_WORK - heat safety breach",
            })
    safe = len(breaches) == 0
    audit_log("evaluate_plan_safety", ctx, "evaluate", {"version_id": version_id, "breaches": len(breaches), "safe": safe})
    return {
        "status": "ok",
        "version_id": version_id,
        "safe": safe,
        "breaches": breaches,
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def compare_schedule_versions(
    previous_version_id: str,
    new_version_id: str,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "WORKER",
    worker_id: Optional[str] = None,
) -> dict:
    """Compare two schedule versions and return per-job change evidence."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "compare_schedule_versions")
    state = get_state()
    prev = state.schedules.get(previous_version_id)
    new = state.schedules.get(new_version_id)
    if prev is None:
        raise MCPError("NOT_FOUND", f"unknown schedule version: {previous_version_id}", 404)
    if new is None:
        raise MCPError("NOT_FOUND", f"unknown schedule version: {new_version_id}", 404)
    evidence = _ENGINE.compare_schedules(prev, new)
    audit_log("compare_schedule_versions", ctx, "compare", {
        "previous": previous_version_id, "new": new_version_id, "changes": len(evidence),
    })
    return {
        "status": "ok",
        "previous_version": previous_version_id,
        "new_version": new_version_id,
        "change_evidence": [e.model_dump() for e in evidence],
        "count": len(evidence),
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def commit_schedule_with_version_check(
    version_id: str,
    expected_parent_version: Optional[str] = None,
    approval: Optional[bool] = None,
    emergency: Optional[bool] = False,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "PLANNER",
    worker_id: Optional[str] = None,
) -> dict:
    """Commit a candidate schedule with optimistic concurrency + approval."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "commit_schedule_with_version_check")
    state = get_state()
    version = state.schedules.get(version_id)
    if version is None:
        raise MCPError("NOT_FOUND", f"unknown schedule version: {version_id}", 404)
    # version check
    if expected_parent_version and version.parent_version_id != expected_parent_version:
        raise MCPError("CONFLICT", "version mismatch - schedule was updated by another operation", 409)
    # approval gate
    if not emergency and not approval:
        raise MCPError("APPROVAL_REQUIRED", "planner approval required to commit non-emergency changes", 403)
    # safety gate
    heat_blocked = [wid for wid, risk in state.workstation_risk.items() if risk == "STOP_WORK"]
    for e in version.entries:
        try:
            m = get_machine(e.machine_id)
        except KeyError:
            raise MCPError("NOT_FOUND", f"unknown machine_id: {e.machine_id}", 404)
        if m.heat_sensitive and e.machine_id in heat_blocked:
            raise MCPError("SAFETY_BLOCKED", f"cannot commit: {e.machine_id} is STOP_WORK", 403)
    version.is_committed = True
    version.commit_correlation_id = ctx.correlation_id
    version.updated_at = datetime.now(timezone.utc)
    state.current_version_id = version_id
    state.audit.append({
        "timestamp": now_iso(), "action": "commit_schedule", "version_id": version_id,
        "correlation_id": ctx.correlation_id, "role": ctx.role,
    })
    audit_log("commit_schedule_with_version_check", ctx, "commit", {"version_id": version_id, "emergency": emergency})
    return {
        "status": "ok",
        "commit_result": CommitResult.COMMITTED.value,
        "version_id": version_id,
        "is_committed": version.is_committed,
        "correlation_id": ctx.correlation_id,
    }


@server.tool()
async def rollback_schedule(
    target_version_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    role: Optional[str] = "PLANNER",
    worker_id: Optional[str] = None,
) -> dict:
    """Rollback to a previous (or last committed) schedule version."""
    ctx = _ctx(correlation_id, role, worker_id)
    enforce_tool_auth(ctx, "rollback_schedule")
    state = get_state()
    if target_version_id:
        version = state.schedules.get(target_version_id)
        if version is None:
            raise MCPError("NOT_FOUND", f"unknown schedule version: {target_version_id}", 404)
    else:
        committed = [v for v in state.schedules.values() if v.is_committed]
        if not committed:
            raise MCPError("NOT_FOUND", "no committed schedule to rollback to", 404)
        version = sorted(committed, key=lambda v: v.created_at or "")[-1]
    state.current_version_id = version.version_id
    audit_log("rollback_schedule", ctx, "rollback", {"to_version": version.version_id})
    return {
        "status": "ok",
        "version_id": version.version_id,
        "is_committed": version.is_committed,
        "correlation_id": ctx.correlation_id,
    }


if __name__ == "__main__":
    server.run(transport="stdio")
