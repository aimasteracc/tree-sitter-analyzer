#!/usr/bin/env python3
"""
Quality Gate - Automated code quality enforcement for tree-sitter-analyzer v2.

Detects:
- Stub functions (pass-only bodies, NotImplementedError, empty returns)
- Fake features (execute() returning hardcoded {"success": True} without real logic)
- Oversized files (>300 lines)
- Missing test coverage (tool files without corresponding tests)

Usage:
    python scripts/quality_gate.py                    # Full scan
    python scripts/quality_gate.py --pre-commit       # Pre-commit mode (fails on CRITICAL)
    python scripts/quality_gate.py --json             # JSON output
    python scripts/quality_gate.py --fix-plan         # Generate fix plan
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Issue:
    file: str
    line: int
    severity: Severity
    category: str
    message: str
    suggestion: str = ""


@dataclass
class ScanResult:
    issues: list[Issue] = field(default_factory=list)
    files_scanned: int = 0
    tools_found: int = 0
    tools_with_tests: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    def to_dict(self) -> dict:
        return {
            "summary": {
                "files_scanned": self.files_scanned,
                "tools_found": self.tools_found,
                "tools_with_tests": self.tools_with_tests,
                "critical": self.critical_count,
                "warnings": self.warning_count,
                "total_issues": len(self.issues),
            },
            "issues": [
                {
                    "file": i.file,
                    "line": i.line,
                    "severity": i.severity.value,
                    "category": i.category,
                    "message": i.message,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
        }


# ---------------------------------------------------------------------------
# AST Helpers
# ---------------------------------------------------------------------------

def _is_pass_only(body: list[ast.stmt]) -> bool:
    """Check if function body is just `pass` (optionally with a docstring)."""
    stmts = [s for s in body if not isinstance(s, ast.Expr) or not isinstance(s.value, ast.Constant)]
    return len(stmts) == 1 and isinstance(stmts[0], ast.Pass)


def _is_not_implemented(body: list[ast.stmt]) -> bool:
    """Check if function body raises NotImplementedError."""
    stmts = [s for s in body if not isinstance(s, ast.Expr) or not isinstance(s.value, ast.Constant)]
    if len(stmts) != 1:
        return False
    stmt = stmts[0]
    if isinstance(stmt, ast.Raise) and stmt.exc:
        if isinstance(stmt.exc, ast.Call) and isinstance(stmt.exc.func, ast.Name):
            return stmt.exc.func.id == "NotImplementedError"
        if isinstance(stmt.exc, ast.Name):
            return stmt.exc.id == "NotImplementedError"
    return False


def _is_trivial_return(body: list[ast.stmt]) -> bool:
    """Check if function body is just returning a hardcoded dict with no real logic."""
    stmts = [s for s in body if not isinstance(s, ast.Expr) or not isinstance(s.value, ast.Constant)]
    if not stmts:
        return True
    # Single return of a dict literal
    if len(stmts) == 1 and isinstance(stmts[0], ast.Return):
        return isinstance(stmts[0].value, ast.Dict)
    return False


def _is_fake_execute(node: ast.FunctionDef) -> bool:
    """Detect execute() methods that wrap everything in try/except and only do trivial work.

    Heuristic: if the function body (inside try) has <=3 real statements
    and they all just build/return a dict, it's likely fake.
    """
    body = node.body
    # Skip docstring
    real_body = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]

    # Pattern: single try/except that catches everything
    if len(real_body) == 1 and isinstance(real_body[0], ast.Try):
        try_body = real_body[0].body
        # Filter docstrings from try body too
        real_try = [s for s in try_body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        # If the try body is just: return {"success": True, ...hardcoded...}
        if len(real_try) == 1 and isinstance(real_try[0], ast.Return):
            return isinstance(real_try[0].value, ast.Dict)
    return False


def _count_real_statements(body: list[ast.stmt]) -> int:
    """Count non-trivial statements (excluding docstrings, pass)."""
    count = 0
    for s in body:
        if isinstance(s, ast.Pass):
            continue
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
            continue
        count += 1
    return count


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------

def scan_stubs(file_path: Path, tree: ast.AST) -> list[Issue]:
    """Detect stub functions and methods."""
    issues = []
    rel = str(file_path)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        name = node.name
        # Skip abstract methods in base classes (these are SUPPOSED to be pass)
        decorators = [
            d.attr if isinstance(d, ast.Attribute) else (d.id if isinstance(d, ast.Name) else "")
            for d in node.decorator_list
        ]
        if "abstractmethod" in decorators:
            continue

        # Skip __init__, __repr__, etc. that legitimately can be minimal
        if name.startswith("__") and name.endswith("__") and name not in ("__init__",):
            continue

        # Check for pass-only
        if _is_pass_only(node.body):
            issues.append(Issue(
                file=rel, line=node.lineno, severity=Severity.CRITICAL,
                category="stub",
                message=f"Function `{name}` has empty body (pass only)",
                suggestion=f"Implement `{name}` or remove it",
            ))

        # Check for NotImplementedError
        elif _is_not_implemented(node.body):
            issues.append(Issue(
                file=rel, line=node.lineno, severity=Severity.CRITICAL,
                category="stub",
                message=f"Function `{name}` raises NotImplementedError",
                suggestion=f"Implement `{name}` or mark as @abstractmethod",
            ))

        # Check for trivial return
        elif name == "execute" and _is_trivial_return(node.body):
            issues.append(Issue(
                file=rel, line=node.lineno, severity=Severity.CRITICAL,
                category="fake_feature",
                message=f"`execute()` returns a hardcoded dict without real logic",
                suggestion="Implement actual functionality in execute()",
            ))

    return issues


def scan_fake_features(file_path: Path, tree: ast.AST) -> list[Issue]:
    """Detect execute() methods that look functional but are actually trivial wrappers."""
    issues = []
    rel = str(file_path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "execute":
            continue

        # Check for fake execute pattern
        if _is_fake_execute(node):
            issues.append(Issue(
                file=rel, line=node.lineno, severity=Severity.WARNING,
                category="fake_feature",
                message="`execute()` has minimal logic (single-statement try body returning hardcoded dict)",
                suggestion="Add real processing logic in execute()",
            ))

    return issues


def scan_file_size(file_path: Path) -> list[Issue]:
    """Flag oversized files."""
    issues = []
    try:
        line_count = len(file_path.read_text(encoding="utf-8").splitlines())
    except Exception:
        return issues

    if line_count > 500:
        issues.append(Issue(
            file=str(file_path), line=1, severity=Severity.WARNING,
            category="file_size",
            message=f"File has {line_count} lines (>500), consider splitting",
            suggestion="Extract related classes into separate modules",
        ))
    elif line_count > 300:
        issues.append(Issue(
            file=str(file_path), line=1, severity=Severity.INFO,
            category="file_size",
            message=f"File has {line_count} lines (>300)",
            suggestion="Consider splitting if the file contains multiple unrelated classes",
        ))

    return issues


def scan_test_coverage(project_root: Path) -> tuple[list[Issue], int, int]:
    """Check that each tool file has a corresponding test file."""
    tools_dir = project_root / "tree_sitter_analyzer_v2" / "mcp" / "tools"
    tests_dirs = [
        project_root / "tests" / "unit",
        project_root / "tests" / "integration",
        project_root / "tests",
    ]

    issues = []
    tool_files = [
        f for f in tools_dir.glob("*.py")
        if f.name not in ("__init__.py", "base.py", "registry.py")
    ]
    tools_count = len(tool_files)
    covered = 0

    for tool_file in tool_files:
        stem = tool_file.stem  # e.g., "search"
        # Look for test files matching test_*<stem>*.py
        found = False
        for test_dir in tests_dirs:
            if not test_dir.exists():
                continue
            matches = list(test_dir.glob(f"test_*{stem}*.py"))
            if matches:
                found = True
                break

        if found:
            covered += 1
        else:
            issues.append(Issue(
                file=str(tool_file), line=1, severity=Severity.CRITICAL,
                category="missing_test",
                message=f"Tool `{tool_file.name}` has no corresponding test file",
                suggestion=f"Create tests/unit/test_{stem}.py with real behavior tests",
            ))

    return issues, tools_count, covered


# ---------------------------------------------------------------------------
# Main Scanner
# ---------------------------------------------------------------------------

def run_scan(project_root: Path) -> ScanResult:
    """Run all quality checks."""
    result = ScanResult()

    # Collect all Python files (excluding tests, fixtures, __pycache__)
    src_dir = project_root / "tree_sitter_analyzer_v2"
    py_files = [
        f for f in src_dir.rglob("*.py")
        if "__pycache__" not in str(f)
    ]

    for py_file in py_files:
        result.files_scanned += 1
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except Exception:
            continue

        # Make paths relative for readability
        try:
            rel_path = py_file.relative_to(project_root)
        except ValueError:
            rel_path = py_file
        py_file_rel = Path(str(rel_path))

        result.issues.extend(scan_stubs(py_file_rel, tree))
        result.issues.extend(scan_fake_features(py_file_rel, tree))
        result.issues.extend(scan_file_size(py_file_rel))

    # Test coverage check
    test_issues, tools_count, covered = scan_test_coverage(project_root)
    result.issues.extend(test_issues)
    result.tools_found = tools_count
    result.tools_with_tests = covered

    return result


def print_report(result: ScanResult) -> None:
    """Print human-readable report."""
    print("=" * 60)
    print("  QUALITY GATE REPORT")
    print("=" * 60)
    print(f"  Files scanned:    {result.files_scanned}")
    print(f"  Tools found:      {result.tools_found}")
    print(f"  Tools with tests: {result.tools_with_tests}/{result.tools_found}")
    print(f"  Issues:           {len(result.issues)}")
    print(f"    CRITICAL:       {result.critical_count}")
    print(f"    WARNING:        {result.warning_count}")
    print("=" * 60)

    if not result.issues:
        print("\n  All checks passed!")
        return

    # Group by severity
    for severity in [Severity.CRITICAL, Severity.WARNING, Severity.INFO]:
        issues = [i for i in result.issues if i.severity == severity]
        if not issues:
            continue
        print(f"\n  [{severity.value}] ({len(issues)} issues)")
        print("-" * 60)
        for issue in issues:
            print(f"  {issue.file}:{issue.line}")
            print(f"    [{issue.category}] {issue.message}")
            if issue.suggestion:
                print(f"    -> {issue.suggestion}")
            print()


def generate_fix_plan(result: ScanResult) -> list[dict]:
    """Generate a prioritized fix plan."""
    plan = []
    for issue in result.issues:
        if issue.severity != Severity.CRITICAL:
            continue
        plan.append({
            "file": issue.file,
            "line": issue.line,
            "category": issue.category,
            "action": issue.suggestion,
            "tdd_steps": [
                f"1. Write a failing test for the expected behavior of {issue.file}",
                "2. Implement the real functionality",
                "3. Run pytest to verify the test passes",
                "4. Run quality_gate.py to verify the issue is resolved",
            ],
        })
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Quality Gate for tree-sitter-analyzer v2")
    parser.add_argument("--pre-commit", action="store_true", help="Pre-commit mode: exit 1 on CRITICAL issues")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--fix-plan", action="store_true", help="Generate fix plan for CRITICAL issues")
    parser.add_argument("--project-root", type=Path, default=None, help="Project root (auto-detected)")
    args = parser.parse_args()

    # Auto-detect project root
    if args.project_root:
        project_root = args.project_root.resolve()
    else:
        # Walk up from this script to find pyproject.toml
        here = Path(__file__).resolve().parent.parent
        if (here / "pyproject.toml").exists():
            project_root = here
        else:
            project_root = Path.cwd()

    if not (project_root / "tree_sitter_analyzer_v2").is_dir():
        print(f"ERROR: {project_root} does not look like the v2 project root", file=sys.stderr)
        return 1

    result = run_scan(project_root)

    if args.json:
        data = result.to_dict()
        if args.fix_plan:
            data["fix_plan"] = generate_fix_plan(result)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_report(result)
        if args.fix_plan and result.critical_count > 0:
            print("\n  FIX PLAN (CRITICAL issues)")
            print("=" * 60)
            plan = generate_fix_plan(result)
            for i, item in enumerate(plan, 1):
                print(f"\n  #{i}: {item['file']}:{item['line']}")
                print(f"      Category: {item['category']}")
                print(f"      Action:   {item['action']}")
                for step in item["tdd_steps"]:
                    print(f"        {step}")

    if args.pre_commit and result.critical_count > 0:
        print(f"\nPRE-COMMIT BLOCKED: {result.critical_count} CRITICAL issues found", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
