"""Basic periodic job schedule checker."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..models import CheckReport, SubmissionData


@dataclass(slots=True)
class PeriodicJob:
    job_id: str
    compatibility_job_id: str
    task_id: str
    instance_index: int
    release: int
    deadline_window_end: int
    execution_time: int
    energy_demand: int
    preempt: int
    executions: list[tuple[int, float, str]] = field(default_factory=list)


class ScheduleBasicChecker:
    """Check basic periodic job scheduling logic only."""

    checker_name = "Schedule Basic Checker"
    HORIZON = 72
    TOLERANCE = 1e-6
    SAMPLE_LIMIT = 10
    REQUIRED_TASK_FIELDS = ("r", "p", "e", "d", "w", "preempt")
    REQUIRED_SCHEDULE_FIELDS = ("t", "P", "k", "sell", "soc", "missed_aperiodic", "rejected_sporadic")
    COMPATIBILITY_JOB_ID_PATTERN = re.compile(r"^(?P<task_id>.+)_j(?P<instance_index>[1-9]\d*)$")

    def check(self, submission_data: SubmissionData) -> CheckReport:
        report = CheckReport(checker_name=self.checker_name)
        schedule_result = submission_data.schedule_result

        self._check_schedule_length(schedule_result, report)
        self._check_schedule_time_index(schedule_result, report)
        self._check_schedule_entry_schema(schedule_result, report)

        jobs = self._expand_periodic_jobs(submission_data.task_set, report)
        self._collect_executions(schedule_result, jobs, report)

        self._check_release_time(jobs, report)
        self._check_deadline(jobs, report)
        self._check_execution_complete(jobs, report)
        self._check_energy_demand(jobs, report)
        self._check_non_preemptive_contiguity(jobs, report)
        return report

    def _check_schedule_length(self, schedule_result: list[Any] | None, report: CheckReport) -> None:
        if not isinstance(schedule_result, list):
            report.add("FAIL", "schedule_length", "schedule_result must be a list")
            return

        actual = len(schedule_result)
        if actual == self.HORIZON:
            report.add("PASS", "schedule_length", "schedule_result has 72 entries", {"actual": actual})
        else:
            report.add(
                "FAIL",
                "schedule_length",
                f"schedule_result has {actual} entries, expected 72",
                {"actual": actual, "expected": self.HORIZON},
            )

    def _check_schedule_time_index(self, schedule_result: list[Any] | None, report: CheckReport) -> None:
        if not isinstance(schedule_result, list):
            report.add("FAIL", "schedule_time_index", "schedule_result must be a list")
            return

        times: list[int] = []
        invalid_entries: list[int] = []
        for index, entry in enumerate(schedule_result):
            if not isinstance(entry, dict):
                invalid_entries.append(index)
                continue
            t_value = self._to_int(entry.get("t"))
            if t_value is None:
                invalid_entries.append(index)
            else:
                times.append(t_value)

        expected_times = set(range(1, self.HORIZON + 1))
        actual_times = set(times)
        missing = sorted(expected_times - actual_times)
        duplicate = sorted({t for t in times if times.count(t) > 1})
        extra = sorted(actual_times - expected_times)

        if not invalid_entries and not missing and not duplicate and not extra:
            report.add("PASS", "schedule_time_index", "t indexes are exactly 1..72")
        else:
            report.add(
                "FAIL",
                "schedule_time_index",
                "t indexes must be exactly 1..72 with no duplicates",
                {
                    "missing": missing[: self.SAMPLE_LIMIT],
                    "duplicates": duplicate[: self.SAMPLE_LIMIT],
                    "extra": extra[: self.SAMPLE_LIMIT],
                    "invalid_entries": invalid_entries[: self.SAMPLE_LIMIT],
                },
            )

    def _check_schedule_entry_schema(self, schedule_result: list[Any] | None, report: CheckReport) -> None:
        if not isinstance(schedule_result, list):
            report.add("FAIL", "schedule_entry_schema", "schedule_result must be a list")
            return

        violations: list[dict[str, Any]] = []
        for index, entry in enumerate(schedule_result):
            if not isinstance(entry, dict):
                violations.append({"index": index, "reason": "entry_not_object"})
                continue
            missing = [field for field in self.REQUIRED_SCHEDULE_FIELDS if field not in entry]
            if missing:
                violations.append(
                    {
                        "index": index,
                        "t": entry.get("t"),
                        "reason": "missing_required_fields",
                        "missing_fields": missing,
                    }
                )
            for field in ("P", "k", "soc"):
                if field in entry and not isinstance(entry[field], dict):
                    violations.append({"index": index, "field": field, "reason": "field_not_object"})
            for field in ("missed_aperiodic", "rejected_sporadic"):
                if field in entry and not isinstance(entry[field], list):
                    violations.append({"index": index, "field": field, "reason": "field_not_list"})

        if violations:
            report.add(
                "FAIL",
                "schedule_entry_schema",
                f"schedule entry schema violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "schedule_entry_schema", "all schedule entries have required Level 1 fields")

    def _expand_periodic_jobs(self, task_set: dict[str, Any] | None, report: CheckReport) -> dict[str, PeriodicJob]:
        if not isinstance(task_set, dict) or not isinstance(task_set.get("periodic"), dict):
            report.add("FAIL", "periodic_jobs_expanded", "task_set.periodic is not available")
            return {}

        jobs: dict[str, PeriodicJob] = {}
        invalid_tasks: list[str] = []
        periodic = task_set["periodic"]

        for task_id, raw_task in periodic.items():
            task = self._parse_task(task_id, raw_task)
            if task is None:
                invalid_tasks.append(str(task_id))
                continue

            r, p, e, d, w, preempt = task
            instance_index = 1
            release = r
            while release <= self.HORIZON:
                task_id_str = str(task_id)
                job_id = f"{task_id_str}_{instance_index}"
                jobs[job_id] = PeriodicJob(
                    job_id=job_id,
                    compatibility_job_id=f"{task_id_str}_j{instance_index}",
                    task_id=task_id_str,
                    instance_index=instance_index,
                    release=release,
                    deadline_window_end=min(release + d - 1, self.HORIZON),
                    execution_time=e,
                    energy_demand=w,
                    preempt=preempt,
                )
                instance_index += 1
                release += p

        if invalid_tasks:
            report.add(
                "FAIL",
                "periodic_jobs_expanded",
                f"failed to expand periodic tasks: {', '.join(invalid_tasks[:self.SAMPLE_LIMIT])}",
                {
                    "count": len(invalid_tasks),
                    "samples": invalid_tasks[: self.SAMPLE_LIMIT],
                    "expanded_job_count": len(jobs),
                },
            )
        else:
            report.add(
                "PASS",
                "periodic_jobs_expanded",
                f"expanded periodic jobs = {len(jobs)}",
                {"expanded_job_count": len(jobs)},
            )

        return jobs

    def _parse_task(self, task_id: Any, raw_task: Any) -> tuple[int, int, int, int, int, int] | None:
        if not isinstance(task_id, str) or not isinstance(raw_task, dict):
            return None

        values: list[int] = []
        for field_name in self.REQUIRED_TASK_FIELDS:
            value = self._to_int(raw_task.get(field_name))
            if value is None:
                return None
            values.append(value)

        r, p, e, d, w, preempt = values
        if p <= 0:
            return None
        return r, p, e, d, w, preempt

    def _collect_executions(
        self,
        schedule_result: list[Any] | None,
        jobs: dict[str, PeriodicJob],
        report: CheckReport,
    ) -> None:
        if not isinstance(schedule_result, list):
            report.add("FAIL", "unknown_periodic_execution", "schedule_result must be a list")
            return

        jobs_by_task: dict[str, list[PeriodicJob]] = {}
        jobs_by_compatibility_id: dict[str, PeriodicJob] = {}
        for job in jobs.values():
            jobs_by_task.setdefault(job.task_id, []).append(job)
            jobs_by_compatibility_id[job.compatibility_job_id] = job
        for task_jobs in jobs_by_task.values():
            task_jobs.sort(key=lambda job: (job.release, job.instance_index))

        unknown_executions: list[dict[str, Any]] = []
        non_standard_keys: list[dict[str, Any]] = []

        for entry in schedule_result:
            if not isinstance(entry, dict):
                continue
            t = self._to_int(entry.get("t"))
            k = entry.get("k")
            if t is None or not isinstance(k, dict):
                continue

            for raw_k_key, allocation in k.items():
                if not isinstance(raw_k_key, str):
                    continue
                amount = self._sum_allocation(allocation)
                if amount <= self.TOLERANCE:
                    continue

                if raw_k_key in jobs_by_task:
                    job = self._job_for_task_at_time(jobs_by_task[raw_k_key], t)
                    if job is None:
                        unknown_executions.append(
                            {
                                "t": t,
                                "raw_k_key": raw_k_key,
                                "reason": "time_outside_periodic_job_window",
                            }
                        )
                    else:
                        job.executions.append((t, amount, raw_k_key))
                    continue

                compatibility_match = self.COMPATIBILITY_JOB_ID_PATTERN.fullmatch(raw_k_key)
                if compatibility_match is None:
                    continue

                task_id = compatibility_match.group("task_id")
                instance_index = int(compatibility_match.group("instance_index"))
                if task_id not in jobs_by_task:
                    unknown_executions.append(
                        {
                            "t": t,
                            "raw_k_key": raw_k_key,
                            "reason": "periodic_task_not_found",
                        }
                    )
                    continue

                job = jobs_by_compatibility_id.get(raw_k_key)
                if job is None:
                    unknown_executions.append(
                        {
                            "t": t,
                            "raw_k_key": raw_k_key,
                            "reason": "periodic_job_instance_not_found",
                            "task_id": task_id,
                            "instance_index": instance_index,
                        }
                    )
                    continue

                non_standard_keys.append({"t": t, "raw_k_key": raw_k_key, "suggested_key": task_id})
                if not self._is_in_job_window(job, t):
                    unknown_executions.append(
                        {
                            "t": t,
                            "raw_k_key": raw_k_key,
                            "reason": "time_outside_periodic_job_window",
                            "job_id": job.job_id,
                            "release": job.release,
                            "deadline_window_end": job.deadline_window_end,
                        }
                    )
                    continue

                job.executions.append((t, amount, raw_k_key))

        if non_standard_keys:
            report.add(
                "WARN",
                "non_standard_periodic_key_format",
                "expanded periodic job ids such as p1_j1 are accepted for compatibility, "
                "but standard schedule_result.k should use task ids such as p1",
                self._sample_details(non_standard_keys),
            )

        if unknown_executions:
            report.add(
                "FAIL",
                "unknown_periodic_execution",
                f"unknown or out-of-window periodic executions = {len(unknown_executions)}",
                self._sample_details(unknown_executions),
            )
        else:
            report.add("PASS", "unknown_periodic_execution", "no unknown periodic executions found")

    def _job_for_task_at_time(self, task_jobs: list[PeriodicJob], t: int) -> PeriodicJob | None:
        for job in task_jobs:
            if self._is_in_job_window(job, t):
                return job
        return None

    def _is_in_job_window(self, job: PeriodicJob, t: int) -> bool:
        return job.release <= t <= job.deadline_window_end

    def _check_release_time(self, jobs: dict[str, PeriodicJob], report: CheckReport) -> None:
        violations = [
            {
                "job_id": job.job_id,
                "task_id": job.task_id,
                "release": job.release,
                "deadline_window_end": job.deadline_window_end,
                "t": t,
                "raw_k_key": source_id,
            }
            for job in jobs.values()
            for t, _amount, source_id in job.executions
            if t < job.release
        ]
        if violations:
            report.add(
                "FAIL",
                "no_release_time_violation",
                f"release time violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "no_release_time_violation", "no periodic job executes before release")

    def _check_deadline(self, jobs: dict[str, PeriodicJob], report: CheckReport) -> None:
        violations = [
            {
                "job_id": job.job_id,
                "task_id": job.task_id,
                "release": job.release,
                "deadline_window_end": job.deadline_window_end,
                "t": t,
                "raw_k_key": source_id,
            }
            for job in jobs.values()
            for t, _amount, source_id in job.executions
            if t > job.deadline_window_end or t > self.HORIZON
        ]
        if violations:
            report.add(
                "FAIL",
                "no_deadline_violation",
                f"deadline violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "no_deadline_violation", "no periodic job executes outside its deadline window")

    def _check_execution_complete(self, jobs: dict[str, PeriodicJob], report: CheckReport) -> None:
        violations = [
            {
                "job_id": job.job_id,
                "task_id": job.task_id,
                "release": job.release,
                "deadline_window_end": job.deadline_window_end,
                "required_slots": job.execution_time,
                "actual_slots": len(job.executions),
                "executed_times": sorted(t for t, _amount, _source_id in job.executions),
            }
            for job in jobs.values()
            if len(job.executions) != job.execution_time
        ]
        if violations:
            report.add(
                "FAIL",
                "periodic_execution_complete",
                f"incomplete or over-executed periodic jobs = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "periodic_execution_complete", "all periodic jobs have exactly e execution slots")

    def _check_energy_demand(self, jobs: dict[str, PeriodicJob], report: CheckReport) -> None:
        violations = [
            {
                "job_id": job.job_id,
                "task_id": job.task_id,
                "t": t,
                "raw_k_key": source_id,
                "expected": job.energy_demand,
                "actual": amount,
            }
            for job in jobs.values()
            for t, amount, source_id in job.executions
            if abs(amount - job.energy_demand) > self.TOLERANCE
        ]
        if violations:
            report.add(
                "FAIL",
                "energy_demand_per_execution",
                f"periodic execution energy mismatches = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add(
                "PASS",
                "energy_demand_per_execution",
                "all periodic execution slots match task energy demand",
            )

    def _check_non_preemptive_contiguity(self, jobs: dict[str, PeriodicJob], report: CheckReport) -> None:
        violations: list[dict[str, Any]] = []
        for job in jobs.values():
            if job.preempt != 0:
                continue
            times = sorted(t for t, _amount, _source_id in job.executions)
            if len(times) <= 1:
                continue
            expected_times = list(range(times[0], times[0] + len(times)))
            if times != expected_times:
                violations.append(
                    {
                        "job_id": job.job_id,
                        "task_id": job.task_id,
                        "release": job.release,
                        "deadline_window_end": job.deadline_window_end,
                        "execution_times": times,
                    }
                )

        if violations:
            report.add(
                "FAIL",
                "non_preemptive_contiguity",
                f"non-preemptive contiguity violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add(
                "PASS",
                "non_preemptive_contiguity",
                "all non-preemptive periodic jobs execute contiguously",
            )

    def _sample_details(self, records: list[Any]) -> dict[str, Any]:
        return {"count": len(records), "samples": records[: self.SAMPLE_LIMIT]}

    def _sum_allocation(self, allocation: Any) -> float:
        if isinstance(allocation, dict):
            return sum(float(value) for value in allocation.values() if isinstance(value, int | float))
        if isinstance(allocation, int | float):
            return float(allocation)
        return 0.0

    def _to_int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None
