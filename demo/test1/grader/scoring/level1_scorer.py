"""Level 1 scorer."""

from __future__ import annotations

from collections.abc import Iterable

from ..models import CheckReport, ScoreItem, ScoreReport, ScoreSection
from .level1_rubric import (
    IMPLEMENTED_AUTO_MAX_SCORE,
    LEVEL,
    MANUAL_REVIEW_MAX_SCORE,
    NOT_IMPLEMENTED_AUTO_MAX_SCORE,
    TOTAL_MAX_SCORE,
)


class Level1Scorer:
    def score(
        self,
        structure_report: CheckReport | None,
        task_set_report: CheckReport | None,
        schedule_basic_report: CheckReport | None,
        model_constraint_report: CheckReport | None = None,
        evaluation_report: CheckReport | None = None,
        acceptance_report: CheckReport | None = None,
    ) -> ScoreReport:
        manual_review_required: list[str] = []

        submission_invalid = bool(structure_report and structure_report.errors)
        if submission_invalid:
            manual_review_required.append("submission structure incomplete")

        sections = [
            self._section_1(task_set_report),
            self._section_2(schedule_basic_report, model_constraint_report, acceptance_report),
            self._section_3(schedule_basic_report),
            self._section_4(manual_review_required, acceptance_report),
            self._section_5(evaluation_report),
            self._section_6(manual_review_required),
        ]
        implemented_auto_score = sum(
            section.score for section in sections if section.section_id in {"1", "2", "3", "4", "5"}
        )
        return ScoreReport(
            level=LEVEL,
            total_max_score=TOTAL_MAX_SCORE,
            implemented_auto_score=implemented_auto_score,
            implemented_auto_max_score=IMPLEMENTED_AUTO_MAX_SCORE,
            not_implemented_auto_max_score=NOT_IMPLEMENTED_AUTO_MAX_SCORE,
            manual_review_max_score=MANUAL_REVIEW_MAX_SCORE,
            sections=sections,
            manual_review_required=manual_review_required,
            not_implemented_items=[],
            submission_invalid=submission_invalid,
        )

    def _section_1(self, report: CheckReport | None) -> ScoreSection:
        items = [
            self._auto_item("1-1", "Periodic task set format", 3.0, report, ["periodic_fields", "periodic_key_format"]),
            self._auto_item("1-2", "Periodic task count", 2.0, report, ["task_count"]),
            self._auto_item("1-3", "Expanded periodic jobs count", 2.0, report, ["expanded_jobs"]),
            self._auto_item(
                "1-4",
                "Periodic parameter ranges",
                2.0,
                report,
                ["parameter_ranges", "period_diversity", "execution_time", "energy_demand"],
            ),
            self._auto_item("1-5", "Workload density", 2.0, report, ["workload_density"]),
            self._auto_item("1-6", "Deadline pressure", 2.0, report, ["deadline_pressure"]),
            self._auto_item("1-7", "Non-preemptive task count", 2.0, report, ["non_preemptive"]),
            self._auto_item("1-8", "Frame size legality", 2.0, report, ["frame_size"]),
        ]
        return self._section("1", "Periodic Task Set Design", 17.0, items)

    def _section_2(
        self,
        schedule_report: CheckReport | None,
        model_report: CheckReport | None,
        acceptance_report: CheckReport | None,
    ) -> ScoreSection:
        generator_checks = [
            "generator_output_bounds",
            "generator_ramp_limits",
            "generator_min_output_ramp_feasibility",
            "generator_min_up_time",
            "generator_min_down_time",
            "generator_initial_on_time",
            "generator_initial_off_time",
        ]
        storage_checks = [
            "storage_discharge_limit",
            "storage_charge_limit",
            "storage_soc_transition",
            "storage_soc_bounds",
            "storage_discharge_available_energy",
            "storage_no_simultaneous_charge_discharge",
            "charging_source_validity",
        ]
        items = [
            self._basic_constraints_item(schedule_report, model_report),
            self._auto_item(
                "2-2",
                "Aperiodic task constraint 4",
                2.0,
                acceptance_report,
                [
                    "acceptance_log_format",
                    "aperiodic_assignment_validity",
                    "aperiodic_miss_consistency",
                    "schedule_log_consistency",
                ],
            ),
            self._auto_item(
                "2-3",
                "Traditional generator constraints 6-12",
                7.0,
                model_report,
                generator_checks,
                pass_reason="all generator constraint checks passed",
            ),
            self._auto_item("2-4", "Renewable constraint 13", 1.0, model_report, ["renewable_output_upper_bound"]),
            self._auto_item("2-5", "Storage constraints 14-19 and 21", 7.0, model_report, storage_checks),
            self._auto_item("2-6", "Sell amount constraint 22", 1.0, model_report, ["sell_non_negative"]),
            self._auto_item("2-7", "Hourly energy balance constraint 23", 4.0, model_report, ["hourly_energy_balance"]),
        ]
        return self._section("2", "Model Constraints", 27.0, items)

    def _section_3(self, report: CheckReport | None) -> ScoreSection:
        items = [
            self._auto_item(
                "3-1",
                "72-hour schedule JSON output",
                2.0,
                report,
                ["schedule_length", "schedule_time_index", "schedule_entry_schema"],
            ),
            self._auto_item(
                "3-2",
                "Periodic jobs complete execution",
                2.0,
                report,
                ["periodic_execution_complete", "energy_demand_per_execution"],
            ),
            self._auto_item(
                "3-3",
                "Periodic jobs deadline and response time",
                4.0,
                report,
                ["no_release_time_violation", "no_deadline_violation", "non_preemptive_contiguity"],
            ),
        ]
        return self._section("3", "Schedule Result and Periodic Task Performance", 8.0, items)

    def _section_4(self, manual_review_required: list[str], acceptance_report: CheckReport | None) -> ScoreSection:
        items = [
            self._manual_item("4-1", "Acceptance test method design", 3.0),
            self._manual_item("4-2", "Accept / reject decision rationale", 3.0),
            self._auto_item(
                "4-3",
                "Sporadic schedule value",
                5.0,
                acceptance_report,
                [
                    "acceptance_log_format",
                    "sporadic_acceptance_validity",
                    "sporadic_rejection_consistency",
                    "sporadic_value_rate_match",
                    "schedule_log_consistency",
                ],
            ),
        ]
        self._record_manual(items, manual_review_required)
        return self._section("4", "Acceptance Test", 11.0, items)

    def _section_5(self, report: CheckReport | None) -> ScoreSection:
        items = [
            self._auto_item(
                "5-1",
                "Hard deadline miss rate",
                1.0,
                report,
                ["deadline_miss_rate_fields", "hard_deadline_miss_rate_match"],
            ),
            self._auto_item("5-2", "Soft deadline miss rate", 1.0, report, ["soft_deadline_miss_rate_match"]),
            self._auto_item("5-3", "Avg / Max Tardiness", 2.0, report, ["tardiness_fields"]),
            self._auto_item("5-4", "Avg / Max Response Time", 2.0, report, ["response_time_fields"]),
            self._auto_item(
                "5-5",
                "Completion-time Jitter",
                1.0,
                report,
                ["completion_time_jitter_field"],
                extra_reason="field validation only; jitter formula remains manual or future-spec review",
            ),
        ]
        return self._section("5", "Evaluation Metrics", 7.0, items)

    def _section_6(self, manual_review_required: list[str]) -> ScoreSection:
        items = [
            self._manual_item("6-1", "Reserve strategy algorithm explanation", 5.0),
            self._manual_item("6-2", "Objective function tradeoff analysis", 5.0),
        ]
        self._record_manual(items, manual_review_required)
        return self._section("6", "Manual Report Review", 10.0, items)

    def _basic_constraints_item(
        self, schedule_report: CheckReport | None, model_report: CheckReport | None
    ) -> ScoreItem:
        schedule_checks = [
            "energy_demand_per_execution",
            "no_release_time_violation",
            "periodic_execution_complete",
            "no_deadline_violation",
            "non_preemptive_contiguity",
        ]
        model_checks = ["device_supply_capacity"]
        statuses = {
            **self._check_statuses(schedule_report, schedule_checks),
            **self._check_statuses(model_report, model_checks),
        }
        passed = all(status in {"PASS", "WARN"} for status in statuses.values())
        reason = (
            "periodic job basic constraints and device supply capacity passed; "
            "sporadic completion is covered by 4-3"
            if passed
            else self._auto_reason(statuses)
        )
        return ScoreItem(
            "2-1",
            "Basic constraints 1-3, 5, and 20",
            5.0,
            5.0 if passed else 0.0,
            "PASS" if passed else "FAIL",
            reason,
            schedule_checks + model_checks,
        )

    def _auto_item(
        self,
        item_id: str,
        name: str,
        max_score: float,
        report: CheckReport | None,
        required_checks: list[str],
        extra_reason: str | None = None,
        pass_reason: str | None = None,
    ) -> ScoreItem:
        check_statuses = self._check_statuses(report, required_checks)
        passed = all(status in {"PASS", "WARN"} for status in check_statuses.values())
        reason = pass_reason if passed and pass_reason else self._auto_reason(check_statuses)
        if extra_reason:
            reason = f"{reason}; {extra_reason}"
        return ScoreItem(item_id, name, max_score, max_score if passed else 0.0, "PASS" if passed else "FAIL", reason, required_checks)

    def _check_statuses(self, report: CheckReport | None, check_ids: Iterable[str]) -> dict[str, str]:
        if report is None:
            return {check_id: "MISSING_REPORT" for check_id in check_ids}
        statuses: dict[str, str] = {}
        for check_id in check_ids:
            severities = [issue.severity for issue in report.issues if issue.check_id == check_id]
            if "FAIL" in severities:
                statuses[check_id] = "FAIL"
            elif "PASS" in severities:
                statuses[check_id] = "PASS"
            elif "WARN" in severities:
                statuses[check_id] = "WARN"
            else:
                statuses[check_id] = "MISSING_CHECK"
        return statuses

    def _auto_reason(self, check_statuses: dict[str, str]) -> str:
        failed = [check_id for check_id, status in check_statuses.items() if status not in {"PASS", "WARN"}]
        if not failed:
            return "all related checks passed"
        return "; ".join(f"{check_id}={check_statuses[check_id]}" for check_id in failed)

    def _manual_item(self, item_id: str, name: str, max_score: float) -> ScoreItem:
        return ScoreItem(item_id, name, max_score, 0.0, "MANUAL", "requires manual review")

    def _section(self, section_id: str, name: str, max_score: float, items: list[ScoreItem]) -> ScoreSection:
        return ScoreSection(section_id, name, max_score, sum(item.score for item in items), items)

    def _record_manual(self, items: list[ScoreItem], manual_review_required: list[str]) -> None:
        for item in items:
            if item.status == "MANUAL":
                manual_review_required.append(f"{item.item_id} {item.name}: {self._format_points(item.max_score)}")

    def _format_points(self, value: float) -> str:
        score = str(int(value)) if value == int(value) else f"{value:.2f}"
        unit = "point" if value == 1 else "points"
        return f"{score} {unit}"
