#!/usr/bin/env python3
"""AST-based loose-assertion ratchet — Layer-1 CI gate.

Parses Python test files with the ``ast`` module and flags ``assert``
statements whose test expression contains a Compare node with a ``>=`` or
``>`` operator applied against an integer literal (or where the left side is a
``len()`` call with the same operators).

This replaces the grep core of ``check_loose_assertions.sh`` so that
multi-line assert statements — which the grep approach could not see — are
now caught.

Usage (diff-scoped, normal CI mode)::

    python scripts/check_loose_assertions.py [<base-ref>]

Baseline count mode (one-time re-pin)::

    python scripts/check_loose_assertions.py --baseline

Exit codes:
    0  no violations (or baseline mode always exits 0)
    1  violations found
    2  usage / configuration error

Exemption marker::

    assert result >= 1  # ratchet: nondeterministic <reason>

The marker may appear on ANY line within the assert statement's source
segment (``ast.get_source_segment`` spanning ``lineno`` … ``end_lineno``).
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXEMPTION_RE = re.compile(r"#\s*ratchet:\s*nondeterministic")
PROPERTY_FILE_RE = re.compile(r"[Pp]ropert", re.IGNORECASE)

# Operators we consider "loose" bounds when compared against int literals
_LOOSE_OPS = (ast.GtE, ast.Gt)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class Violation(NamedTuple):
    path: str
    lineno: int
    snippet: str
    end_lineno: int = 0
    operator: str = ""
    category: str = "general"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _is_int_literal(node: ast.expr) -> bool:
    """Return True for integer constant literals (0, 1, 2, …)."""
    return isinstance(node, ast.Constant) and isinstance(node.value, int)


def _is_loose_compare(compare: ast.Compare) -> bool:
    """Return True if the Compare contains a >= / > check against an int.

    Catches all four original grep patterns:
      1.  assert expr >= N       (GtE, any left-hand expr)
      2.  assert expr > 0        (Gt,  any left-hand expr, right == 0)
      3.  assert len(x) >= N     (GtE, left is len() call)
      4.  assert len(x) > N      (Gt,  left is len() call)

    A compare node can chain: ``a < b < c``.  We scan every op+comparator
    pair and flag if any matches.
    """
    pairs = zip(compare.ops, compare.comparators, strict=False)
    for op, comparator in pairs:
        if isinstance(op, ast.GtE) and _is_int_literal(comparator):
            return True
        if isinstance(op, ast.Gt) and _is_int_literal(comparator):
            return True
    return False


def _assert_has_eq_compare(assert_node: ast.Assert) -> bool:
    """Return True if the assert's test contains any == comparison.

    Lines that already use ``==`` are exact assertions and MUST NOT be
    flagged as loose (mirrors the grep-time ``== skip`` rule).
    """
    for node in ast.walk(assert_node.test):
        if isinstance(node, ast.Compare):
            if any(isinstance(op, ast.Eq) for op in node.ops):
                return True
    return False


def _find_loose_compares(assert_node: ast.Assert) -> list[ast.Compare]:
    """Return all Compare nodes inside the assert that are loose bounds."""
    result = []
    for node in ast.walk(assert_node.test):
        if isinstance(node, ast.Compare) and _is_loose_compare(node):
            result.append(node)
    return result


def _loose_operator(compare: ast.Compare) -> str:
    """Return the first loose operator in *compare* as source-like text."""
    for op, comparator in zip(compare.ops, compare.comparators, strict=False):
        if isinstance(op, ast.GtE) and _is_int_literal(comparator):
            return ">="
        if isinstance(op, ast.Gt) and _is_int_literal(comparator):
            return ">"
    return ""


def _category_for_path(path: Path) -> str:
    """Best-effort triage category for baseline queueing."""
    lowered = path.as_posix().lower()
    if "benchmark" in lowered or "performance" in lowered:
        return "performance"
    if "property" in lowered:
        return "property"
    if "platform" in lowered or "windows" in lowered or "macos" in lowered:
        return "platform"
    if "optional" in lowered or "dependency" in lowered:
        return "optional-dependency"
    return "general"


# ---------------------------------------------------------------------------
# Source-segment exemption check
# ---------------------------------------------------------------------------


def _segment_is_exempt(source_lines: list[str], lineno: int, end_lineno: int) -> bool:
    """Return True if the exemption marker appears in the assert's source lines.

    ``lineno`` and ``end_lineno`` are 1-based, inclusive (as AST provides).
    """
    segment = source_lines[lineno - 1 : end_lineno]
    for line in segment:
        if EXEMPTION_RE.search(line):
            return True
    return False


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------


def check_file(path: Path) -> list[Violation]:
    """Return Violation entries for every loose assert in the file."""
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # Unparseable file — skip silently (CI lint step catches syntax errors)
        return []

    source_lines = source.splitlines()
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue

        # Skip asserts that already have an == comparison — they are exact
        if _assert_has_eq_compare(node):
            continue

        loose = _find_loose_compares(node)
        if not loose:
            continue

        end = getattr(node, "end_lineno", node.lineno)

        # Check for exemption marker in the assert's source segment
        if _segment_is_exempt(source_lines, node.lineno, end):
            continue

        # Build a short snippet (first line of the assert)
        snippet = source_lines[node.lineno - 1].strip() if source_lines else ""
        operator = _loose_operator(loose[0])
        violations.append(
            Violation(
                str(path),
                node.lineno,
                snippet,
                end,
                operator,
                _category_for_path(path),
            )
        )

    return violations


# ---------------------------------------------------------------------------
# Diff-scoped mode helpers
# ---------------------------------------------------------------------------


def _added_line_ranges(base_ref: str) -> dict[str, set[int]]:
    """Map changed test file (new path) → set of ADDED line numbers.

    Parses ``git diff -U0`` hunk headers so the ratchet can scope violations
    to lines the PR actually added (Codex P1 on #586: scanning whole changed
    files re-flagged the 1000+ pre-existing baseline asserts on any touch).
    ``--diff-filter=AMR`` includes renamed files — additions inside a rename
    must not evade the gate (Codex P2 on #586); ``+++ b/`` carries the new
    path for renames.
    """
    result = subprocess.run(
        [
            "git",
            "diff",
            f"{base_ref}..HEAD",
            "--unified=0",
            "--diff-filter=AMR",
            "--",
            "tests",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    added: dict[str, set[int]] = {}
    current: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            added.setdefault(current, set())
        elif line.startswith("+++ "):
            current = None  # /dev/null (deletion) or unexpected form
        elif line.startswith("@@") and current is not None:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                added[current].update(range(start, start + count))
    return added


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def check_diff(base_ref: str) -> int:
    """Run diff-scoped check.  Returns exit code (0 = OK, 1 = violations).

    A violation counts only when its assert source segment overlaps a line
    the PR added — pre-existing loose asserts elsewhere in a touched file
    stay the baseline's problem, not this PR's.
    """
    added = _added_line_ranges(base_ref)
    all_violations: list[Violation] = []
    for fname, added_lines in added.items():
        if not added_lines:
            continue
        path = Path(fname)
        if path.suffix != ".py" or not path.exists():
            continue
        # Skip hypothesis property test files (same whitelist as .sh)
        if PROPERTY_FILE_RE.search(path.name):
            continue
        for v in check_file(path):
            end = v.end_lineno or v.lineno
            if added_lines.intersection(range(v.lineno, end + 1)):
                all_violations.append(v)

    if not all_violations:
        return 0

    print(f"❌ Found {len(all_violations)} new loose assertion(s) in the PR diff:\n")
    for v in all_violations:
        print(f"  {v.path}:{v.lineno}: {v.snippet}")
    print()
    print("Loose assertion patterns detected:")
    print("  assert ... >= N   (GtE against integer literal)")
    print("  assert ... > N    (Gt  against integer literal)")
    print()
    print("To exempt a line, add comment anywhere in the assert block:")
    print("  assert x >= 1  # ratchet: nondeterministic <reason>")
    return 1


def count_baseline(tests_dir: Path) -> int:
    """Count all loose assertions under *tests_dir* using AST rules."""
    return len(baseline_violations(tests_dir))


def baseline_violations(tests_dir: Path) -> list[Violation]:
    """Return all baseline loose assertions under *tests_dir* using AST rules."""
    violations: list[Violation] = []
    for py_file in sorted(tests_dir.rglob("*.py")):
        if PROPERTY_FILE_RE.search(py_file.name):
            continue
        violations.extend(check_file(py_file))
    return violations


def _repo_relative(path: str, project_root: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def format_baseline_json(violations: list[Violation], project_root: Path) -> str:
    """Format violations as stable machine-readable JSON."""
    payload = [
        {
            "path": _repo_relative(v.path, project_root),
            "line": v.lineno,
            "end_line": v.end_lineno or v.lineno,
            "operator": v.operator,
            "snippet": v.snippet,
            "category": v.category,
            "exemption": None,
        }
        for v in violations
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_baseline_table(violations: list[Violation], project_root: Path) -> str:
    """Format violations as a short human-readable summary table."""
    by_path = Counter(_repo_relative(v.path, project_root) for v in violations)
    lines = [f"Total loose assertions: {len(violations)}", "", "| path | count |"]
    lines.append("|---|---:|")
    for path, count in by_path.most_common():
        lines.append(f"| {path} | {count} |")
    return "\n".join(lines)


def count_baseline_legacy(tests_dir: Path) -> int:
    """Compatibility alias retained for older callers."""
    total = 0
    for py_file in sorted(tests_dir.rglob("*.py")):
        if PROPERTY_FILE_RE.search(py_file.name):
            continue
        total += len(check_file(py_file))
    return total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if "--baseline" in args:
        # Baseline counting mode — always exits 0
        project_root = Path(__file__).resolve().parents[1]
        tests_dir = project_root / "tests"
        output_format = "count"
        if "--format" in args:
            format_index = args.index("--format")
            if format_index + 1 >= len(args):
                print("❌ --format requires one of: count, json, table", file=sys.stderr)
                return 2
            output_format = args[format_index + 1]

        violations = baseline_violations(tests_dir)
        if output_format == "count":
            print(len(violations))
        elif output_format == "json":
            print(format_baseline_json(violations, project_root))
        elif output_format == "table":
            print(format_baseline_table(violations, project_root))
        else:
            print("❌ --format requires one of: count, json, table", file=sys.stderr)
            return 2
        return 0

    base_ref = args[0] if args else "origin/develop"

    # Verify base ref exists
    check = subprocess.run(
        ["git", "rev-parse", "--verify", base_ref],
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        print(f"❌ Base ref not found: {base_ref}", file=sys.stderr)
        return 2

    return check_diff(base_ref)


if __name__ == "__main__":
    sys.exit(main())
