#!/usr/bin/env python3
"""dogfood_sprint.py — Full dogfood sequence using TSA to analyze TSA.

Runs six TSA tools against the project itself and emits a prioritized JSON
task list. This is the data source for the multi-model agent pipeline:

    Opus 4.8 reads this output → writes task briefs → spawns Sonnet dev agents
    Sonnet dev agents → open feature PRs → GPT-5.5 reviews them

Exit codes
----------
0  Dogfood complete, no actionable items found.
1  Dogfood complete, actionable items found.
2  Tool invocation failed (unexpected — check logs).

Output JSON schema
------------------
{
    "generated_at_utc": "<ISO timestamp>",
    "dogfood_sequence": [
        {"tool": "<name>", "status": "ok|error", "elapsed_s": 1.2, "data": {...}}
    ],
    "claim_invariant_status": [
        {"test": "<name>", "status": "passed|failed|xfail|xpass|skipped", "message": "..."}
    ],
    "priority_matrix": [
        {"priority": "P0|P1|P2|P3", "category": "<category>", "title": "<title>",
         "details": "<details>", "verification_command": "<cmd>"}
    ],
    "summary": {
        "work_item_count": N,
        "highest_priority": "P0|P1|P2|None",
        "health_grade": "A|B|C|D|F",
        "claim_failures": N,
        "tool_failures": N
    }
}
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from importlib import import_module
from pathlib import Path
from typing import Any, cast

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

_HELPER_PREFIX = f"{__package__}." if __package__ else ""
_orchestration = import_module(f"{_HELPER_PREFIX}_dogfood_sprint_orchestration")
_priority = import_module(f"{_HELPER_PREFIX}_dogfood_sprint_priority")
_runner = import_module(f"{_HELPER_PREFIX}_dogfood_sprint_runner")

run_dogfood = _orchestration.run_dogfood
build_priority_matrix = _priority.build_priority_matrix
count_tool_failures = _priority.count_tool_failures
project_health_grade = _priority.project_health_grade
parse_claim_junit_report = _runner.parse_claim_junit_report
run_claim_tests = _runner.run_claim_tests
run_readme_counts = _runner.run_readme_counts
run_tsa = _runner.run_tsa

ROOT = Path(__file__).resolve().parent.parent
TOOL_BIN = [sys.executable, "-m", "tree_sitter_analyzer"]
PYTEST_BIN = [sys.executable, "-m", "pytest"]

# Stable helper names retained for tests and downstream script imports.
_build_priority_matrix = build_priority_matrix
_count_tool_failures = count_tool_failures
_project_health_grade = project_health_grade


def _run_tsa(args: list[str], *, timeout: int = 120) -> dict[str, Any]:
    """Run one TSA command through the historical facade injection points."""
    return cast(
        dict[str, Any],
        run_tsa(
            args,
            root=ROOT,
            tool_bin=TOOL_BIN,
            timeout=timeout,
            process_runner=subprocess.run,
            clock=time.perf_counter,
        ),
    )


def _parse_claim_junit_report(report_path: Path) -> list[dict[str, Any]]:
    """Parse one claim report through the stable facade helper."""
    return cast(list[dict[str, Any]], parse_claim_junit_report(report_path))


def _run_claim_tests() -> list[dict[str, Any]]:
    """Run claim invariants through the historical facade injection points."""
    return cast(
        list[dict[str, Any]],
        run_claim_tests(
            root=ROOT,
            pytest_bin=PYTEST_BIN,
            process_runner=subprocess.run,
            report_parser=_parse_claim_junit_report,
        ),
    )


def _run_readme_counts() -> dict[str, Any]:
    """Run README count verification through the stable process seam."""
    return cast(
        dict[str, Any],
        run_readme_counts(
            root=ROOT,
            pytest_bin=PYTEST_BIN,
            process_runner=subprocess.run,
        ),
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

    report, exit_code = cast(
        tuple[dict[str, Any], int],
        run_dogfood(
            skip_claims=args.skip_claims,
            log=log,
            tsa_runner=_run_tsa,
            claim_runner=_run_claim_tests,
            readme_runner=_run_readme_counts,
            priority_builder=_build_priority_matrix,
            grade_resolver=_project_health_grade,
            failure_counter=_count_tool_failures,
        ),
    )
    output = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out == "-":
        sys.stdout.write(f"{output}\n")
        sys.stdout.flush()
    else:
        Path(args.out).write_text(output, encoding="utf-8")
        log(f"Report written to {args.out}")
    summary = report["summary"]
    log(
        "Done. Work items: "
        f"{summary['work_item_count']}, "
        f"highest priority: {summary['highest_priority']}"
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
