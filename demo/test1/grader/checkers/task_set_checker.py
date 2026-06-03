"""Checker for the generated periodic task set."""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import ceil, gcd
from typing import Any

from ..models import CheckReport, SubmissionData


@dataclass(frozen=True, slots=True)
class PeriodicTask:
    task_id: str
    r: int
    p: int
    e: int
    d: int
    w: int
    preempt: int


class TaskSetChecker:
    """Validate only output/task_set.json periodic task set rules."""

    CHECKER_NAME = "Task Set Checker"
    REQUIRED_FIELDS = ("r", "p", "e", "d", "w", "preempt")
    HORIZON = 72
    TASK_ID_PATTERN = re.compile(r"^p[1-9]\d*$")

    def check(self, submission_data: SubmissionData) -> CheckReport:
        report = CheckReport(checker_name=self.CHECKER_NAME)
        task_set = submission_data.task_set

        if task_set is None:
            report.add("FAIL", "task_set_available", "task_set.json was not loaded")
            return report

        periodic = task_set.get("periodic")
        if not isinstance(periodic, dict):
            report.add("FAIL", "periodic_available", "task_set.periodic must be an object")
            return report

        tasks = self._parse_periodic_tasks(periodic, report)
        self._check_task_count(tasks, report)
        self._check_expanded_jobs(tasks, report)
        self._check_parameter_ranges(tasks, report)
        self._check_period_diversity(tasks, report)
        self._check_execution_time(tasks, report)
        self._check_energy_demand(tasks, report)
        self._check_workload_density(tasks, report)
        self._check_deadline_pressure(tasks, report)
        self._check_non_preemptive(tasks, report)
        self._check_frame_size(tasks, report)
        return report

    def _parse_periodic_tasks(self, periodic: dict[str, Any], report: CheckReport) -> list[PeriodicTask]:
        tasks: list[PeriodicTask] = []

        for task_id, raw_task in periodic.items():
            if not isinstance(task_id, str) or self.TASK_ID_PATTERN.fullmatch(task_id) is None:
                report.add(
                    "FAIL",
                    "periodic_key_format",
                    f"{task_id}: periodic task key must use standard format p1, p2, ...",
                    {"task_id": task_id},
                )

            if not isinstance(raw_task, dict):
                report.add(
                    "FAIL",
                    "periodic_fields",
                    f"{task_id}: periodic task must be an object",
                    {"task_id": task_id},
                )
                continue

            missing_fields = [field for field in self.REQUIRED_FIELDS if field not in raw_task]
            if missing_fields:
                report.add(
                    "FAIL",
                    "periodic_fields",
                    f"{task_id}: missing required fields: {', '.join(missing_fields)}",
                    {"task_id": task_id, "missing_fields": missing_fields},
                )
                continue

            converted: dict[str, int] = {}
            invalid_fields: list[str] = []
            for field in self.REQUIRED_FIELDS:
                value = self._to_int(raw_task[field])
                if value is None:
                    invalid_fields.append(field)
                else:
                    converted[field] = value

            if invalid_fields:
                report.add(
                    "FAIL",
                    "periodic_fields",
                    f"{task_id}: fields must be integer-valued: {', '.join(invalid_fields)}",
                    {"task_id": task_id, "invalid_fields": invalid_fields},
                )
                continue

            tasks.append(
                PeriodicTask(
                    task_id=task_id,
                    r=converted["r"],
                    p=converted["p"],
                    e=converted["e"],
                    d=converted["d"],
                    w=converted["w"],
                    preempt=converted["preempt"],
                )
            )

        if len(tasks) == len(periodic):
            report.add("PASS", "periodic_fields", "all periodic tasks have required integer-valued fields")
        if not any(issue.check_id == "periodic_key_format" for issue in report.issues):
            report.add("PASS", "periodic_key_format", "all periodic task keys use standard format p1, p2, ...")
        return tasks

    def _to_int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None

    def _check_task_count(self, tasks: list[PeriodicTask], report: CheckReport) -> None:
        task_count = len(tasks)
        if 6 <= task_count <= 10:
            report.add("PASS", "task_count", f"periodic task count = {task_count}", {"task_count": task_count})
        else:
            report.add(
                "FAIL",
                "task_count",
                f"periodic task count = {task_count}, expected 6..10",
                {"task_count": task_count, "expected_min": 6, "expected_max": 10},
            )

    def _check_expanded_jobs(self, tasks: list[PeriodicTask], report: CheckReport) -> None:
        expanded_jobs = sum(self._expanded_job_count(task) for task in tasks if task.p > 0)
        if expanded_jobs > 30:
            report.add(
                "PASS",
                "expanded_jobs",
                f"expanded periodic jobs = {expanded_jobs}",
                {"expanded_jobs": expanded_jobs, "horizon": self.HORIZON},
            )
        else:
            report.add(
                "FAIL",
                "expanded_jobs",
                f"expanded periodic jobs = {expanded_jobs}, expected > 30",
                {"expanded_jobs": expanded_jobs, "expected_gt": 30, "horizon": self.HORIZON},
            )

    def _expanded_job_count(self, task: PeriodicTask) -> int:
        if task.p <= 0 or task.r > self.HORIZON:
            return 0
        return ((self.HORIZON - task.r) // task.p) + 1

    def _check_parameter_ranges(self, tasks: list[PeriodicTask], report: CheckReport) -> None:
        failures: list[dict[str, Any]] = []
        for task in tasks:
            task_failures: list[str] = []
            if not (1 <= task.r <= task.p):
                task_failures.append("1 <= r <= p")
            if not (6 <= task.p <= 24):
                task_failures.append("6 <= p <= 24")
            if not (1 <= task.e <= 4):
                task_failures.append("1 <= e <= 4")
            if not (task.e <= task.d <= task.p):
                task_failures.append("e <= d <= p")
            if not (6 <= task.w <= 18):
                task_failures.append("6 <= w <= 18")
            if task_failures:
                failures.append({"task_id": task.task_id, "failed_rules": task_failures})

        if failures:
            report.add(
                "FAIL",
                "parameter_ranges",
                f"{len(failures)} periodic task(s) violate parameter ranges",
                {"failures": failures},
            )
        else:
            report.add("PASS", "parameter_ranges", "all periodic task parameters are within required ranges")

    def _check_period_diversity(self, tasks: list[PeriodicTask], report: CheckReport) -> None:
        distinct_periods = sorted({task.p for task in tasks})
        if len(distinct_periods) >= 3:
            report.add(
                "PASS",
                "period_diversity",
                f"distinct periods = {distinct_periods}",
                {"distinct_periods": distinct_periods},
            )
        else:
            report.add(
                "FAIL",
                "period_diversity",
                f"distinct period count = {len(distinct_periods)}, expected >= 3",
                {"distinct_periods": distinct_periods, "expected_min": 3},
            )

    def _check_execution_time(self, tasks: list[PeriodicTask], report: CheckReport) -> None:
        e2_count = sum(1 for task in tasks if task.e == 2)
        e3_plus_count = sum(1 for task in tasks if task.e >= 3)
        if e2_count >= 2 and e3_plus_count >= 1:
            report.add(
                "PASS",
                "execution_time",
                f"e=2 tasks = {e2_count}, e>=3 tasks = {e3_plus_count}",
                {"e2_count": e2_count, "e3_plus_count": e3_plus_count},
            )
        else:
            report.add(
                "FAIL",
                "execution_time",
                f"e=2 tasks = {e2_count} expected >= 2; e>=3 tasks = {e3_plus_count} expected >= 1",
                {"e2_count": e2_count, "e3_plus_count": e3_plus_count},
            )

    def _check_energy_demand(self, tasks: list[PeriodicTask], report: CheckReport) -> None:
        high_energy_count = sum(1 for task in tasks if task.w >= 14)
        if high_energy_count >= 2:
            report.add(
                "PASS",
                "energy_demand",
                f"w>=14 tasks = {high_energy_count}",
                {"high_energy_count": high_energy_count},
            )
        else:
            report.add(
                "FAIL",
                "energy_demand",
                f"w>=14 tasks = {high_energy_count}, expected >= 2",
                {"high_energy_count": high_energy_count, "expected_min": 2},
            )

    def _check_workload_density(self, tasks: list[PeriodicTask], report: CheckReport) -> None:
        density = sum(task.e / task.p for task in tasks if task.p != 0)
        if density >= 0.7:
            report.add("PASS", "workload_density", f"DW = {density:.3f}", {"density": density})
        else:
            report.add(
                "FAIL",
                "workload_density",
                f"DW = {density:.3f}, expected >= 0.7",
                {"density": density, "expected_min": 0.7},
            )

    def _check_deadline_pressure(self, tasks: list[PeriodicTask], report: CheckReport) -> None:
        task_count = len(tasks)
        required_count = ceil(0.2 * task_count)
        tight_deadline_count = sum(1 for task in tasks if task.d == task.e)
        if tight_deadline_count >= required_count:
            report.add(
                "PASS",
                "deadline_pressure",
                f"d=e tasks = {tight_deadline_count}, expected >= {required_count}",
                {"tight_deadline_count": tight_deadline_count, "expected_min": required_count},
            )
        else:
            report.add(
                "FAIL",
                "deadline_pressure",
                f"d=e tasks = {tight_deadline_count}, expected >= {required_count}",
                {"tight_deadline_count": tight_deadline_count, "expected_min": required_count},
            )

    def _check_non_preemptive(self, tasks: list[PeriodicTask], report: CheckReport) -> None:
        non_preemptive_count = sum(1 for task in tasks if task.e != 1 and task.preempt == 0)
        if non_preemptive_count >= 2:
            report.add(
                "PASS",
                "non_preemptive",
                f"non-preemptive e!=1 tasks = {non_preemptive_count}",
                {"non_preemptive_count": non_preemptive_count},
            )
        else:
            report.add(
                "FAIL",
                "non_preemptive",
                f"non-preemptive e!=1 tasks = {non_preemptive_count}, expected >= 2",
                {"non_preemptive_count": non_preemptive_count, "expected_min": 2},
            )

    def _check_frame_size(self, tasks: list[PeriodicTask], report: CheckReport) -> None:
        if not tasks:
            report.add("FAIL", "frame_size", "no valid periodic tasks available for frame size check")
            return

        max_execution_time = max(task.e for task in tasks)
        frame_candidates = [f for f in range(1, self.HORIZON + 1) if self.HORIZON % f == 0]
        legal_frame_sizes = [
            f
            for f in frame_candidates
            if f >= max_execution_time
            and all(2 * f - gcd(f, task.p) <= task.d for task in tasks)
        ]

        if legal_frame_sizes:
            report.add(
                "PASS",
                "frame_size",
                f"legal frame sizes = {legal_frame_sizes}",
                {"legal_frame_sizes": legal_frame_sizes},
            )
        else:
            report.add(
                "FAIL",
                "frame_size",
                "no legal frame size exists",
                {"legal_frame_sizes": [], "max_execution_time": max_execution_time},
            )
