#!/usr/bin/env python3
"""Run TSA's six-stage self-analysis and emit a prioritized JSON report.

Exit codes:
    0: dogfood completed with no actionable items
    1: dogfood completed with actionable items
    2: a tool or claim-suite invocation failed
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._dogfood_sprint_orchestration import run_dogfood
from scripts._dogfood_sprint_priority import (
    build_priority_matrix,
    count_tool_failures,
    project_health_grade,
)
from scripts._dogfood_sprint_runner import (
    parse_claim_junit_report,
    run_claim_tests,
    run_readme_counts,
    run_tsa,
)

ROOT = Path(__file__).resolve().parent.parent
TOOL_BIN = [sys.executable, "-m", "tree_sitter_analyzer"]
PYTEST_BIN = [sys.executable, "-m", "pytest"]

# Stable helper names retained for tests and downstream script imports.
_build_priority_matrix = build_priority_matrix
_count_tool_failures = count_tool_failures
_project_health_grade = project_health_grade


def _run_tsa(args: list[str], *, timeout: int = 120) -> dict[str, Any]:
    """Run one TSA command through the historical facade injection points."""
    return run_tsa(
        args,
        root=ROOT,
        tool_bin=TOOL_BIN,
        timeout=timeout,
        process_runner=subprocess.run,
        clock=time.perf_counter,
    )


def _parse_claim_junit_report(report_path: Path) -> list[dict[str, Any]]:
    """Parse one claim report through the stable facade helper."""
    return parse_claim_junit_report(report_path)


def _run_claim_tests() -> list[dict[str, Any]]:
    """Run claim invariants through the historical facade injection points."""
    return run_claim_tests(
        root=ROOT,
        pytest_bin=PYTEST_BIN,
        process_runner=subprocess.run,
        report_parser=_parse_claim_junit_report,
    )


def _run_readme_counts() -> dict[str, Any]:
    """Run README count verification through the stable process seam."""
    return run_readme_counts(
        root=ROOT,
        pytest_bin=PYTEST_BIN,
        process_runner=subprocess.run,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="-", help="Output file path (- = stdout)")
    parser.add_argument(
        "--skip-claims",
        action="store_true",
        help="Skip running claim invariant tests (faster)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages",
    )
    return parser.parse_args()


def main() -> int:
    """Execute the dogfood sequence and write its stable report schema."""
    args = _parse_args()

    def log(message: str) -> None:
        if not args.quiet:
            sys.stderr.write(f"[dogfood] {message}\n")

    report, exit_code = run_dogfood(
        skip_claims=args.skip_claims,
        log=log,
        tsa_runner=_run_tsa,
        claim_runner=_run_claim_tests,
        readme_runner=_run_readme_counts,
        priority_builder=_build_priority_matrix,
        grade_resolver=_project_health_grade,
        failure_counter=_count_tool_failures,
    )
    output = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out == "-":
        sys.stdout.write(f"{output}\n")
    else:
        Path(args.out).write_text(output, encoding="utf-8")
        log(f"Report written to {args.out}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
