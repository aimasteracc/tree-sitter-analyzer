#!/usr/bin/env python3
"""
Self-Hosting Quality Gate — Dynamic Discovery

Automatically discovers ALL analyzers in the analysis package and runs them
on new/modified Python files. No hardcoding — as tools grow, checks grow.

Usage:
    uv run python scripts/self-hosting-gate.py --last-commit
    uv run python scripts/self-hosting-gate.py --last-n 3
    uv run python scripts/self-hosting-gate.py file1.py file2.py
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ANALYSIS_PACKAGE = "tree_sitter_analyzer.analysis"
_METHOD_NAMES = ["analyze_file", "analyze", "detect_file", "detect"]


def _find_analyzers() -> list[tuple[str, str, str]]:
    """Dynamically discover all single-file analyzers.

    Returns: list of (module_name, class_name, method_name)
    """
    import tree_sitter_analyzer.analysis as pkg

    analyzers: list[tuple[str, str, str]] = []

    for _importer, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
        if modname.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{ANALYSIS_PACKAGE}.{modname}")
        except Exception:
            continue

        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if not isinstance(obj, type) or attr_name.startswith("_"):
                continue

            for method in _METHOD_NAMES:
                if not hasattr(obj, method):
                    continue

                init = getattr(obj, "__init__", None)
                if init is None:
                    break
                sig = inspect.signature(init)
                params = list(sig.parameters.keys())

                # Skip tools that require project_root (directory-level)
                if "project_root" in params and "language" not in params:
                    break

                analyzers.append((modname, attr_name, method))
                break

    return analyzers


def get_changed_files(last_n: int = 1) -> list[Path]:
    """Get Python files changed in last N commits."""
    result = subprocess.run(
        ["git", "diff", f"HEAD~{last_n}", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
    )
    return [
        Path(f)
        for f in result.stdout.strip().split("\n")
        if f.endswith(".py") and Path(f).exists()
    ]


def _extract_findings(result: Any) -> tuple[int, dict[str, Any]]:
    """Extract findings count from various result types."""
    # Type annotation coverage
    if hasattr(result, "total_elements") and hasattr(result, "annotated_elements"):
        missing = result.total_elements - result.annotated_elements
        pct = result.coverage_pct if result.total_elements > 0 else 100.0
        return missing, {"coverage_pct": round(pct, 1)}

    # Magic values
    if hasattr(result, "total_count"):
        return result.total_count, {}

    # Code smells, test smells, issues
    for attr in ("smells", "issues", "hotspots", "violations"):
        val = getattr(result, attr, None)
        if val is not None:
            count = len(val) if isinstance(val, list | tuple) else int(val)
            return count, {}

    # Functions (function_size, etc.)
    if hasattr(result, "functions"):
        funcs = result.functions
        if isinstance(funcs, list):
            oversized = sum(1 for f in funcs if getattr(f, "is_oversized", False))
            return oversized, {}
        return 0, {}

    # References (magic values)
    if hasattr(result, "references") and hasattr(result, "total_count"):
        return result.total_count, {}

    # Raw list
    if isinstance(result, list):
        return len(result), {}

    return 0, {}


def run_analyzer(
    modname: str, classname: str, method: str, file_path: Path
) -> dict[str, Any]:
    """Run a single analyzer on a file."""
    try:
        mod = importlib.import_module(f"{ANALYSIS_PACKAGE}.{modname}")
        cls = getattr(mod, classname)

        try:
            instance = cls()
        except TypeError:
            try:
                instance = cls("python")
            except TypeError:
                return {"tool": classname, "status": "skip", "error": "cannot construct"}

        fn = getattr(instance, method)
        result = fn(file_path)

        findings, extra = _extract_findings(result)
        return {"tool": classname, "status": "ok", "findings": findings, **extra}

    except Exception as e:
        return {"tool": classname, "status": "error", "error": str(e)[:120]}


def _check_architecture() -> list[str]:
    """Verify architectural invariants. Returns list of violations."""
    violations: list[str] = []
    analysis_dir = Path("tree_sitter_analyzer/analysis")
    tools_dir = Path("tree_sitter_analyzer/mcp/tools")
    tests_dir = Path("tests")
    registration = Path("tree_sitter_analyzer/mcp/tool_registration.py")

    # Analyzers that are exempt from BaseAnalyzer inheritance
    base_analyzer_exempt = {
        "base.py", "__init__.py",
        "error_recovery.py",   # encoding detection utility, not AST analysis
        "health_score.py",     # aggregates other analyzers, no direct parsing
        "ci_report.py",        # report generator, not analyzer
        "dependency_graph.py", # project-level, cross-file analysis
        "code_clones.py",      # project-level, cross-file analysis
        "design_patterns.py",  # project-level pattern matching
        "semantic_impact.py",  # project-level impact analysis
        "refactoring_suggestions.py",  # aggregates other analyzers
        "java_patterns.py",    # specialized multi-file analysis
        "llm_benchmark.py",    # benchmark harness, not analysis
        "api_discovery.py",    # project-level API scanning
        "coupling_metrics.py", # project-level coupling analysis
        "test_coverage.py",    # project-level test analysis
    }

    if analysis_dir.exists():
        for f in analysis_dir.glob("*.py"):
            content = f.read_text()

            # Rule 1a: No _LANGUAGE_MODULES outside base.py
            if f.name != "base.py" and "_LANGUAGE_MODULES" in content:
                violations.append(
                    f"{f.name}: contains _LANGUAGE_MODULES (use BaseAnalyzer)"
                )

            # Rule 1b: No _EXT_TO_LANG outside base.py
            if f.name not in base_analyzer_exempt and f.name != "base.py" and "_EXT_TO_LANG" in content:
                violations.append(
                    f"{f.name}: contains _EXT_TO_LANG (use BaseAnalyzer._get_parser)"
                )

            # Rule 1c: AST-based analyzers must inherit BaseAnalyzer
            if f.name not in base_analyzer_exempt:
                has_analyze_method = any(
                    m in content
                    for m in ("analyze_file", "def analyze(", "def detect(")
                )
                if has_analyze_method and "BaseAnalyzer" not in content:
                    violations.append(
                        f"{f.name}: has analysis method but does not inherit BaseAnalyzer"
                    )

    # Rule 2: Tool files must be registered (deprecated tools are exempt)
    deprecated_tools = {
        "error_handling_tool.py", "exception_quality_tool.py",
        "error_message_quality_tool.py", "magic_string_tool.py",
        "code_smell_detector_tool.py",
        "dead_code_path_tool.py", "data_clump_tool.py",
        "nesting_depth_tool.py", "loop_complexity_tool.py",
    }
    if tools_dir.exists() and registration.exists():
        reg_content = registration.read_text()
        for f in tools_dir.glob("*_tool.py"):
            if f.name == "base_tool.py" or f.name in deprecated_tools:
                continue
            tool_name = f.stem.removesuffix("_tool")
            if tool_name not in reg_content:
                violations.append(
                    f"{f.name}: tool file not registered in tool_registration.py"
                )

    # Rule 3: Tool count limit
    reg_count = reg_content.count("registry.register(") if registration.exists() else 0
    max_tools = 150
    if reg_count > max_tools:
        violations.append(
            f"Tool count ({reg_count}) exceeds MAX_TOOLS ({max_tools})"
        )

    # Rule 4: Analyzers must have test files
    if analysis_dir.exists() and tests_dir.exists():
        test_file_names: set[str] = set()
        for tf in tests_dir.rglob("test_*.py"):
            test_file_names.add(tf.name)

        for f in analysis_dir.glob("*.py"):
            if f.name in base_analyzer_exempt:
                continue
            expected_test = f"test_{f.stem}.py"
            if expected_test not in test_file_names:
                # Also check for test files that include the analyzer name
                has_test = any(f.stem in tf.name for tf in tests_dir.rglob("test_*.py"))
                if not has_test:
                    violations.append(
                        f"{f.name}: no test file found (expected {expected_test})"
                    )

    return violations


def main() -> None:
    files: list[Path] = []
    do_arch_check = "--architecture" in sys.argv
    fail_threshold = 80

    if "--fail-threshold" in sys.argv:
        idx = sys.argv.index("--fail-threshold")
        fail_threshold = int(sys.argv[idx + 1])

    if "--last-commit" in sys.argv:
        files = get_changed_files(1)
    elif "--last-n" in sys.argv:
        idx = sys.argv.index("--last-n")
        n = int(sys.argv[idx + 1])
        files = get_changed_files(n)
    else:
        files = [Path(f) for f in sys.argv[1:] if f.endswith(".py") and Path(f).exists()]

    # Architecture check (runs regardless of files)
    if do_arch_check:
        print("=" * 50)
        print("Architecture Quality Check")
        arch_violations = _check_architecture()
        if arch_violations:
            print(f"  Found {len(arch_violations)} violations:")
            for v in arch_violations:
                print(f"  ❌ {v}")
            sys.exit(1)
        else:
            print("  ✅ All architecture invariants pass")

    if not files:
        print("No Python files to check.")
        return

    analyzers = _find_analyzers()

    print("Self-Hosting Quality Gate")
    print(f"Files: {len(files)}")
    print(f"Analyzers auto-discovered: {len(analyzers)}")
    for modname, classname, method in analyzers:
        print(f"  - {classname}.{method}() [{modname}]")
    print("=" * 50)

    total_findings = 0
    runs_ok = 0
    runs_fail = 0

    for file_path in files:
        print(f"\n📄 {file_path}")
        for modname, classname, method in analyzers:
            result = run_analyzer(modname, classname, method, file_path)

            if result["status"] == "error":
                runs_fail += 1
                print(f"  ❌ {classname}: {result['error']}")
                continue

            if result["status"] == "skip":
                print(f"  ⏭️  {classname}: skipped (needs project context)")
                continue

            runs_ok += 1
            findings = result["findings"]
            if findings == 0:
                print(f"  ✅ {classname}: clean")
            else:
                total_findings += findings
                if "coverage_pct" in result:
                    print(
                        f"  🔍 {classname}: {result['coverage_pct']}% ({findings} missing)"
                    )
                else:
                    print(f"  🔍 {classname}: {findings} findings")

    total = runs_ok + runs_fail
    score = (runs_ok / total * 100) if total > 0 else 0
    print(f"\n{'=' * 50}")
    print(f"Self-hosting score: {runs_ok}/{total} tools ran ({score:.0f}%)")
    print(f"Total findings: {total_findings}")

    # Enforce quality threshold
    if score < fail_threshold:
        print(f"\n❌ FAIL: Score {score:.0f}% < threshold {fail_threshold}%")
        sys.exit(1)
    else:
        print(f"\n✅ PASS: Score {score:.0f}% >= threshold {fail_threshold}%")


if __name__ == "__main__":
    main()
