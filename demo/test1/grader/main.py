"""CLI entry point for the RTS/VPP submission reader."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .checkers import (
    AcceptanceChecker,
    EvaluationChecker,
    ModelConstraintChecker,
    ScheduleBasicChecker,
    SubmissionStructureChecker,
    TaskSetChecker,
)
from .reader import SubmissionReader
from .reporting import ReportExporter
from .scoring import Level1Scorer
from .models import CheckReport, SubmissionData


DEFAULT_EVENT_FILE = Path("input/aperiodic_n_sporadic.json")


def _print_reader_report(report) -> None:
    print("Reader Report:")
    for issue in report.issues:
        line = f"[{issue.severity}] {issue.path} {issue.message}"
        if issue.fields and issue.message == "has extra top-level fields":
            line += f": {', '.join(issue.fields)}"
        print(line)


def _print_check_report(report) -> None:
    print(f"{report.checker_name}:")
    for issue in report.issues:
        print(f"[{issue.severity}] {issue.check_id}: {issue.message}")
        if issue.severity in {"FAIL", "WARN"} and issue.details:
            print(f"  details: {json.dumps(issue.details, ensure_ascii=False)}")


def _run_checker(checker, data: SubmissionData) -> CheckReport:
    try:
        return checker.check(data)
    except Exception as exc:  # noqa: BLE001 - grader must never crash on one checker
        report = CheckReport(checker_name=getattr(checker, "checker_name", checker.__class__.__name__))
        report.add(
            "FAIL",
            "checker_exception",
            f"{report.checker_name} raised unexpected exception",
            {"exception_type": type(exc).__name__, "exception_message": str(exc)},
        )
        return report


def _format_score(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:.2f}"


def _print_score_report(report) -> None:
    print("Level 1 Score Summary:")
    print(
        "Implemented auto-graded score: "
        f"{_format_score(report.implemented_auto_score)} / {_format_score(report.implemented_auto_max_score)}"
    )
    print(
        "Auto-gradable but not implemented: "
        f"{_format_score(report.not_implemented_auto_max_score)} points"
    )
    print(f"Manual review required: {_format_score(report.manual_review_max_score)} points")
    print(f"Total Level 1 score: pending / {_format_score(report.total_max_score)}")
    if report.submission_invalid:
        print("Submission status: INVALID - structure checker failed")

    print()
    print("Implemented Auto-Graded Sections:")
    for section in report.sections:
        if section.section_id not in {"1", "2", "3", "4", "5"}:
            continue
        print(f"{section.name}: {_format_score(section.score)} / {_format_score(section.max_score)}")
        for item in section.items:
            print(
                f"  [{item.status}] {item.item_id} {item.name}: "
                f"{_format_score(item.score)} / {_format_score(item.max_score)}"
            )
            if item.reason:
                print(f"    reason: {item.reason}")

    if report.not_implemented_items:
        print()
        print("Not Implemented Auto-Graded Items:")
        for item in report.not_implemented_items:
            print(f"- {item}")

    if report.manual_review_required:
        print()
        print("Manual Review Required:")
        for item in report.manual_review_required:
            print(f"- {item}")


def _build_summary(
    submission_dir,
    event_file,
    event_file_loaded,
    event_file_sporadic_count,
    event_file_aperiodic_count,
    report_dir,
    structure_report,
    reader_report,
    task_set_report,
    schedule_basic_report,
    model_constraint_report,
    evaluation_report,
    acceptance_report,
    score_report,
) -> dict[str, Any]:
    resolved_submission_dir = Path(submission_dir).resolve()
    summary: dict[str, Any] = {
        "submission_path": str(resolved_submission_dir),
        "submission_name": resolved_submission_dir.name,
        "event_file": _path_label(event_file),
        "event_file_loaded": event_file_loaded,
        "event_file_sporadic_count": event_file_sporadic_count,
        "event_file_aperiodic_count": event_file_aperiodic_count,
        "report_dir": str(report_dir),
        "structure_passed": structure_report.passed,
        "structure_errors": len(structure_report.errors),
        "files_loaded": reader_report.files_loaded,
        "reader_errors": len(reader_report.errors),
        "reader_warnings": len(reader_report.warnings),
    }
    for prefix, report in (
        ("task_set", task_set_report),
        ("schedule_basic", schedule_basic_report),
        ("model_constraints", model_constraint_report),
        ("evaluation", evaluation_report),
        ("acceptance", acceptance_report),
    ):
        if report is not None:
            summary[f"{prefix}_passed"] = report.passed
            summary[f"{prefix}_errors"] = len(report.errors)
            summary[f"{prefix}_warnings"] = len(report.warnings)
    if score_report is not None:
        summary.update(
            {
                "implemented_auto_score": score_report.implemented_auto_score,
                "implemented_auto_graded_score": score_report.implemented_auto_score,
                "implemented_auto_max_score": score_report.implemented_auto_max_score,
                "manual_review_max_score": score_report.manual_review_max_score,
                "total_level1_max_score": score_report.total_max_score,
                "total_level1_score_pending": f"pending / {score_report.total_max_score:g}",
            }
        )
    return summary


def _event_file_for_report(event_file: Path | None) -> Path:
    return event_file if event_file is not None else DEFAULT_EVENT_FILE


def _path_label(path: Path | None) -> str | None:
    if path is None:
        return None
    if path.is_absolute():
        return str(path)
    return path.as_posix()


def _event_counts(event_data: dict[str, Any] | None) -> tuple[int | None, int | None]:
    if not isinstance(event_data, dict):
        return None, None
    sporadic = event_data.get("sporadic")
    aperiodic = event_data.get("aperiodic")
    return (
        len(sporadic) if isinstance(sporadic, dict) else None,
        len(aperiodic) if isinstance(aperiodic, dict) else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Read an RTS/VPP assignment submission.")
    parser.add_argument("submission_dir", type=Path, help="Path to Submission_xxx directory")
    parser.add_argument("--report-dir", type=Path, help="Directory to write <submission_name>_report.json/txt")
    parser.add_argument("--event-file", type=Path, help="Official aperiodic/sporadic event file for grading")
    args = parser.parse_args()

    structure_report = SubmissionStructureChecker().check(args.submission_dir)
    _print_check_report(structure_report)
    print()

    event_file_for_report = _event_file_for_report(args.event_file)
    data = SubmissionReader().read(args.submission_dir, event_file=args.event_file)
    reader_report = data.read_report
    sporadic_count, aperiodic_count = _event_counts(data.event_file)

    _print_reader_report(reader_report)

    print()
    task_set_report = _run_checker(TaskSetChecker(), data)
    _print_check_report(task_set_report)
    print()
    schedule_basic_report = _run_checker(ScheduleBasicChecker(), data)
    _print_check_report(schedule_basic_report)
    print()
    model_constraint_report = _run_checker(ModelConstraintChecker(), data)
    _print_check_report(model_constraint_report)
    print()
    evaluation_report = _run_checker(EvaluationChecker(), data)
    _print_check_report(evaluation_report)
    print()
    acceptance_report = _run_checker(AcceptanceChecker(), data)
    _print_check_report(acceptance_report)

    print()
    score_report = Level1Scorer().score(
        structure_report,
        task_set_report,
        schedule_basic_report,
        model_constraint_report,
        evaluation_report,
        acceptance_report,
    )
    _print_score_report(score_report)

    report_dir = args.report_dir or args.submission_dir
    summary = _build_summary(
        args.submission_dir,
        event_file_for_report,
        data.event_file is not None,
        sporadic_count,
        aperiodic_count,
        report_dir,
        structure_report,
        reader_report,
        task_set_report,
        schedule_basic_report,
        model_constraint_report,
        evaluation_report,
        acceptance_report,
        score_report,
    )
    json_report_path, text_report_path = ReportExporter().export(
        report_dir,
        args.submission_dir,
        event_file_for_report,
        structure_report,
        reader_report,
        task_set_report,
        schedule_basic_report,
        model_constraint_report,
        evaluation_report,
        acceptance_report,
        score_report,
        summary,
    )
    print()
    print("Reports written:")
    print(f"- {json_report_path}")
    print(f"- {text_report_path}")

    print()
    print("Summary:")
    print(f"structure_passed: {str(summary['structure_passed']).lower()}")
    print(f"structure_errors: {summary['structure_errors']}")
    print(f"files_loaded: {summary['files_loaded']}")
    print(f"reader_errors: {summary['reader_errors']}")
    print(f"reader_warnings: {summary['reader_warnings']}")
    if task_set_report is not None:
        print(f"task_set_passed: {str(task_set_report.passed).lower()}")
        print(f"task_set_errors: {len(task_set_report.errors)}")
        print(f"task_set_warnings: {len(task_set_report.warnings)}")
    if schedule_basic_report is not None:
        print(f"schedule_basic_passed: {str(schedule_basic_report.passed).lower()}")
        print(f"schedule_basic_errors: {len(schedule_basic_report.errors)}")
        print(f"schedule_basic_warnings: {len(schedule_basic_report.warnings)}")
    if model_constraint_report is not None:
        print(f"model_constraints_passed: {str(model_constraint_report.passed).lower()}")
        print(f"model_constraints_errors: {len(model_constraint_report.errors)}")
        print(f"model_constraints_warnings: {len(model_constraint_report.warnings)}")
    if evaluation_report is not None:
        print(f"evaluation_passed: {str(evaluation_report.passed).lower()}")
        print(f"evaluation_errors: {len(evaluation_report.errors)}")
        print(f"evaluation_warnings: {len(evaluation_report.warnings)}")
    if acceptance_report is not None:
        print(f"acceptance_passed: {str(acceptance_report.passed).lower()}")
        print(f"acceptance_errors: {len(acceptance_report.errors)}")
        print(f"acceptance_warnings: {len(acceptance_report.warnings)}")

    if structure_report.errors:
        return 1
    if reader_report.errors:
        return 1
    if task_set_report is not None and task_set_report.errors:
        return 1
    if schedule_basic_report is not None and schedule_basic_report.errors:
        return 1
    if model_constraint_report is not None and model_constraint_report.errors:
        return 1
    if evaluation_report is not None and evaluation_report.errors:
        return 1
    if acceptance_report is not None and acceptance_report.errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
