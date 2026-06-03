"""Data models for reading RTS/VPP assignment submissions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ReadIssue:
    """A single reader event reported to the CLI or later checkers."""

    severity: str
    path: str
    message: str
    fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReadReport:
    """Structured report produced while reading a submission."""

    issues: list[ReadIssue] = field(default_factory=list)
    files_loaded: int = 0

    @property
    def errors(self) -> list[ReadIssue]:
        return [issue for issue in self.issues if issue.severity == "FAIL"]

    @property
    def warnings(self) -> list[ReadIssue]:
        return [issue for issue in self.issues if issue.severity == "WARN"]

    @property
    def passes(self) -> list[ReadIssue]:
        return [issue for issue in self.issues if issue.severity == "PASS"]

    def add(self, severity: str, path: str, message: str, fields: list[str] | None = None) -> None:
        self.issues.append(ReadIssue(severity=severity, path=path, message=message, fields=fields or []))


@dataclass(slots=True)
class SubmissionData:
    """Unified data object for a submission.

    The reader keeps parsed JSON as-is except for schedule_result, which is
    normalized to the required schedule_result list.
    """

    submission_dir: Path
    processor_settings: dict[str, Any] | None
    price_72hr: dict[str, Any] | None
    task_set: dict[str, Any] | None
    schedule_result: list[Any] | None
    evaluation_results: dict[str, Any] | None
    acceptance_test_log: Any | None
    event_file: dict[str, Any] | None
    read_report: ReadReport


@dataclass(slots=True)
class CheckIssue:
    """A single issue from a checker."""

    severity: str
    check_id: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CheckReport:
    """Structured report produced by a checker."""

    checker_name: str
    issues: list[CheckIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[CheckIssue]:
        return [issue for issue in self.issues if issue.severity == "FAIL"]

    @property
    def warnings(self) -> list[CheckIssue]:
        return [issue for issue in self.issues if issue.severity == "WARN"]

    @property
    def skipped(self) -> list[CheckIssue]:
        return [issue for issue in self.issues if issue.severity == "SKIP"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def add(
        self,
        severity: str,
        check_id: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.issues.append(
            CheckIssue(severity=severity, check_id=check_id, message=message, details=details or {})
        )


@dataclass(slots=True)
class ScoreItem:
    item_id: str
    name: str
    max_score: float
    score: float
    status: str
    reason: str
    related_checks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScoreSection:
    section_id: str
    name: str
    max_score: float
    score: float
    items: list[ScoreItem] = field(default_factory=list)


@dataclass(slots=True)
class ScoreReport:
    level: str
    total_max_score: float
    implemented_auto_score: float
    implemented_auto_max_score: float
    not_implemented_auto_max_score: float
    manual_review_max_score: float
    sections: list[ScoreSection] = field(default_factory=list)
    manual_review_required: list[str] = field(default_factory=list)
    not_implemented_items: list[str] = field(default_factory=list)
    submission_invalid: bool = False

    @property
    def max_score(self) -> float:
        return self.total_max_score

    @property
    def auto_score(self) -> float:
        return self.implemented_auto_score
