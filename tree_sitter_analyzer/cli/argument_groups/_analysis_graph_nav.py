"""CodeGraph navigation, call-path, import-graph, dead-code, symbol-search,
and code-similarity argument groups.

Extracted from ``_add_mcp_analysis_options`` to keep every file under 500 lines.
Called at the end of that function via ``_add_mcp_graph_nav_options``.
"""

from __future__ import annotations

import argparse


def _add_mcp_graph_nav_options(parser: argparse.ArgumentParser) -> None:
    """Add ast-path, codegraph-overview/navigate/explore/query, callers, call-path,
    import-graph, dead-code, doc-sync, symbol-search, and code-similarity flags."""
    parser.add_argument(
        "--ast-path",
        action="store_true",
        help="AST path/scope navigation — what is at line X? (CodeGraph parity)",
    )
    parser.add_argument(
        "--ast-path-mode",
        choices=["path", "scope", "outline", "siblings"],
        default="scope",
        help="AST path query mode (default: scope)",
    )
    parser.add_argument(
        "--ast-path-line",
        type=int,
        help="Target line number for --ast-path path/scope/siblings modes",
    )
    parser.add_argument(
        "--ast-path-depth",
        type=int,
        default=3,
        help="Max outline depth for --ast-path outline mode (default: 3)",
    )
    parser.add_argument(
        "--codegraph-overview",
        action="store_true",
        help="Project-wide call graph intelligence: entry points, dead code, hubs, coupling (CodeGraph parity)",
    )
    parser.add_argument(
        "--codegraph-overview-max-entry-points",
        type=int,
        default=30,
        help="Max entry points in --codegraph-overview output (default: 30)",
    )
    parser.add_argument(
        "--codegraph-overview-max-hubs",
        type=int,
        default=20,
        help="Max hub functions in --codegraph-overview output (default: 20)",
    )
    parser.add_argument(
        "--codegraph-overview-max-dead",
        type=int,
        default=20,
        help="Max dead code candidates in --codegraph-overview output (default: 20)",
    )
    parser.add_argument(
        "--codegraph-overview-max-coupled",
        type=int,
        default=15,
        help="Max coupled files in --codegraph-overview output (default: 15)",
    )
    parser.add_argument(
        "--callers",
        help="Find all functions that call the given function (CodeGraph parity). "
        "Shorthand for --call-graph callers --call-graph-function",
    )
    parser.add_argument(
        "--codegraph-navigate",
        metavar="SYMBOL",
        help="Unified symbol navigation: go-to-def + references + call hierarchy in one call",
    )
    parser.add_argument(
        "--codegraph-navigate-mode",
        choices=["definition", "references", "hierarchy", "full"],
        default="full",
        help="Mode for --codegraph-navigate (default: full)",
    )
    parser.add_argument(
        "--codegraph-navigate-file",
        help="File path to disambiguate for --codegraph-navigate",
    )
    parser.add_argument(
        "--codegraph-navigate-depth",
        type=int,
        default=2,
        help="Max transitive depth for --codegraph-navigate hierarchy (default: 2)",
    )
    # CodeGraph parity gap-closure (2026-05-24).
    parser.add_argument(
        "--codegraph-status",
        action="store_true",
        help="Index health at-a-glance: indexed yes/no, total files/symbols, "
        "schema version, FTS5, cache lag (CodeGraph parity).",
    )
    parser.add_argument(
        "--codegraph-status-no-lag",
        action="store_true",
        help="Skip lag computation in --codegraph-status (faster on huge repos)",
    )
    parser.add_argument(
        "--codegraph-context",
        metavar="TASK",
        help=(
            "One-call architecture context: entry points, graph nodes, edges, "
            "and source blocks for a natural-language task"
        ),
    )
    parser.add_argument(
        "--codegraph-context-max-nodes",
        type=int,
        default=30,
        help="Max nodes returned for --codegraph-context (default: 30)",
    )
    parser.add_argument(
        "--codegraph-context-max-code-blocks",
        type=int,
        default=8,
        help="Max source snippets returned for --codegraph-context (default: 8)",
    )
    parser.add_argument(
        "--codegraph-explore",
        metavar="QUERY",
        help="Bulk-fetch N related symbols' source + relationship map in one call. "
        "Query is space-separated symbol names + optional file hints "
        "(e.g. 'CodeGraphNavigateTool execute call_graph_tool.py').",
    )
    parser.add_argument(
        "--codegraph-explore-max-files",
        type=int,
        default=12,
        help="Max distinct source files for --codegraph-explore (default: 12, cap 30)",
    )
    parser.add_argument(
        "--codegraph-explore-max-symbols",
        type=int,
        default=20,
        help="Max symbols to resolve for --codegraph-explore (default: 20, cap 50)",
    )
    parser.add_argument(
        "--codegraph-explore-outline-only",
        action="store_true",
        help="Return symbol outline without source snippets for --codegraph-explore",
    )
    parser.add_argument(
        "--codegraph-query",
        metavar="CHAIN",
        help=(
            "jQuery-style chained graph query in one process. Example: "
            "search('CommandService').explore(max_files=4).callees().callers()"
        ),
    )
    parser.add_argument(
        "--codegraph-query-max-files",
        type=int,
        default=8,
        help="Default max files for --codegraph-query explore steps (default: 8)",
    )
    parser.add_argument(
        "--codegraph-query-max-symbols",
        type=int,
        default=20,
        help="Default max symbols for --codegraph-query steps (default: 20)",
    )
    parser.add_argument(
        "--codegraph-query-outline-only",
        action="store_true",
        help="Return outlines without source snippets for --codegraph-query",
    )
    parser.add_argument(
        "--codegraph-query-compact",
        action="store_true",
        help="Return compact answer-pack output for --codegraph-query",
    )
    # --affected: CodeGraph CLI parity (the last CLI surface they had
    # over us). Takes one or more changed files, returns the union of
    # test files transitively affected.
    parser.add_argument(
        "--affected",
        metavar="FILE",
        nargs="+",
        help="List test files transitively affected by changes to FILE(s). "
        "Multi-language test-path heuristic (Python / Go / Java / Rust / "
        "TS / Swift / Kotlin). Use --affected-filter to override.",
    )
    parser.add_argument(
        "--affected-filter",
        metavar="GLOB",
        help="Custom glob for test files (overrides the multi-language "
        "heuristic). Example: 'tests/e2e/*.spec.ts'.",
    )
    parser.add_argument(
        "--affected-quiet",
        action="store_true",
        help="Emit test file paths only (one per line), no envelope. "
        "Matches CodeGraph's --quiet behaviour for shell-pipeline use.",
    )
    # Pain pass 2: 3 new MCP tools (codegraph_impact, codegraph_pr_review,
    # semantic_classify) need CLI parity to satisfy the contract test.
    parser.add_argument(
        "--codegraph-impact",
        metavar="FUNCTION",
        help="Function-level blast radius / risk score (CodeGraph parity).",
    )
    parser.add_argument(
        "--codegraph-impact-mode",
        choices=["function_impact", "blast_radius", "risk_score"],
        default="function_impact",
        help="Mode for --codegraph-impact (default: function_impact)",
    )
    parser.add_argument(
        "--codegraph-impact-file",
        help="File path to disambiguate for --codegraph-impact",
    )
    parser.add_argument(
        "--codegraph-impact-depth",
        type=int,
        default=5,
        help="Max transitive depth for --codegraph-impact (default: 5)",
    )
    parser.add_argument(
        "--pr-review",
        nargs="?",
        const="diff",
        choices=["diff", "staged", "branch"],
        help="AI-powered PR review (AST diff + semantic classify + call graph).",
    )
    parser.add_argument(
        "--semantic-classify",
        nargs="?",
        const="classify_file",
        choices=["classify_file", "classify_string"],
        help="Semantic change classification (api_change/refactor/feature/...).",
    )
    parser.add_argument(
        "--callers-file",
        help="File path to disambiguate overloaded functions for --callers",
    )
    parser.add_argument(
        "--callees",
        help="Find all functions called by the given function (CodeGraph parity). "
        "Shorthand for --call-graph callees --call-graph-function",
    )
    parser.add_argument(
        "--callees-file",
        help="File path to disambiguate overloaded functions for --callees",
    )
    parser.add_argument(
        "--call-path",
        nargs="?",
        const="bidirectional",
        choices=["forward", "backward", "bidirectional"],
        help="Find execution paths between two functions via BFS on call edges (CodeGraph parity). "
        "Direction: forward, backward, or bidirectional (default)",
    )
    parser.add_argument(
        "--call-path-source",
        help="Source function name for --call-path (required)",
    )
    parser.add_argument(
        "--call-path-target",
        help="Target function name for --call-path (required)",
    )
    parser.add_argument(
        "--call-path-source-file",
        help="File path to disambiguate source function for --call-path",
    )
    parser.add_argument(
        "--call-path-target-file",
        help="File path to disambiguate target function for --call-path",
    )
    parser.add_argument(
        "--call-path-max-depth",
        type=int,
        default=10,
        help="Max BFS depth for --call-path (default: 10)",
    )
    parser.add_argument(
        "--call-path-max-paths",
        type=int,
        default=5,
        help="Max number of paths for --call-path (default: 5)",
    )
    parser.add_argument(
        "--import-graph",
        action="store_true",
        help="File-level import dependency graph (CodeGraph parity)",
    )
    parser.add_argument(
        "--import-graph-mode",
        choices=["summary", "deps", "dependents", "blast_radius", "cycles", "coupling"],
        default="summary",
        help="Mode for --import-graph (default: summary)",
    )
    parser.add_argument(
        "--import-graph-file",
        help="File path for --import-graph deps/dependents/blast_radius modes",
    )
    parser.add_argument(
        "--import-graph-max-depth",
        type=int,
        default=10,
        help="Max depth for --import-graph blast_radius (default: 10)",
    )
    parser.add_argument(
        "--dead-code",
        action="store_true",
        help="Dead code analysis: transitive dead functions, unused imports, unreferenced variables",
    )
    parser.add_argument(
        "--dead-code-mode",
        choices=["all", "dead_functions", "unused_imports", "variables"],
        default="all",
        help="Mode for --dead-code (default: all)",
    )
    parser.add_argument(
        "--dead-code-include-tests",
        action="store_true",
        default=False,
        help="Include test files in dead code analysis",
    )
    parser.add_argument(
        "--dead-code-max",
        type=int,
        default=50,
        help="Max dead function candidates (default: 50)",
    )
    parser.add_argument(
        "--doc-sync",
        action="store_true",
        help="Scan markdown docs for stale file-path references (broken links)",
    )
    parser.add_argument(
        "--doc-sync-patterns",
        nargs="+",
        metavar="PATTERN",
        help="Glob patterns for docs to scan (default: docs/**/*.md README.md CHANGELOG.md)",
    )
    parser.add_argument(
        "--symbol-search",
        help="FTS5-powered instant symbol search (CodeGraph parity). "
        "Use exact name, * wildcards, or ~ fuzzy prefix",
    )
    parser.add_argument(
        "--code-similarity",
        action="store_true",
        help="AST-structural clone detection: finds duplicate/near-duplicate functions (CodeGraph parity)",
    )
    parser.add_argument(
        "--code-similarity-mode",
        choices=["all", "structural", "textual"],
        default="all",
        help="Mode for --code-similarity (default: all)",
    )
    parser.add_argument(
        "--code-similarity-min-lines",
        type=int,
        default=5,
        help="Minimum function body lines for --code-similarity (default: 5)",
    )
    parser.add_argument(
        "--code-similarity-min-group",
        type=int,
        default=2,
        help="Minimum clone group size for --code-similarity (default: 2)",
    )
    parser.add_argument(
        "--code-similarity-max-groups",
        type=int,
        default=20,
        help="Max similarity groups for --code-similarity (default: 20)",
    )
    parser.add_argument(
        "--code-similarity-no-cache",
        action="store_true",
        help="Skip AST cache and do full project scan for --code-similarity",
    )
