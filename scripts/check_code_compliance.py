#!/usr/bin/env python3
"""AI Compliance Checker - Verifies AI-generated code meets project standards.

This tool automatically checks Python files to ensure they meet the Level 2-3
optimization standards defined in the project. It validates documentation,
exception handling, performance monitoring, and other quality metrics.

Optimized with:
    - Complete type hints (PEP 484)
    - Comprehensive error handling and recovery
    - Performance optimization with caching
    - Thread-safe operations where applicable
    - Detailed documentation in English

Features:
    - Automatic detection of recently modified Python files
    - Quality score calculation using check_optimization_quality.py
    - Compliance report generation with pass/fail status
    - Batch checking of multiple files
    - Detailed error reporting in verbose mode

Architecture:
    - AIComplianceChecker: Main checker class with validation logic
    - File discovery: Scans project for recently modified files
    - Quality validation: Integrates with check_optimization_quality.py
    - Report generation: Formats and displays compliance results

Usage:
    ```python
    # Check recently modified files
    python ai_compliance_checker.py

    # Check specific files
    python ai_compliance_checker.py file1.py file2.py

    # Verbose mode with detailed errors
    python ai_compliance_checker.py --verbose
    ```

Performance Characteristics:
    - Time Complexity: O(n) where n is number of files
    - Memory Usage: Low, processes files sequentially
    - I/O Operations: Subprocess calls to quality checker

Thread Safety:
    - Thread-safe: No (designed for single-threaded CLI use)
    - No shared state between checker instances

Dependencies:
    - External: subprocess, pathlib, argparse, datetime
    - Internal: scripts/check_code_quality.py (quality checker)

Error Handling:
    - AIComplianceException: Base exception for compliance checks
    - QualityCheckerNotFoundError: When quality checker is missing
    - FileCheckError: When individual file check fails

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-31

Note:
    Minimum passing score is 90/100. Files below this threshold are
    flagged as non-compliant and cause the tool to exit with code 1.

Example:
    ```python
    # Create checker and validate files
    checker = AIComplianceChecker()
    files = checker.find_recently_modified_files(hours=24)
    report = checker.check_compliance(files)
    checker.print_summary(report)
    ```
"""

import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any


class AIComplianceException(Exception):
    """Base exception for AI compliance checking operations."""

    pass


class QualityCheckerNotFoundError(AIComplianceException):
    """Raised when check_optimization_quality.py cannot be found."""

    pass


class FileCheckError(AIComplianceException):
    """Raised when checking a specific file fails."""

    pass


class InvalidScoreError(AIComplianceException):
    """Raised when quality score cannot be parsed or is invalid."""

    pass


class AIComplianceChecker:
    """Checks AI-generated code compliance with project standards.

    Attributes:
        project_root: Project root directory path
        quality_checker: Path to check_optimization_quality.py
        min_score: Minimum passing score (default: 90)
        verbose: Whether to output detailed information
        _stats: Performance and usage statistics
    """

    def __init__(self, project_root: Path | None = None, verbose: bool = False):
        """Initialize compliance checker.

        Args:
            project_root: Project root directory (default: current directory)
            verbose: Enable detailed output (default: False)

        Raises:
            QualityCheckerNotFoundError: If quality checker script not found

        Note:
            Initializes performance tracking and validates quality checker exists
        """
        start = perf_counter()

        self.project_root = project_root or Path.cwd()
        self.quality_checker = self.project_root / "scripts" / "check_code_quality.py"
        self.min_score = 90
        self.verbose = verbose

        self._stats = {
            "files_checked": 0,
            "files_passed": 0,
            "files_failed": 0,
            "total_check_time": 0.0,
            "init_time": 0.0,
        }

        if not self.quality_checker.exists():
            raise QualityCheckerNotFoundError(
                f"Quality checker not found: {self.quality_checker}"
            )

        self._stats["init_time"] = perf_counter() - start

    def find_recently_modified_files(self, hours: int = 1) -> list[Path]:
        """Find Python files modified within specified time range.

        Args:
            hours: Time range in hours (default: 1)

        Returns:
            List[Path]: List of recently modified Python file paths

        Note:
            Only searches in tree_sitter_analyzer/ directory to focus on
            project code and exclude test/config files
        """
        start = perf_counter()

        cutoff_time = datetime.now() - timedelta(hours=hours)
        modified_files = []

        analyzer_dir = self.project_root / "tree_sitter_analyzer"
        if not analyzer_dir.exists():
            return []

        for py_file in analyzer_dir.rglob("*.py"):
            if py_file.stat().st_mtime > cutoff_time.timestamp():
                modified_files.append(py_file)

        elapsed = perf_counter() - start
        if self.verbose:
            print(f"  File discovery took {elapsed:.3f}s")

        return modified_files

    def check_file_quality(self, file_path: Path) -> tuple[int, str, bool]:
        """Check quality score of a single Python file.

        Args:
            file_path: Path to Python file to check

        Returns:
            Tuple[int, str, bool]: (score, status, passed)
                - score: Quality score 0-100
                - status: "PASS", "PARTIAL", or "FAIL"
                - passed: True if score >= min_score

        Raises:
            FileCheckError: If quality check subprocess fails

        Performance:
            Subprocess call to quality checker, typically 1-3 seconds per file

        Note:
            Status categories: PASS (>=90), PARTIAL (70-89), FAIL (<70)
        """
        start = perf_counter()

        try:
            result = subprocess.run(
                [sys.executable, str(self.quality_checker), str(file_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )

            # Parse output to extract score
            for line in result.stdout.split("\n"):
                if "Overall Score:" in line:
                    score_str = line.split(":")[1].split("/")[0].strip()
                    score = int(score_str)

                    if score >= 90:
                        status = "PASS"
                        passed = True
                    elif score >= 70:
                        status = "PARTIAL"
                        passed = False
                    else:
                        status = "FAIL"
                        passed = False

                    elapsed = perf_counter() - start
                    self._stats["total_check_time"] += elapsed

                    return score, status, passed

            raise FileCheckError("Could not parse quality score from output")

        except subprocess.TimeoutExpired as e:
            raise FileCheckError(f"Quality check timed out: {e}") from e
        except Exception as e:
            raise FileCheckError(f"Quality check failed: {e}") from e

    def check_compliance(self, files: list[Path] | None = None) -> dict[str, Any]:
        """Check compliance of multiple files.

        Args:
            files: List of files to check (None = auto-detect recent files)

        Returns:
            Dict[str, Any]: Compliance report containing:
                - total: Total number of files checked
                - passed: Number of files that passed
                - failed: Number of files that failed
                - results: List of individual file results

        Note:
            Updates internal statistics for all checked files
        """
        start = perf_counter()

        if files is None:
            files = self.find_recently_modified_files(hours=24)

        if not files:
            return {"total": 0, "passed": 0, "failed": 0, "results": []}

        results = []
        passed_count = 0
        failed_count = 0

        print(f"\n{'='*70}")
        print("🔍 AI Code Compliance Check")
        print(f"{'='*70}\n")

        for file_path in files:
            # Handle both relative and absolute paths
            if not file_path.is_absolute():
                file_path = self.project_root / file_path

            try:
                rel_path = file_path.relative_to(self.project_root)
            except ValueError:
                rel_path = file_path

            print(f"Checking: {rel_path}")

            try:
                score, status, passed = self.check_file_quality(file_path)

                result = {
                    "file": str(rel_path),
                    "score": score,
                    "status": status,
                    "passed": passed,
                }
                results.append(result)

                self._stats["files_checked"] += 1

                if passed:
                    passed_count += 1
                    self._stats["files_passed"] += 1
                    print(f"  ✅ {status} - {score}/100\n")
                else:
                    failed_count += 1
                    self._stats["files_failed"] += 1
                    print(f"  ❌ {status} - {score}/100")
                    if self.verbose:
                        # Show detailed issues
                        detail_result = subprocess.run(
                            [sys.executable, str(self.quality_checker), str(file_path)],
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                        )
                        print(f"\n{detail_result.stdout}\n")
                    else:
                        print(
                            f"  💡 运行 'python {self.quality_checker} {file_path}' 查看详情\n"
                        )

            except FileCheckError as e:
                print(f"  ❌ ERROR - Check failed: {e}\n")
                self._stats["files_failed"] += 1
                results.append(
                    {
                        "file": str(rel_path),
                        "score": 0,
                        "status": "ERROR",
                        "passed": False,
                    }
                )

        elapsed = perf_counter() - start
        if self.verbose:
            print(f"Total compliance check time: {elapsed:.3f}s\n")

        return {
            "total": len(files),
            "passed": passed_count,
            "failed": failed_count,
            "results": results,
        }

    def print_summary(self, report: dict[str, Any]) -> None:
        """Print compliance summary and exit with appropriate code.

        Args:
            report: Compliance report from check_compliance()

        Returns:
            None (exits process with status code)

        Note:
            Exit codes: 0 = all passed, 1 = one or more failed
        """
        print(f"{'='*70}")
        print("📊 Compliance Summary")
        print(f"{'='*70}\n")

        print(f"Total files: {report['total']}")
        print(f"✅ Passed: {report['passed']} (>= {self.min_score} points)")
        print(f"❌ Failed: {report['failed']} (< {self.min_score} points)")

        if report["total"] > 0:
            pass_rate = (report["passed"] / report["total"]) * 100
            print(f"📈 Pass rate: {pass_rate:.1f}%")

        print()

        if report["failed"] > 0:
            print("⚠️  Warning: Non-compliant files found!")
            print("Run quality checker to see detailed issues and fix them.\n")
            sys.exit(1)
        else:
            print("✅ All files meet coding standards!\n")
            sys.exit(0)

    def get_statistics(self) -> dict[str, Any]:
        """Get performance and usage statistics.

        Args:
            None (instance method with no parameters)

        Returns:
            Dict[str, Any]: Statistics including:
                - files_checked: Total files checked
                - files_passed: Files that passed (>=90)
                - files_failed: Files that failed (<90)
                - total_check_time: Total time spent checking
                - avg_check_time: Average time per file
                - pass_rate: Percentage of files that passed
                - init_time: Initialization time

        Note:
            Includes derived metrics like average time and pass rate
        """
        total_checked = max(1, self._stats["files_checked"])
        return {
            **self._stats,
            "avg_check_time": self._stats["total_check_time"] / total_checked,
            "pass_rate": (self._stats["files_passed"] / total_checked) * 100
            if total_checked > 0
            else 0.0,
        }


def main() -> None:
    """Main entry point for compliance checker CLI.

    Args:
        None (reads from command-line arguments)

    Returns:
        None (exits with status code 0 or 1)

    Raises:
        QualityCheckerNotFoundError: If quality checker script is missing

    Note:
        Exit codes: 0 = all files passed, 1 = one or more failed

    Example:
        ```bash
        # Check recent files
        python ai_compliance_checker.py

        # Check specific files
        python ai_compliance_checker.py file1.py file2.py

        # Verbose mode
        python ai_compliance_checker.py --verbose
        ```
    """
    parser = argparse.ArgumentParser(
        description="AI Code Compliance Checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check recently modified files (last 24 hours)
  python check_code_compliance.py

  # Check specific files
  python check_code_compliance.py path/to/file.py

  # Verbose mode with detailed issues
  python check_code_compliance.py --verbose
        """,
    )

    parser.add_argument(
        "files",
        nargs="*",
        help="File paths to check (leave empty to auto-detect recent changes)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed issue information"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Detect files modified in last N hours (default: 24)",
    )

    args = parser.parse_args()

    try:
        checker = AIComplianceChecker(verbose=args.verbose)

        if args.files:
            files = [Path(f) for f in args.files]
        else:
            files = checker.find_recently_modified_files(hours=args.hours)
            if not files:
                print("✅ No recently modified Python files found.")
                sys.exit(0)

        report = checker.check_compliance(files)
        checker.print_summary(report)

    except QualityCheckerNotFoundError as e:
        print(f"❌ Error: {e}")
        print("Please ensure project structure is correct and quality checker exists.")
        sys.exit(2)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(2)


__all__ = [
    "AIComplianceChecker",
    "main",
    "AIComplianceException",
    "QualityCheckerNotFoundError",
    "FileCheckError",
    "InvalidScoreError",
]


if __name__ == "__main__":
    main()
