"""Submission reader for RTS/VPP assignment outputs."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .models import ReadReport, SubmissionData


class SubmissionReader:
    """Read and lightly validate the fixed Level 1 JSON submission format."""

    REQUIRED_FILES = (
        "input/processor_settings.json",
        "input/price_72hr.json",
        "input/aperiodic_n_sporadic.json",
        "output/task_set.json",
        "output/schedule_result.json",
        "output/evaluation_results.json",
        "output/acceptance_test_log.json",
    )
    DEFAULT_EVENT_FILE = "input/aperiodic_n_sporadic.json"

    PROCESSOR_FIELDS = ("generator", "renewable_capacity", "renewable_forecast", "storage")
    PROCESSOR_KNOWN_FIELDS = PROCESSOR_FIELDS + ("charging_jobs",)
    PRICE_FIELDS = ("price",)
    TASK_SET_FIELDS = ("periodic", "sporadic", "aperiodic")
    TASK_SET_OPTIONAL_FIELDS = ("frame_size", "meta")
    TASK_SET_KNOWN_FIELDS = TASK_SET_FIELDS + TASK_SET_OPTIONAL_FIELDS
    EVALUATION_FIELDS = (
        "hard_deadline_miss_rate",
        "soft_deadline_miss_rate",
        "average_tardiness",
        "max_tardiness",
        "average_response_time",
        "max_response_time",
        "completion_time_jitter",
        "generator_cost",
        "market_revenue",
        "objective_value",
    )
    EVALUATION_OPTIONAL_FIELDS = (
        "acceptance_test",
        "sporadic_value_rate",
        "post_acceptance_violation_rate",
        "detail",
    )
    EVALUATION_KNOWN_FIELDS = EVALUATION_FIELDS + EVALUATION_OPTIONAL_FIELDS

    def read(self, submission_dir: str | Path, event_file: str | Path | None = None) -> SubmissionData:
        base_dir = Path(submission_dir)
        report = ReadReport()

        processor_settings = self._load_object_file(
            base_dir,
            "input/processor_settings.json",
            self.PROCESSOR_FIELDS,
            report,
            known_fields=self.PROCESSOR_KNOWN_FIELDS,
            warn_extra=True,
        )
        price_72hr = self._load_object_file(base_dir, "input/price_72hr.json", self.PRICE_FIELDS, report)
        task_set = self._load_task_set(base_dir, report)
        raw_schedule_result = self._load_json(base_dir, "output/schedule_result.json", report)
        schedule_result = self._normalize_schedule_result(raw_schedule_result, "output/schedule_result.json", report)
        evaluation_results = self._load_object_file(
            base_dir,
            "output/evaluation_results.json",
            self.EVALUATION_FIELDS,
            report,
            known_fields=self.EVALUATION_KNOWN_FIELDS,
            warn_extra=True,
        )
        acceptance_test_log = self._load_json(base_dir, "output/acceptance_test_log.json", report)
        official_events = self._load_event_file(base_dir, event_file, report)

        return SubmissionData(
            submission_dir=base_dir,
            processor_settings=processor_settings,
            price_72hr=price_72hr,
            task_set=task_set,
            schedule_result=schedule_result,
            evaluation_results=evaluation_results,
            acceptance_test_log=acceptance_test_log,
            event_file=official_events,
            read_report=report,
        )

    def _load_event_file(self, base_dir: Path, event_file: str | Path | None, report: ReadReport) -> dict[str, Any] | None:
        if event_file is None:
            path = base_dir / self.DEFAULT_EVENT_FILE
            path_label = self.DEFAULT_EVENT_FILE
        else:
            path = Path(event_file)
            path_label = str(path)
        if not path.exists():
            report.add("FAIL", path_label, "event file missing")
            return None
        if not path.is_file():
            report.add("FAIL", path_label, "event file path is not a file")
            return None

        try:
            with path.open("r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
        except JSONDecodeError as exc:
            report.add("FAIL", path_label, f"event file invalid JSON: {exc.msg}")
            return None
        except OSError as exc:
            report.add("FAIL", path_label, f"could not read event file: {exc}")
            return None

        if not isinstance(data, dict):
            report.add("FAIL", path_label, "event file top-level JSON value must be an object")
            return None
        for field in ("sporadic", "aperiodic"):
            if field not in data:
                report.add("FAIL", path_label, f"event file missing required field: {field}", [field])
            elif not isinstance(data[field], dict):
                report.add("FAIL", path_label, f"event file field must be an object: {field}", [field])
            else:
                self._check_event_jobs(data[field], field, path_label, report)
        if any(issue.severity == "FAIL" and issue.path == path_label for issue in report.issues):
            return None

        report.files_loaded += 1
        report.add("PASS", path_label, "event file loaded")
        return data

    def _check_event_jobs(
        self,
        jobs: dict[str, Any],
        job_type: str,
        path_label: str,
        report: ReadReport,
    ) -> None:
        required_fields = ("r", "e", "d", "w", "preempt")
        for job_id, raw_job in jobs.items():
            entry_label = f"{job_type}.{job_id}"
            if not isinstance(raw_job, dict):
                report.add("FAIL", path_label, f"event job must be an object: {entry_label}", [entry_label])
                continue
            missing_fields = [field for field in required_fields if field not in raw_job]
            if missing_fields:
                report.add("FAIL", path_label, f"event job missing required fields: {entry_label}", missing_fields)

    def _load_json(self, base_dir: Path, relative_path: str, report: ReadReport) -> Any | None:
        path = base_dir / relative_path
        if not path.exists():
            report.add("FAIL", relative_path, "missing file")
            return None
        if not path.is_file():
            report.add("FAIL", relative_path, "is not a file")
            return None

        try:
            with path.open("r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
        except JSONDecodeError as exc:
            report.add("FAIL", relative_path, f"invalid JSON: {exc.msg}")
            return None
        except OSError as exc:
            report.add("FAIL", relative_path, f"could not read file: {exc}")
            return None

        report.files_loaded += 1
        report.add("PASS", relative_path, "loaded")
        return data

    def _load_object_file(
        self,
        base_dir: Path,
        relative_path: str,
        required_fields: tuple[str, ...],
        report: ReadReport,
        *,
        known_fields: tuple[str, ...] | None = None,
        warn_extra: bool = False,
    ) -> dict[str, Any] | None:
        data = self._load_json(base_dir, relative_path, report)
        if data is None:
            return None
        if not isinstance(data, dict):
            report.add("FAIL", relative_path, "top-level JSON value must be an object")
            return None

        self._check_required_fields(data, required_fields, relative_path, report)
        if warn_extra:
            self._record_extra_fields(data, known_fields or required_fields, relative_path, report)
        return data

    def _load_task_set(self, base_dir: Path, report: ReadReport) -> dict[str, Any] | None:
        relative_path = "output/task_set.json"
        data = self._load_json(base_dir, relative_path, report)
        if data is None:
            return None
        if not isinstance(data, dict):
            report.add("FAIL", relative_path, "top-level JSON value must be an object")
            return None

        self._check_required_fields(data, ("periodic",), relative_path, report)
        for task_type in self.TASK_SET_FIELDS:
            if task_type in data and not isinstance(data[task_type], dict):
                report.add("FAIL", relative_path, f"field must be an object: {task_type}", [task_type])
        self._record_extra_fields(data, self.TASK_SET_KNOWN_FIELDS, relative_path, report)
        return data

    def _check_required_fields(
        self, data: dict[str, Any], required_fields: tuple[str, ...], relative_path: str, report: ReadReport
    ) -> None:
        missing_fields = [field for field in required_fields if field not in data]
        for field in missing_fields:
            report.add("FAIL", relative_path, f"missing required field: {field}", [field])

    def _record_extra_fields(
        self, data: dict[str, Any], known_fields: tuple[str, ...], relative_path: str, report: ReadReport
    ) -> None:
        extra_fields = [field for field in data if field not in known_fields]
        if extra_fields:
            report.add("WARN", relative_path, "has extra top-level fields", extra_fields)

    def _normalize_schedule_result(
        self, data: Any | None, relative_path: str, report: ReadReport
    ) -> list[Any] | None:
        if data is None:
            return None

        if isinstance(data, list):
            report.add(
                "FAIL",
                relative_path,
                "top-level JSON value must be an object with field: schedule_result",
                ["schedule_result"],
            )
            return None

        if isinstance(data, dict):
            self._check_required_fields(data, ("schedule_result",), relative_path, report)
            self._record_extra_fields(data, ("schedule_result",), relative_path, report)
            schedule_result = data.get("schedule_result")
            if schedule_result is None:
                return None
            if not isinstance(schedule_result, list):
                report.add("FAIL", relative_path, "field must be a list: schedule_result", ["schedule_result"])
                return None
            self._check_schedule_entries(schedule_result, relative_path, report)
            return schedule_result

        report.add("FAIL", relative_path, "top-level JSON value must be an object or list")
        return None

    def _check_schedule_entries(
        self, schedule_result: list[Any], relative_path: str, report: ReadReport
    ) -> None:
        required_fields = ("t", "P", "k", "sell", "soc", "missed_aperiodic", "rejected_sporadic")
        object_fields = ("P", "k", "soc")
        list_fields = ("missed_aperiodic", "rejected_sporadic")

        for index, entry in enumerate(schedule_result):
            entry_path = f"{relative_path}[{index}]"
            if not isinstance(entry, dict):
                report.add("FAIL", entry_path, "schedule entry must be an object")
                continue

            self._check_required_fields(entry, required_fields, entry_path, report)

            for field in object_fields:
                if field in entry and not isinstance(entry[field], dict):
                    report.add("FAIL", entry_path, f"field must be an object: {field}", [field])

            for field in list_fields:
                if field in entry and not isinstance(entry[field], list):
                    report.add("FAIL", entry_path, f"field must be a list: {field}", [field])
