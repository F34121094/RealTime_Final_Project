"""Export grader reports as JSON and text."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import CheckReport, ReadReport, ScoreReport


class ReportExporter:
    LINE = "=" * 60
    SECTION_LINE = "-" * 60
    MANUAL_REVIEW_ITEMS = (
        "4-1 Acceptance test 方法設計說明：3 分",
        "4-2 Accept / Reject 判斷合理性：3 分",
        "6-1 保留策略演算法說明：5 分",
        "6-2 目標函數權衡分析：5 分",
    )
    ISSUE_TRANSLATIONS = {
        "generator_ramp_limits": (
            "傳統機組 ramp rate 違反",
            "相鄰時段的出力變化超過 ramp_up_rate 或 ramp_down_rate。",
            "模型限制式 / 傳統機組限制",
        ),
        "generator_min_up_time": (
            "傳統機組最小開機時間違反",
            "機組啟動後沒有連續運轉滿 min_up_time。",
            "模型限制式 / 傳統機組限制",
        ),
        "generator_min_down_time": (
            "傳統機組最小關機時間違反",
            "機組關機後沒有連續停機滿 min_down_time。",
            "模型限制式 / 傳統機組限制",
        ),
        "hourly_energy_balance": (
            "每小時供需平衡違反",
            "某些時段總供給不等於任務用電、儲能充電與售電量總和。",
            "模型限制式 / 每小時供需平衡",
        ),
        "renewable_output_upper_bound": (
            "再生能源出力超過 forecast 上限",
            "再生能源輸出超過該時段可用預測發電量。",
            "模型限制式 / 再生能源限制",
        ),
        "storage_soc_transition": (
            "儲能 SOC 轉移不一致",
            "SOC_t 不等於 SOC_{t-1} + charge - discharge。",
            "模型限制式 / 儲能限制",
        ),
        "storage_soc_bounds": (
            "儲能 SOC 超出上下限",
            "儲能設備 SOC 超出 soc_min 或 soc_max。",
            "模型限制式 / 儲能限制",
        ),
        "storage_no_simultaneous_charge_discharge": (
            "儲能同時充放電",
            "同一儲能設備同一時段同時充電與放電。",
            "模型限制式 / 儲能限制",
        ),
        "device_supply_capacity": (
            "設備供電分配超過出力",
            "某設備分配給 jobs 或充電的能量超過該時段設備實際輸出。",
            "模型限制式 / 供電分配",
        ),
        "sell_non_negative": ("售電量為負值", "sell 不可為負值。", "模型限制式 / 售電限制"),
        "evaluation_required_fields": (
            "evaluation_results.json 缺少必要欄位",
            "evaluation_results.json 未包含 Level 1 固定格式要求的必要 metric 欄位。",
            "評估指標",
        ),
        "hard_deadline_miss_rate_match": (
            "Hard deadline miss rate 計算不一致",
            "evaluation_results.json 回報的 hard_deadline_miss_rate 與 grader 根據 schedule_result / acceptance_test_log 重算結果不一致。",
            "評估指標 / Hard deadline",
        ),
        "soft_deadline_miss_rate_match": (
            "Soft deadline miss rate 計算不一致",
            "evaluation_results.json 回報的 soft_deadline_miss_rate 與 grader 重算結果不一致。",
            "評估指標 / Soft deadline",
        ),
        "tardiness_fields": (
            "Tardiness 指標錯誤",
            "average_tardiness 或 max_tardiness 缺失、格式錯誤，或與 grader 重算結果不一致。",
            "評估指標 / Tardiness",
        ),
        "response_time_fields": (
            "Response time 指標錯誤",
            "average_response_time 或 max_response_time 缺失、格式錯誤，或與 grader 重算結果不一致。",
            "評估指標 / Response time",
        ),
        "generator_cost_match": (
            "Generator cost 計算不一致",
            "evaluation_results.json 回報的 generator_cost 與 grader 根據 generator output 重算結果不一致。",
            "評估指標 / 成本",
        ),
        "market_revenue_match": (
            "Market revenue 計算不一致",
            "evaluation_results.json 回報的 market_revenue 與 grader 根據 sell 與 price 重算結果不一致。",
            "評估指標 / 市場收益",
        ),
        "objective_value_match": (
            "Objective value 計算不一致",
            "objective_value 應為 10000 * aperiodic_miss_count + generator_cost - market_revenue。",
            "評估指標 / 目標函數",
        ),
        "sporadic_value_rate_match": (
            "Sporadic value rate 計算不一致",
            "sporadic_value_rate 應根據 deadline 前完成的 sporadic execution time / 官方 sporadic execution time 總和計算。",
            "Acceptance Test / Sporadic value",
        ),
        "acceptance_log_format": (
            "acceptance_test_log.json 格式錯誤",
            "acceptance_test_log.json 缺少必要欄位或格式不符合 grader 預期。",
            "Acceptance Test / Log 格式",
        ),
        "aperiodic_assignment_validity": (
            "Aperiodic job 安排不合法",
            "aperiodic assigned_hours 與 release time、execution time、schedule_result 或 energy demand 不一致。",
            "Acceptance Test / Aperiodic",
        ),
        "aperiodic_miss_consistency": (
            "Aperiodic miss 紀錄不一致",
            "missed_aperiodic / miss flag / completion_time 與 deadline 判斷不一致。",
            "Acceptance Test / Aperiodic",
        ),
        "sporadic_acceptance_validity": (
            "Sporadic acceptance 安排不合法",
            "accepted sporadic job 的 assigned_hours、deadline、energy demand 或 schedule_result 不一致。",
            "Acceptance Test / Sporadic",
        ),
        "sporadic_rejection_consistency": (
            "Sporadic rejection 紀錄不一致",
            "被 rejected 的 sporadic job 不應出現在 schedule_result，且 rejected_sporadic 紀錄需一致。",
            "Acceptance Test / Sporadic",
        ),
        "schedule_log_consistency": (
            "schedule_result 與 acceptance_test_log 不一致",
            "schedule_result 中的 non-periodic jobs 與 acceptance_test_log 紀錄不一致。",
            "Acceptance Test / Schedule log",
        ),
        "non_standard_periodic_key_format": (
            "periodic job key 格式非標準",
            "目前接受 p1_j1 這類 expanded job id，但標準 schedule_result.k 建議使用 p1、p2 這類 task id。",
            "目前不扣分，但建議修正以避免相容性問題。",
        ),
        "generator_min_down_time_horizon_truncated": (
            "排程結尾處 min down time 檢查被 horizon 截斷",
            "部分機組在接近 t=72 時關機，min_down_time 延伸超出 72 小時，因此只能檢查到 horizon 結尾。",
            "這是 warning，不直接扣分。",
        ),
    }

    def export(
        self,
        output_dir: Path,
        submission_dir: Path,
        event_file: Path | None,
        structure_report: CheckReport | None,
        read_report: ReadReport | None,
        task_set_report: CheckReport | None,
        schedule_basic_report: CheckReport | None,
        model_constraint_report: CheckReport | None,
        evaluation_report: CheckReport | None,
        acceptance_report: CheckReport | None,
        score_report: ScoreReport | None,
        summary: dict[str, Any],
    ) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_at = datetime.now().isoformat(timespec="seconds")
        checker_reports = [
            structure_report,
            task_set_report,
            schedule_basic_report,
            model_constraint_report,
            evaluation_report,
            acceptance_report,
        ]
        failed_checks = self._issues_by_severity(checker_reports, "FAIL")
        warning_checks = self._issues_by_severity(checker_reports, "WARN")
        skipped_checks = self._issues_by_severity(checker_reports, "SKIP")
        checker_exceptions = [
            (checker_name, issue)
            for checker_name, issue in failed_checks
            if issue.check_id == "checker_exception"
        ]
        reader_failures = self._reader_issues_by_severity(read_report, "FAIL")
        reader_warnings = self._reader_issues_by_severity(read_report, "WARN")
        resolved_submission_dir = submission_dir.resolve()
        payload = {
            "submission_dir": str(submission_dir),
            "submission_path": str(resolved_submission_dir),
            "submission_name": resolved_submission_dir.name,
            "event_file": self._event_file_label(event_file),
            "event_file_loaded": bool(summary.get("event_file_loaded", self._event_file_loaded(read_report, event_file))),
            "event_file_info": {
                "path": self._event_file_label(event_file),
                "loaded": bool(summary.get("event_file_loaded", self._event_file_loaded(read_report, event_file))),
                "sporadic_count": summary.get("event_file_sporadic_count"),
                "aperiodic_count": summary.get("event_file_aperiodic_count"),
            },
            "report_dir": str(output_dir),
            "generated_at": generated_at,
            "summary": self._to_serializable(summary),
            "failed_checks": self._serialized_reader_issue_list(reader_failures)
            + self._serialized_issue_list(failed_checks),
            "warnings": self._serialized_reader_issue_list(reader_warnings) + self._serialized_issue_list(warning_checks),
            "skipped_checks": self._serialized_issue_list(skipped_checks),
            "checker_exceptions": self._serialized_issue_list(checker_exceptions),
            "manual_review_required": (
                self._to_serializable(score_report.manual_review_required) if score_report is not None else []
            ),
            "reports": {
                "structure": self._to_serializable(structure_report),
                "reader": self._to_serializable(read_report),
                "task_set": self._to_serializable(task_set_report),
                "schedule_basic": self._to_serializable(schedule_basic_report),
                "model_constraints": self._to_serializable(model_constraint_report),
                "evaluation": self._to_serializable(evaluation_report),
                "acceptance": self._to_serializable(acceptance_report),
                "score": self._to_serializable(score_report),
            },
        }

        report_stem = self._report_stem(submission_dir)
        json_report_path = output_dir / f"{report_stem}.json"
        text_report_path = output_dir / f"{report_stem}.txt"

        with json_report_path.open("w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)

        with text_report_path.open("w", encoding="utf-8") as file_obj:
            file_obj.write(
                self._text_report(
                    submission_dir=submission_dir,
                    event_file=event_file,
                    report_dir=output_dir,
                    generated_at=generated_at,
                    summary=summary,
                    read_report=read_report,
                    reports=checker_reports,
                    score_report=score_report,
                )
            )

        return json_report_path, text_report_path

    def _report_stem(self, submission_dir: Path) -> str:
        submission_name = submission_dir.resolve().name or "submission"
        return f"{submission_name}_report"

    def _text_report(
        self,
        submission_dir: Path,
        event_file: Path | None,
        report_dir: Path,
        generated_at: str,
        summary: dict[str, Any],
        read_report: ReadReport | None,
        reports: list[CheckReport | None],
        score_report: ScoreReport | None,
    ) -> str:
        reader_failures = self._reader_issues_by_severity(read_report, "FAIL")
        reader_warnings = self._reader_issues_by_severity(read_report, "WARN")
        checker_failures = self._issues_by_severity(reports, "FAIL")
        checker_warnings = self._issues_by_severity(reports, "WARN")
        checker_skips = self._issues_by_severity(reports, "SKIP")
        all_failures = self._reader_as_issue_tuples(reader_failures) + checker_failures
        all_warnings = self._reader_as_issue_tuples(reader_warnings) + checker_warnings
        overall_status = "FAIL" if all_failures else "PASS"
        lines: list[str] = [
            self.LINE,
            "Level 1 自動評分報告",
            self.LINE,
            "",
            "一、基本資訊",
            self.SECTION_LINE,
            f"繳交資料夾：{submission_dir}",
            f"繳交名稱：{submission_dir.resolve().name}",
            f"Event file：{self._event_file_label(event_file) or 'None'}",
            f"Event file 是否成功載入：{'是' if self._event_file_loaded_from_summary(summary) else '否'}",
            f"Event file sporadic jobs：{summary.get('event_file_sporadic_count')}",
            f"Event file aperiodic jobs：{summary.get('event_file_aperiodic_count')}",
            f"報告輸出位置：{report_dir}",
            f"產生時間：{generated_at}",
            "",
            "二、總覽",
            self.SECTION_LINE,
            f"整體狀態：{overall_status}",
        ]

        if score_report is not None:
            lines.extend(
                [
                    f"自動評分：{self._format_score(score_report.implemented_auto_score)} / {self._format_score(score_report.implemented_auto_max_score)}",
                    f"人工審查：{self._format_score(score_report.manual_review_max_score)} 分",
                    f"Level 1 總分：pending / {self._format_score(score_report.total_max_score)}",
                ]
            )
        else:
            lines.extend(["自動評分：N/A", "人工審查：N/A", "Level 1 總分：pending / 80"])

        lines.extend(["", "Checker 狀態:"])
        lines.extend(self._checker_status_lines(read_report, reports, summary))
        lines.extend(["", "Response time 算法判定:"])
        lines.extend(self._response_time_convention_lines(reports))
        lines.extend(["", "三、各項分數", self.SECTION_LINE])
        lines.extend(self._score_section_lines(score_report))
        lines.extend(["", "四、主要問題摘要", self.SECTION_LINE])
        lines.extend(self._issue_summary_lines(all_failures, empty_message="未發現自動檢查錯誤。"))
        lines.extend(["", "五、主要問題詳情", self.SECTION_LINE])
        lines.extend(self._human_issue_lines(all_failures, empty_message="未發現自動檢查錯誤。", severity="FAIL"))
        lines.extend(["", "六、警告", self.SECTION_LINE])
        lines.extend(self._human_issue_lines(all_warnings, empty_message="無警告。", severity="WARN"))
        lines.extend(["", "七、違規類型與原因總表", self.SECTION_LINE])
        lines.extend(self._violation_reason_table_lines(all_failures, all_warnings))
        lines.extend(["", "八、人工審查項目", self.SECTION_LINE])
        lines.extend(f"- {item}" for item in self.MANUAL_REVIEW_ITEMS)
        lines.extend(["", "九、技術細節摘要", self.SECTION_LINE])
        lines.extend(self._technical_summary_lines(all_failures, all_warnings, checker_skips))

        return "\n".join(lines) + "\n"

    def _checker_status_lines(
        self,
        read_report: ReadReport | None,
        reports: list[CheckReport | None],
        summary: dict[str, Any],
    ) -> list[str]:
        lines = [
            f"- Submission Reader：{self._status_text(len(self._reader_issues_by_severity(read_report, 'FAIL')), len(self._reader_issues_by_severity(read_report, 'WARN')))}",
            f"- Submission Structure Checker：{self._status_text(summary.get('structure_errors', 0), 0)}",
        ]
        for report in reports:
            if report is None or report.checker_name == "Submission Structure Checker":
                continue
            lines.append(f"- {report.checker_name}：{self._status_text(len(report.errors), len(report.warnings))}")
        return lines

    def _response_time_convention_lines(self, reports: list[CheckReport | None]) -> list[str]:
        for report in reports:
            if report is None:
                continue
            for issue in report.issues:
                if issue.check_id != "response_time_fields":
                    continue
                details = issue.details or {}
                lines = [
                    f"- 檢查結果：{issue.severity}，{issue.message}",
                    f"- 偵測到的算法：{details.get('detected_response_time_convention', 'N/A')}",
                    f"- 不 +1 重算：average={details.get('expected_average_response_time', 'N/A')}，max={details.get('expected_max_response_time', 'N/A')}",
                    f"- +1 重算：average={details.get('expected_average_response_time_plus_one', 'N/A')}，max={details.get('expected_max_response_time_plus_one', 'N/A')}",
                    f"- evaluation_results.json 回報：average={details.get('actual_average_response_time', 'N/A')}，max={details.get('actual_max_response_time', 'N/A')}",
                ]
                if "completed_job_count" in details:
                    lines.append(f"- 納入 response time 的完成工作數：{details['completed_job_count']}")
                return lines
        return ["- 未找到 response_time_fields 檢查結果。"]

    def _score_section_lines(self, score_report: ScoreReport | None) -> list[str]:
        if score_report is None:
            return [
                "1. Periodic Task Set 設計：N/A",
                "2. 模型限制式：N/A",
                "3. 排程結果與 Periodic Task 效能：N/A",
                "4. Acceptance Test：N/A",
                "5. 評估指標：N/A",
                "6. 人工報告審查：MANUAL，0 / 10",
            ]

        names = {
            "1": "1. Periodic Task Set 設計",
            "2": "2. 模型限制式",
            "3": "3. 排程結果與 Periodic Task 效能",
            "4": "4. Acceptance Test",
            "5": "5. 評估指標",
        }
        lines: list[str] = []
        for section in score_report.sections:
            label = names.get(section.section_id)
            if label is None:
                continue
            status = self._section_status(section)
            note = "，含 4-1、4-2 人工審查" if section.section_id == "4" else ""
            lines.append(
                f"{label}：{status}，{self._format_score(section.score)} / {self._format_score(section.max_score)}{note}"
            )
        lines.append("6. 人工報告審查：MANUAL，0 / 10，需人工審查")
        return lines

    def _issue_summary_lines(self, issues: list[tuple[str, Any]], *, empty_message: str) -> list[str]:
        if not issues:
            return [empty_message]
        lines = [f"共 {len(issues)} 個主要錯誤："]
        for index, (checker_name, issue) in enumerate(issues, start=1):
            title, _description, _impact = self._issue_translation(self._issue_check_id(issue))
            count = self._issue_count(self._issue_details(issue))
            suffix = f"：{count} 筆" if count is not None else ""
            lines.append(f"{index}. {title}{suffix}")
        return lines

    def _human_issue_lines(
        self,
        issues: list[tuple[str, Any]],
        *,
        empty_message: str,
        severity: str,
    ) -> list[str]:
        if not issues:
            return [empty_message]

        lines: list[str] = []
        for index, (checker_name, issue) in enumerate(issues, start=1):
            check_id = self._issue_check_id(issue)
            title, description, impact = self._issue_translation(check_id)
            lines.extend(
                [
                    f"[{severity} {index}] {title}",
                    f"對應檢查：{checker_name}.{check_id}",
                    f"問題說明：{description}",
                    f"影響項目：{impact}",
                ]
            )
            sample_lines = self._issue_sample_lines(check_id, self._issue_details(issue))
            if sample_lines:
                lines.append("")
                lines.append("違規摘要：" if severity == "FAIL" else "警告摘要：")
                lines.extend(sample_lines)
            lines.append("")
        if lines and lines[-1] == "":
            lines.pop()
        return lines

    def _violation_reason_table_lines(
        self,
        failures: list[tuple[str, Any]],
        warnings: list[tuple[str, Any]],
    ) -> list[str]:
        issues = [("FAIL", checker_name, issue) for checker_name, issue in failures]
        issues.extend(("WARN", checker_name, issue) for checker_name, issue in warnings)
        if not issues:
            return ["未發現違規或警告類型。"]

        lines = ["每列代表一種自動檢查偵測到的違規或警告類型；完整 details 請見同名 JSON report。"]
        for index, (severity, checker_name, issue) in enumerate(issues, start=1):
            details = self._issue_details(issue)
            count = self._issue_count(details)
            count_text = f"，筆數：{count}" if count is not None else ""
            lines.append(
                f"{index}. [{severity}] {self._issue_check_id(issue)}（{checker_name}）："
                f"{self._issue_message(issue)}{count_text}"
            )
        return lines

    def _technical_summary_lines(
        self,
        failures: list[tuple[str, Any]],
        warnings: list[tuple[str, Any]],
        skips: list[tuple[str, Any]],
    ) -> list[str]:
        lines = [
            "完整 details 請見同名 JSON report；TXT 僅保留簡短摘要。",
            f"- Failed Checks：{len(failures)}",
            f"- Warnings：{len(warnings)}",
            f"- Skipped Checks：{len(skips)}",
        ]
        for label, issues in (("FAIL", failures), ("WARN", warnings), ("SKIP", skips)):
            for checker_name, issue in issues:
                detail_summary = self._details_summary(self._issue_details(issue))
                lines.append(f"- [{label}] {checker_name}.{self._issue_check_id(issue)}: {self._issue_message(issue)}{detail_summary}")
        return lines

    def _reader_as_issue_tuples(self, issues: list[Any]) -> list[tuple[str, Any]]:
        return [("Submission Reader", issue) for issue in issues]

    def _issue_check_id(self, issue: Any) -> str:
        return str(getattr(issue, "check_id", getattr(issue, "path", "unknown_check")))

    def _issue_message(self, issue: Any) -> str:
        return str(getattr(issue, "message", ""))

    def _issue_details(self, issue: Any) -> dict[str, Any]:
        details = getattr(issue, "details", None)
        if isinstance(details, dict):
            return details
        fields = getattr(issue, "fields", None)
        if fields:
            return {"missing_fields": fields}
        return {}

    def _issue_translation(self, check_id: str) -> tuple[str, str, str]:
        return self.ISSUE_TRANSLATIONS.get(
            check_id,
            (
                check_id,
                "此檢查未建立專用中文說明；請參考技術細節摘要與同名 JSON report。",
                "需依 check_id 人工判讀",
            ),
        )

    def _issue_count(self, details: Any) -> int | None:
        if isinstance(details, dict):
            count = details.get("count")
            if isinstance(count, int | float) and not isinstance(count, bool):
                return int(count)
            samples = details.get("samples")
            if isinstance(samples, list):
                return len(samples)
            missing_fields = details.get("missing_fields")
            if isinstance(missing_fields, list):
                return len(missing_fields)
        return None

    def _issue_sample_lines(self, check_id: str, details: Any) -> list[str]:
        if not isinstance(details, dict):
            return []

        special_lines = self._special_detail_lines(check_id, details)
        if special_lines:
            return special_lines
        return self._generic_detail_lines(check_id, details)

        lines: list[str] = []
        count = self._issue_count(details)
        if count is not None:
            lines.append(f"- 違規筆數：{count}")
        if isinstance(details.get("missing_fields"), list):
            lines.append("- 缺少欄位：" + ", ".join(str(item) for item in details["missing_fields"]))
        if isinstance(details.get("invalid_fields"), list) and details["invalid_fields"]:
            lines.append(f"- 格式錯誤欄位：{len(details['invalid_fields'])} 筆")

        samples = details.get("samples")
        if isinstance(samples, list):
            for index, sample in enumerate(samples[:5], start=1):
                lines.append(f"- 範例 {index}：{self._format_sample(check_id, sample)}")
        elif not lines:
            lines.append(f"- 細節摘要：{self._details_summary(details).lstrip('；') or '請見 JSON report'}")
        return lines

    def _special_detail_lines(self, check_id: str, details: dict[str, Any]) -> list[str]:
        if check_id == "response_time_fields":
            return self._known_fields_lines(
                details,
                (
                    ("detected_response_time_convention", "偵測到的 response_time 算法"),
                    ("expected_average_response_time", "Grader 重算 average_response_time"),
                    ("expected_average_response_time_plus_one", "Grader 重算 average_response_time（+1 算法）"),
                    ("actual_average_response_time", "evaluation_results.json 回報 average_response_time"),
                    ("expected_max_response_time", "Grader 重算 max_response_time"),
                    ("expected_max_response_time_plus_one", "Grader 重算 max_response_time（+1 算法）"),
                    ("actual_max_response_time", "evaluation_results.json 回報 max_response_time"),
                    ("completed_job_count", "completed_job_count"),
                ),
            )
        if check_id == "objective_value_match":
            lines = ["- 使用公式：10000 * aperiodic_miss_count + generator_cost - market_revenue"]
            lines.extend(
                self._known_fields_lines(
                    details,
                    (
                        ("reason", "原因"),
                        ("aperiodic_miss_count", "aperiodic_miss_count"),
                        ("computed_generator_cost", "computed_generator_cost"),
                        ("computed_market_revenue", "computed_market_revenue"),
                        ("expected_objective_value", "expected_objective_value"),
                        ("actual_objective_value", "actual_objective_value"),
                        ("difference", "difference"),
                        ("computed_generator_cost_available", "computed_generator_cost 可重算"),
                        ("computed_market_revenue_available", "computed_market_revenue 可重算"),
                        ("raw_entry_count", "acceptance_test_log 原始筆數"),
                        ("normalized_entry_count", "成功解析筆數"),
                    ),
                )
            )
            if isinstance(details.get("missing_fields"), list):
                lines.append("- 缺少欄位 missing_fields：" + self._format_list(details["missing_fields"]))
            return lines
        if check_id == "sporadic_value_rate_match":
            lines = self._known_fields_lines(
                details,
                (
                    ("total_sporadic_exec_time", "官方 sporadic execution time 總和"),
                    ("accepted_completed_exec_time", "deadline 前完成的 sporadic execution time"),
                    ("expected", "Grader 重算值 expected"),
                    ("actual", "evaluation_results.json 回報值 actual"),
                    ("denominator_source", "denominator_source"),
                    ("numerator_source", "numerator_source"),
                ),
            )
            completed = details.get("completed_sporadic_jobs")
            if isinstance(completed, list):
                lines.append("- completed_sporadic_jobs：" + self._format_list(completed[:5]))
            not_counted = details.get("not_counted_samples")
            if isinstance(not_counted, list) and not_counted:
                lines.append("- not_counted_samples 前 5 筆：")
                for sample in not_counted[:5]:
                    if isinstance(sample, dict):
                        lines.append(f"  - {sample.get('job_id')}：{sample.get('reason')}")
                    else:
                        lines.append(f"  - {sample}")
            return lines
        if check_id == "hard_deadline_miss_rate_match":
            return self._deadline_rate_detail_lines(
                details,
                expected_label="Grader 重算 hard_deadline_miss_rate",
                actual_label="evaluation_results.json 回報 hard_deadline_miss_rate",
                total_key="total_hard_deadline_jobs",
                missed_key="missed_hard_deadline_jobs",
                hard_deadline=True,
            )
        if check_id == "soft_deadline_miss_rate_match":
            return self._deadline_rate_detail_lines(
                details,
                expected_label="Grader 重算 soft_deadline_miss_rate",
                actual_label="evaluation_results.json 回報 soft_deadline_miss_rate",
                total_key="total_aperiodic_jobs",
                missed_key="missed_aperiodic_jobs",
                hard_deadline=False,
            )
        if check_id == "generator_cost_match":
            lines = self._known_fields_lines(
                details,
                (
                    ("expected_generator_cost", "Grader 重算 generator_cost"),
                    ("actual_generator_cost", "evaluation_results.json 回報 generator_cost"),
                    ("difference", "difference"),
                ),
            )
            self._append_sample_block(
                lines,
                details.get("samples"),
                "前幾筆成本樣本",
                ("t", "generator_id", "output", "fixed_cost", "variable_cost", "computed_cost"),
            )
            return lines
        if check_id == "market_revenue_match":
            lines = self._known_fields_lines(
                details,
                (
                    ("expected_market_revenue", "Grader 重算 market_revenue"),
                    ("actual_market_revenue", "evaluation_results.json 回報 market_revenue"),
                    ("difference", "difference"),
                ),
            )
            self._append_sample_block(
                lines,
                details.get("samples"),
                "前幾筆收益樣本",
                ("t", "sell", "market_price", "revenue"),
            )
            return lines
        if check_id == "evaluation_required_fields":
            lines: list[str] = []
            if isinstance(details.get("missing_fields"), list):
                lines.append("- 缺少欄位 missing_fields：" + self._format_list(details["missing_fields"]))
            invalid_fields = details.get("invalid_fields")
            if isinstance(invalid_fields, list) and invalid_fields:
                lines.append("- 格式錯誤欄位 invalid_fields：")
                for index, item in enumerate(invalid_fields[:5], start=1):
                    lines.append(f"  - {index}. {self._format_sample('invalid_field', item)}")
            present_fields = details.get("present_fields")
            if isinstance(present_fields, list) and present_fields:
                lines.append("- 已出現欄位 present_fields 前 10 筆：" + self._format_list(present_fields[:10]))
            return lines
        return []

    def _deadline_rate_detail_lines(
        self,
        details: dict[str, Any],
        *,
        expected_label: str,
        actual_label: str,
        total_key: str,
        missed_key: str,
        hard_deadline: bool,
    ) -> list[str]:
        lines = self._known_fields_lines(
            details,
            (
                ("expected", expected_label),
                ("actual", actual_label),
                (total_key, total_key),
                (missed_key, missed_key),
            ),
        )
        samples = details.get("samples")
        if isinstance(samples, list) and samples:
            lines.append("- samples 前 5 筆：")
            for index, sample in enumerate(samples[:5], start=1):
                lines.append(f"  - {index}. {self._format_sample('deadline_rate_sample', sample)}")
            if hard_deadline and any(self._completion_before_release(sample) for sample in samples[:5]):
                lines.append(
                    "- 注意：completion_time 早於 release_time，可能代表 acceptance log 的 assigned_hours 或 completion_time 填寫不合理。"
                )
        return lines

    def _generic_detail_lines(self, check_id: str, details: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        count = self._issue_count(details)
        if count is not None:
            lines.append(f"- 違規筆數：{count}")
        for key in self._generic_detail_keys(details):
            if key in {"count", "samples", "missing_fields", "invalid_fields"}:
                continue
            lines.append(f"- {key}：{self._format_value(details[key])}")
        if isinstance(details.get("missing_fields"), list):
            lines.append("- 缺少欄位 missing_fields：" + self._format_list(details["missing_fields"]))
        if isinstance(details.get("invalid_fields"), list) and details["invalid_fields"]:
            lines.append(f"- 格式錯誤欄位 invalid_fields：{len(details['invalid_fields'])} 筆")
        samples = details.get("samples")
        if isinstance(samples, list) and samples:
            lines.append("- samples 前 5 筆：")
            for index, sample in enumerate(samples[:5], start=1):
                lines.append(f"  - {index}. {self._format_sample(check_id, sample)}")
        if lines:
            lines.append("- 完整 details 請見同名 JSON report。")
            return lines
        return ["- 完整細節請見同名 JSON report"]

    def _generic_detail_keys(self, details: dict[str, Any]) -> list[str]:
        prefixes = ("expected", "actual", "computed", "reported", "denominator", "numerator", "total", "completed")
        return [
            key
            for key in details
            if key in {"difference", "reason"} or any(key.startswith(prefix) for prefix in prefixes)
        ]

    def _known_fields_lines(self, details: dict[str, Any], fields: tuple[tuple[str, str], ...]) -> list[str]:
        return [f"- {label}：{self._format_value(details[key])}" for key, label in fields if key in details]

    def _append_sample_block(
        self,
        lines: list[str],
        samples: Any,
        title: str,
        fields: tuple[str, ...],
    ) -> None:
        if not isinstance(samples, list) or not samples:
            return
        lines.append(f"- {title}：")
        for index, sample in enumerate(samples[:5], start=1):
            if isinstance(sample, dict):
                lines.append(f"  - {index}. {self._field_summary(sample, fields)}")
            else:
                lines.append(f"  - {index}. {sample}")

    def _completion_before_release(self, sample: Any) -> bool:
        if not isinstance(sample, dict):
            return False
        completion_time = sample.get("completion_time")
        release_time = sample.get("release_time")
        if isinstance(completion_time, int | float) and isinstance(release_time, int | float):
            return completion_time < release_time
        return False

    def _format_value(self, value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.6g}"
        if isinstance(value, list):
            return self._format_list(value)
        if isinstance(value, dict):
            return self._field_summary(value, tuple(value.keys())[:8])
        return str(value)

    def _format_list(self, values: list[Any]) -> str:
        if not values:
            return "[]"
        return ", ".join(self._format_value(value) for value in values[:10])

    def _format_sample(self, check_id: str, sample: Any) -> str:
        if not isinstance(sample, dict):
            return str(sample)
        if check_id == "generator_ramp_limits":
            return (
                f"t={sample.get('t')}，{sample.get('generator_id')} 從 {sample.get('previous_output')} "
                f"變到 {sample.get('current_output')}，ramp_up_rate={sample.get('ramp_up_rate')}，"
                f"ramp_down_rate={sample.get('ramp_down_rate')}，原因：{sample.get('reason')}"
            )
        if check_id == "generator_min_up_time":
            return (
                f"generator_id={sample.get('generator_id')}，startup_t={sample.get('startup_t')}，"
                f"min_up_time={sample.get('min_up_time')}，required_on_until={sample.get('required_on_until')}，"
                f"first_off_t={sample.get('first_off_t')}"
            )
        if check_id == "generator_min_down_time":
            return (
                f"generator_id={sample.get('generator_id')}，shutdown_t={sample.get('shutdown_t')}，"
                f"min_down_time={sample.get('min_down_time')}，required_off_until={sample.get('required_off_until')}，"
                f"first_on_t={sample.get('first_on_t')}"
            )
        if check_id == "hourly_energy_balance":
            return (
                f"t={sample.get('t')}，total_generation={sample.get('total_generation')}，"
                f"rhs={sample.get('rhs')}，difference={sample.get('difference')}"
            )
        if check_id in {"renewable_output_upper_bound", "storage_soc_transition", "storage_soc_bounds"}:
            return self._field_summary(sample, ("t", "renewable_id", "storage_id", "expected_soc", "actual_soc", "difference", "reason"))
        if check_id in {"storage_no_simultaneous_charge_discharge", "device_supply_capacity", "sell_non_negative"}:
            return self._field_summary(sample, ("t", "storage_id", "device_id", "charge", "discharge", "sell", "reason"))
        return self._field_summary(sample, tuple(sample.keys())[:8])

    def _field_summary(self, data: dict[str, Any], fields: tuple[str, ...]) -> str:
        parts = [f"{field}={data.get(field)}" for field in fields if field in data]
        return "，".join(parts) if parts else str(data)

    def _details_summary(self, details: Any) -> str:
        if not isinstance(details, dict) or not details:
            return ""
        parts: list[str] = []
        if isinstance(details.get("count"), int | float):
            parts.append(f"count={int(details['count'])}")
        if isinstance(details.get("missing_fields"), list):
            parts.append("missing_fields=" + ",".join(str(item) for item in details["missing_fields"][:5]))
        if isinstance(details.get("samples"), list):
            parts.append(f"samples={len(details['samples'])}")
        return "；" + "，".join(parts) if parts else ""

    def _status_text(self, error_count: Any, warning_count: Any) -> str:
        errors = int(error_count or 0)
        warnings = int(warning_count or 0)
        status = "FAIL" if errors else "PASS"
        return f"{status}（錯誤 {errors}，警告 {warnings}）"

    def _section_status(self, section: Any) -> str:
        if any(getattr(item, "status", "") == "FAIL" for item in getattr(section, "items", [])):
            return "FAIL"
        if any(getattr(item, "status", "") == "MANUAL" for item in getattr(section, "items", [])):
            return "MANUAL"
        return "PASS"

    def _issues_by_severity(
        self,
        reports: list[CheckReport | None],
        severity: str,
    ) -> list[tuple[str, Any]]:
        issues: list[tuple[str, Any]] = []
        for report in reports:
            if report is None:
                continue
            for issue in report.issues:
                if issue.severity == severity:
                    issues.append((report.checker_name, issue))
        return issues

    def _reader_issues_by_severity(self, report: ReadReport | None, severity: str) -> list[Any]:
        if report is None:
            return []
        return [issue for issue in report.issues if issue.severity == severity]

    def _issue_lines(self, issues: list[tuple[str, Any]]) -> list[str]:
        lines: list[str] = []
        for checker_name, issue in issues:
            lines.append(f"[{issue.severity}] {checker_name}.{issue.check_id}: {issue.message}")
            if issue.details:
                compact_details = json.dumps(self._to_serializable(issue.details), ensure_ascii=False, separators=(",", ":"))
                lines.append(f"details: {compact_details}")
        return lines

    def _reader_issue_lines(self, issues: list[Any]) -> list[str]:
        lines: list[str] = []
        for issue in issues:
            lines.append(f"[{issue.severity}] Submission Reader.{issue.path}: {issue.message}")
            if issue.fields:
                compact_details = json.dumps({"fields": self._to_serializable(issue.fields)}, ensure_ascii=False, separators=(",", ":"))
                lines.append(f"details: {compact_details}")
        return lines

    def _serialized_issue_list(self, issues: list[tuple[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "checker_name": checker_name,
                "severity": issue.severity,
                "check_id": issue.check_id,
                "message": issue.message,
                "details": self._to_serializable(issue.details),
            }
            for checker_name, issue in issues
        ]

    def _serialized_reader_issue_list(self, issues: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "checker_name": "Submission Reader",
                "severity": issue.severity,
                "check_id": issue.path,
                "message": issue.message,
                "details": {"fields": self._to_serializable(issue.fields)} if issue.fields else {},
            }
            for issue in issues
        ]

    def _event_file_loaded(self, report: ReadReport | None, event_file: Path | None) -> bool:
        if report is None or event_file is None:
            return False
        event_file_paths = {str(event_file), self._event_file_label(event_file)}
        return any(
            issue.severity == "PASS" and issue.path in event_file_paths and issue.message == "event file loaded"
            for issue in report.issues
        )

    def _event_file_loaded_from_summary(self, summary: dict[str, Any]) -> bool:
        return bool(summary.get("event_file_loaded"))

    def _event_file_label(self, event_file: Path | None) -> str | None:
        if event_file is None:
            return None
        if event_file.is_absolute():
            return str(event_file)
        return event_file.as_posix()

    def _to_serializable(self, value: Any) -> Any:
        if value is None:
            return None
        if is_dataclass(value):
            return self._to_serializable(asdict(value))
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): self._to_serializable(item) for key, item in value.items()}
        if isinstance(value, list | tuple | set):
            return [self._to_serializable(item) for item in value]
        if isinstance(value, str | int | float | bool):
            return value
        return str(value)

    def _format_score(self, value: float) -> str:
        return str(int(value)) if value == int(value) else f"{value:.2f}"
