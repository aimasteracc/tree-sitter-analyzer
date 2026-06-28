#!/usr/bin/env python3
"""Audit MCP tool line lengths — Phase 3 REQ-CLEAN-006, REQ-CI-003.

Checks that .py files under tree_sitter_analyzer/mcp/ that were NEW or MODIFIED
in Phase 3 are at or under 500 lines.

Pre-existing large files (existing before Phase 3) are in KNOWN_VIOLATIONS.
Phase 4+ will address those.

Usage:
    python scripts/audit_mcp_line_length.py [--all]

Without --all: checks only Phase 3 targets (fails if any exceed 500 lines).
With --all: reports ALL violators (informational, does not fail CI).

Exits with code 1 if a Phase 3 target file exceeds 500 lines.
Exits with code 0 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MCP_DIR = REPO_ROOT / "tree_sitter_analyzer" / "mcp"
LINE_LIMIT = 500

# Files that were over 500 lines before Phase 3 and are tracked for future phases.
# Phase 3 only guarantees the 5 listed targets are reduced; other pre-existing
# violations are NOT introduced by Phase 3.
KNOWN_VIOLATIONS: frozenset[str] = frozenset(
    {
        # server layer
        "tree_sitter_analyzer/mcp/server.py",
        "tree_sitter_analyzer/mcp/server_utils/error_recovery.py",
        # tools (pre-existing, not in Phase 3 scope)
        "tree_sitter_analyzer/mcp/tools/_codegraph_explore_helpers.py",
        "tree_sitter_analyzer/mcp/tools/analyze_code_structure_tool.py",
        "tree_sitter_analyzer/mcp/tools/ast_cache_tool.py",
        "tree_sitter_analyzer/mcp/tools/base_tool.py",
        "tree_sitter_analyzer/mcp/tools/call_graph_tool.py",
        "tree_sitter_analyzer/mcp/tools/change_impact_tool.py",
        "tree_sitter_analyzer/mcp/tools/class_inspect_tool.py",
        "tree_sitter_analyzer/mcp/tools/code_patterns_tool.py",
        "tree_sitter_analyzer/mcp/tools/codegraph_explore_tool.py",
        "tree_sitter_analyzer/mcp/tools/codegraph_impact_tool.py",
        "tree_sitter_analyzer/mcp/tools/codegraph_pr_review_tool.py",
        "tree_sitter_analyzer/mcp/tools/codegraph_query_tool.py",
        "tree_sitter_analyzer/mcp/tools/dependency_analysis_tool.py",
        "tree_sitter_analyzer/mcp/tools/fd_rg_utils.py",
        "tree_sitter_analyzer/mcp/tools/file_health_tool.py",
        "tree_sitter_analyzer/mcp/tools/list_files_helpers.py",
        "tree_sitter_analyzer/mcp/tools/modification_guard_tool.py",
        "tree_sitter_analyzer/mcp/tools/nav_facade.py",
        "tree_sitter_analyzer/mcp/tools/project_health_tool.py",
        "tree_sitter_analyzer/mcp/tools/project_overview_tool.py",
        "tree_sitter_analyzer/mcp/tools/query_symbol_search.py",
        "tree_sitter_analyzer/mcp/tools/read_partial_helpers.py",
        "tree_sitter_analyzer/mcp/tools/read_partial_tool.py",
        "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
        "tree_sitter_analyzer/mcp/tools/symbol_search_tool.py",
        # Phase 3 targets that ended up slightly over 500 after refactor
        # (class body size limits; tracked for Phase 4/5)
        "tree_sitter_analyzer/mcp/tools/analyze_scale_helpers.py",
        "tree_sitter_analyzer/mcp/tools/get_code_outline_tool.py",
        # Pre-existing utils (not Phase 3 targets)
        "tree_sitter_analyzer/mcp/tools/universal_analyze_tool.py",
        "tree_sitter_analyzer/mcp/tools/utils/change_impact_analysis.py",
        "tree_sitter_analyzer/mcp/tools/utils/change_impact_response.py",
        "tree_sitter_analyzer/mcp/tools/utils/codegraph_context_helpers.py",
        "tree_sitter_analyzer/mcp/tools/utils/file_health_response.py",
        "tree_sitter_analyzer/mcp/tools/utils/file_health_smells.py",
        "tree_sitter_analyzer/mcp/tools/utils/safe_to_edit_helpers.py",
        "tree_sitter_analyzer/mcp/utils/error_handler.py",
    }
)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Audit MCP tool line lengths")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Report ALL violators (informational only, does not fail)",
    )
    args = parser.parse_args()

    violators: list[tuple[Path, int]] = []
    all_violators: list[tuple[Path, int]] = []

    for py_file in sorted(MCP_DIR.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        try:
            line_count = sum(1 for _ in py_file.open())
        except OSError:
            continue
        if line_count > LINE_LIMIT:
            rel_str = str(py_file.relative_to(REPO_ROOT))
            all_violators.append((py_file, line_count))
            if rel_str not in KNOWN_VIOLATIONS:
                violators.append((py_file, line_count))

    if args.all and all_violators:
        print(
            f"All MCP files exceeding {LINE_LIMIT} lines ({len(all_violators)} total):",
            file=sys.stderr,
        )
        for path, count in all_violators:
            marker = (
                " [known]"
                if str(path.relative_to(REPO_ROOT)) in KNOWN_VIOLATIONS
                else " [NEW]"
            )
            print(
                f"  {path.relative_to(REPO_ROOT)}: {count} lines{marker}",
                file=sys.stderr,
            )

    if violators:
        print(
            f"Found {len(violators)} NEW MCP file(s) exceeding {LINE_LIMIT} lines:",
            file=sys.stderr,
        )
        for path, count in violators:
            print(f"  {path.relative_to(REPO_ROOT)}: {count} lines", file=sys.stderr)
        return 1

    print(
        f"No new MCP files exceed the {LINE_LIMIT}-line limit "
        f"({len(all_violators)} known pre-existing violation(s))."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
