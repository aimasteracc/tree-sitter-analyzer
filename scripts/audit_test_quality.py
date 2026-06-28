#!/usr/bin/env python3
"""
Test Quality Audit Script for tree-sitter-analyzer

Detects 6 anti-patterns (P1-P6) in test files using AST analysis:
- P1: assert True only (with no docstring excuse)
- P2: assert <expr> is not None only (with no follow-up validation)
- P3: Always-true assertions (>= 0, > -1, len(...) >= 0)
- P4: Zero assertions (pass only)
- P5: Placeholder tests ("placeholder" string + assert True)
- P6: Loose boundary assertions (>= / > with deterministic counts)

Usage:
    python scripts/audit_test_quality.py [--output PATH] [--strict]
"""

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TestAntiPatternDetector(ast.NodeVisitor):
    """AST visitor to detect anti-patterns in test functions."""

    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.source_lines = source.splitlines()
        self.findings: list[dict[str, Any]] = []
        self.ambiguous_findings: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions and check test functions."""
        if node.name.startswith("test_"):
            self._check_test_function(node)
        self.generic_visit(node)

    def _check_test_function(self, node: ast.FunctionDef) -> None:
        """Analyze a test function for anti-patterns."""
        # Extract function body (filter out docstrings)
        body = node.body
        docstring = None
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
        ):
            docstring = ast.get_docstring(node)
            body = body[1:]

        # Collect assertions
        assertions = []
        has_placeholder_string = False

        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assert):
                assertions.append(stmt)
            # Check for "placeholder" string literal
            if isinstance(stmt, ast.Constant):
                value = stmt.value if isinstance(stmt.value, str) else None
                if value and "placeholder" in value.lower():
                    has_placeholder_string = True

        # Check for ambiguous cases (regression/issue tests)
        is_ambiguous = self._is_ambiguous_test(node, docstring)

        # P4: Zero assertion (pass only)
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            self._add_finding(
                node, "P4", "MUST_DELETE", "Zero assertion (pass only)", is_ambiguous
            )
            return

        if len(body) == 0:
            self._add_finding(
                node, "P4", "MUST_DELETE", "Empty test body", is_ambiguous
            )
            return

        # P1: assert True only
        if len(assertions) == 1 and self._is_assert_true(assertions[0]):
            # Exempt if docstring explains it's intentional
            if not (
                docstring
                and any(
                    kw in docstring.lower()
                    for kw in ["intentional", "expected", "smoke"]
                )
            ):
                self._add_finding(
                    node,
                    "P1",
                    "MUST_DELETE",
                    "assert True only (no meaningful validation)",
                    is_ambiguous,
                )
                return

        # P5: Placeholder test (has "placeholder" string + assert True)
        if has_placeholder_string and any(self._is_assert_true(a) for a in assertions):
            self._add_finding(
                node,
                "P5",
                "MUST_DELETE",
                "Placeholder test (placeholder string + assert True)",
                is_ambiguous,
            )
            return

        # P2: assert <expr> is not None only
        if len(assertions) == 1 and self._is_assert_is_not_none(assertions[0]):
            # Check if there's any follow-up validation
            has_followup = any(not isinstance(stmt, ast.Assert) for stmt in body[1:])
            if not has_followup:
                self._add_finding(
                    node,
                    "P2",
                    "SHOULD_DELETE",
                    "assert is not None only (no follow-up validation)",
                    is_ambiguous,
                )
                return

        # P3: Always-true assertions
        for assertion in assertions:
            if self._is_always_true_assertion(assertion):
                if not self._has_ratchet_exemption(assertion):
                    self._add_finding(
                        node,
                        "P3",
                        "SHOULD_DELETE",
                        "Always-true assertion (>= 0, > -1, etc.)",
                        is_ambiguous,
                    )
                    return

        # P6: Loose boundary assertions (>= / >)
        # Record at most one P6 per test function (dedup by function).
        for assertion in assertions:
            if self._is_loose_boundary_assertion(assertion):
                if not self._has_ratchet_exemption(assertion):
                    self._add_finding(
                        node,
                        "P6",
                        "REVIEW_REQUIRED",
                        "Loose boundary assertion (should use exact ==)",
                        is_ambiguous,
                    )
                    break  # one finding per function; avoid duplicate entries

    def _has_ratchet_exemption(self, assertion: ast.Assert) -> bool:
        """Check if assertion has a 'ratchet: nondeterministic' inline comment.

        Handles multi-line assertions where the comment appears on any line
        from lineno to end_lineno.
        """
        # Check all lines spanned by this assertion for the ratchet comment
        start = assertion.lineno - 1
        end = getattr(assertion, "end_lineno", assertion.lineno)
        for line_idx in range(start, min(end, len(self.source_lines))):
            line = self.source_lines[line_idx]
            if (
                "ratchet: nondeterministic" in line
                or "ratchet:nondeterministic" in line
            ):
                return True
        # Also check the line immediately after (closing paren on next line)
        if end < len(self.source_lines):
            next_line = self.source_lines[end]
            if (
                "ratchet: nondeterministic" in next_line
                or "ratchet:nondeterministic" in next_line
            ):
                return True
        # Also check the assertion message (msg field) for ratchet comment
        if assertion.msg is not None:
            try:
                msg_src = ast.unparse(assertion.msg)
                if "ratchet" in msg_src.lower():
                    return True
            except Exception:
                pass
        return False

    def _is_assert_true(self, assertion: ast.Assert) -> bool:
        """Check if assertion is 'assert True'."""
        if isinstance(assertion.test, ast.Constant) and assertion.test.value is True:
            return True
        return False

    def _is_assert_is_not_none(self, assertion: ast.Assert) -> bool:
        """Check if assertion is 'assert <expr> is not None'."""
        test = assertion.test
        if isinstance(test, ast.Compare):
            if len(test.ops) == 1 and isinstance(test.ops[0], ast.IsNot):
                if len(test.comparators) == 1:
                    comp = test.comparators[0]
                    if isinstance(comp, ast.Constant) and comp.value is None:
                        return True
        return False

    def _is_always_true_assertion(self, assertion: ast.Assert) -> bool:
        """Check for always-true assertions like len(...) >= 0.

        Only flags len() calls and literal numeric comparisons.
        Does NOT flag attribute access (e.g. obj.count >= 0) which may be
        a meaningful invariant check against buggy implementations.
        """
        test = assertion.test
        if not isinstance(test, ast.Compare):
            return False

        if len(test.ops) != 1:
            return False

        op = test.ops[0]
        left = test.left

        # Check for >= 0 or > -1 — but only for len() calls, not attribute access
        if isinstance(op, (ast.GtE, ast.Gt)):
            if len(test.comparators) == 1:
                comp = test.comparators[0]
                # Only flag len(...) >= 0 (mathematically always true)
                is_len_call = (
                    isinstance(left, ast.Call)
                    and isinstance(left.func, ast.Name)
                    and left.func.id == "len"
                )
                if not is_len_call:
                    return False

                # Check for len(...) >= 0
                if isinstance(op, ast.GtE):
                    if isinstance(comp, ast.Constant) and comp.value == 0:
                        return True
                # Check for len(...) > -1
                if isinstance(op, ast.Gt):
                    if isinstance(comp, ast.Constant) and comp.value == -1:
                        return True
                    if isinstance(comp, ast.UnaryOp) and isinstance(comp.op, ast.USub):
                        if (
                            isinstance(comp.operand, ast.Constant)
                            and comp.operand.value == 1
                        ):
                            return True

        return False

    def _is_loose_boundary_assertion(self, assertion: ast.Assert) -> bool:
        """Check for loose boundary assertions (>= / > with likely deterministic counts)."""
        test = assertion.test
        if not isinstance(test, ast.Compare):
            return False

        if len(test.ops) != 1:
            return False

        op = test.ops[0]

        # Only flag >= and > (not < or <=, which are upper bounds)
        if not isinstance(op, (ast.GtE, ast.Gt)):
            return False

        # Check if comparing to a non-zero number (0 is caught by always-true)
        if len(test.comparators) == 1:
            comp = test.comparators[0]
            if (
                isinstance(comp, ast.Constant)
                and isinstance(comp.value, int)
                and comp.value > 0
            ):
                return True

        return False

    def _is_ambiguous_test(self, node: ast.FunctionDef, docstring: str | None) -> bool:
        """Check if test is ambiguous (might be intentional regression test)."""
        # Check function name
        name_lower = node.name.lower()
        if any(kw in name_lower for kw in ["regression", "issue", "bug", "fix"]):
            return True

        # Check docstring for TODO/FIXME (skip) or implementation intent
        if docstring:
            doc_lower = docstring.lower()
            # Skip TODO/FIXME marked tests
            if "todo" in doc_lower or "fixme" in doc_lower:
                return False
            # Look for meaningful intent descriptions
            if any(
                kw in doc_lower
                for kw in ["verify", "ensure", "check", "test that", "should"]
            ):
                return True

        return False

    def _add_finding(
        self,
        node: ast.FunctionDef,
        pattern: str,
        severity: str,
        description: str,
        is_ambiguous: bool,
    ) -> None:
        """Add a finding to the appropriate list."""
        snippet_lines = self.source_lines[
            node.lineno - 1 : min(node.end_lineno, node.lineno + 5)
        ]
        snippet = "\n".join(snippet_lines)

        finding = {
            "file": self.file_path,
            "line": node.lineno,
            "function": node.name,
            "pattern": pattern,
            "severity": severity,
            "description": description,
            "snippet": snippet,
        }

        if is_ambiguous:
            self.ambiguous_findings.append(finding)
        else:
            self.findings.append(finding)


def audit_test_files(test_root: Path) -> tuple[list[dict], list[dict], int]:
    """
    Audit all test files under test_root.

    Returns:
        (findings, ambiguous_findings, total_test_count)
    """
    all_findings = []
    all_ambiguous = []
    total_tests = 0

    test_files = list(test_root.rglob("test_*.py"))

    for test_file in test_files:
        try:
            source = test_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(test_file))

            # Count test functions
            test_count = sum(
                1
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
            )
            total_tests += test_count

            # Run detector
            detector = TestAntiPatternDetector(
                str(test_file.relative_to(test_root.parent)), source
            )
            detector.visit(tree)

            all_findings.extend(detector.findings)
            all_ambiguous.extend(detector.ambiguous_findings)

        except SyntaxError as e:
            print(f"Warning: Syntax error in {test_file}: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"Warning: Error processing {test_file}: {e}", file=sys.stderr)
            continue

    return all_findings, all_ambiguous, total_tests


def generate_report(
    findings: list[dict],
    ambiguous: list[dict],
    total_tests: int,
    output_path: Path | None = None,
) -> dict:
    """Generate JSON report."""
    # Count by pattern and severity
    by_pattern = {}
    by_severity = {}

    for finding in findings:
        pattern = finding["pattern"]
        severity = finding["severity"]
        by_pattern[pattern] = by_pattern.get(pattern, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_tests": total_tests,
            "total_issues": len(findings),
            "ambiguous_cases": len(ambiguous),
            "by_pattern": by_pattern,
            "by_severity": by_severity,
        },
        "findings": findings,
    }

    # Clean state check
    if len(findings) == 0:
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "clean",
            "total_tests": total_tests,
            "issues": [],
        }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2))

        # Also write ambiguous cases
        if ambiguous:
            ambiguous_path = output_path.parent / "ambiguous-tests.json"
            ambiguous_report = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_ambiguous": len(ambiguous),
                "findings": ambiguous,
            }
            ambiguous_path.write_text(json.dumps(ambiguous_report, indent=2))

    return report


def main():
    parser = argparse.ArgumentParser(description="Audit test quality")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/test-audit.json"),
        help="Output JSON report path",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if anti-patterns found (for CI)",
    )
    parser.add_argument(
        "--include-ambiguous",
        action="store_true",
        help="Include ambiguous cases in main findings",
    )

    args = parser.parse_args()

    # Find test root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    test_root = project_root / "tests"

    if not test_root.exists():
        print(f"Error: Test directory not found: {test_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Auditing tests in {test_root}...")
    findings, ambiguous, total_tests = audit_test_files(test_root)

    # Merge ambiguous into findings if requested
    if args.include_ambiguous:
        findings.extend(ambiguous)
        ambiguous = []

    print(f"Found {len(findings)} issues in {total_tests} tests")
    print(f"Found {len(ambiguous)} ambiguous cases")

    report = generate_report(findings, ambiguous, total_tests, args.output)

    # Print summary
    if findings:
        print("\nSummary by severity:")
        for severity, count in sorted(report["summary"]["by_severity"].items()):
            print(f"  {severity}: {count}")
        print("\nSummary by pattern:")
        for pattern, count in sorted(report["summary"]["by_pattern"].items()):
            print(f"  {pattern}: {count}")

    # Strict mode: exit 1 if MUST_DELETE or SHOULD_DELETE issues found
    # REVIEW_REQUIRED (P6) issues are flagged but do not block CI
    blocking_findings = [
        f for f in findings if f.get("severity") in ("MUST_DELETE", "SHOULD_DELETE")
    ]
    if args.strict and len(blocking_findings) > 0:
        print(
            f"\nStrict mode: {len(blocking_findings)} blocking anti-patterns found (MUST_DELETE/SHOULD_DELETE)",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
