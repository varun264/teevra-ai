"""Shared helpers for TEEVRA MCP servers: auth, audit, errors."""

from __future__ import annotations

from datetime import datetime, timezone
import sys
from typing import Any, Optional

from pydantic import BaseModel, Field


class AuthContext(BaseModel):
    role: str
    worker_id: Optional[str] = None
    correlation_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)


class MCPError(Exception):
    """Machine-readable MCP tool error."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "status": self.status}}


PLANNER_ROLES = {"PLANNER", "SUPERVISOR", "ADMIN"}
WORKER_ROLES = {"WORKER", "OPERATOR"}


def require_role(ctx: AuthContext, allowed: set[str]) -> None:
    if ctx.role not in allowed:
        raise MCPError(
            "FORBIDDEN",
            f"role '{ctx.role}' not authorized; required one of {sorted(allowed)}",
            403,
        )


def require_planner(ctx: AuthContext) -> None:
    require_role(ctx, PLANNER_ROLES)


def require_worker_or_planner(ctx: AuthContext) -> None:
    require_role(ctx, PLANNER_ROLES | WORKER_ROLES)


PLANNER_ONLY_TOOLS = {
    "validate_schedule",
    "solve_recovery_plan",
    "commit_schedule_with_version_check",
    "rollback_schedule",
    "create_supervisor_alert",
    "get_production_constraints",
}


def enforce_tool_auth(ctx: AuthContext, tool_name: str) -> None:
    if tool_name in PLANNER_ONLY_TOOLS:
        require_planner(ctx)
    else:
        require_worker_or_planner(ctx)


def audit_log(
    tool_name: str,
    ctx: AuthContext,
    action: str,
    detail: Optional[dict[str, Any]] = None,
    level: str = "INFO",
) -> dict[str, Any]:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "tool": tool_name,
        "correlation_id": ctx.correlation_id,
        "role": ctx.role,
        "worker_id": ctx.worker_id,
        "action": action,
        "detail": detail or {},
    }
    print(
        f"AUDIT {record['timestamp']} | {tool_name} | {action} | "
        f"corr={ctx.correlation_id} | role={ctx.role} | detail={detail}",
        file=sys.stderr,
    )
    return record


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "AuthContext",
    "MCPError",
    "PLANNER_ROLES",
    "WORKER_ROLES",
    "require_role",
    "require_planner",
    "require_worker_or_planner",
    "enforce_tool_auth",
    "audit_log",
    "now_iso",
]
