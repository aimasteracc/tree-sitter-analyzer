#!/usr/bin/env python3
"""
Level 2-3 Optimization Quality Checker

This script validates that Python files meet the Level 2-3 optimization standards
established for the tree-sitter-analyzer project.

Usage:
    python check_optimization_quality.py <file_path>
    python check_optimization_quality.py tree_sitter_analyzer/languages/python_plugin.py

Standards Checked:
- Module documentation format
- Custom exception classes (3 per module)
- Public method documentation completeness
- Private method documentation standards
- Performance monitoring presence
- Statistics tracking implementation
- Thread safety documentation
- Exception handling patterns

Author: aisheng.yu
Date: 2026-01-31
"""

import re
import sys
from pathlib import Path
from typing import Any

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


class OptimizationChecker:
    """Quality checker for Level 2-3 optimized Python files."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.content = self.file_path.read_text(encoding="utf-8")
        self.issues: list[str] = []
        self.warnings: list[str] = []
        self.stats: dict[str, Any] = {}

    def check_all(self) -> dict[str, Any]:
        """Run all quality checks."""
        print(f"Checking Checking: {self.file_path.name}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)

        self.check_module_header()
        self.check_exception_classes()
        self.check_public_methods()
        self.check_private_methods()
        self.check_performance_monitoring()
        self.check_statistics_tracking()
        self.check_exports()

        return self.generate_report()

    def check_module_header(self) -> None:
        """Check module docstring format."""
        print("\nModule Header:")

        required_sections = [
            "Optimized with:",
            "- Complete type hints (PEP 484)",
            "- Comprehensive error handling and recovery",
            "- Performance optimization with caching",
            "- Thread-safe operations where applicable",
            "- Detailed documentation in English",
            "Features:",
            "Architecture:",
            "Usage:",
        ]

        # Check for Author/Version/Date with flexible matching
        flexible_patterns = {
            "Author:": r"Author:\s*\S+",
            "Version:": r"Version:\s*\d+\.\d+",
            "Date:": r"Date:\s*\d{4}-\d{2}-\d{2}",
        }

        missing = []
        for section in required_sections:
            if section not in self.content[:3000]:  # Check first 3000 chars
                missing.append(section)

        # Check flexible patterns
        import re

        for label, pattern in flexible_patterns.items():
            if not re.search(pattern, self.content[:3000]):
                missing.append(label)

        if missing:
            self.issues.append(f"Missing module header sections: {', '.join(missing)}")
            print(f"   Missing sections: {len(missing)}")
        else:
            print("   All required sections present")

    def check_exception_classes(self) -> None:
        """Check custom exception hierarchy."""
        print("\n Exception Classes:")

        # Find exception classes
        exception_pattern = r"class (\w+Error)\((\w+)\):"
        exceptions = re.findall(exception_pattern, self.content)

        self.stats["exception_count"] = len(exceptions)

        if len(exceptions) < 3:
            self.issues.append(f"Expected 3 exception classes, found {len(exceptions)}")
            print(f"   Found {len(exceptions)}/3 exception classes")
        else:
            print(f"   Found {len(exceptions)} exception classes")

        # Check pass statement format
        for exc_name, _ in exceptions:
            # Check if pass is on separate line
            exc_section = self._find_section(f"class {exc_name}")
            if exc_section and "pass" in exc_section:
                if not re.search(r"\n\s+pass\s*\n", exc_section):
                    self.warnings.append(
                        f"{exc_name}: 'pass' should be on separate line"
                    )

    def check_public_methods(self) -> None:
        """Check public method documentation."""
        print("\n Public Methods:")

        # Find public methods (not starting with _)
        method_pattern = r"def ([a-z]\w+)\(self[^\)]*\)\s*->\s*[^\:]+:"
        public_methods = re.findall(method_pattern, self.content)

        self.stats["public_method_count"] = len(public_methods)

        required_docs = ["Args:", "Returns:", "Note:"]
        recommended_docs = ["Raises:", "Performance:", "Thread Safety:", "Example:"]

        method_scores = {}
        for method_name in public_methods:
            section = self._find_section(f"def {method_name}(")
            if not section:
                continue

            # Count documentation sections
            has_required = sum(1 for doc in required_docs if doc in section)
            has_recommended = sum(1 for doc in recommended_docs if doc in section)

            total_score = has_required + has_recommended
            method_scores[method_name] = {
                "required": has_required,
                "recommended": has_recommended,
                "total": total_score,
            }

            if has_required < len(required_docs):
                missing = [d for d in required_docs if d not in section]
                self.issues.append(
                    f"{method_name}(): Missing required docs: {', '.join(missing)}"
                )

        # Calculate coverage
        if method_scores:
            avg_required = sum(s["required"] for s in method_scores.values()) / len(
                method_scores
            )
            avg_total = sum(s["total"] for s in method_scores.values()) / len(
                method_scores
            )

            required_pct = (avg_required / len(required_docs)) * 100
            total_pct = (avg_total / (len(required_docs) + len(recommended_docs))) * 100

            self.stats["doc_required_pct"] = required_pct
            self.stats["doc_total_pct"] = total_pct

            print(f"  Required sections: {required_pct:.1f}%")
            print(f"  All sections: {total_pct:.1f}%")

            if required_pct < 100:
                self.issues.append("Some public methods lack required documentation")

    def check_private_methods(self) -> None:
        """Check private method documentation."""
        print("\n Private Methods:")

        # Find private methods (starting with _)
        method_pattern = r"def (_[a-z]\w+)\(self[^\)]*\)\s*->\s*[^\:]+:"
        private_methods = re.findall(method_pattern, self.content)

        self.stats["private_method_count"] = len(private_methods)

        required_docs = ["Args:", "Returns:"]
        missing_count = 0

        for method_name in private_methods:
            section = self._find_section(f"def {method_name}(")
            if not section:
                continue

            # Check for at least Args and Returns
            has_args = "Args:" in section
            has_returns = "Returns:" in section or "Return:" in section

            if not (has_args and has_returns):
                missing_count += 1

        if missing_count > 0:
            self.warnings.append(
                f"{missing_count}/{len(private_methods)} private methods lack Args/Returns docs"
            )
            print(f"   {missing_count} methods need better docs")
        else:
            print(f"   All {len(private_methods)} methods documented")

    def check_performance_monitoring(self) -> None:
        """Check performance monitoring implementation."""
        print("\n Performance Monitoring:")

        # Check for perf_counter usage
        perf_imports = "from time import perf_counter" in self.content
        perf_usage = len(re.findall(r"perf_counter\(\)", self.content))

        self.stats["perf_monitoring_points"] = perf_usage

        if not perf_imports:
            self.issues.append("Missing 'from time import perf_counter' import")
            print("   perf_counter not imported")
        else:
            print("   perf_counter imported")

        if perf_usage < 2:
            self.warnings.append(
                f"Only {perf_usage} performance monitoring points found (recommend 5-8)"
            )
            print(f"   Found {perf_usage} monitoring points")
        else:
            print(f"   Found {perf_usage} monitoring points")

        # Check for performance logging
        log_perf = "log_debug" in self.content or "logger.warning" in self.content
        if log_perf:
            print("   Performance logging present")
        else:
            self.warnings.append("No performance logging found")

    def check_statistics_tracking(self) -> None:
        """Check statistics tracking implementation."""
        print("\n Statistics Tracking:")

        has_stats_dict = "_stats" in self.content
        has_stats_method = "def get_statistics(self)" in self.content

        if has_stats_dict:
            print("   _stats dictionary found")
        else:
            self.issues.append("Missing _stats dictionary for statistics tracking")

        if has_stats_method:
            print("   get_statistics() method found")
        else:
            self.issues.append("Missing get_statistics() method")

        # Check for lock usage with stats
        if has_stats_dict:
            lock_usage = len(re.findall(r"with self\._(\w+_)?lock:", self.content))
            if lock_usage > 0:
                print(f"   Thread-safe with {lock_usage} lock usages")
            else:
                self.warnings.append(
                    "Statistics may not be thread-safe (no locks found)"
                )

    def check_exports(self) -> None:
        """Check __all__ exports."""
        print("\n Exports:")

        # Check for both __all__ = [ and __all__: list = [
        if "__all__" not in self.content:
            self.issues.append("Missing __all__ export list")
            print("  No __all__ found")
            return

        print("  __all__ list present")

        # Check if exceptions are exported
        exception_pattern = r"class (\w+Error)\("
        exceptions = re.findall(exception_pattern, self.content)

        all_section = self._find_section("__all__ = [")
        if all_section:
            for exc in exceptions:
                if f'"{exc}"' not in all_section and f"'{exc}'" not in all_section:
                    self.warnings.append(f"Exception {exc} not exported in __all__")

            print("   __all__ list present")
        else:
            print("   Cannot parse __all__")

    def _find_section(self, pattern: str, lines: int = 50) -> str:
        """Find section of code around pattern."""
        try:
            start = self.content.index(pattern)
            end = start + lines * 80  # Approximate line length
            return self.content[start:end]
        except ValueError:
            return ""

    def generate_report(self) -> dict[str, Any]:
        """Generate final report."""
        print("\n" + "=" * 70)
        print(" SUMMARY")
        print("=" * 70)

        # Calculate score
        total_checks = len(self.issues) + len(self.warnings)
        score = max(0, 100 - (len(self.issues) * 10) - (len(self.warnings) * 3))

        print(f"\n Overall Score: {score}/100")
        print(f"   Issues: {len(self.issues)}")
        print(f"   Warnings: {len(self.warnings)}")

        # Print issues
        if self.issues:
            print("\n ISSUES (Must Fix):")
            for i, issue in enumerate(self.issues, 1):
                print(f"   {i}. {issue}")

        # Print warnings
        if self.warnings:
            print("\n  WARNINGS (Should Fix):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"   {i}. {warning}")

        # Print stats
        if self.stats:
            print("\n METRICS:")
            for key, value in self.stats.items():
                if isinstance(value, float):
                    print(f"   {key}: {value:.1f}")
                else:
                    print(f"   {key}: {value}")

        # Pass/Fail
        print("\n" + "=" * 70)
        if score >= 90:
            print(" PASS - Meets Level 2-3 standards")
            result = "PASS"
        elif score >= 70:
            print("  PARTIAL - Needs improvements")
            result = "PARTIAL"
        else:
            print(" FAIL - Does not meet standards")
            result = "FAIL"
        print("=" * 70)

        return {
            "score": score,
            "result": result,
            "issues": self.issues,
            "warnings": self.warnings,
            "stats": self.stats,
        }


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python check_optimization_quality.py <file_path>")
        print("\nExample:")
        print(
            "  python check_optimization_quality.py tree_sitter_analyzer/languages/python_plugin.py"
        )
        sys.exit(1)

    file_path = sys.argv[1]

    if not Path(file_path).exists():
        print(f" Error: File not found: {file_path}")
        sys.exit(1)

    checker = OptimizationChecker(file_path)
    report = checker.check_all()

    # Exit with appropriate code
    if report["result"] == "PASS":
        sys.exit(0)
    elif report["result"] == "PARTIAL":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
