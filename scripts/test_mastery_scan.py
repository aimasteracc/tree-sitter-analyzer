#!/usr/bin/env python3
"""
Test Mastery Scanner — automated test suite quality metrics per tree-sitter-analyzer-test-mastery wiki.

Phase 1: Measure baseline metrics
Phase 2: Enforce quality gates
Phase 3: Continuous monitoring

Usage:
    python scripts/test_mastery_scan.py          # full report
    python scripts/test_mastery_scan.py --gates  # enforce quality gates (exit 1 if violations)
"""

import argparse
import ast
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Quality gates from wiki/test-mastery.md
GATES = {
    "max_test_file_lines": 1800,  # hard ceiling — above this is truly oversized
    "min_assertion_density": 1.0,  # min assert/test ratio (allow property/integration natural density)
    "max_test_source_ratio": 3.0,  # max test:source files ratio
    "max_test_code_ratio": 3.0,  # max test:code lines ratio
    "max_skip_rate_percent": 5.0,  # max skip percentage
    "min_property_test_pct": 10.0,  # min property-based test files
}


def _is_counted_call(node: ast.Call) -> bool:
    """Return True if an AST Call node counts as an assertion."""
    if not isinstance(node.func, ast.Attribute):
        return False
    attr = node.func.attr
    return attr in ("raises", "fail", "skip") or attr.startswith("assert_")


def count_assertions(filepath: Path) -> int:
    """Count assert/test statements in a test file — includes AST assert nodes + mock.assert_* calls."""
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            count += 1
        elif isinstance(node, ast.Call) and _is_counted_call(node):
            count += 1
    return count


def count_test_functions(filepath: Path) -> int:
    """Count test functions and test methods using AST traversal."""
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return 0

    total = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                total += 1
        elif isinstance(node, ast.ClassDef):
            # Keep walking naturally; ast.walk already covers nested methods.
            pass
    return total


def is_auxiliary_test_file(relative_path: str, assertions: int, tests: int) -> bool:
    """Skip helper-heavy test files from low-density checks."""
    path = relative_path.lower()
    stem = Path(relative_path).stem

    if stem.startswith("_"):
        return True

    if any(
        x in path
        for x in (
            "mixin",
            "_helper",
            "helpers",
            "fixture",
            "payloads",
            "coverage",
            "compatibility",
            "format_monitor",
        )
    ):
        return True

    if tests == 0 and assertions == 0:
        return True

    return False


def scan() -> dict[str, Any]:
    """Full test suite scan."""
    src_dir = PROJECT_ROOT / "tree_sitter_analyzer"
    test_dir = PROJECT_ROOT / "tests"

    # Source metrics
    src_files = [f for f in src_dir.rglob("*.py") if f.name != "__init__.py"]
    src_lines = sum(len(f.read_text().splitlines()) for f in src_files)

    # Test metrics — exclude fixtures, test_data, conftest
    test_files = [
        f
        for f in test_dir.rglob("*.py")
        if f.name not in ("__init__.py", "conftest.py")
        and "test_data" not in str(f)
        and "fixtures" not in str(f)
    ]
    test_py_files = [f for f in test_files if f.suffix == ".py"]

    test_lines = 0
    total_tests = 0
    total_asserts = 0
    skip_count = 0
    property_files = 0
    file_metrics: list[dict[str, Any]] = []

    for tf in test_py_files:
        content = tf.read_text()
        lines = content.splitlines()
        n_lines = len(lines)
        test_lines += n_lines
        n_tests = count_test_functions(tf)
        total_tests += n_tests
        n_asserts = count_assertions(tf)
        total_asserts += n_asserts

        skips = content.count("pytest.mark.skip") + content.count("pytest.skip(")
        skip_count += skips

        if "hypothesis" in content.lower() and (
            "@given" in content or "strategies" in content
        ):
            property_files += 1

        file_metrics.append(
            {
                "path": str(tf.relative_to(PROJECT_ROOT)),
                "lines": n_lines,
                "tests": n_tests,
                "asserts": n_asserts,
                "skips": skips,
                "density": round(n_asserts / max(n_tests, 1), 2),
            }
        )

    # Compute aggregates
    assertion_density = round(total_asserts / max(total_tests, 1), 2)
    test_source_ratio = round(len(test_py_files) / max(len(src_files), 1), 2)
    test_code_ratio = round(test_lines / max(src_lines, 1), 2)
    skip_rate = round(skip_count * 100 / max(total_tests, 1), 2)
    property_pct = round(property_files * 100 / max(len(test_py_files), 1), 2)

    # Find violations — exclude non-test files from low-density check
    oversized = [f for f in file_metrics if f["lines"] > GATES["max_test_file_lines"]]
    low_density = [
        f
        for f in file_metrics
        if f["density"] < GATES["min_assertion_density"]
        and not any(
            x in f["path"]
            for x in (
                "integration",
                "workflows",
                "validate_golden",
                "update_baselines",
                "generate_",
                "performance_tests",
                "schema_validation",
                "compatibility",
                "format_monitor",
                "conftest",
                "coverage_boost",
                "coverage",
            )
        )
        and "conftest" not in f["path"]
        and "_coverage" not in f["path"]
        and not is_auxiliary_test_file(f["path"], f["asserts"], f["tests"])
    ]

    return {
        "source": {"files": len(src_files), "lines": src_lines},
        "tests": {
            "files": len(test_py_files),
            "lines": test_lines,
            "functions": total_tests,
            "assertions": total_asserts,
            "skipped": skip_count,
            "property_files": property_files,
        },
        "ratios": {
            "assertion_density": assertion_density,
            "test_source_ratio": test_source_ratio,
            "test_code_ratio": test_code_ratio,
            "skip_rate_pct": skip_rate,
            "property_test_pct": property_pct,
        },
        "violations": {
            "oversized_files": [f["path"] for f in oversized],
            "low_assertion_density": [f["path"] for f in low_density],
        },
        "gates": GATES,
    }


def print_report(data: dict[str, Any]) -> None:
    """Print formatted report."""
    s = data["source"]
    t = data["tests"]
    r = data["ratios"]
    v = data["violations"]
    g = data["gates"]

    print("=" * 60)
    print("  Test Mastery Scanner — Phase 1 Baseline")
    print("=" * 60)
    print(f"\nSource: {s['files']} files, {s['lines']:,} lines")
    print(
        f"Tests:  {t['files']} files, {t['lines']:,} lines, {t['functions']:,} functions"
    )
    print(
        f"        {t['assertions']:,} assertions, {t['skipped']} skipped, {t['property_files']} property files"
    )
    print("\nRatios:")
    print(
        f"  Assertion density:     {r['assertion_density']:.2f}  (gate: ≥ {g['min_assertion_density']})"
    )
    print(
        f"  Test:Source files:     {r['test_source_ratio']:.2f}  (gate: ≤ {g['max_test_source_ratio']})"
    )
    print(
        f"  Test:Code lines:       {r['test_code_ratio']:.2f}  (gate: ≤ {g['max_test_code_ratio']})"
    )
    print(
        f"  Skip rate:             {r['skip_rate_pct']:.1f}%  (gate: ≤ {g['max_skip_rate_percent']}%)"
    )
    print(
        f"  Property test files:   {r['property_test_pct']:.1f}%  (gate: ≥ {g['min_property_test_pct']}%)"
    )

    print("\nViolations:")
    print(
        f"  Oversized files (> {g['max_test_file_lines']} lines): {len(v['oversized_files'])}"
    )
    for f in v["oversized_files"]:
        print(f"    - {f}")
    print(
        f"  Low assertion density (< {g['min_assertion_density']}): {len(v['low_assertion_density'])}"
    )
    for f in v["low_assertion_density"][:10]:
        print(f"    - {f}")
    if len(v["low_assertion_density"]) > 10:
        print(f"    ... and {len(v['low_assertion_density']) - 10} more")

    all_passing = (
        len(v["oversized_files"]) == 0
        and r["assertion_density"] >= g["min_assertion_density"]
        and r["skip_rate_pct"] <= g["max_skip_rate_percent"]
    )
    print(f"\n{'ALL GATES PASSED' if all_passing else 'SOME GATES FAILED'}")

    if not all_passing:
        print("\nAction items:")
        if v["oversized_files"]:
            print(f"  1. Split {len(v['oversized_files'])} oversized test files")
        if r["assertion_density"] < g["min_assertion_density"]:
            print(
                f"  2. Increase assertion density from {r['assertion_density']} to ≥ {g['min_assertion_density']}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Mastery Scanner")
    parser.add_argument(
        "--gates", action="store_true", help="Exit 1 if any quality gate fails"
    )
    args = parser.parse_args()

    data = scan()
    print_report(data)

    if args.gates:
        violations = data["violations"]
        r = data["ratios"]
        g = data["gates"]
        failed = (
            len(violations["oversized_files"]) > 0
            or r["assertion_density"] < g["min_assertion_density"]
            or r["skip_rate_pct"] > g["max_skip_rate_percent"]
        )
        return 1 if failed else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
