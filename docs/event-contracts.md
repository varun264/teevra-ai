# TEEVR AI — Event Contracts

Event envelopes (packages/event-contracts): event_id, event_type, source, timestamp (UTC), correlation_id, payload, trace_id, span_id.

- MACHINE_FAULT: {event_id, machine_id, event_type, timestamp, estimated_repair_minutes, severity, source}
  Example: fault-001, CNC-A, MACHINE_BREAKDOWN, 2026-10-17T11:30:00+05:30, 180 min, HIGH, SIMULATOR
- MACHINE_RESTORED: {event_id, machine_id, restored_at, source}
- HEAT_RISK: {event_id, workstation_id, wbgt_c, risk_level, timestamp}
- SCHEDULE_UPDATE: {event_id, version_id, change_evidence, timestamp}
- WORKER_CHECK_IN: {event_id, worker_id, response, workstation_id, timestamp}

Idempotency: fault events deduplicated on {event_type, machine_id, timestamp}. All persisted timestamps UTC; presentation converts to Asia/Kolkata.
