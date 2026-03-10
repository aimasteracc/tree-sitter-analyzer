#!/usr/bin/env python
"""Run full coverage report and save results."""

import json
import os
import subprocess  # nosec
import sys


def run_quick_test():
    """Run quick test without coverage to verify tests pass."""
    print("=" * 60)
    print("Running quick test (no coverage) to verify all tests pass...")
    print("=" * 60)

    cmd = [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"]

    result = subprocess.run(  # nosec
        cmd,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    # Write output
    with open("test_output.txt", "w", encoding="utf-8") as f:
        f.write(result.stdout)
        f.write("\n")
        f.write(result.stderr)

    # Print summary
    lines = result.stdout.strip().split("\n")
    print("\n".join(lines[-20:]))

    return result.returncode


def run_coverage():
    """Run pytest with coverage."""
    print("=" * 60)
    print("Running full test suite with coverage...")
    print("=" * 60)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "--cov=tree_sitter_analyzer",
        "--cov-branch",
        "--cov-report=term",
        "--cov-report=json",
        "--cov-report=html",
        "-q",
        "--tb=no",
    ]

    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(  # nosec
        cmd,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    # Write output to file
    with open("coverage_output.txt", "w", encoding="utf-8") as f:
        f.write("=== STDOUT ===\n")
        f.write(result.stdout)
        f.write("\n\n=== STDERR ===\n")
        f.write(result.stderr)
        f.write(f"\n\n=== RETURN CODE: {result.returncode} ===\n")

    print(f"Return code: {result.returncode}")
    print("Output written to coverage_output.txt")

    # Print last 200 lines of stdout
    lines = result.stdout.split("\n")
    print("\n--- Last 200 lines of output ---")
    for line in lines[-200:]:
        print(line)

    return result.returncode


def analyze_coverage():
    """Analyze coverage.json if it exists."""
    print("\n" + "=" * 60)
    print("Analyzing coverage results...")
    print("=" * 60)

    if not os.path.exists("coverage.json"):
        print("coverage.json not found!")
        return

    with open("coverage.json") as f:
        data = json.load(f)

    totals = data.get("totals", {})
    print("\nOverall Coverage:")
    print(f"  Line Coverage: {totals.get('percent_covered', 0):.2f}%")
    print(f"  Covered Lines: {totals.get('covered_lines', 0)}")
    print(f"  Total Lines: {totals.get('num_statements', 0)}")
    print(f"  Missing Lines: {totals.get('missing_lines', 0)}")
    print(f"  Excluded Lines: {totals.get('excluded_lines', 0)}")

    if "covered_branches" in totals:
        print("\nBranch Coverage:")
        print(f"  Covered Branches: {totals.get('covered_branches', 0)}")
        print(f"  Total Branches: {totals.get('num_branches', 0)}")
        print(f"  Missing Branches: {totals.get('missing_branches', 0)}")

    # Analyze by file
    files = data.get("files", {})
    low_coverage = []
    high_coverage = []

    for path, file_data in files.items():
        summary = file_data.get("summary", {})
        percent = summary.get("percent_covered", 0)
        statements = summary.get("num_statements", 0)

        if statements > 20:
            if percent < 50:
                low_coverage.append((path, percent, statements))
            elif percent >= 80:
                high_coverage.append((path, percent, statements))

    print(f"\n\nHigh Coverage Files (>= 80%, > 20 statements): {len(high_coverage)}")
    for path, pct, stmts in sorted(high_coverage, key=lambda x: -x[1])[:10]:
        print(f"  {pct:.1f}% - {os.path.basename(path)} ({stmts} stmts)")

    print(f"\n\nLow Coverage Files (< 50%, > 20 statements): {len(low_coverage)}")
    for path, pct, stmts in sorted(low_coverage, key=lambda x: x[1])[:15]:
        print(f"  {pct:.1f}% - {os.path.basename(path)} ({stmts} stmts)")


def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        return run_quick_test()
    elif len(sys.argv) > 1 and sys.argv[1] == "--analyze":
        analyze_coverage()
        return 0
    else:
        rc = run_coverage()
        if rc == 0:
            analyze_coverage()
        return rc


if __name__ == "__main__":
    sys.exit(main())
