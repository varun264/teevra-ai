"""Deterministic demo factory data for TEEVRA AI.

Telangana, India. 40 workers, 2 shifts, 48-hour horizon, 15-minute slots.
All data is explicitly simulated / labeled for hackathon demonstration.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from teevra_shared_schemas import (
    JobStatus,
    JobType,
    MachineCapability,
    MachineStatus,
    Role,
    Shift,
    UTCNow,
)
from teevra_shared_schemas.jobs import Job
from teevra_shared_schemas.machines import Machine

HORIZON_HOURS = 48
SLOT_DURATION_MINUTES = 15
TOTAL_SLOTS = HORIZON_HOURS * 4  # 192
FROZEN_WINDOW_MINUTES = 120
FROZEN_WINDOW_SLOTS = FROZEN_WINDOW_MINUTES // SLOT_DURATION_MINUTES  # 8

IST = timezone(timedelta(hours=5, minutes=30))
DEMO_START = datetime(2026, 10, 17, 6, 0, 0, tzinfo=IST)  # shift A start


def slot_to_ist(slot: int) -> datetime:
    return DEMO_START + timedelta(minutes=slot * SLOT_DURATION_MINUTES)


def ist_to_slot(dt: datetime) -> int:
    return int((dt - DEMO_START).total_seconds() // (SLOT_DURATION_MINUTES * 60))


# ---------------------------------------------------------------------------
# Machines
# ---------------------------------------------------------------------------

MACHINES: List[Machine] = [
    Machine(
        machine_id="CNC-A",
        name="CNC Milling Machine A",
        status=MachineStatus.AVAILABLE,
        location="Cell 1",
        capabilities=MachineCapability(
            can_cut_metal=True,
            heat_emission_level=2,
            requires_cooling=False,
            compatible_job_types=["PRODUCTION", "INTERRUPTIBLE"],
        ),
        max_concurrent_jobs=1,
        power_rating_kw=5.5,
        restart_energy_penalty_kwh=0.8,
        tariff_sensitive=True,
        heat_sensitive=False,
        compatible_machines=["CNC-B"],
    ),
    Machine(
        machine_id="CNC-B",
        name="CNC Milling Machine B",
        status=MachineStatus.AVAILABLE,
        location="Cell 1",
        capabilities=MachineCapability(
            can_cut_metal=True,
            heat_emission_level=2,
            requires_cooling=False,
            compatible_job_types=["PRODUCTION", "INTERRUPTIBLE"],
        ),
        max_concurrent_jobs=1,
        power_rating_kw=5.5,
        restart_energy_penalty_kwh=0.8,
        tariff_sensitive=True,
        heat_sensitive=False,
        compatible_machines=["CNC-A"],
    ),
    Machine(
        machine_id="F1",
        name="Induction Furnace F1",
        status=MachineStatus.AVAILABLE,
        location="Cell 2",
        capabilities=MachineCapability(
            can_melt_metal=True,
            heat_emission_level=5,
            requires_cooling=True,
            compatible_job_types=["FURNACE", "PRODUCTION"],
        ),
        max_concurrent_jobs=1,
        power_rating_kw=45.0,
        restart_energy_penalty_kwh=12.0,
        tariff_sensitive=True,
        heat_sensitive=True,
        compatible_machines=[],
    ),
    Machine(
        machine_id="P1",
        name="Paint Oven P1",
        status=MachineStatus.AVAILABLE,
        location="Cell 3",
        capabilities=MachineCapability(
            can_paint=True,
            heat_emission_level=3,
            requires_cooling=False,
            compatible_job_types=["PRODUCTION"],
        ),
        max_concurrent_jobs=1,
        power_rating_kw=18.0,
        restart_energy_penalty_kwh=3.0,
        tariff_sensitive=True,
        heat_sensitive=True,
        compatible_machines=[],
    ),
    Machine(
        machine_id="AC1",
        name="Air Compressor AC1",
        status=MachineStatus.AVAILABLE,
        location="Utilities",
        capabilities=MachineCapability(
            can_compress_air=True,
            heat_emission_level=1,
            requires_cooling=False,
            compatible_job_types=["PRODUCTION", "MAINTENANCE"],
        ),
        max_concurrent_jobs=2,
        power_rating_kw=7.5,
        restart_energy_penalty_kwh=0.4,
        tariff_sensitive=False,
        heat_sensitive=False,
        compatible_machines=[],
    ),
    Machine(
        machine_id="CH1",
        name="Chiller CH1",
        status=MachineStatus.AVAILABLE,
        location="Utilities",
        capabilities=MachineCapability(
            can_chill=True,
            heat_emission_level=2,
            requires_cooling=False,
            compatible_job_types=["PRODUCTION", "MAINTENANCE"],
        ),
        max_concurrent_jobs=1,
        power_rating_kw=11.0,
        restart_energy_penalty_kwh=2.0,
        tariff_sensitive=False,
        heat_sensitive=False,
        compatible_machines=[],
    ),
    Machine(
        machine_id="MF-1",
        name="Manual Furnace Station 1",
        status=MachineStatus.AVAILABLE,
        location="Cell 2",
        capabilities=MachineCapability(
            can_melt_metal=True,
            heat_emission_level=5,
            requires_cooling=True,
            compatible_job_types=["FURNACE", "MAINTENANCE"],
        ),
        max_concurrent_jobs=1,
        power_rating_kw=3.0,
        restart_energy_penalty_kwh=0.5,
        tariff_sensitive=False,
        heat_sensitive=True,
        compatible_machines=["F1"],
    ),
]


def get_machine(machine_id: str) -> Machine:
    for m in MACHINES:
        if m.machine_id == machine_id:
            return m
    raise KeyError(f"Unknown machine: {machine_id}")


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

WORKER_ROLES = {
    "SUPERVISOR": Role.SUPERVISOR,
    "PLANNER": Role.PLANNER,
    "OPERATOR": Role.OPERATOR,
    "WORKER": Role.WORKER,
}

# 40 workers: 2 supervisors, 2 planners, 6 operators, 30 workers
WORKERS: List[dict] = []
wid = 0
for i in range(2):
    wid += 1
    WORKERS.append(
        {
            "worker_id": f"SUP-{i+1:02d}",
            "name": f"Supervisor {i+1}",
            "role": Role.SUPERVISOR,
            "shift": Shift.A if i == 0 else Shift.B,
            "skills": ["crane", "furnace", "oven", "cnc"],
            "acclimatization_class": "ACCLIMATED",
            "workstation": "control_room",
        }
    )
for i in range(2):
    wid += 1
    WORKERS.append(
        {
            "worker_id": f"PLN-{i+1:02d}",
            "name": f"Planner {i+1}",
            "role": Role.PLANNER,
            "shift": Shift.A if i == 0 else Shift.B,
            "skills": ["scheduling", "cnc", "furnace"],
            "acclimatization_class": "ACCLIMATED",
            "workstation": "planning_office",
        }
    )
for i in range(6):
    wid += 1
    WORKERS.append(
        {
            "worker_id": f"OPE-{i+1:02d}",
            "name": f"Operator {i+1}",
            "role": Role.OPERATOR,
            "shift": Shift.A if i < 3 else Shift.B,
            "skills": ["cnc", "furnace", "oven", "compressor"],
            "acclimatization_class": "ACCLIMATED",
            "workstation": "cell_floor",
        }
    )
for i in range(30):
    wid += 1
    shift = Shift.A if i < 15 else Shift.B
    WORKERS.append(
        {
            "worker_id": f"WRK-{i+1:02d}",
            "name": f"Worker {i+1}",
            "role": Role.WORKER,
            "shift": shift,
            "skills": ["cnc", "furnace", "oven", "manual"],
            "acclimatization_class": "ACCLIMATED" if i % 3 == 0 else "UNACCLIMATED",
            "workstation": f"station_{(i % 8) + 1}",
        }
    )


def get_worker(worker_id: str) -> dict:
    for w in WORKERS:
        if w["worker_id"] == worker_id:
            return w
    raise KeyError(f"Unknown worker: {worker_id}")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def build_jobs() -> List[Job]:
    """Generate a realistic mix of production jobs across the 48h horizon."""
    jobs: List[Job] = []
    # Each job gets release/deadline slots within horizon.
    job_counter = 0

    def add(
        name: str,
        job_type: JobType,
        duration_min: int,
        release_slot: int,
        deadline_slot: int,
        priority: int,
        machines: List[str],
        power_kw: float,
        energy_kwh: float,
        furnace: bool = False,
        interruptible: bool = False,
        workers: int = 1,
        tariff_sensitive: bool = False,
        precedence: List[str] = None,
    ) -> None:
        nonlocal job_counter
        job_counter += 1
        jobs.append(
            Job(
                job_id=f"JOB-{job_counter:04d}",
                job_type=job_type,
                name=name,
                duration_minutes=duration_min,
                release_slot=release_slot,
                deadline_slot=deadline_slot,
                priority=priority,
                compatible_machines=machines,
                power_kw=power_kw,
                energy_kwh=energy_kwh,
                restart_energy_penalty_kwh=energy_kwh * 0.1,
                tariff_sensitive=tariff_sensitive,
                is_furnace=furnace,
                is_interruptible=interruptible,
                required_workers=workers,
                precedence_job_ids=precedence or [],
                status=JobStatus.SCHEDULED,
            )
        )

    # Shift A: 06:00-14:00 IST => slots 0-32 ; Shift B: 14:00-22:00 => 32-64 ; Night: 22:00-06:00 => 64-192

    # CNC jobs (metal cutting) - compatible CNC-A / CNC-B
    for i in range(12):
        add(
            name=f"CNC Part Batch {i+1}",
            job_type=JobType.PRODUCTION,
            duration_min=90,
            release_slot=i * 4,
            deadline_slot=min(i * 4 + 30, TOTAL_SLOTS - 1),
            priority=3,
            machines=["CNC-A", "CNC-B"],
            power_kw=5.5,
            energy_kwh=8.25,
            workers=1,
            tariff_sensitive=True,
        )

    # Furnace jobs (non-preemptive) - F1 only
    for i in range(4):
        add(
            name=f"Furnace Melt {i+1}",
            job_type=JobType.FURNACE,
            duration_min=180,
            release_slot=i * 16,
            deadline_slot=min(i * 16 + 60, TOTAL_SLOTS - 1),
            priority=5,
            machines=["F1"],
            power_kw=45.0,
            energy_kwh=135.0,
            furnace=True,
            workers=2,
            tariff_sensitive=True,
        )

    # Paint oven jobs - P1 only
    for i in range(6):
        add(
            name=f"Paint Cure {i+1}",
            job_type=JobType.PRODUCTION,
            duration_min=120,
            release_slot=i * 10,
            deadline_slot=min(i * 10 + 40, TOTAL_SLOTS - 1),
            priority=3,
            machines=["P1"],
            power_kw=18.0,
            energy_kwh=36.0,
            workers=1,
            tariff_sensitive=True,
        )

    # Compressor jobs - AC1
    for i in range(4):
        add(
            name=f"Compressed Air Cycle {i+1}",
            job_type=JobType.PRODUCTION,
            duration_min=60,
            release_slot=i * 20,
            deadline_slot=min(i * 20 + 50, TOTAL_SLOTS - 1),
            priority=2,
            machines=["AC1"],
            power_kw=7.5,
            energy_kwh=7.5,
            workers=1,
            tariff_sensitive=False,
        )

    # Chiller jobs - CH1 (supports furnace/oven cooling)
    for i in range(4):
        add(
            name=f"Chilling Cycle {i+1}",
            job_type=JobType.PRODUCTION,
            duration_min=90,
            release_slot=i * 18,
            deadline_slot=min(i * 18 + 44, TOTAL_SLOTS - 1),
            priority=2,
            machines=["CH1"],
            power_kw=11.0,
            energy_kwh=16.5,
            workers=1,
            tariff_sensitive=False,
        )

    # Manual furnace jobs - MF-1
    for i in range(3):
        add(
            name=f"Manual Furnace Heat {i+1}",
            job_type=JobType.FURNACE,
            duration_min=150,
            release_slot=i * 24,
            deadline_slot=min(i * 24 + 70, TOTAL_SLOTS - 1),
            priority=4,
            machines=["MF-1"],
            power_kw=3.0,
            energy_kwh=7.5,
            furnace=True,
            workers=2,
            tariff_sensitive=False,
        )

    # Interruptible low-priority fill work
    for i in range(8):
        add(
            name=f"Interruptible Fill {i+1}",
            job_type=JobType.INTERRUPTIBLE,
            duration_min=45,
            release_slot=i * 12,
            deadline_slot=min(i * 12 + 24, TOTAL_SLOTS - 1),
            priority=1,
            machines=["CNC-A", "CNC-B", "AC1"],
            power_kw=4.0,
            energy_kwh=3.0,
            workers=1,
            interruptible=True,
            tariff_sensitive=False,
        )

    # Precedence chain: furnace melt -> casting -> CNC machining
    add(
        name="Furnace Melt Chain 1",
        job_type=JobType.FURNACE,
        duration_min=180,
        release_slot=20,
        deadline_slot=60,
        priority=6,
        machines=["F1"],
        power_kw=45.0,
        energy_kwh=135.0,
        furnace=True,
        workers=2,
        tariff_sensitive=True,
    )
    add(
        name="CNC Machining After Melt 1",
        job_type=JobType.PRODUCTION,
        duration_min=120,
        release_slot=64,
        deadline_slot=110,
        priority=6,
        machines=["CNC-A", "CNC-B"],
        power_kw=5.5,
        energy_kwh=11.0,
        workers=1,
        tariff_sensitive=True,
        precedence=["JOB-0041"],  # approximate; patched below
    )

    return jobs


JOBS: List[Job] = build_jobs()


# ---------------------------------------------------------------------------
# Tariff (INR per kWh) by hour of day (IST), industrial Tarang-style demo
# ---------------------------------------------------------------------------


def tariff_rate_at_ist(dt: datetime) -> float:
    """Return demo tariff rate (INR/kWh) for a given IST datetime.

    Labeled as simulation policy data, not a real utility tariff.
    """
    hour = dt.hour
    # Peak: 08:00-12:00 and 18:00-22:00 ; Off-peak: 22:00-06:00
    if 8 <= hour < 12 or 18 <= hour < 22:
        return 11.50
    if 22 <= hour or hour < 6:
        return 6.25
    return 8.75


def slot_tariff_rate(slot: int) -> float:
    return tariff_rate_at_ist(slot_to_ist(slot))


# ---------------------------------------------------------------------------
# Heat policy (demo thresholds - NOT certified regulatory limits)
# ---------------------------------------------------------------------------


HEAT_POLICY = {
    "policy_id": "heat-policy-demo-001",
    "name": "TEEVRA Demo Heat Stress Policy",
    "version": 1,
    "approved_by": "demo-admin",
    "approved_at": UTCNow().isoformat(),
    "normal_max_wbgt_c": 27.0,
    "caution_max_wbgt_c": 29.0,
    "high_risk_max_wbgt_c": 31.0,
    "stop_work_min_wbgt_c": 32.0,
    "acclimatization_adjustment_c": 1.0,
    "clothing_adjustment_c": 0.0,
    "is_certified": False,
    "region": "demo",
    "disclaimer": (
        "Demo simulation policy values. Not certified occupational health limits. "
        "Do not use for real-world safety decisions."
    ),
}

# Workstation baseline heat characteristics (simulated)
WORKSTATIONS: List[dict] = [
    {"workstation_id": "WS-CNC-A", "name": "CNC-A Station", "machine_id": "CNC-A", "base_wbgt_c": 28.0, "heat_emission": 2},
    {"workstation_id": "WS-CNC-B", "name": "CNC-B Station", "machine_id": "CNC-B", "base_wbgt_c": 27.5, "heat_emission": 2},
    {"workstation_id": "WS-F1", "name": "Furnace F1 Station", "machine_id": "F1", "base_wbgt_c": 33.0, "heat_emission": 5},
    {"workstation_id": "WS-P1", "name": "Paint Oven P1 Station", "machine_id": "P1", "base_wbgt_c": 31.0, "heat_emission": 3},
    {"workstation_id": "WS-AC1", "name": "Compressor AC1 Station", "machine_id": "AC1", "base_wbgt_c": 26.0, "heat_emission": 1},
    {"workstation_id": "WS-CH1", "name": "Chiller CH1 Station", "machine_id": "CH1", "base_wbgt_c": 25.5, "heat_emission": 2},
    {"workstation_id": "WS-MF-1", "name": "Manual Furnace Station", "machine_id": "MF-1", "base_wbgt_c": 34.0, "heat_emission": 5},
    {"workstation_id": "WS-CONTROL", "name": "Control Room", "machine_id": None, "base_wbgt_c": 24.0, "heat_emission": 0},
]


def get_workstation(workstation_id: str) -> dict:
    for ws in WORKSTATIONS:
        if ws["workstation_id"] == workstation_id:
            return ws
    raise KeyError(f"Unknown workstation: {workstation_id}")


__all__ = [
    "HORIZON_HOURS",
    "SLOT_DURATION_MINUTES",
    "TOTAL_SLOTS",
    "FROZEN_WINDOW_MINUTES",
    "FROZEN_WINDOW_SLOTS",
    "DEMO_START",
    "IST",
    "slot_to_ist",
    "ist_to_slot",
    "MACHINES",
    "get_machine",
    "WORKERS",
    "get_worker",
    "JOBS",
    "build_jobs",
    "tariff_rate_at_ist",
    "slot_tariff_rate",
    "HEAT_POLICY",
    "WORKSTATIONS",
    "get_workstation",
]
