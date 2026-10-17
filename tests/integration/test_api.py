"""Integration tests for the TEEVRA API gateway (local mode)."""

from fastapi.testclient import TestClient
import sys

sys.path.insert(0, "services/api-gateway")
import main as gw  # noqa: E402


def _client():
    return TestClient(gw.app)


def test_health_and_readiness():
    c = _client()
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/readiness").status_code == 200


def test_demo_reset_seeds_schedule():
    c = _client()
    r = c.post("/api/demo/reset", headers={"Authorization": "Bearer role:PLANNER"})
    assert r.status_code == 200
    assert r.json()["entries"] == 43


def test_machine_fault_dedup():
    c = _client()
    c.post("/api/demo/reset", headers={"Authorization": "Bearer role:PLANNER"})
    body = {"machine_id": "CNC-A", "event_type": "MACHINE_BREAKDOWN", "timestamp": "2026-10-17T11:30:00+05:30",
            "estimated_repair_minutes": 180, "severity": "HIGH", "source": "SIMULATOR"}
    r1 = c.post("/api/events/machine-fault", json=body, headers={"Authorization": "Bearer role:PLANNER"})
    assert r1.json()["status"] == "accepted"
    r2 = c.post("/api/events/machine-fault", json=body, headers={"Authorization": "Bearer role:PLANNER"})
    assert r2.json()["status"] == "duplicate"


def test_breakdown_recovery_end_to_end():
    c = _client()
    c.post("/api/demo/reset", headers={"Authorization": "Bearer role:PLANNER"})
    cur = c.get("/api/schedule/current").json()
    assert cur["status"] == "ok"
    rec = c.post("/api/schedule/recover", json={
        "fault_machine": "CNC-A", "fault_start_slot": 20, "fault_end_slot": 31, "now_slot": 20,
    }, headers={"Authorization": "Bearer role:PLANNER"})
    assert rec.status_code == 200
    plan = rec.json()["plan"]
    assert plan["is_feasible"] is True
    assert plan["jobs_unchanged"] + plan["jobs_reassigned"] + plan["jobs_delayed"] + plan["jobs_blocked"] >= 0
    assert plan["recovery_duration_ms"] > 0


def test_approve_reject_rollback():
    c = _client()
    c.post("/api/demo/reset", headers={"Authorization": "Bearer role:PLANNER"})
    cur = c.get("/api/schedule/current").json()
    rec = c.post("/api/schedule/recover", json={"fault_machine": "CNC-A", "fault_start_slot": 20, "fault_end_slot": 31, "now_slot": 20}, headers={"Authorization": "Bearer role:PLANNER"})
    vid = rec.json()["version_id"]
    # commit needs approval
    r = c.post("/api/schedule/approve", json={"version_id": vid}, headers={"Authorization": "Bearer role:PLANNER"})
    assert r.status_code == 200
    # rollback
    rb = c.post("/api/schedule/rollback", headers={"Authorization": "Bearer role:PLANNER"})
    assert rb.status_code == 200


def test_heat_reading_missing_sensor_not_safe():
    c = _client()
    r = c.post("/api/events/heat-reading", json={
        "workstation_id": "WS-F1", "temperature_c": 45, "relative_humidity": 90,
        "natural_wet_bulb_c": None, "globe_temperature_c": None,
        "sensor_quality": "FAULTY", "sensor_fresh_seconds": 600,
    }, headers={"Authorization": "Bearer role:PLANNER"})
    assert r.status_code == 200
    assert r.json()["risk_level"] == "UNKNOWN"


def test_worker_sos_raises_alert():
    c = _client()
    r = c.post("/api/worker/checkin", json={"worker_id": "WRK-09", "response": "SOS", "language": "en"}, headers={"Authorization": "Bearer role:WORKER"})
    assert r.status_code == 200
    alerts = c.get("/api/alerts", headers={"Authorization": "Bearer role:PLANNER"}).json()["alerts"]
    sos = [a for a in alerts if a["alert_type"] == "WORKER_SOS"]
    assert len(sos) >= 1
    assert sos[0]["severity"] == "CRITICAL"


def test_role_based_access():
    c = _client()
    # worker cannot approve schedule
    r = c.post("/api/schedule/approve", json={"version_id": "v000"}, headers={"Authorization": "Bearer role:WORKER"})
    assert r.status_code == 403


def test_missing_firebase_config_local_mode():
    c = _client()
    r = c.get("/api/health")
    assert r.status_code == 200
    assert r.json()["mode"] == "local"
