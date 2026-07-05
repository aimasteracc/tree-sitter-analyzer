#!/usr/bin/env python3
"""AST-based assertion-quality ratchet - Layer-1 CI gate.

Parses Python test files with the ``ast`` module and flags ``assert``
statements that are too weak to prove deterministic behavior:

* loose count bounds such as ``assert len(items) >= 1``;
* placeholder existence checks such as ``assert result is not None`` when the
  same test does not also assert concrete behavior; and
* tautologies such as ``assert result is not None or result is None``.

This replaces the grep core of ``check_loose_assertions.sh`` so that
multi-line assert statements — which the grep approach could not see — are
now caught. The script name is retained for existing CI/pre-commit call sites.

Usage (diff-scoped, normal CI mode)::

    python scripts/check_loose_assertions.py [<base-ref>]

Staged mode (pre-commit)::

    python scripts/check_loose_assertions.py --staged

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
_PLACEHOLDER_OPERATOR = "is-not-none"
_TAUTOLOGY_OPERATOR = "tautology"


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


def _is_none_literal(node: ast.expr) -> bool:
    """Return True for the None singleton literal."""
    return isinstance(node, ast.Constant) and node.value is None


def _expr_key(node: ast.expr) -> str:
    """Return a stable structural key for comparing simple expressions."""
    return ast.dump(node, include_attributes=False)


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


def _none_compare_subject(compare: ast.Compare, op_type: type[ast.cmpop]) -> str | None:
    """Return the expression key for ``expr is/is not None`` comparisons."""
    if len(compare.ops) != 1 or len(compare.comparators) != 1:
        return None
    if not isinstance(compare.ops[0], op_type):
        return None
    if not _is_none_literal(compare.comparators[0]):
        return None
    return _expr_key(compare.left)


def _is_placeholder_compare(compare: ast.Compare) -> bool:
    """Return True for the placeholder shape ``expr is not None``."""
    return _none_compare_subject(compare, ast.IsNot) is not None


def _is_none_tautology(expr: ast.expr) -> bool:
    """Return True for ``x is not None or x is None`` style tautologies."""
    if not isinstance(expr, ast.BoolOp) or not isinstance(expr.op, ast.Or):
        return False

    is_not_none_subjects: set[str] = set()
    is_none_subjects: set[str] = set()
    for value in expr.values:
        if not isinstance(value, ast.Compare):
            continue
        is_not_none = _none_compare_subject(value, ast.IsNot)
        if is_not_none is not None:
            is_not_none_subjects.add(is_not_none)
        is_none = _none_compare_subject(value, ast.Is)
        if is_none is not None:
            is_none_subjects.add(is_none)
    return bool(is_not_none_subjects.intersection(is_none_subjects))


def _assert_has_none_tautology(assert_node: ast.Assert) -> bool:
    """Return True if the assert contains a None-check tautology."""
    return any(_is_none_tautology(node) for node in ast.walk(assert_node.test))


def _assert_is_placeholder_candidate(assert_node: ast.Assert) -> bool:
    """Return True when an assert is only an existence check."""
    return isinstance(assert_node.test, ast.Compare) and _is_placeholder_compare(
        assert_node.test
    )


def _assert_has_concrete_behavior(assert_node: ast.Assert) -> bool:
    """Return True when an assert checks behavior, not only a weak shape."""
    if _assert_has_none_tautology(assert_node):
        return False
    if _assert_is_placeholder_candidate(assert_node):
        return False
    if _find_loose_compares(assert_node):
        return False
    return True


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


def _asserts_by_function(tree: ast.AST) -> dict[int, bool]:
    """Map assert node ids to whether their function has concrete assertions."""
    result: dict[int, bool] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        assert_nodes = [
            child for child in ast.walk(node) if isinstance(child, ast.Assert)
        ]
        has_concrete = any(
            _assert_has_concrete_behavior(child) for child in assert_nodes
        )
        for assert_node in assert_nodes:
            result[id(assert_node)] = has_concrete
    return result


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
    """Return Violation entries for every weak assert in the file."""
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # Unparseable file — skip silently (CI lint step catches syntax errors)
        return []

    source_lines = source.splitlines()
    violations: list[Violation] = []
    function_has_concrete_assert = _asserts_by_function(tree)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue

        end = getattr(node, "end_lineno", node.lineno)

        # Check for exemption marker in the assert's source segment
        if _segment_is_exempt(source_lines, node.lineno, end):
            continue

        snippet = source_lines[node.lineno - 1].strip() if source_lines else ""

        if _assert_has_none_tautology(node):
            violations.append(
                Violation(
                    str(path),
                    node.lineno,
                    snippet,
                    end,
                    _TAUTOLOGY_OPERATOR,
                    "tautology",
                )
            )
            continue

        if _assert_is_placeholder_candidate(
            node
        ) and not function_has_concrete_assert.get(id(node), False):
            violations.append(
                Violation(
                    str(path),
                    node.lineno,
                    snippet,
                    end,
                    _PLACEHOLDER_OPERATOR,
                    "placeholder",
                )
            )
            continue

        # Skip asserts that already have an == comparison — they are exact
        if _assert_has_eq_compare(node):
            continue

        loose = _find_loose_compares(node)
        if not loose:
            continue

        # Build a short snippet (first line of the assert)
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
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return _parse_added_line_ranges(result.stdout)


def _added_line_ranges_staged() -> dict[str, set[int]]:
    """Map staged test file (new path) -> set of ADDED line numbers."""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--unified=0",
            "--diff-filter=AMR",
            "--",
            "tests",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return _parse_added_line_ranges(result.stdout)


def _parse_added_line_ranges(diff_text: str) -> dict[str, set[int]]:
    """Parse ``git diff -U0`` output into added line numbers."""
    added: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
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
    return _check_added_ranges(_added_line_ranges(base_ref), "PR diff")


def check_staged() -> int:
    """Run staged diff check. Returns exit code (0 = OK, 1 = violations)."""
    return _check_added_ranges(_added_line_ranges_staged(), "staged diff")


def _check_added_ranges(added: dict[str, set[int]], source_label: str) -> int:
    """Run assertion-quality checks against already parsed added line ranges."""
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

    print(
        f"❌ Found {len(all_violations)} new weak assertion(s) in the {source_label}:\n"
    )
    for v in all_violations:
        print(f"  {v.path}:{v.lineno}: {v.snippet}")
    print()
    print("Weak assertion patterns detected:")
    print("  assert ... >= N   (GtE against integer literal)")
    print("  assert ... > N    (Gt  against integer literal)")
    print("  assert x is not None without concrete behavior in the same test")
    print("  assert x is not None or x is None")
    print()
    print("To exempt a line, add comment anywhere in the assert block:")
    print("  assert x >= 1  # ratchet: nondeterministic <reason>")
    return 1


def count_baseline(tests_dir: Path) -> int:
    """Count all weak assertions under *tests_dir* using AST rules."""
    return len(baseline_violations(tests_dir))


def baseline_violations(tests_dir: Path) -> list[Violation]:
    """Return all baseline weak assertions under *tests_dir* using AST rules."""
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
    return json.dumps(payload, ensure_ascii=True, indent=2)


def format_baseline_table(violations: list[Violation], project_root: Path) -> str:
    """Format violations as a short human-readable summary table."""
    by_path = Counter(_repo_relative(v.path, project_root) for v in violations)
    lines = [f"Total weak assertions: {len(violations)}", "", "| path | count |"]
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

    if "--staged" in args:
        return check_staged()

    if "--baseline" in args:
        # Baseline counting mode — always exits 0
        project_root = Path(__file__).resolve().parents[1]
        tests_dir = project_root / "tests"
        output_format = "count"
        if "--format" in args:
            format_index = args.index("--format")
            if format_index + 1 >= len(args):
                print(
                    "❌ --format requires one of: count, json, table", file=sys.stderr
                )
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
