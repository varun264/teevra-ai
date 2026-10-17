"""TEEVRA observability - OpenTelemetry traces, correlation IDs, audit logging."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str] = ContextVar("correlation_id")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_correlation_id(cid: str):
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    try:
        return _correlation_id.get()
    except LookupError:
        cid = new_correlation_id()
        _correlation_id.set(cid)
        return cid


def audit_event(action: str, detail: dict, correlation_id: str | None = None) -> dict:
    cid = correlation_id or get_correlation_id()
    return {"action": action, "detail": detail, "correlation_id": cid}
