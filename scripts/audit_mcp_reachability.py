#!/usr/bin/env python3
"""Audit MCP tool reachability — detect dead code in tree_sitter_analyzer/mcp/tools/.

REQ-DEAD-001, REQ-DEAD-004, REQ-CI-001, REQ-CI-003 — Phase 3 Step 3.

Usage:
    python scripts/audit_mcp_reachability.py [--strict]

Without --strict: lists unreachable files and writes reports/mcp-dead-code.json.
With --strict: exits with code 1 if any unreachable files are found.

Algorithm:
  1. Seed the reachable set from facade files + _tool_registry.py (static import AST).
  2. Expand transitively: any tool module imported by an already-reachable module
     is also reachable. Repeat until fixed point.
  3. Enumerate all .py files in tools/ (excluding shared infra); anything not
     in the reachable set is dead code.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TOOLS_DIR = REPO_ROOT / "tree_sitter_analyzer" / "mcp" / "tools"
REPORTS_DIR = REPO_ROOT / "reports"

# Files excluded from reachability checking (shared infra, not inner tools).
# These are either entrypoints, shared helpers imported by base_tool.py, or
# modules imported from outside the tools/ directory (e.g. from server.py).
EXCLUDE_NAMES: frozenset[str] = frozenset(
    {
        "__init__.py",
        "base_tool.py",
        "facade_tool.py",
        # Facade files themselves are entrypoints
        "search_facade.py",
        "nav_facade.py",
        "structure_facade.py",
        "health_facade.py",
        "edit_facade.py",
        "project_facade.py",
        "index_facade.py",
        "viz_facade.py",
        # Imported by base_tool.py (which is in EXCLUDE_NAMES, so transitive
        # expansion from base_tool is skipped — list them explicitly)
        "_language_mismatch.py",
        "_strict_params.py",
        "_verdict.py",
        # Imported from server.py (outside tools/)
        "universal_analyze_tool.py",
        "universal_analyze_helpers.py",
        # Shared response helper used by many tools
        "tool_response.py",
    }
)


def _local_imports_from_file(py_file: Path) -> set[str]:
    """Return module stems that py_file imports from the same tools/ package (level=1 relative).

    Handles two patterns:
      from .stem import Foo          (node.module = 'stem', level=1)
      from . import stem             (node.module = None, level=1, names=['stem'])
    """
    stems: set[str] = set()
    try:
        tree = ast.parse(py_file.read_text())
    except SyntaxError:
        return stems
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 1:
                if node.module:
                    # from .stem import Foo  OR  from .stem.sub import Foo
                    stem = node.module.split(".")[0]
                    stems.add(stem)
                else:
                    # from . import stem1, stem2
                    for alias in node.names:
                        stems.add(alias.name.split(".")[0])
    return stems


def _seed_reachable_from_facades_and_registry() -> set[str]:
    """Collect module stems directly imported by facade files and the tool registry."""
    reachable: set[str] = set()

    # Facade files
    for facade_file in TOOLS_DIR.glob("*_facade.py"):
        if facade_file.name == "facade_tool.py":
            continue
        reachable.update(_local_imports_from_file(facade_file))

    # _tool_registry.py in the parent mcp/ directory
    registry_path = REPO_ROOT / "tree_sitter_analyzer" / "mcp" / "_tool_registry.py"
    if registry_path.exists():
        try:
            tree = ast.parse(registry_path.read_text())
        except SyntaxError:
            pass
        else:
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    # from tree_sitter_analyzer.mcp.tools.STEM import ...
                    if "mcp.tools" in node.module and node.level == 0:
                        parts = node.module.split(".")
                        # last part after "tools" is the module stem
                        try:
                            idx = parts.index("tools")
                            if idx + 1 < len(parts):
                                reachable.add(parts[idx + 1])
                        except ValueError:
                            pass

    return reachable


def _collect_candidate_tools() -> set[str]:
    """Return set of .py file stems in tools/ that are candidates for reachability check.

    Excludes __init__.py, base_tool.py, facade_tool.py, facade files, and utils/ subdir.
    """
    candidates: set[str] = set()
    for py_file in TOOLS_DIR.iterdir():
        if py_file.is_dir():
            continue
        if py_file.name in EXCLUDE_NAMES:
            continue
        if py_file.suffix != ".py":
            continue
        candidates.add(py_file.stem)
    return candidates


def _expand_reachable(candidates: set[str], seed: set[str]) -> set[str]:
    """Transitively expand the reachable set via local imports until fixed point."""
    reachable = set(seed)
    changed = True
    while changed:
        changed = False
        for stem in list(candidates):
            if stem in reachable:
                continue
            py_file = TOOLS_DIR / f"{stem}.py"
            if not py_file.exists():
                continue
            _local_imports_from_file(py_file)
            # If any of this file's imports is already reachable AND the file
            # itself is imported by a reachable file, it is reachable.
            # Simpler check: if this file is transitively reachable via any
            # already-reachable file.
        # Reverse approach: for every reachable file, mark its imports reachable
        for stem in list(reachable):
            py_file = TOOLS_DIR / f"{stem}.py"
            if not py_file.exists():
                continue
            for imported in _local_imports_from_file(py_file):
                if imported in candidates and imported not in reachable:
                    reachable.add(imported)
                    changed = True
    return reachable


def run_audit(strict: bool = False) -> int:
    """Run the reachability audit.

    Returns 0 if no dead code; 1 if dead code found and --strict is set.
    """
    candidates = _collect_candidate_tools()
    seed = _seed_reachable_from_facades_and_registry()
    reachable = _expand_reachable(candidates, seed)

    unreachable = sorted(candidates - reachable)

    # Write report
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / "mcp-dead-code.json"
    report_path.write_text(json.dumps(unreachable, indent=2) + "\n")

    if unreachable:
        print(f"Found {len(unreachable)} unreachable MCP tool(s):", file=sys.stderr)
        for name in unreachable:
            print(f"  {TOOLS_DIR / (name + '.py')}", file=sys.stderr)
        print(f"\nReport written to {report_path}", file=sys.stderr)
        if strict:
            return 1
    else:
        print(f"No unreachable MCP tools found. Report: {report_path}")

    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Audit MCP tool reachability")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any unreachable files are found",
    )
    args = parser.parse_args()
    return run_audit(strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
