"""Evaluation metrics checker for Level 1 official metric fields."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..models import CheckReport, SubmissionData


@dataclass(slots=True)
class PeriodicEvalJob:
    job_id: str
    compatibility_job_id: str
    task_id: str
    instance_index: int
    release: int
    deadline: int
    execution_time: int
    executed_times: list[int] = field(default_factory=list)

    @property
    def completed(self) -> bool:
        return len(self.executed_times) >= self.execution_time

    @property
    def completion_time(self) -> int | None:
        if not self.completed:
            return None
        return max(self.executed_times)


class EvaluationChecker:
    checker_name = "Evaluation Metrics Checker"
    HORIZON = 72
    OBJECTIVE_ALPHA = 10000.0
    TOLERANCE = 1e-6
    DEFAULT_TOLERANCE = 1e-3
    COMPARE_TOLERANCE = 1e-2
    SAMPLE_LIMIT = 10
    REQUIRED_TASK_FIELDS = ("r", "p", "e", "d")
    COMPATIBILITY_JOB_ID_PATTERN = re.compile(r"^(?P<task_id>.+)_j(?P<instance_index>[1-9]\d*)$")

    REQUIRED_METRIC_FIELDS = {
        "hard_deadline_miss_rate": "rate",
        "soft_deadline_miss_rate": "rate",
        "average_tardiness": "non_negative_number",
        "max_tardiness": "non_negative_number",
        "average_response_time": "non_negative_number",
        "max_response_time": "non_negative_number",
        "completion_time_jitter": "non_negative_number",
        "sporadic_value_rate": "rate",
        "post_acceptance_violation_rate": "rate",
        "generator_cost": "non_negative_number",
        "market_revenue": "number",
        "objective_value": "number",
    }

    def check(self, submission_data: SubmissionData) -> CheckReport:
        report = CheckReport(checker_name=self.checker_name)
        evaluation_results = submission_data.evaluation_results
        jobs = self._periodic_jobs(submission_data.task_set)
        self._collect_executions(submission_data.schedule_result, jobs)
        acceptance_entries = self._acceptance_entries(submission_data.acceptance_test_log, submission_data.event_file)
        acceptance_entries = self._with_schedule_aperiodic_entries(
            acceptance_entries,
            submission_data.schedule_result,
            submission_data.event_file,
        )

        self._check_required_metric_fields(evaluation_results, report)
        self._check_deadline_miss_rate_fields(evaluation_results, jobs, acceptance_entries, report)
        self._check_tardiness_fields(evaluation_results, jobs, acceptance_entries, report)
        self._check_response_time_fields(evaluation_results, jobs, acceptance_entries, report)
        self._check_completion_time_jitter_field(evaluation_results, report)
        self._check_sporadic_value_rate_field(evaluation_results, report)
        self._check_post_acceptance_violation_rate_field(evaluation_results, report)
        self._check_cost_revenue_objective_fields(evaluation_results, report)
        computed_generator_cost = self._check_generator_cost_match(
            evaluation_results,
            submission_data.processor_settings,
            submission_data.schedule_result,
            report,
        )
        computed_market_revenue = self._check_market_revenue_match(
            evaluation_results,
            submission_data.price_72hr,
            submission_data.schedule_result,
            report,
        )
        self._check_objective_value_match(
            evaluation_results,
            acceptance_entries,
            computed_generator_cost,
            computed_market_revenue,
            report,
        )
        return report

    def _check_required_metric_fields(self, evaluation_results: dict[str, Any] | None, report: CheckReport) -> None:
        if not isinstance(evaluation_results, dict):
            report.add(
                "FAIL",
                "evaluation_required_fields",
                "evaluation_results.json must be a JSON object with required metric fields",
                {"missing_fields": sorted(self.REQUIRED_METRIC_FIELDS), "present_fields": [], "invalid_fields": []},
            )
            return

        missing_fields = [field_name for field_name in self.REQUIRED_METRIC_FIELDS if self._metric_value(evaluation_results, field_name) is None]
        invalid_fields = []
        for field_name, rule in self.REQUIRED_METRIC_FIELDS.items():
            value = self._metric_value(evaluation_results, field_name)
            if value is None:
                continue
            reason = self._validation_error(value, rule)
            if reason is not None:
                invalid_fields.append(
                    {
                        "field": field_name,
                        "actual": self._compact_actual(value),
                        "reason": reason,
                    }
                )

        if missing_fields or invalid_fields:
            report.add(
                "FAIL",
                "evaluation_required_fields",
                "evaluation_results.json missing required fields",
                {
                    "missing_fields": missing_fields,
                    "present_fields": sorted(evaluation_results.keys()),
                    "invalid_fields": invalid_fields[: self.SAMPLE_LIMIT],
                },
            )
        else:
            report.add("PASS", "evaluation_required_fields", "all required evaluation metric fields are present and valid")

    def _check_deadline_miss_rate_fields(
        self,
        evaluation_results: dict[str, Any] | None,
        jobs: dict[str, PeriodicEvalJob],
        acceptance_entries: list[dict[str, Any]],
        report: CheckReport,
    ) -> None:
        hard_rate = self._number_field(evaluation_results, "hard_deadline_miss_rate")
        soft_rate = self._number_field(evaluation_results, "soft_deadline_miss_rate")
        missing_fields = self._missing_fields(evaluation_results, ("hard_deadline_miss_rate", "soft_deadline_miss_rate"))
        invalid = []
        if missing_fields:
            report.add(
                "FAIL",
                "deadline_miss_rate_fields",
                "missing required fields; cannot validate deadline miss rate metrics",
                {"missing_fields": missing_fields},
            )
            return
        if hard_rate is None or not 0.0 <= hard_rate <= 1.0:
            invalid.append({"field": "hard_deadline_miss_rate", "actual": hard_rate, "reason": "expected number in [0,1]"})
        if soft_rate is None or not 0.0 <= soft_rate <= 1.0:
            invalid.append({"field": "soft_deadline_miss_rate", "actual": soft_rate, "reason": "expected number in [0,1]"})
        if invalid:
            report.add("FAIL", "deadline_miss_rate_fields", "deadline miss rate fields are invalid", {"invalid_fields": invalid})
            return

        report.add(
            "PASS",
            "deadline_miss_rate_fields",
            "deadline miss rate fields are present and in [0, 1]",
        )
        self._check_hard_deadline_miss_rate_match(hard_rate, jobs, acceptance_entries, report)
        self._check_soft_deadline_miss_rate_match(soft_rate, acceptance_entries, report)

    def _check_hard_deadline_miss_rate_match(
        self,
        actual: float,
        jobs: dict[str, PeriodicEvalJob],
        acceptance_entries: list[dict[str, Any]],
        report: CheckReport,
    ) -> None:
        hard_jobs: list[dict[str, Any]] = []
        missed: list[dict[str, Any]] = []

        for job in jobs.values():
            completion_time = job.completion_time
            record = {
                "job_id": job.job_id,
                "type": "periodic",
                "release_time": job.release,
                "abs_deadline": job.deadline,
                "completion_time": completion_time,
            }
            hard_jobs.append(record)
            if completion_time is None or completion_time > job.deadline:
                missed.append(record)

        for entry in acceptance_entries:
            if entry["type"] != "sporadic" or entry.get("accepted") is not True:
                continue
            completion_time = self._completion_time(entry)
            record = {
                "job_id": entry["job_id"],
                "type": "sporadic",
                "release_time": entry["release_time"],
                "abs_deadline": entry["abs_deadline"],
                "completion_time": completion_time,
            }
            hard_jobs.append(record)
            if (
                len(entry["assigned_hours"]) < int(entry["execution_time"])
                or completion_time is None
                or completion_time > int(entry["abs_deadline"])
            ):
                missed.append(record)

        expected = len(missed) / len(hard_jobs) if hard_jobs else 0.0
        details = {
            "expected": expected,
            "actual": actual,
            "total_hard_deadline_jobs": len(hard_jobs),
            "missed_hard_deadline_jobs": len(missed),
            "samples": missed[: self.SAMPLE_LIMIT],
        }
        if abs(actual - expected) > self.DEFAULT_TOLERANCE:
            report.add(
                "FAIL",
                "hard_deadline_miss_rate_match",
                "hard_deadline_miss_rate does not match periodic plus accepted sporadic recomputation",
                details,
            )
        else:
            report.add(
                "PASS",
                "hard_deadline_miss_rate_match",
                "hard_deadline_miss_rate matches periodic plus accepted sporadic recomputation",
            )

    def _check_soft_deadline_miss_rate_match(
        self,
        actual: float,
        acceptance_entries: list[dict[str, Any]],
        report: CheckReport,
    ) -> None:
        aperiodic_entries = [entry for entry in acceptance_entries if entry["type"] == "aperiodic"]
        missed = [entry for entry in aperiodic_entries if self._aperiodic_missed(entry)]
        expected = len(missed) / len(aperiodic_entries) if aperiodic_entries else 0.0
        details = {
            "expected": expected,
            "actual": actual,
            "total_aperiodic_jobs": len(aperiodic_entries),
            "missed_aperiodic_jobs": len(missed),
            "samples": self._entry_samples(missed),
        }
        if abs(actual - expected) > self.DEFAULT_TOLERANCE:
            report.add(
                "FAIL",
                "soft_deadline_miss_rate_match",
                "soft_deadline_miss_rate does not match schedule-derived aperiodic recomputation",
                details,
            )
        else:
            report.add(
                "PASS",
                "soft_deadline_miss_rate_match",
                "soft_deadline_miss_rate matches schedule-derived aperiodic recomputation",
            )

    def _check_tardiness_fields(
        self,
        evaluation_results: dict[str, Any] | None,
        jobs: dict[str, PeriodicEvalJob],
        acceptance_entries: list[dict[str, Any]],
        report: CheckReport,
    ) -> None:
        actual_average = self._number_field(evaluation_results, "average_tardiness")
        actual_max = self._number_field(evaluation_results, "max_tardiness")
        missing_fields = self._missing_fields(evaluation_results, ("average_tardiness", "max_tardiness"))
        if missing_fields:
            report.add(
                "FAIL",
                "tardiness_fields",
                "missing required fields; cannot validate tardiness metrics",
                {"missing_fields": missing_fields},
            )
            return
        if actual_average is None or actual_average < 0 or actual_max is None or actual_max < 0:
            report.add(
                "FAIL",
                "tardiness_fields",
                "average_tardiness and max_tardiness must be non-negative numbers",
                {"actual_average_tardiness": actual_average, "actual_max_tardiness": actual_max},
            )
            return

        tardiness_values = self._periodic_tardiness_values(jobs) + self._non_periodic_tardiness_values(acceptance_entries)
        expected_average = sum(tardiness_values) / len(tardiness_values) if tardiness_values else 0.0
        expected_max = max(tardiness_values) if tardiness_values else 0.0
        details = {
            "definition": "periodic jobs plus schedule-derived aperiodic jobs and accepted sporadic jobs; rejected sporadic jobs excluded",
            "expected_average_tardiness": expected_average,
            "actual_average_tardiness": actual_average,
            "expected_max_tardiness": expected_max,
            "actual_max_tardiness": actual_max,
            "job_count": len(tardiness_values),
        }
        if (
            abs(actual_average - expected_average) > self.DEFAULT_TOLERANCE
            or abs(actual_max - expected_max) > self.DEFAULT_TOLERANCE
        ):
            report.add("FAIL", "tardiness_fields", "tardiness metrics do not match v2 recomputation", details)
        else:
            report.add("PASS", "tardiness_fields", "tardiness fields are valid and match v2 recomputation")

    def _check_response_time_fields(
        self,
        evaluation_results: dict[str, Any] | None,
        jobs: dict[str, PeriodicEvalJob],
        acceptance_entries: list[dict[str, Any]],
        report: CheckReport,
    ) -> None:
        actual_average = self._number_field(evaluation_results, "average_response_time")
        actual_max = self._number_field(evaluation_results, "max_response_time")
        missing_fields = self._missing_fields(evaluation_results, ("average_response_time", "max_response_time"))
        if missing_fields:
            report.add(
                "FAIL",
                "response_time_fields",
                "missing required fields; cannot validate response time metrics",
                {"missing_fields": missing_fields},
            )
            return
        if actual_average is None or actual_average < 0 or actual_max is None or actual_max < 0:
            report.add(
                "FAIL",
                "response_time_fields",
                "average_response_time and max_response_time must be non-negative numbers",
                {"actual_average_response_time": actual_average, "actual_max_response_time": actual_max},
            )
            return

        response_times = self._periodic_response_times(jobs) + self._non_periodic_response_times(acceptance_entries)
        response_times_plus_one = [value + 1 for value in response_times]
        expected_average = sum(response_times) / len(response_times) if response_times else 0.0
        expected_max = max(response_times) if response_times else 0.0
        expected_average_plus_one = sum(response_times_plus_one) / len(response_times_plus_one) if response_times_plus_one else 0.0
        expected_max_plus_one = max(response_times_plus_one) if response_times_plus_one else 0.0
        no_plus_one_matches = self._numbers_match(actual_average, expected_average) and self._numbers_match(actual_max, expected_max)
        plus_one_matches = self._numbers_match(actual_average, expected_average_plus_one) and self._numbers_match(actual_max, expected_max_plus_one)
        detected_convention = self._response_time_convention_label(no_plus_one_matches, plus_one_matches)
        details = {
            "definition": (
                "Accepted conventions: periodic jobs use schedule execution hours; "
                "aperiodic jobs are derived from schedule_result.k; accepted sporadic jobs use acceptance_log assigned_hours; "
                "absolute_deadline = r + d - 1; response_time may be completion_time - release_time "
                "or completion_time - release_time + 1"
            ),
            "expected_average_response_time": expected_average,
            "expected_average_response_time_plus_one": expected_average_plus_one,
            "actual_average_response_time": actual_average,
            "expected_max_response_time": expected_max,
            "expected_max_response_time_plus_one": expected_max_plus_one,
            "actual_max_response_time": actual_max,
            "completed_job_count": len(response_times),
            "detected_response_time_convention": detected_convention,
        }
        if not no_plus_one_matches and not plus_one_matches:
            report.add("FAIL", "response_time_fields", "response time metrics do not match accepted recomputations", details)
        else:
            report.add("PASS", "response_time_fields", f"response time fields match {detected_convention}", details)

    def _check_completion_time_jitter_field(self, evaluation_results: dict[str, Any] | None, report: CheckReport) -> None:
        actual = self._number_field(evaluation_results, "completion_time_jitter")
        missing_fields = self._missing_fields(evaluation_results, ("completion_time_jitter",))
        if missing_fields:
            report.add("FAIL", "completion_time_jitter_field", "missing required field", {"missing_fields": missing_fields})
            return
        if actual is None or actual < 0:
            report.add(
                "FAIL",
                "completion_time_jitter_field",
                "completion_time_jitter must be a non-negative number",
                {"actual": actual},
            )
        else:
            report.add(
                "PASS",
                "completion_time_jitter_field",
                "completion_time_jitter formula is not strictly auto-recomputed in v2; field validation only",
            )

    def _check_sporadic_value_rate_field(self, evaluation_results: dict[str, Any] | None, report: CheckReport) -> None:
        actual = self._number_field(evaluation_results, "sporadic_value_rate")
        missing_fields = self._missing_fields(evaluation_results, ("sporadic_value_rate",))
        if missing_fields:
            report.add("FAIL", "sporadic_value_rate_field", "missing required field", {"missing_fields": missing_fields})
            return
        if actual is None or not 0.0 <= actual <= 1.0:
            report.add("FAIL", "sporadic_value_rate_field", "sporadic_value_rate must be a number in [0, 1]", {"actual": actual})
        else:
            report.add(
                "PASS",
                "sporadic_value_rate_field",
                "sporadic_value_rate field is valid; recomputation remains in AcceptanceChecker.sporadic_value_rate_match",
            )

    def _check_post_acceptance_violation_rate_field(self, evaluation_results: dict[str, Any] | None, report: CheckReport) -> None:
        actual = self._number_field(evaluation_results, "post_acceptance_violation_rate")
        missing_fields = self._missing_fields(evaluation_results, ("post_acceptance_violation_rate",))
        if missing_fields:
            report.add("FAIL", "post_acceptance_violation_rate_field", "missing required field", {"missing_fields": missing_fields})
            return
        if actual is None or not 0.0 <= actual <= 1.0:
            report.add(
                "FAIL",
                "post_acceptance_violation_rate_field",
                "post_acceptance_violation_rate must be a number in [0, 1]",
                {"actual": actual},
            )
        else:
            report.add(
                "PASS",
                "post_acceptance_violation_rate_field",
                "post_acceptance_violation_rate recomputation is not implemented in EvaluationChecker v2; field validation only",
            )

    def _check_cost_revenue_objective_fields(self, evaluation_results: dict[str, Any] | None, report: CheckReport) -> None:
        generator_cost = self._number_field(evaluation_results, "generator_cost")
        market_revenue = self._number_field(evaluation_results, "market_revenue")
        objective_value = self._number_field(evaluation_results, "objective_value")
        missing_fields = self._missing_fields(evaluation_results, ("generator_cost", "market_revenue", "objective_value"))
        if missing_fields:
            report.add(
                "FAIL",
                "cost_revenue_objective_fields",
                "missing required fields; cannot validate cost/revenue/objective metrics",
                {"missing_fields": missing_fields},
            )
            return
        invalid = []
        if generator_cost is None or generator_cost < 0:
            invalid.append({"field": "generator_cost", "actual": generator_cost, "reason": "expected number >= 0"})
        if market_revenue is None:
            invalid.append({"field": "market_revenue", "actual": market_revenue, "reason": "expected number"})
        if objective_value is None:
            invalid.append({"field": "objective_value", "actual": objective_value, "reason": "expected number"})
        if invalid:
            report.add("FAIL", "cost_revenue_objective_fields", "cost/revenue/objective fields are invalid", {"invalid_fields": invalid})
        else:
            report.add(
                "PASS",
                "cost_revenue_objective_fields",
                "cost/revenue/objective fields are present and type-valid; v3 recomputation checks run separately",
            )

    def _check_generator_cost_match(
        self,
        evaluation_results: dict[str, Any] | None,
        processor_settings: dict[str, Any] | None,
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> float | None:
        actual = self._number_field(evaluation_results, "generator_cost")
        if actual is None:
            details = {"missing_fields": self._missing_fields(evaluation_results, ("generator_cost",))}
            report.add("FAIL", "generator_cost_match", "cannot compare generator_cost because field is missing or not numeric", details)
            return None

        generator_specs, spec_errors = self._generator_cost_specs(processor_settings)
        if spec_errors:
            report.add(
                "FAIL",
                "generator_cost_match",
                "cannot compute generator_cost from processor_settings.generator",
                {"errors": spec_errors[: self.SAMPLE_LIMIT]},
            )
            return None
        if not isinstance(schedule_result, list):
            report.add("FAIL", "generator_cost_match", "cannot compute generator_cost because schedule_result is not a list")
            return None

        total = 0.0
        samples: list[dict[str, Any]] = []
        for entry in schedule_result:
            if not isinstance(entry, dict):
                continue
            t = self._to_int(entry.get("t"))
            p_values = entry.get("P")
            if t is None or not isinstance(p_values, dict):
                continue
            for spec in generator_specs:
                output = self._to_number(p_values.get(spec["generator_id"])) or 0.0
                computed_cost = 0.0
                if output > self.TOLERANCE:
                    computed_cost = spec["fixed_cost"] + spec["variable_cost"] * output
                    total += computed_cost
                if computed_cost > 0 and len(samples) < self.SAMPLE_LIMIT:
                    samples.append(
                        {
                            "t": t,
                            "generator_id": spec["generator_id"],
                            "output": output,
                            "fixed_cost": spec["fixed_cost"],
                            "variable_cost": spec["variable_cost"],
                            "computed_cost": computed_cost,
                        }
                    )

        details = {
            "expected_generator_cost": total,
            "actual_generator_cost": actual,
            "difference": actual - total,
            "samples": samples,
        }
        if abs(actual - total) > self.COMPARE_TOLERANCE:
            report.add("FAIL", "generator_cost_match", "generator_cost does not match v3 recomputation", details)
        else:
            report.add("PASS", "generator_cost_match", "generator_cost matches v3 recomputation")
        return total

    def _check_market_revenue_match(
        self,
        evaluation_results: dict[str, Any] | None,
        price_72hr: dict[str, Any] | None,
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> float | None:
        actual = self._number_field(evaluation_results, "market_revenue")
        if actual is None:
            details = {"missing_fields": self._missing_fields(evaluation_results, ("market_revenue",))}
            report.add("FAIL", "market_revenue_match", "cannot compare market_revenue because field is missing or not numeric", details)
            return None

        price_by_hour, price_errors = self._price_by_hour(price_72hr)
        if price_errors:
            report.add(
                "FAIL",
                "market_revenue_match",
                "cannot compute market_revenue because price_72hr.json format is invalid",
                {"errors": price_errors[: self.SAMPLE_LIMIT]},
            )
            return None
        if not isinstance(schedule_result, list):
            report.add("FAIL", "market_revenue_match", "cannot compute market_revenue because schedule_result is not a list")
            return None

        schedule_by_hour = self._schedule_by_hour(schedule_result)
        total = 0.0
        samples: list[dict[str, Any]] = []
        for hour in range(1, self.HORIZON + 1):
            entry = schedule_by_hour.get(hour, {})
            sell = self._to_number(entry.get("sell")) or 0.0
            market_price = price_by_hour[hour]
            revenue = sell * market_price
            total += revenue
            if abs(revenue) > self.TOLERANCE and len(samples) < self.SAMPLE_LIMIT:
                samples.append({"t": hour, "sell": sell, "market_price": market_price, "revenue": revenue})

        details = {
            "expected_market_revenue": total,
            "actual_market_revenue": actual,
            "difference": actual - total,
            "samples": samples,
        }
        if abs(actual - total) > self.COMPARE_TOLERANCE:
            report.add("FAIL", "market_revenue_match", "market_revenue does not match v3 recomputation", details)
        else:
            report.add("PASS", "market_revenue_match", "market_revenue matches v3 recomputation")
        return total

    def _check_objective_value_match(
        self,
        evaluation_results: dict[str, Any] | None,
        acceptance_entries: list[dict[str, Any]],
        computed_generator_cost: float | None,
        computed_market_revenue: float | None,
        report: CheckReport,
    ) -> None:
        actual = self._number_field(evaluation_results, "objective_value")
        if actual is None:
            details = {"missing_fields": self._missing_fields(evaluation_results, ("objective_value",))}
            report.add("FAIL", "objective_value_match", "cannot compare objective_value because field is missing or not numeric", details)
            return
        if computed_generator_cost is None or computed_market_revenue is None:
            report.add(
                "FAIL",
                "objective_value_match",
                "cannot compute objective_value because generator_cost or market_revenue recomputation failed",
                {
                    "computed_generator_cost_available": computed_generator_cost is not None,
                    "computed_market_revenue_available": computed_market_revenue is not None,
                },
            )
            return
        aperiodic_entries = [entry for entry in acceptance_entries if entry["type"] == "aperiodic"]
        missed_entries = [entry for entry in aperiodic_entries if self._aperiodic_missed(entry)]
        expected = self.OBJECTIVE_ALPHA * len(missed_entries) + computed_generator_cost - computed_market_revenue
        details = {
            "alpha": self.OBJECTIVE_ALPHA,
            "aperiodic_miss_count": len(missed_entries),
            "computed_generator_cost": computed_generator_cost,
            "computed_market_revenue": computed_market_revenue,
            "expected_objective_value": expected,
            "actual_objective_value": actual,
            "difference": actual - expected,
        }
        if abs(actual - expected) > self.COMPARE_TOLERANCE:
            report.add("FAIL", "objective_value_match", "objective_value does not match Level 1 v3 formula", details)
        else:
            report.add("PASS", "objective_value_match", "objective_value matches Level 1 v3 formula")

    def _generator_cost_specs(self, processor_settings: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not isinstance(processor_settings, dict) or not isinstance(processor_settings.get("generator"), list):
            return [], [{"field": "generator", "reason": "missing_or_not_list"}]

        specs: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index, raw_generator in enumerate(processor_settings["generator"]):
            if not isinstance(raw_generator, dict):
                errors.append({"index": index, "reason": "generator_not_object"})
                continue
            generator_id = raw_generator.get("generator_id")
            fixed_cost = self._to_number(raw_generator.get("cost_fixed"))
            variable_cost = self._to_number(raw_generator.get("cost_variable"))
            if fixed_cost is None:
                fixed_cost = self._to_number(raw_generator.get("cost_on"))
            if variable_cost is None:
                variable_cost = self._to_number(raw_generator.get("cost_up"))
            if not isinstance(generator_id, str):
                errors.append({"index": index, "field": "generator_id", "reason": "missing_or_not_string"})
                continue
            if fixed_cost is None:
                errors.append({"generator_id": generator_id, "field": "cost_fixed/cost_on", "reason": "missing_or_not_number"})
                continue
            if variable_cost is None:
                errors.append({"generator_id": generator_id, "field": "cost_variable/cost_up", "reason": "missing_or_not_number"})
                continue
            specs.append({"generator_id": generator_id, "fixed_cost": fixed_cost, "variable_cost": variable_cost})
        if not specs and not errors:
            errors.append({"field": "generator", "reason": "empty_generator_list"})
        return specs, errors

    def _price_by_hour(self, price_72hr: dict[str, Any] | None) -> tuple[dict[int, float], list[dict[str, Any]]]:
        if not isinstance(price_72hr, dict) or not isinstance(price_72hr.get("price"), list):
            return {}, [{"field": "price", "reason": "invalid_price_format"}]

        price_by_hour: dict[int, float] = {}
        errors: list[dict[str, Any]] = []
        duplicate_hours: list[int] = []
        for index, raw_price in enumerate(price_72hr["price"]):
            if not isinstance(raw_price, dict):
                errors.append({"index": index, "reason": "invalid_price_format"})
                continue
            hour = self._to_int(raw_price.get("hour"))
            market_price = self._compatible_market_price(raw_price)
            if hour is None or not 1 <= hour <= self.HORIZON:
                errors.append({"index": index, "field": "hour", "actual": raw_price.get("hour"), "reason": "invalid_price_hour"})
                continue
            if market_price is None:
                errors.append({"index": index, "hour": hour, "field": "market_price", "reason": "invalid_price_format"})
                continue
            if hour in price_by_hour:
                duplicate_hours.append(hour)
                continue
            price_by_hour[hour] = market_price

        missing_hours = [hour for hour in range(1, self.HORIZON + 1) if hour not in price_by_hour]
        if missing_hours:
            errors.append({"reason": "missing_price_hour", "hours": missing_hours[: self.SAMPLE_LIMIT], "count": len(missing_hours)})
        if duplicate_hours:
            errors.append({"reason": "duplicate_hour", "hours": duplicate_hours[: self.SAMPLE_LIMIT], "count": len(duplicate_hours)})
        return price_by_hour, errors

    def _compatible_market_price(self, raw_price: dict[str, Any]) -> float | None:
        return self._to_number(raw_price.get("market_price"))

    def _schedule_by_hour(self, schedule_result: list[Any]) -> dict[int, dict[str, Any]]:
        entries: dict[int, dict[str, Any]] = {}
        for raw_entry in schedule_result:
            if not isinstance(raw_entry, dict):
                continue
            t = self._to_int(raw_entry.get("t"))
            if t is not None:
                entries[t] = raw_entry
        return entries

    def _has_official_acceptance_log(self, raw_log: Any) -> bool:
        return isinstance(raw_log, dict) and isinstance(raw_log.get("acceptance_test_log"), list)

    def _periodic_jobs(self, task_set: dict[str, Any] | None) -> dict[str, PeriodicEvalJob]:
        if not isinstance(task_set, dict) or not isinstance(task_set.get("periodic"), dict):
            return {}

        jobs: dict[str, PeriodicEvalJob] = {}
        for task_id, raw_task in task_set["periodic"].items():
            parsed = self._parse_task(task_id, raw_task)
            if parsed is None:
                continue
            task_id_str, r, p, e, d = parsed
            instance_index = 1
            release = r
            while release <= self.HORIZON:
                job_id = f"{task_id_str}_{instance_index}"
                jobs[job_id] = PeriodicEvalJob(
                    job_id=job_id,
                    compatibility_job_id=f"{task_id_str}_j{instance_index}",
                    task_id=task_id_str,
                    instance_index=instance_index,
                    release=release,
                    deadline=release + d - 1,
                    execution_time=e,
                )
                instance_index += 1
                release += p
        return jobs

    def _parse_task(self, task_id: Any, raw_task: Any) -> tuple[str, int, int, int, int] | None:
        if not isinstance(task_id, str) or not isinstance(raw_task, dict):
            return None
        values: list[int] = []
        for field_name in self.REQUIRED_TASK_FIELDS:
            value = self._to_int(raw_task.get(field_name))
            if value is None:
                return None
            values.append(value)
        r, p, e, d = values
        if p <= 0:
            return None
        return task_id, r, p, e, d

    def _collect_executions(self, schedule_result: list[Any] | None, jobs: dict[str, PeriodicEvalJob]) -> None:
        if not isinstance(schedule_result, list):
            return

        jobs_by_task: dict[str, list[PeriodicEvalJob]] = {}
        jobs_by_compatibility_id: dict[str, PeriodicEvalJob] = {}
        for job in jobs.values():
            jobs_by_task.setdefault(job.task_id, []).append(job)
            jobs_by_compatibility_id[job.compatibility_job_id] = job
        for task_jobs in jobs_by_task.values():
            task_jobs.sort(key=lambda job: (job.release, job.instance_index))

        for entry in schedule_result:
            if not isinstance(entry, dict):
                continue
            t = self._to_int(entry.get("t"))
            k_values = entry.get("k")
            if t is None or not isinstance(k_values, dict):
                continue
            for raw_key, allocation in k_values.items():
                if not isinstance(raw_key, str) or self._sum_allocation(allocation) <= self.TOLERANCE:
                    continue
                if raw_key in jobs_by_task:
                    job = self._job_for_task_at_time(jobs_by_task[raw_key], t)
                    if job is not None:
                        job.executed_times.append(t)
                    continue
                job = jobs_by_compatibility_id.get(raw_key)
                if job is not None and t >= job.release:
                    job.executed_times.append(t)

    def _job_for_task_at_time(self, task_jobs: list[PeriodicEvalJob], t: int) -> PeriodicEvalJob | None:
        eligible_jobs = [job for job in task_jobs if job.release <= t]
        if not eligible_jobs:
            return None
        incomplete_jobs = [job for job in eligible_jobs if not job.completed]
        if incomplete_jobs:
            return incomplete_jobs[0]
        latest_job = eligible_jobs[-1]
        return latest_job if t <= latest_job.deadline else None

    def _acceptance_entries(self, raw_log: Any, event_file: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(raw_log, dict):
            return []
        raw_entries = raw_log.get("acceptance_test_log")
        if not isinstance(raw_entries, list):
            raw_entries = raw_log.get("logs")
        if not isinstance(raw_entries, list):
            return []
        official_events = self._official_events_by_id(event_file)
        entries: list[dict[str, Any]] = []
        for raw_entry in raw_entries:
            normalized = self._normalize_acceptance_entry(raw_entry)
            if normalized is not None:
                normalized = self._with_official_event_fields(normalized, official_events)
                entries.append(normalized)
        return entries

    def _with_schedule_aperiodic_entries(
        self,
        entries: list[dict[str, Any]],
        schedule_result: list[Any] | None,
        event_file: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        official_events = self._official_events_by_id(event_file)
        aperiodic_ids = {
            job_id
            for job_id, event in official_events.items()
            if event.get("type") == "aperiodic"
        }
        if not aperiodic_ids:
            return entries

        assigned_hours_by_job: dict[str, set[int]] = {job_id: set() for job_id in aperiodic_ids}
        if isinstance(schedule_result, list):
            for schedule_entry in schedule_result:
                if not isinstance(schedule_entry, dict):
                    continue
                t = self._to_int(schedule_entry.get("t"))
                k_values = schedule_entry.get("k")
                if t is None or not isinstance(k_values, dict):
                    continue
                for job_id, allocation in k_values.items():
                    if (
                        isinstance(job_id, str)
                        and job_id in assigned_hours_by_job
                        and self._sum_allocation(allocation) > self.TOLERANCE
                    ):
                        assigned_hours_by_job[job_id].add(t)

        existing_non_aperiodic = [entry for entry in entries if entry.get("type") != "aperiodic"]
        schedule_aperiodic_entries = []
        for job_id in sorted(aperiodic_ids):
            event = official_events[job_id]
            schedule_aperiodic_entries.append(
                {
                    "job_id": job_id,
                    "type": "aperiodic",
                    "release_time": event["release_time"],
                    "abs_deadline": event["abs_deadline"],
                    "execution_time": event["execution_time"],
                    "assigned_hours": sorted(assigned_hours_by_job[job_id]),
                }
            )
        return existing_non_aperiodic + schedule_aperiodic_entries

    def _normalize_acceptance_entry(self, raw_entry: Any) -> dict[str, Any] | None:
        if not isinstance(raw_entry, dict):
            return None
        job_id = raw_entry.get("job_id")
        job_type = raw_entry.get("type")
        release_time = self._to_int(raw_entry.get("release_time"))
        abs_deadline = self._to_int(raw_entry.get("abs_deadline"))
        execution_time = self._to_int(raw_entry.get("execution_time"))
        assigned_hours = self._int_list(raw_entry.get("assigned_hours"))
        if (
            not isinstance(job_id, str)
            or job_type not in {"sporadic", "aperiodic"}
            or release_time is None
            or abs_deadline is None
            or execution_time is None
            or assigned_hours is None
        ):
            return None
        normalized = {
            **raw_entry,
            "job_id": job_id,
            "type": job_type,
            "release_time": release_time,
            "abs_deadline": abs_deadline,
            "execution_time": execution_time,
            "assigned_hours": assigned_hours,
        }
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
                if release_time is None or relative_deadline is None or execution_time is None:
                    continue
                official_events[job_id] = {
                    "type": job_type,
                    "release_time": release_time,
                    "abs_deadline": release_time + relative_deadline - 1,
                    "execution_time": execution_time,
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

    def _periodic_tardiness_values(self, jobs: dict[str, PeriodicEvalJob]) -> list[float]:
        values = []
        for job in jobs.values():
            completion_time = job.completion_time
            if completion_time is not None:
                values.append(float(max(0, completion_time - job.deadline)))
        return values

    def _non_periodic_tardiness_values(self, entries: list[dict[str, Any]]) -> list[float]:
        values = []
        for entry in entries:
            if entry["type"] == "sporadic" and entry.get("accepted") is not True:
                continue
            completion_time = self._completion_time(entry)
            if completion_time is None:
                continue
            values.append(float(max(0, completion_time - int(entry["abs_deadline"]))))
        return values

    def _periodic_response_times(self, jobs: dict[str, PeriodicEvalJob]) -> list[float]:
        return [
            float(job.completion_time - job.release)
            for job in jobs.values()
            if job.completion_time is not None
        ]

    def _non_periodic_response_times(self, entries: list[dict[str, Any]]) -> list[float]:
        values = []
        for entry in entries:
            if entry["type"] == "sporadic" and entry.get("accepted") is not True:
                continue
            completion_time = self._completion_time(entry)
            if completion_time is None:
                continue
            values.append(float(completion_time - int(entry["release_time"])))
        return values

    def _aperiodic_missed(self, entry: dict[str, Any]) -> bool:
        completion_time = self._completion_time(entry)
        return (
            len(entry["assigned_hours"]) < int(entry["execution_time"])
            or completion_time is None
            or completion_time > int(entry["abs_deadline"])
        )

    def _completion_time(self, entry: dict[str, Any]) -> int | None:
        assigned_hours = entry.get("assigned_hours")
        if isinstance(assigned_hours, list) and assigned_hours:
            return max(assigned_hours)
        completion_time = self._to_int(entry.get("completion_time"))
        if completion_time is not None:
            return completion_time
        return None

    def _validation_error(self, value: Any, rule: str) -> str | None:
        if rule == "object":
            return None if isinstance(value, dict) else "expected object"
        number = self._to_number(value)
        if number is None:
            if rule == "rate":
                return "expected number in [0,1]"
            if rule == "non_negative_number":
                return "expected number >= 0"
            return "expected number"
        if rule == "rate" and not 0.0 <= number <= 1.0:
            return "expected number in [0,1]"
        if rule == "non_negative_number" and number < 0:
            return "expected number >= 0"
        return None

    def _numbers_match(self, actual: float, expected: float) -> bool:
        return abs(actual - expected) <= self.DEFAULT_TOLERANCE

    def _response_time_convention_label(self, no_plus_one_matches: bool, plus_one_matches: bool) -> str:
        if no_plus_one_matches and plus_one_matches:
            return "ambiguous_both_match"
        if plus_one_matches:
            return "completion_time - release_time + 1"
        if no_plus_one_matches:
            return "completion_time - release_time"
        return "no_accepted_convention_matched"

    def _entry_samples(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "job_id": entry.get("job_id"),
                "type": entry.get("type"),
                "release_time": entry.get("release_time"),
                "abs_deadline": entry.get("abs_deadline"),
                "execution_time": entry.get("execution_time"),
                "completion_time": self._completion_time(entry),
            }
            for entry in entries[: self.SAMPLE_LIMIT]
        ]

    def _number_field(self, evaluation_results: dict[str, Any] | None, field_name: str) -> float | None:
        if not isinstance(evaluation_results, dict):
            return None
        return self._to_number(evaluation_results.get(field_name))

    def _missing_fields(self, data: dict[str, Any] | None, field_names: tuple[str, ...]) -> list[str]:
        if not isinstance(data, dict):
            return list(field_names)
        return [field_name for field_name in field_names if data.get(field_name) is None]

    def _metric_value(self, evaluation_results: dict[str, Any], field_name: str) -> Any:
        return evaluation_results.get(field_name)

    def _compact_actual(self, value: Any) -> Any:
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return f"list[{len(value)}]"
        return value

    def _sum_allocation(self, allocation: Any) -> float:
        if isinstance(allocation, dict):
            return sum(float(value) for value in allocation.values() if isinstance(value, int | float) and not isinstance(value, bool))
        return self._to_number(allocation) or 0.0

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
