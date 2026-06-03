"""Convenience entry point for running the packaged Level 1 grader."""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path


def _looks_like_submission(path: Path) -> bool:
    return (path / "input").is_dir() and (path / "output").is_dir()


def _submission_root() -> Path:
    cwd = Path.cwd().resolve()
    script_dir = Path(__file__).resolve().parent

    if _looks_like_submission(cwd):
        return cwd
    if cwd == script_dir and _looks_like_submission(cwd.parent):
        return cwd.parent
    return cwd


def main() -> int:
    submission_root = _submission_root()
    if str(submission_root) not in sys.path:
        sys.path.insert(0, str(submission_root))

    reports_dir = submission_root / "test1" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    from test1.grader.main import main as grader_main

    original_argv = sys.argv[:]
    sys.argv = [
        original_argv[0],
        str(submission_root),
        "--report-dir",
        str(reports_dir),
    ]
    try:
        with open(os.devnull, "w", encoding="utf-8") as devnull, contextlib.redirect_stdout(devnull):
            exit_code = grader_main()
    finally:
        sys.argv = original_argv
    report_stem = f"{submission_root.name or 'submission'}_report"
    print("Reports written:")
    print(f"- {reports_dir / (report_stem + '.json')}")
    print(f"- {reports_dir / (report_stem + '.txt')}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
