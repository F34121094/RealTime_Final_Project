"""Checker for Level 1 submission folder structure."""

from __future__ import annotations

from pathlib import Path

from ..models import CheckReport


class SubmissionStructureChecker:
    """Check required Level 1 files and folders without reading their contents."""

    checker_name = "Submission Structure Checker"

    def check(self, submission_dir: str | Path) -> CheckReport:
        base_dir = Path(submission_dir)
        report = CheckReport(checker_name=self.checker_name)

        self._check_file(base_dir, "README.md", "root_readme", "README.md exists", "missing README.md", report)
        self._check_file(base_dir, "report.pdf", "root_report", "report.pdf exists", "missing report.pdf", report)

        self._check_dir(base_dir, "src", "dir_src", "src/ exists", "missing src/", report)
        self._check_dir(base_dir, "input", "dir_input", "input/ exists", "missing input/", report)
        self._check_dir(base_dir, "output", "dir_output", "output/ exists", "missing output/", report)

        self._check_file(
            base_dir,
            "input/processor_settings.json",
            "input_processor_settings",
            "input/processor_settings.json exists",
            "missing input/processor_settings.json",
            report,
        )
        self._check_file(
            base_dir,
            "input/price_72hr.json",
            "input_price_72hr",
            "input/price_72hr.json exists",
            "missing input/price_72hr.json",
            report,
        )
        self._check_file(
            base_dir,
            "input/aperiodic_n_sporadic.json",
            "input_aperiodic_n_sporadic",
            "input/aperiodic_n_sporadic.json exists",
            "missing input/aperiodic_n_sporadic.json",
            report,
        )

        self._check_file(
            base_dir,
            "output/task_set.json",
            "output_task_set",
            "output/task_set.json exists",
            "missing output/task_set.json",
            report,
        )
        self._check_file(
            base_dir,
            "output/schedule_result.json",
            "output_schedule_result",
            "output/schedule_result.json exists",
            "missing output/schedule_result.json",
            report,
        )
        self._check_file(
            base_dir,
            "output/evaluation_results.json",
            "output_evaluation_results",
            "output/evaluation_results.json exists",
            "missing output/evaluation_results.json",
            report,
        )
        self._check_file(
            base_dir,
            "output/acceptance_test_log.json",
            "output_acceptance_test_log",
            "output/acceptance_test_log.json exists",
            "missing output/acceptance_test_log.json",
            report,
        )

        return report

    def _check_file(
        self,
        base_dir: Path,
        relative_path: str,
        check_id: str,
        pass_message: str,
        fail_message: str,
        report: CheckReport,
    ) -> None:
        path = base_dir / relative_path
        if path.is_file():
            report.add("PASS", check_id, pass_message, {"path": relative_path})
        else:
            report.add("FAIL", check_id, fail_message, {"path": relative_path})

    def _check_dir(
        self,
        base_dir: Path,
        relative_path: str,
        check_id: str,
        pass_message: str,
        fail_message: str,
        report: CheckReport,
    ) -> None:
        path = base_dir / relative_path
        if path.is_dir():
            report.add("PASS", check_id, pass_message, {"path": relative_path})
        else:
            report.add("FAIL", check_id, fail_message, {"path": relative_path})
