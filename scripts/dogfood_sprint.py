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
        "claim_failures": N
    }
}
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TOOL_BIN = [sys.executable, "-m", "tree_sitter_analyzer"]
PYTEST_BIN = [sys.executable, "-m", "pytest"]


# ─── Tool runners ─────────────────────────────────────────────────────────────

def _run_tsa(args: list[str], *, timeout: int = 120) -> dict[str, Any]:
    cmd = [*TOOL_BIN, *args, "--output-format", "json"]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True,
            timeout=timeout, check=False,
        )
        elapsed = time.perf_counter() - t0
        if proc.stdout.strip():
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                data = {"raw": proc.stdout[:2000]}
        else:
            data = {"stderr": proc.stderr[:1000]} if proc.stderr else {}
        return {"status": "ok" if proc.returncode == 0 else "error",
                "elapsed_s": round(elapsed, 2), "data": data}
    except subprocess.TimeoutExpired:
        return {"status": "error", "elapsed_s": timeout,
                "data": {"error": f"timeout after {timeout}s"}}
    except Exception as exc:
        return {"status": "error", "elapsed_s": 0,
                "data": {"error": str(exc)}}


def _run_claim_tests() -> list[dict[str, Any]]:
    """Run the claims benchmark suite and parse results."""
    cmd = [
        *PYTEST_BIN,
        "tests/benchmarks/claims/",
        "-v", "--tb=line", "--no-header", "-q",
        "--override-ini=addopts=--strict-markers --timeout=60",
        "--json-report", "--json-report-file=dogfood-claims-report.json",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True,
            timeout=120, check=False,
        )
        # Try to parse json-report
        report_path = ROOT / "dogfood-claims-report.json"
        if report_path.exists():
            report = json.loads(report_path.read_text())
            results = []
            for test in report.get("tests", []):
                results.append({
                    "test": test.get("nodeid", ""),
                    "status": test.get("outcome", "unknown"),
                    "message": (test.get("call", {}).get("longrepr", "") or "")[:500],
                })
            return results
        # Fallback: parse stdout
        results = []
        for line in proc.stdout.splitlines():
            if " PASSED" in line or " FAILED" in line or " XFAIL" in line or " XPASS" in line:
                parts = line.strip().split()
                name = parts[0] if parts else "unknown"
                status = "passed" if "PASSED" in line else \
                         "failed" if "FAILED" in line else \
                         "xfail" if "XFAIL" in line else "xpass"
                results.append({"test": name, "status": status, "message": ""})
        return results
    except Exception as exc:
        return [{"test": "claims_suite", "status": "error", "message": str(exc)}]


# ─── Priority matrix builder ──────────────────────────────────────────────────

def _build_priority_matrix(
    health: dict, dead_code: dict, constraints: dict,
    claim_results: list[dict],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    # P0: Claim invariant failures (README claims that are false)
    failed_claims = [c for c in claim_results if c["status"] in ("failed", "xpass")]
    for claim in failed_claims:
        items.append({
            "priority": "P0",
            "category": "claim_failure",
            "title": f"Claim invariant failed: {claim['test'].split('::')[-1]}",
            "details": claim["message"][:300],
            "verification_command": "uv run pytest tests/benchmarks/claims/ -v",
        })

    # P0: Unexpected xpass (a fixed claim that needs un-xfail)
    xpass = [c for c in claim_results if c["status"] == "xpass"]
    for claim in xpass:
        items.append({
            "priority": "P0",
            "category": "xpass_needs_un_xfail",
            "title": f"xpass — remove strict xfail: {claim['test'].split('::')[-1]}",
            "details": "A previously-failing claim now passes. Remove the xfail decorator.",
            "verification_command": f"uv run pytest {claim['test']} -v",
        })

    # P1: Architectural constraint violations
    violations = (constraints.get("data", {}).get("violations") or [])
    for v in violations[:5]:
        items.append({
            "priority": "P1",
            "category": "constraint_violation",
            "title": f"Architecture violation: {v.get('rule_name', '?')}",
            "details": str(v)[:300],
            "verification_command": "uv run python -m tree_sitter_analyzer --check-constraints",
        })

    # P2: Files graded D or F in project health
    health_data = health.get("data", {})
    graded_files = health_data.get("files") or health_data.get("file_grades") or []
    df_files = [f for f in graded_files
                if isinstance(f, dict) and f.get("grade") in ("D", "F")]
    for f in df_files[:5]:
        items.append({
            "priority": "P2",
            "category": "health_grade_df",
            "title": f"File graded {f.get('grade')}: {f.get('file_path', '?')}",
            "details": f"Score: {f.get('score', '?')}, weakest: {f.get('weakest_dimension', '?')}",
            "verification_command": (
                f"uv run python -m tree_sitter_analyzer --file-health "
                f"{f.get('file_path', '?')}"
            ),
        })

    # P3: Dead code symbols
    dead_data = dead_code.get("data", {})
    dead_funcs = dead_data.get("dead_functions") or []
    if dead_funcs:
        items.append({
            "priority": "P3",
            "category": "dead_code",
            "title": f"{len(dead_funcs)} potentially dead function(s) detected",
            "details": ", ".join(
                f.get("name", "?") for f in dead_funcs[:10]
            ),
            "verification_command": (
                "uv run python -m tree_sitter_analyzer --dead-code --output-format json"
            ),
        })

    return items


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="-", help="Output file path (- = stdout)")
    parser.add_argument("--skip-claims", action="store_true",
                        help="Skip running claim invariant tests (faster)")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages")
    args = parser.parse_args()

    def log(msg: str) -> None:
        if not args.quiet:
            print(f"[dogfood] {msg}", file=sys.stderr)

    log("Starting full dogfood sequence...")
    sequence: list[dict[str, Any]] = []

    # 1. Project health
    log("1/6 project health...")
    health = _run_tsa(["--project-health"])
    sequence.append({"tool": "project_health", **health})

    # 2. Dead code
    log("2/6 dead code analysis...")
    dead_code = _run_tsa(["--dead-code"], timeout=60)
    sequence.append({"tool": "dead_code", **dead_code})

    # 3. Change impact (current working tree diff)
    log("3/6 change impact...")
    change_impact = _run_tsa(["--change-impact"])
    sequence.append({"tool": "change_impact", **change_impact})

    # 4. Architectural constraints
    log("4/6 architectural constraints...")
    constraints = _run_tsa(["--check-constraints"])
    sequence.append({"tool": "check_constraints", **constraints})

    # 5. README numbers
    log("5/6 README number verification...")
    try:
        readme_proc = subprocess.run(
            [*PYTEST_BIN, "tests/", "-k", "readme_counts", "-v", "--no-header",
             "--override-ini=addopts=--strict-markers --timeout=30"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60, check=False,
        )
        readme_status = "ok" if readme_proc.returncode == 0 else "error"
        sequence.append({
            "tool": "readme_counts",
            "status": readme_status,
            "elapsed_s": 0,
            "data": {"output": readme_proc.stdout[-1000:]},
        })
    except Exception as exc:
        sequence.append({"tool": "readme_counts", "status": "error",
                          "elapsed_s": 0, "data": {"error": str(exc)}})

    # 6. Claim invariants
    claim_results: list[dict] = []
    if not args.skip_claims:
        log("6/6 claim invariant suite...")
        claim_results = _run_claim_tests()
    else:
        log("6/6 claim invariants SKIPPED (--skip-claims)")

    # Build priority matrix
    log("Building priority matrix...")
    health_step = next((s for s in sequence if s["tool"] == "project_health"), {})
    dead_step = next((s for s in sequence if s["tool"] == "dead_code"), {})
    constraint_step = next((s for s in sequence if s["tool"] == "check_constraints"), {})
    priority_matrix = _build_priority_matrix(
        health_step, dead_step, constraint_step, claim_results
    )

    # Overall grade from health data
    health_grade = (
        health_step.get("data", {}).get("overall_grade")
        or health_step.get("data", {}).get("grade")
        or "?"
    )
    highest_priority = "None"
    for level in ("P0", "P1", "P2", "P3"):
        if any(i["priority"] == level for i in priority_matrix):
            highest_priority = level
            break

    claim_failures = sum(1 for c in claim_results if c["status"] == "failed")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dogfood_sequence": sequence,
        "claim_invariant_status": claim_results,
        "priority_matrix": priority_matrix,
        "summary": {
            "work_item_count": len(priority_matrix),
            "highest_priority": highest_priority,
            "health_grade": health_grade,
            "claim_failures": claim_failures,
        },
    }

    output = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out == "-":
        print(output)
    else:
        Path(args.out).write_text(output, encoding="utf-8")
        log(f"Report written to {args.out}")

    log(f"Done. Work items: {len(priority_matrix)}, highest priority: {highest_priority}")
    return 1 if priority_matrix else 0


if __name__ == "__main__":
    sys.exit(main())
