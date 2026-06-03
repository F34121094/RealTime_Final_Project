"""Acceptance and non-periodic job checker."""

from __future__ import annotations

import re
from typing import Any

from ..models import CheckReport, SubmissionData


class AcceptanceChecker:
    checker_name = "Acceptance Checker"
    HORIZON = 72
    TOLERANCE = 1e-6
    DEFAULT_TOLERANCE = 1e-3
    SAMPLE_LIMIT = 10
    NON_PERIODIC_KEY_PATTERN = re.compile(r"^[sa]\w*$")

    def check(self, submission_data: SubmissionData) -> CheckReport:
        report = CheckReport(checker_name=self.checker_name)
        raw_log = submission_data.acceptance_test_log
        entries = self._entries(raw_log, submission_data.event_file)
        schedule_entries = self._schedule_entries(submission_data.schedule_result)

        self._check_acceptance_log_format(raw_log, report)
        self._check_aperiodic_assignment_validity(entries, schedule_entries, report)
        self._check_aperiodic_miss_consistency(raw_log, entries, report)
        self._check_sporadic_acceptance_validity(raw_log, entries, schedule_entries, report)
        self._check_sporadic_rejection_consistency(raw_log, entries, schedule_entries, report)
        self._check_sporadic_value_rate(
            submission_data.evaluation_results,
            entries,
            submission_data.event_file,
            schedule_entries,
            report,
        )
        self._check_schedule_log_consistency(entries, schedule_entries, report)
        return report

    def _check_acceptance_log_format(self, raw_log: Any, report: CheckReport) -> None:
        failures: list[dict[str, Any]] = []
        if not isinstance(raw_log, dict):
            failures.append({"reason": "top_level_not_object"})
        else:
            raw_entries = self._raw_log_entries(raw_log)
            if not raw_entries:
                failures.append({"field": "acceptance_test_log", "reason": "missing_or_not_list"})
            for index, entry in enumerate(raw_entries):
                if not isinstance(entry, dict):
                    failures.append({"index": index, "reason": "entry_not_object"})
                    continue
                normalized = self._normalize_entry(entry)
                if normalized is None:
                    failures.append({"index": index, "reason": "entry_format_not_recognized"})
                elif self._has_duplicates(normalized["assigned_hours"]):
                    failures.append({"index": index, "field": "assigned_hours", "reason": "duplicate_hours"})

        if failures:
            severe = any(item.get("reason") not in {"top_level_not_object", "missing_or_not_list"} for item in failures)
            severity = "FAIL" if severe else "WARN"
            message = (
                f"acceptance_test_log format violations = {len(failures)}"
                if severe
                else "acceptance_test_log format not recognized; using schedule_result and official event file for auto checks"
            )
            report.add(severity, "acceptance_log_format", message, self._sample_details(failures))
        else:
            report.add("PASS", "acceptance_log_format", "acceptance_test_log format is valid")

    def _check_aperiodic_assignment_validity(self, entries: list[dict[str, Any]], schedule_entries: dict[int, dict[str, Any]], report: CheckReport) -> None:
        violations: list[dict[str, Any]] = []
        for entry in self._typed_entries(entries, "aperiodic"):
            job_id = entry["job_id"]
            release_time = int(entry["release_time"])
            execution_time = int(entry["execution_time"])
            energy_demand = float(entry["energy_demand"])
            assigned_hours = entry["assigned_hours"]
            if self._has_duplicates(assigned_hours):
                violations.append({"job_id": job_id, "assigned_hours": assigned_hours, "reason": "duplicate_assigned_hours"})
            if len(assigned_hours) > execution_time:
                violations.append({"job_id": job_id, "expected_slots": execution_time, "actual_slots": len(assigned_hours), "reason": "execution_time_exceeded"})
            for t in assigned_hours:
                if t < release_time:
                    violations.append({"job_id": job_id, "t": t, "reason": "scheduled_before_release"})
                if not (1 <= t <= self.HORIZON):
                    violations.append({"job_id": job_id, "t": t, "reason": "scheduled_outside_horizon"})
                    continue
                allocation = schedule_entries.get(t, {}).get("k", {}).get(job_id)
                if allocation is None:
                    violations.append({"job_id": job_id, "t": t, "reason": "missing_from_schedule_k"})
                    continue
                actual_energy = self._sum_allocation(allocation)
                if abs(actual_energy - energy_demand) > self.TOLERANCE:
                    violations.append({"job_id": job_id, "t": t, "expected_energy": energy_demand, "actual_energy": actual_energy, "reason": "energy_mismatch"})

        if violations:
            report.add("FAIL", "aperiodic_assignment_validity", f"aperiodic assignment violations = {len(violations)}", self._sample_details(violations))
        else:
            report.add("PASS", "aperiodic_assignment_validity", "all aperiodic assignments are valid")

    def _check_aperiodic_miss_consistency(self, raw_log: Any, entries: list[dict[str, Any]], report: CheckReport) -> None:
        violations: list[dict[str, Any]] = []
        computed_missed: set[str] = set()
        for entry in self._typed_entries(entries, "aperiodic"):
            job_id = entry["job_id"]
            assigned_hours = entry["assigned_hours"]
            expected_completion_time = max(assigned_hours) if assigned_hours else None
            expected_miss = (
                len(assigned_hours) < int(entry["execution_time"])
                or expected_completion_time is None
                or expected_completion_time > int(entry["abs_deadline"])
            )
            if expected_miss:
                computed_missed.add(job_id)
            actual_completion_time = self._to_int(entry.get("completion_time"))
            actual_miss = entry.get("miss")
            if actual_completion_time != expected_completion_time or actual_miss != expected_miss:
                violations.append({"job_id": job_id, "expected_miss": expected_miss, "actual_miss": actual_miss, "expected_completion_time": expected_completion_time, "actual_completion_time": actual_completion_time})

        reported_missed = set(self._string_list(raw_log.get("missed_aperiodic") if isinstance(raw_log, dict) else []))
        if reported_missed != computed_missed:
            violations.append({"expected_missed_aperiodic": sorted(computed_missed), "actual_missed_aperiodic": sorted(reported_missed), "reason": "top_level_missed_aperiodic_mismatch"})

        if violations:
            report.add("FAIL", "aperiodic_miss_consistency", f"aperiodic miss consistency violations = {len(violations)}", self._sample_details(violations))
        else:
            report.add("PASS", "aperiodic_miss_consistency", "aperiodic miss records are consistent")

    def _check_sporadic_acceptance_validity(self, raw_log: Any, entries: list[dict[str, Any]], schedule_entries: dict[int, dict[str, Any]], report: CheckReport) -> None:
        violations: list[dict[str, Any]] = []
        for raw_entry in self._raw_log_entries(raw_log):
            if raw_entry.get("type") != "sporadic":
                continue
            missing_fields = [field for field in ("assigned_hours",) if field not in raw_entry]
            if missing_fields:
                violations.append(
                    {
                        "job_id": raw_entry.get("job_id"),
                        "missing_fields": missing_fields,
                        "reason": "sporadic log missing assigned_hours",
                    }
                )
        for entry in self._typed_entries(entries, "sporadic"):
            job_id = entry["job_id"]
            assigned_hours = entry["assigned_hours"]
            scheduled_hours = self._scheduled_hours(job_id, schedule_entries)
            accepted = entry.get("accepted") is True
            if self._has_duplicates(assigned_hours):
                violations.append({"job_id": job_id, "assigned_hours": assigned_hours, "reason": "duplicate_assigned_hours"})
            if accepted:
                if len(assigned_hours) != int(entry["execution_time"]):
                    violations.append({"job_id": job_id, "expected_slots": int(entry["execution_time"]), "actual_slots": len(assigned_hours), "reason": "execution_time_mismatch"})
                for t in assigned_hours:
                    if t < int(entry["release_time"]):
                        violations.append({"job_id": job_id, "t": t, "reason": "accepted_sporadic_executed_before_release"})
                    if t > int(entry["abs_deadline"]):
                        violations.append({"job_id": job_id, "t": t, "reason": "accepted_sporadic_executed_after_deadline"})
                    if not (1 <= t <= self.HORIZON):
                        violations.append({"job_id": job_id, "t": t, "reason": "scheduled_outside_horizon"})
                        continue
                    allocation = schedule_entries.get(t, {}).get("k", {}).get(job_id)
                    if allocation is None:
                        violations.append({"job_id": job_id, "t": t, "reason": "missing_from_schedule_k"})
                        continue
                    actual_energy = self._sum_allocation(allocation)
                    if abs(actual_energy - float(entry["energy_demand"])) > self.TOLERANCE:
                        violations.append({"job_id": job_id, "t": t, "expected_energy": float(entry["energy_demand"]), "actual_energy": actual_energy, "reason": "energy_mismatch"})
                completion_time = max(assigned_hours) if assigned_hours else None
                if completion_time is None or completion_time > int(entry["abs_deadline"]):
                    violations.append({"job_id": job_id, "completion_time": completion_time, "abs_deadline": int(entry["abs_deadline"]), "reason": "accepted_sporadic_not_completed_by_deadline"})
            else:
                if assigned_hours:
                    violations.append({"job_id": job_id, "assigned_hours": assigned_hours, "reason": "rejected_sporadic_has_assigned_hours"})
                if scheduled_hours:
                    violations.append({"job_id": job_id, "scheduled_hours": scheduled_hours, "reason": "rejected_sporadic_executed"})

        if violations:
            message = "sporadic log missing assigned_hours" if any("missing_fields" in item for item in violations) else f"sporadic acceptance validity violations = {len(violations)}"
            report.add("FAIL", "sporadic_acceptance_validity", message, self._sample_details(violations))
        else:
            report.add("PASS", "sporadic_acceptance_validity", "sporadic acceptance assignments are valid")

    def _check_sporadic_rejection_consistency(self, raw_log: Any, entries: list[dict[str, Any]], schedule_entries: dict[int, dict[str, Any]], report: CheckReport) -> None:
        computed_rejected = {entry["job_id"] for entry in self._typed_entries(entries, "sporadic") if entry.get("accepted") is False}
        schedule_rejected = {job_id for entry in schedule_entries.values() for job_id in self._string_list(entry.get("rejected_sporadic", []))}
        violations: list[dict[str, Any]] = []
        if schedule_rejected != computed_rejected:
            violations.append({"expected_schedule_rejected_sporadic": sorted(computed_rejected), "actual_schedule_rejected_sporadic": sorted(schedule_rejected), "reason": "schedule_rejected_sporadic_mismatch"})
        if violations:
            report.add("FAIL", "sporadic_rejection_consistency", f"sporadic rejection consistency violations = {len(violations)}", self._sample_details(violations))
        else:
            report.add("PASS", "sporadic_rejection_consistency", "sporadic accepted/rejected records are consistent")

    def _check_sporadic_value_rate(
        self,
        evaluation_results: dict[str, Any] | None,
        entries: list[dict[str, Any]],
        event_file: dict[str, Any] | None,
        schedule_entries: dict[int, dict[str, Any]],
        report: CheckReport,
    ) -> None:
        event_sporadic = event_file.get("sporadic") if isinstance(event_file, dict) else None
        actual = self._number_field(evaluation_results, "sporadic_value_rate")
        if not isinstance(event_sporadic, dict):
            report.add(
                "FAIL",
                "sporadic_value_rate_match",
                "cannot recompute sporadic_value_rate because official event file sporadic jobs are unavailable",
                {"actual": actual, "denominator_source": "official_event_data"},
            )
            return

        total_exec_time = 0
        accepted_completed_exec_time = 0
        completed_jobs: list[str] = []
        incomplete_jobs: list[dict[str, Any]] = []
        for job_id, raw_job in event_sporadic.items():
            if not isinstance(job_id, str) or not isinstance(raw_job, dict):
                continue
            execution_time = self._to_int(raw_job.get("e"))
            if execution_time is None:
                continue
            total_exec_time += execution_time
            completed, reason = self._official_sporadic_completed(job_id, raw_job, schedule_entries)
            if completed:
                accepted_completed_exec_time += execution_time
                completed_jobs.append(job_id)
            else:
                incomplete_jobs.append({"job_id": job_id, "reason": reason})
        details = {
            "actual": actual,
            "total_sporadic_exec_time": total_exec_time,
            "accepted_completed_exec_time": accepted_completed_exec_time,
            "denominator_source": "official_event_data",
            "numerator_source": "schedule_result",
            "completed_sporadic_jobs": completed_jobs[: self.SAMPLE_LIMIT],
            "not_counted_samples": incomplete_jobs[: self.SAMPLE_LIMIT],
        }
        if total_exec_time <= 0:
            report.add(
                "FAIL",
                "sporadic_value_rate_match",
                "cannot recompute sporadic_value_rate because total sporadic execution time is zero",
                details,
            )
            return
        expected = accepted_completed_exec_time / total_exec_time
        details["expected"] = expected
        if actual is None or abs(actual - expected) > self.DEFAULT_TOLERANCE:
            report.add("FAIL", "sporadic_value_rate_match", "sporadic_value_rate does not match recomputation", details)
        else:
            report.add("PASS", "sporadic_value_rate_match", "sporadic_value_rate matches recomputation")

    def _official_sporadic_completed(
        self,
        job_id: str,
        raw_job: dict[str, Any],
        schedule_entries: dict[int, dict[str, Any]],
    ) -> tuple[bool, str]:
        release_time = self._to_int(raw_job.get("r"))
        execution_time = self._to_int(raw_job.get("e"))
        relative_deadline = self._to_int(raw_job.get("d"))
        energy_demand = self._to_number(raw_job.get("w"))
        if release_time is None or execution_time is None or relative_deadline is None or energy_demand is None:
            return False, "invalid_official_sporadic_fields"

        executed_hours: list[int] = []
        for t, entry in schedule_entries.items():
            allocation = entry.get("k", {}).get(job_id)
            if allocation is None:
                continue
            supplied = self._sum_allocation(allocation)
            if supplied <= self.TOLERANCE:
                continue
            if abs(supplied - energy_demand) > self.DEFAULT_TOLERANCE:
                return False, "energy_mismatch"
            executed_hours.append(t)

        if len(executed_hours) != execution_time:
            return False, "execution_time_mismatch"
        if any(t < release_time for t in executed_hours):
            return False, "scheduled_before_release"
        completion_time = max(executed_hours) if executed_hours else None
        if completion_time is None:
            return False, "not_scheduled"
        if completion_time > release_time + relative_deadline - 1:
            return False, "completed_after_deadline"
        return True, "completed_before_deadline"

    def _check_schedule_log_consistency(self, entries: list[dict[str, Any]], schedule_entries: dict[int, dict[str, Any]], report: CheckReport) -> None:
        sporadic_entries = self._typed_entries(entries, "sporadic")
        known_jobs = {entry["job_id"] for entry in sporadic_entries}
        assigned_hours_by_job = {entry["job_id"]: set(entry["assigned_hours"]) for entry in sporadic_entries}
        violations: list[dict[str, Any]] = []
        for t, schedule_entry in schedule_entries.items():
            for job_id, allocation in schedule_entry.get("k", {}).items():
                if not isinstance(job_id, str) or self._sum_allocation(allocation) <= self.TOLERANCE:
                    continue
                if not self.NON_PERIODIC_KEY_PATTERN.fullmatch(job_id):
                    continue
                if not job_id.startswith("s"):
                    continue
                if job_id not in known_jobs:
                    violations.append({"job_id": job_id, "t": t, "reason": "sporadic_job_not_in_acceptance_log"})
                elif t not in assigned_hours_by_job.get(job_id, set()):
                    violations.append({"job_id": job_id, "t": t, "reason": "execution_not_in_assigned_hours"})
        for job_id, assigned_hours in assigned_hours_by_job.items():
            for t in assigned_hours:
                if t not in schedule_entries or job_id not in schedule_entries[t].get("k", {}):
                    violations.append({"job_id": job_id, "t": t, "reason": "assigned_hour_missing_from_schedule"})
        if violations:
            report.add("FAIL", "schedule_log_consistency", f"schedule log consistency violations = {len(violations)}", self._sample_details(violations))
        else:
            report.add("PASS", "schedule_log_consistency", "schedule non-periodic jobs match acceptance log")

    def _entries(self, raw_log: Any, event_file: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(raw_log, dict):
            return []
        official_events = self._official_events_by_id(event_file)
        entries: list[dict[str, Any]] = []
        for raw_entry in self._raw_log_entries(raw_log):
            normalized = self._normalize_entry(raw_entry)
            if normalized is not None:
                normalized = self._with_official_event_fields(normalized, official_events)
                entries.append(normalized)
        return entries

    def _raw_log_entries(self, raw_log: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_log, dict):
            return []
        raw_entries = raw_log.get("acceptance_test_log")
        if not isinstance(raw_entries, list):
            raw_entries = raw_log.get("logs")
        if not isinstance(raw_entries, list):
            return []
        return [entry for entry in raw_entries if isinstance(entry, dict)]

    def _normalize_entry(self, raw_entry: Any) -> dict[str, Any] | None:
        if not isinstance(raw_entry, dict):
            return None
        job_id = raw_entry.get("job_id")
        job_type = raw_entry.get("type")
        release_time = self._to_int(raw_entry.get("release_time"))
        abs_deadline = self._to_int(raw_entry.get("abs_deadline"))
        execution_time = self._to_int(raw_entry.get("execution_time"))
        energy_demand = self._to_number(raw_entry.get("energy_demand"))
        assigned_hours = self._int_list(raw_entry.get("assigned_hours"))
        if not isinstance(job_id, str) or job_type not in {"sporadic", "aperiodic"} or release_time is None or abs_deadline is None or execution_time is None or energy_demand is None or assigned_hours is None:
            return None
        normalized = {**raw_entry, "job_id": job_id, "type": job_type, "release_time": release_time, "abs_deadline": abs_deadline, "execution_time": execution_time, "energy_demand": energy_demand, "assigned_hours": assigned_hours}
        return normalized

    def _official_events_by_id(self, event_file: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not isinstance(event_file, dict):
            return {}
        official_events: dict[str, dict[str, Any]] = {}
        for job_type in ("sporadic", "aperiodic"):
            raw_jobs = event_file.get(job_type)
            if not isinstance(raw_jobs, dict):
                continue
            for job_id, raw_job in raw_jobs.items():
                if not isinstance(job_id, str) or not isinstance(raw_job, dict):
                    continue
                release_time = self._to_int(raw_job.get("r"))
                relative_deadline = self._to_int(raw_job.get("d"))
                execution_time = self._to_int(raw_job.get("e"))
                energy_demand = self._to_number(raw_job.get("w"))
                if (
                    release_time is None
                    or relative_deadline is None
                    or execution_time is None
                    or energy_demand is None
                ):
                    continue
                official_events[job_id] = {
                    "type": job_type,
                    "release_time": release_time,
                    "abs_deadline": release_time + relative_deadline - 1,
                    "execution_time": execution_time,
                    "energy_demand": energy_demand,
                }
        return official_events

    def _with_official_event_fields(
        self,
        entry: dict[str, Any],
        official_events: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        official_event = official_events.get(entry["job_id"])
        if official_event is None:
            return entry
        return {**entry, **official_event}

    def _typed_entries(self, entries: list[dict[str, Any]], job_type: str) -> list[dict[str, Any]]:
        return [entry for entry in entries if entry["type"] == job_type]

    def _schedule_entries(self, schedule_result: list[Any] | None) -> dict[int, dict[str, Any]]:
        if not isinstance(schedule_result, list):
            return {}
        entries: dict[int, dict[str, Any]] = {}
        for raw_entry in schedule_result:
            if not isinstance(raw_entry, dict):
                continue
            t = self._to_int(raw_entry.get("t"))
            if t is None:
                continue
            entries[t] = {**raw_entry, "t": t, "k": raw_entry.get("k") if isinstance(raw_entry.get("k"), dict) else {}, "rejected_sporadic": raw_entry.get("rejected_sporadic", [])}
        return entries

    def _scheduled_hours(self, job_id: str, schedule_entries: dict[int, dict[str, Any]]) -> list[int]:
        return sorted(t for t, entry in schedule_entries.items() if job_id in entry.get("k", {}) and self._sum_allocation(entry["k"][job_id]) > self.TOLERANCE)

    def _accepted_sporadic_completed(self, entry: dict[str, Any]) -> bool:
        if entry.get("accepted") is not True or not entry["assigned_hours"]:
            return False
        if self._has_duplicates(entry["assigned_hours"]):
            return False
        return len(entry["assigned_hours"]) == int(entry["execution_time"]) and max(entry["assigned_hours"]) <= int(entry["abs_deadline"])

    def _number_field(self, data: dict[str, Any] | None, field_name: str) -> float | None:
        if not isinstance(data, dict):
            return None
        return self._to_number(data.get(field_name))

    def _sum_allocation(self, allocation: Any) -> float:
        if isinstance(allocation, dict):
            return sum(self._to_number(value) or 0.0 for value in allocation.values())
        return self._to_number(allocation) or 0.0

    def _sample_details(self, records: list[Any]) -> dict[str, Any]:
        return {"count": len(records), "samples": records[: self.SAMPLE_LIMIT]}

    def _int_list(self, value: Any) -> list[int] | None:
        if not isinstance(value, list):
            return None
        result: list[int] = []
        for item in value:
            int_value = self._to_int(item)
            if int_value is None:
                return None
            result.append(int_value)
        return result

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    def _has_duplicates(self, value: list[Any]) -> bool:
        seen: list[Any] = []
        for item in value:
            if item in seen:
                return True
            seen.append(item)
        return False

    def _to_number(self, value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value)

    def _to_int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None
