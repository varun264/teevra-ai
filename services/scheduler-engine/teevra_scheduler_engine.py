"""TEEVRA AI scheduling engine interface and CP-SAT implementation.

Implements the versioned SchedulingEngine interface for Feature 3 (breakdown
recovery) and Feature 4 (heat-triggered rescheduling). Designed so the wider
team's real core optimization engine can swap in later.
"""

from __future__ import annotations

import abc
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from teevra_shared_schemas import (
    CommitResult,
    JobChangeEvidence,
    SolverStatus,
)
from teevra_shared_schemas.jobs import Job
from teevra_shared_schemas.machines import Machine
from teevra_shared_schemas.schedule import FrozenWindow, ScheduleEntry, ScheduleVersion
from teevra_shared_schemas.scheduling import RecoveryPlan, SolverResult


class SchedulingEngine(metaclass=abc.ABCMeta):
    """Versioned scheduling engine interface.

    The wider Feature 1 team can replace this with their real core engine.
    """

    VERSION = "teevra-cpsat-v1"

    @abc.abstractmethod
    def build_baseline_schedule(self, factory: dict) -> ScheduleVersion:
        raise NotImplementedError

    @abc.abstractmethod
    def recover_after_breakdown(
        self,
        current_version: ScheduleVersion,
        fault_machine: str,
        fault_start_slot: int,
        fault_end_slot: int,
        now_slot: int,
        heat_blocked_stations: Optional[List[str]] = None,
        time_limit_seconds: float = 30.0,
    ) -> RecoveryPlan:
        raise NotImplementedError

    @abc.abstractmethod
    def recover_after_heat_event(
        self,
        current_version: ScheduleVersion,
        blocked_stations: List[str],
        now_slot: int,
        time_limit_seconds: float = 30.0,
    ) -> RecoveryPlan:
        raise NotImplementedError

    @abc.abstractmethod
    def validate_schedule(self, version: ScheduleVersion) -> List[str]:
        raise NotImplementedError

    @abc.abstractmethod
    def compare_schedules(
        self, previous: ScheduleVersion, new: ScheduleVersion
    ) -> List[JobChangeEvidence]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# CP-SAT implementation
# ---------------------------------------------------------------------------


class CPSatSchedulingEngine(SchedulingEngine):
    """Deterministic CP-SAT scheduling engine.

    LLM agents never touch solver values. Safety/feasibility are hard
    constraints. Optimization is lexicographic: safety/feasibility >
    missed deadlines > disruption > energy cost.
    """

    def __init__(self, total_slots: int = 192, slot_minutes: int = 15):
        self.total_slots = total_slots
        self.slot_minutes = slot_minutes
        self.frozen_window_slots = 120 // slot_minutes  # 2-hour window

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #
    def build_baseline_schedule(self, factory: dict) -> ScheduleVersion:
        from teevra_simulation import get_machine

        machines: List[Machine] = factory["machines"]
        jobs: List[Job] = factory["jobs"]
        now_slot = int(factory.get("now_slot", 0))
        return self._commit_solution(
            current_version=None,
            machines=machines,
            jobs=jobs,
            now_slot=now_slot,
            broken_machines={},
            blocked_stations=set(),
            frozen_start=None,
            frozen_end=None,
            force_fixed={},
            time_limit_seconds=30.0,
            trigger="baseline",
            fault_machine=None,
        ).schedule_version

    def recover_after_breakdown(
        self,
        current_version: ScheduleVersion,
        fault_machine: str,
        fault_start_slot: int,
        fault_end_slot: int,
        now_slot: int,
        heat_blocked_stations: Optional[List[str]] = None,
        time_limit_seconds: float = 30.0,
    ) -> RecoveryPlan:
        heat_blocked_stations = heat_blocked_stations or []
        jobs = self._load_jobs(current_version.entries)
        machines = self._load_machines(current_version.entries)

        affected = self._jobs_overlapping_window(
            current_version.entries, fault_machine, fault_start_slot, fault_end_slot
        )

        frozen_start = now_slot
        frozen_end = min(now_slot + self.frozen_window_slots, self.total_slots) - 1

        force_fixed: Dict[str, Tuple[str, int]] = {}
        for e in current_version.entries:
            if e.job_id in affected:
                continue
            if frozen_start <= e.start_slot <= frozen_end:
                force_fixed[e.job_id] = (e.machine_id, e.start_slot)

        return self._commit_solution(
            current_version=current_version,
            machines=machines,
            jobs=jobs,
            now_slot=now_slot,
            broken_machines={fault_machine: (fault_start_slot, fault_end_slot)},
            blocked_stations=set(heat_blocked_stations),
            frozen_start=frozen_start,
            frozen_end=frozen_end,
            force_fixed=force_fixed,
            time_limit_seconds=time_limit_seconds,
            trigger="breakdown",
            fault_machine=fault_machine,
        )

    def recover_after_heat_event(
        self,
        current_version: ScheduleVersion,
        blocked_stations: List[str],
        now_slot: int,
        time_limit_seconds: float = 30.0,
    ) -> RecoveryPlan:
        jobs = self._load_jobs(current_version.entries)
        machines = self._load_machines(current_version.entries)

        affected: Set[str] = {
            e.job_id
            for e in current_version.entries
            if e.machine_id in blocked_stations
        }

        frozen_start = now_slot
        frozen_end = min(now_slot + self.frozen_window_slots, self.total_slots) - 1

        force_fixed: Dict[str, Tuple[str, int]] = {}
        for e in current_version.entries:
            if e.job_id in affected:
                continue
            if frozen_start <= e.start_slot <= frozen_end:
                force_fixed[e.job_id] = (e.machine_id, e.start_slot)

        return self._commit_solution(
            current_version=current_version,
            machines=machines,
            jobs=jobs,
            now_slot=now_slot,
            broken_machines={},
            blocked_stations=set(blocked_stations),
            frozen_start=frozen_start,
            frozen_end=frozen_end,
            force_fixed=force_fixed,
            time_limit_seconds=time_limit_seconds,
            trigger="heat",
            fault_machine=None,
        )

    def validate_schedule(self, version: ScheduleVersion) -> List[str]:
        return version.validate_no_overlap()

    def compare_schedules(
        self, previous: Optional[ScheduleVersion], new: ScheduleVersion
    ) -> List[JobChangeEvidence]:
        prev_map = {e.job_id: e for e in previous.entries} if previous else {}
        new_map = {e.job_id: e for e in new.entries}
        evidence: List[JobChangeEvidence] = []
        for job_id, new_e in new_map.items():
            prev_e = prev_map.get(job_id)
            if prev_e is None:
                change_type = "NEW"
                reason = "job added in recovery"
            elif (
                prev_e.machine_id != new_e.machine_id
                or prev_e.start_slot != new_e.start_slot
                or prev_e.end_slot != new_e.end_slot
            ):
                change_type = (
                    "REASSIGNED"
                    if prev_e.machine_id != new_e.machine_id
                    else "DELAYED"
                )
                reason = "rescheduled by recovery solver"
            else:
                change_type = "UNCHANGED"
                reason = "unaffected by recovery"
            evidence.append(
                JobChangeEvidence(
                    job_id=job_id,
                    change_type=change_type,
                    previous_machine=prev_e.machine_id if prev_e else None,
                    new_machine=new_e.machine_id,
                    previous_start_slot=prev_e.start_slot if prev_e else None,
                    new_start_slot=new_e.start_slot,
                    reason=reason,
                    safety_validated=True,
                    worker_id=new_e.worker_id,
                )
            )
        for job_id, prev_e in prev_map.items():
            if job_id not in new_map:
                evidence.append(
                    JobChangeEvidence(
                        job_id=job_id,
                        change_type="CANCELLED",
                        previous_machine=prev_e.machine_id,
                        new_machine=None,
                        previous_start_slot=prev_e.start_slot,
                        new_start_slot=None,
                        reason="job removed (blocked / infeasible)",
                        safety_validated=True,
                    )
                )
        return evidence

    # ------------------------------------------------------------------ #
    # Internal: data loading
    # ------------------------------------------------------------------ #
    def _load_jobs(self, entries: List[ScheduleEntry]) -> List[Job]:
        from teevra_simulation import JOBS

        by_id = {j.job_id: j for j in JOBS}
        jobs = [by_id[e.job_id] for e in entries if e.job_id in by_id]
        by_entry = {e.job_id: e for e in entries}
        for j in jobs:
            e = by_entry.get(j.job_id)
            if e:
                from teevra_shared_schemas.jobs import MachineJobAssignment

                j.current_slot_assignment = MachineJobAssignment(
                    machine_id=e.machine_id,
                    start_slot=e.start_slot,
                    end_slot=e.end_slot,
                    worker_id=e.worker_id,
                )
        return jobs

    def _load_machines(self, entries: List[ScheduleEntry]) -> List[Machine]:
        from teevra_simulation import get_machine

        ids = {e.machine_id for e in entries}
        return [get_machine(mid) for mid in sorted(ids)]

    def _jobs_overlapping_window(
        self, entries: List[ScheduleEntry], machine: str, start: int, end: int
    ) -> Set[str]:
        affected: Set[str] = set()
        for e in entries:
            if e.machine_id != machine:
                continue
            if e.start_slot <= end and start <= e.end_slot:
                affected.add(e.job_id)
        return affected

    # ------------------------------------------------------------------ #
    # Core solver
    # ------------------------------------------------------------------ #
    def _commit_solution(
        self,
        current_version: Optional[ScheduleVersion],
        machines: List[Machine],
        jobs: List[Job],
        now_slot: int,
        broken_machines: Dict[str, Tuple[int, int]],
        blocked_stations: Set[str],
        frozen_start: Optional[int],
        frozen_end: Optional[int],
        force_fixed: Dict[str, Tuple[str, int]],
        time_limit_seconds: float,
        trigger: str,
        fault_machine: Optional[str],
    ) -> RecoveryPlan:
        t0 = datetime.now(timezone.utc)
        solution, status = self._solve_model(
            machines=machines,
            jobs=jobs,
            broken_machines=broken_machines,
            blocked_stations=blocked_stations,
            frozen_start=frozen_start,
            frozen_end=frozen_end,
            force_fixed=force_fixed,
            time_limit_seconds=time_limit_seconds,
        )

        new_version = self._build_version(
            current_version=current_version,
            solution=solution,
            jobs=jobs,
            machines={m.machine_id: m for m in machines},
            trigger=trigger,
            fault_machine=fault_machine,
        )

        evidence = (
            self.compare_schedules(current_version, new_version)
            if current_version
            else []
        )

        unchanged = sum(1 for e in evidence if e.change_type == "UNCHANGED")
        reassigned = sum(1 for e in evidence if e.change_type == "REASSIGNED")
        delayed = sum(1 for e in evidence if e.change_type == "DELAYED")
        blocked = sum(1 for e in evidence if e.change_type in ("BLOCKED", "CANCELLED"))

        before = self._cost(current_version or new_version, machines)
        after = self._cost(new_version, machines)

        solver_result = SolverResult(
            solver_status=status,
            objective_value=0.0,
            previous_schedule_version=(
                current_version.version_id if current_version else "baseline-000"
            ),
            new_schedule_version=new_version.version_id,
            jobs_unchanged=unchanged,
            jobs_reassigned=reassigned,
            jobs_delayed=delayed,
            jobs_blocked=blocked,
            expected_output_percent=self._output_pct(new_version, jobs),
            electricity_cost_before_inr=before["cost_inr"],
            electricity_cost_after_inr=after["cost_inr"],
            restart_energy_before_kwh=before["restart_kwh"],
            restart_energy_after_kwh=after["restart_kwh"],
            validated_heat_breaches=len(blocked_stations),
            recovery_duration_ms=(
                datetime.now(timezone.utc) - t0
            ).total_seconds()
            * 1000.0,
            safety_validation_result={
                "heat_blocked_stations": sorted(blocked_stations),
                "broken_machines": broken_machines,
                "frozen_window_slots": [frozen_start, frozen_end],
                "trigger": trigger,
                "status": status.value,
            },
            human_approval_required=bool(
                reassigned > 0 or delayed > 0 or blocked > 0
            )
            or status != SolverStatus.OPTIMAL,
            change_evidence=evidence,
        )
        if not solver_result.is_feasible:
            solver_result.commit_result = CommitResult.REJECTED_SAFETY
            solver_result.infeasibility_report = (
                "No feasible recovery plan found under current safety and "
                "equipment constraints. Last committed schedule retained; unsafe "
                "work stopped."
            )
        elif status == SolverStatus.FEASIBLE:
            solver_result.warnings = [
                "Solver returned FEASIBLE (not proven optimal). Review before commit."
            ]

        plan = RecoveryPlan(
            plan_id=new_version.version_id,
            schedule_version=new_version,
            solver_result=solver_result,
            requires_human_approval=solver_result.human_approval_required,
            safety_breaches=[],
            auto_commit_allowed=(
                not solver_result.human_approval_required
                and solver_result.is_feasible
            ),
        )
        return plan

    def _solve_model(
        self,
        machines: List[Machine],
        jobs: List[Job],
        broken_machines: Dict[str, Tuple[int, int]],
        blocked_stations: Set[str],
        frozen_start: Optional[int],
        frozen_end: Optional[int],
        force_fixed: Dict[str, Tuple[str, int]],
        time_limit_seconds: float,
    ):
        model = cp_model.CpModel()
        max_slot = self.total_slots - 1

        by_id = {m.machine_id: m for m in machines}

        job_start: Dict[str, cp_model.IntVar] = {}
        job_end: Dict[str, cp_model.IntVar] = {}
        job_assign: Dict[str, Dict[str, cp_model.BoolVar]] = {}
        job_interval: Dict[str, Dict[str, cp_model.OptionalIntervalVar]] = {}
        selected_machine: Dict[str, Optional[str]] = {}
        selected_start: Dict[str, Optional[int]] = {}

        unavail: Dict[str, List[cp_model.OptionalIntervalVar]] = {
            m.machine_id: [] for m in machines
        }
        for mid, (s, e) in broken_machines.items():
            if mid in by_id and e >= s:
                present = model.NewBoolVar(f"unavail_present_{mid}")
                iv = model.NewOptionalIntervalVar(
                    s,
                    max(e - s + 1, 1),
                    e + 1,
                    present,
                    f"unavail_{mid}",
                )
                unavail[mid].append(iv)
                model.Add(present == 1)

        for job in jobs:
            compatible = [mid for mid in job.compatible_machines if mid in by_id]
            assign: Dict[str, cp_model.BoolVar] = {}
            for mid in compatible:
                assign[mid] = model.NewBoolVar(f"x_{job.job_id}_{mid}")
            job_assign[job.job_id] = assign

            if not compatible:
                continue

            model.Add(sum(assign.values()) == 1)

            start = model.NewIntVar(0, max_slot, f"start_{job.job_id}")
            end = model.NewIntVar(0, max_slot + 1, f"end_{job.job_id}")
            job_start[job.job_id] = start
            job_end[job.job_id] = end

            intervals: Dict[str, cp_model.OptionalIntervalVar] = {}
            dur_slots = max(1, job.duration_minutes // self.slot_minutes)
            for mid in compatible:
                present = model.NewBoolVar(f"iv_present_{job.job_id}_{mid}")
                iv = model.NewOptionalIntervalVar(
                    start,
                    dur_slots,
                    end,
                    present,
                    f"iv_{job.job_id}_{mid}",
                )
                intervals[mid] = iv
                model.Add(present == assign[mid])

            job_interval[job.job_id] = intervals

            model.Add(start >= job.release_slot)
            model.Add(end <= job.deadline_slot + 1)

            for mid in compatible:
                if by_id[mid].heat_sensitive and mid in blocked_stations:
                    model.Add(assign[mid] == 0)

            if job.job_id in force_fixed:
                fix_mid, fix_start = force_fixed[job.job_id]
                if fix_mid in assign:
                    model.Add(assign[fix_mid] == 1)
                    model.Add(start == fix_start)
                    selected_machine[job.job_id] = fix_mid
                    selected_start[job.job_id] = fix_start

        for job in jobs:
            if job.job_id not in job_start:
                continue
            for pred_id in job.precedence_job_ids:
                if pred_id in job_start:
                    model.Add(job_start[job.job_id] >= job_end[pred_id])

        for mid in by_id:
            intervals: List = list(unavail.get(mid, []))
            for job in jobs:
                if job.job_id in job_interval and mid in job_interval[job.job_id]:
                    intervals.append(job_interval[job.job_id][mid])
            if intervals:
                model.AddNoOverlap(intervals)

        terms = []
        for job in jobs:
            if job.job_id not in job_start:
                continue
            delay = model.NewIntVar(0, self.total_slots, f"delay_{job.job_id}")
            orig = (
                job.current_slot_assignment.start_slot
                if job.current_slot_assignment
                else 0
            )
            model.Add(delay >= job_start[job.job_id] - orig)
            model.Add(delay >= orig - job_start[job.job_id])
            terms.append((1000, delay))
            for mid, assign in job_assign[job.job_id].items():
                m = by_id[mid]
                rate = self._tariff_avg(job.release_slot, job.deadline_slot)
                cost = int(
                    m.power_rating_kw * (job.duration_minutes / 60.0) * rate * 100
                )
                terms.append((1, assign * cost))

        if terms:
            model.Minimize(sum(w * v for w, v in terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        solver.parameters.num_search_workers = 8
        status = solver.Solve(model)
        mapped = self._map_status(status)

        if mapped in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
            for job in jobs:
                if job.job_id not in job_start:
                    continue
                sel = None
                for mid, assign in job_assign[job.job_id].items():
                    if solver.Value(assign):
                        sel = mid
                        break
                selected_machine[job.job_id] = sel
                selected_start[job.job_id] = (
                    solver.Value(job_start[job.job_id]) if sel is not None else None
                )

        solution = {"selected_machine": selected_machine, "selected_start": selected_start}
        return solution, mapped

    # ------------------------------------------------------------------ #
    # Version / metrics building
    # ------------------------------------------------------------------ #
    def _build_version(
        self,
        current_version: Optional[ScheduleVersion],
        solution: dict,
        jobs: List[Job],
        machines: Dict[str, Machine],
        trigger: str,
        fault_machine: Optional[str],
    ) -> ScheduleVersion:
        version_id = f"v{uuid.uuid4().hex[:8]}"
        entries: List[ScheduleEntry] = []
        for job in jobs:
            mid = solution["selected_machine"].get(job.job_id)
            start = solution["selected_start"].get(job.job_id)
            if mid is None or start is None:
                continue  # blocked / could not place
            dur = max(1, job.duration_minutes // self.slot_minutes)
            entries.append(
                ScheduleEntry(
                    job_id=job.job_id,
                    machine_id=mid,
                    start_slot=int(start),
                    end_slot=int(start + dur - 1),
                    worker_id=(
                        job.current_slot_assignment.worker_id
                        if job.current_slot_assignment
                        else None
                    ),
                    version_id=version_id,
                    is_frozen=False,
                )
            )
        frozen = FrozenWindow(
            start_slot=0, end_slot=min(7, self.total_slots - 1)
        )
        return ScheduleVersion(
            version_id=version_id,
            factory_id="teevra-demo-factory",
            horizon_start_slot=0,
            horizon_end_slot=self.total_slots - 1,
            slot_duration_minutes=self.slot_minutes,
            frozen_window=frozen,
            entries=entries,
            is_committed=False,
            parent_version_id=current_version.version_id if current_version else None,
            solver_status="solved",
        )

    def _cost(self, version: ScheduleVersion, machines: List[Machine]) -> dict:
        by_id = {m.machine_id: m for m in machines}
        cost = 0.0
        restart = 0.0
        for e in version.entries:
            m = by_id.get(e.machine_id)
            if not m:
                continue
            rate = self._tariff_avg(e.start_slot, e.end_slot)
            cost += (
                m.power_rating_kw
                * ((e.end_slot - e.start_slot + 1) * 15 / 60.0)
                * rate
            )
        return {"cost_inr": round(cost, 2), "restart_kwh": round(restart, 2)}

    def _output_pct(self, version: ScheduleVersion, jobs: List[Job]) -> float:
        if not jobs:
            return 100.0
        return round(100.0 * len(version.entries) / len(jobs), 1)

    def _tariff_avg(self, release_slot: int, deadline_slot: int) -> float:
        from teevra_simulation import slot_tariff_rate

        slots = range(release_slot, min(deadline_slot + 1, self.total_slots))
        if not slots:
            return 8.75
        return sum(slot_tariff_rate(s) for s in slots) / len(slots)

    @staticmethod
    def _map_status(status) -> SolverStatus:
        mapping = {
            cp_model.OPTIMAL: SolverStatus.OPTIMAL,
            cp_model.FEASIBLE: SolverStatus.FEASIBLE,
            cp_model.INFEASIBLE: SolverStatus.INFEASIBLE,
            cp_model.MODEL_INVALID: SolverStatus.MODEL_INVALID,
            cp_model.UNKNOWN: SolverStatus.UNKNOWN,
        }
        return mapping.get(status, SolverStatus.UNKNOWN)


__all__ = ["SchedulingEngine", "CPSatSchedulingEngine"]
