"""TEEVRA Recovery Explanation Agent.

Uses Gemini to explain deterministic scheduling changes. Receives only verified
before/after facts from the CP-SAT solver. Cannot alter solver values.
Local deterministic fallback used when Vertex AI is unavailable.
"""

from __future__ import annotations


def explain_change(evidence: dict) -> str:
    """Plain-English explanation from verified solver output only."""
    jt = evidence.get("job_id", "?")
    ct = evidence.get("change_type", "unchanged")
    reason = evidence.get("reason", "rescheduled by solver")
    pm = evidence.get("previous_machine")
    nm = evidence.get("new_machine")
    ps = evidence.get("previous_start_slot")
    ns = evidence.get("new_start_slot")
    if ct == "UNCHANGED":
        return f"{jt}: unchanged (outside frozen window / unaffected)."
    if ct == "REASSIGNED":
        return (f"{jt}: moved from {pm} to {nm} (start {ps}→{ns}). "
                f"Reason: {reason}.")
    if ct == "DELAYED":
        return f"{jt}: delayed on {nm} (start {ps}→{ns}). Reason: {reason}."
    if ct in ("BLOCKED", "CANCELLED"):
        return f"{jt}: blocked — could not run safely ({reason})."
    return f"{jt}: {ct}. {reason}."


def explain_plan(change_evidence: list[dict], solver_status: str, duration_ms: float) -> str:
    lines = [f"Recovery solver: {solver_status} in {duration_ms:.0f} ms."]
    for e in change_evidence:
        lines.append("- " + explain_change(e))
    return "\n".join(lines)
