"""Source-analysis, health, change, and dependency argument groups."""

from __future__ import annotations

import argparse

from ._analysis_codegraph import _add_mcp_codegraph_map_options
from ._analysis_graph_nav import _add_mcp_graph_nav_options


def _add_analysis_options(parser: argparse.ArgumentParser) -> None:
    """Add source-analysis options."""
    parser.add_argument(
        "--advanced", action="store_true", help="Use advanced analysis features"
    )
    parser.add_argument(
        "--summary",
        nargs="?",
        const="classes,methods",
        help="Display summary of specified element types (default: classes,methods)",
    )
    parser.add_argument(
        "--structure",
        action="store_true",
        help="Output detailed structure information in JSON format",
    )
    parser.add_argument(
        "--statistics",
        action="store_true",
        help="Display only statistical information (requires --query-key or --advanced)",
    )
    parser.add_argument(
        "--language",
        help="Explicitly specify language (auto-detected from extension if omitted)",
    )


def _add_mcp_health_options(parser: argparse.ArgumentParser) -> None:
    """Add project and file health MCP mirror flags."""
    parser.add_argument(
        "--file-health",
        action="store_true",
        help="Score a single file's health (A-F grade, 7 dimensions, signal, smells)",
    )
    parser.add_argument(
        "--project-health",
        action="store_true",
        help="Score ALL project files: grade distribution, worst files, refactoring targets",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=30,
        help="Project health: maximum detailed files to include (default: 30)",
    )
    parser.add_argument(
        "--overview",
        action="store_true",
        help="Project portrait: language distribution, file counts, health summary",
    )
    parser.add_argument(
        "--safe-to-edit",
        action="store_true",
        help="Edit risk assessment: risk level, downstream deps, test proximity",
    )
    parser.add_argument(
        "--edit-type",
        default="refactor",
        choices=["refactor", "add_feature", "fix_bug", "rename"],
        help="Planned edit type for --safe-to-edit risk scoring (default: refactor)",
    )


def _add_mcp_change_options(parser: argparse.ArgumentParser) -> None:
    """Add change-impact MCP mirror flags."""
    parser.add_argument(
        "--change-impact",
        action="store_true",
        help="Analyze git diff impact: affected files, tests to run, risk level",
    )
    parser.add_argument(
        "--change-impact-mode",
        default="diff",
        choices=["diff", "staged", "branch", "pr"],
        help="Change-impact source: diff=unstaged, staged=index, branch=HEAD~1..HEAD, pr=from GitHub PR",
    )
    parser.add_argument(
        "--pr-url",
        default="",
        metavar="URL",
        help="GitHub PR URL for change-impact analysis (e.g. https://github.com/owner/repo/pull/123)",
    )
    parser.add_argument(
        "--change-impact-scope",
        nargs="+",
        default=[],
        metavar="PATH",
        help="Limit --change-impact to one or more pathspecs for the current edit queue",
    )
    parser.add_argument(
        "--change-impact-no-tests",
        dest="change_impact_include_tests",
        action="store_false",
        default=True,
        help="Skip related test discovery for --change-impact",
    )
    parser.add_argument(
        "--agent-summary-only",
        action="store_true",
        default=True,
        help=(
            "For --change-impact, output only the compact agent decision "
            "surface (now the DEFAULT — pass --change-impact-full to opt "
            "out of trimming)."
        ),
    )
    parser.add_argument(
        "--change-impact-full",
        action="store_true",
        default=False,
        help=(
            "Emit the full 145KB --change-impact envelope (default since "
            "v1.12: trimmed agent-summary). Use this when you genuinely "
            "need verification_command, raw_files, raw_test_paths, etc."
        ),
    )


def _add_mcp_analysis_options(parser: argparse.ArgumentParser) -> None:
    """Add dependency, refactor, and context MCP mirror flags."""
    parser.add_argument(
        "--parser-readiness",
        action="store_true",
        help="Advise next language parser/plugin work from local parser readiness signals",
    )
    parser.add_argument(
        "--parser-readiness-language",
        help="Language to inspect for --parser-readiness (also accepts parser-readiness LANGUAGE)",
    )
    parser.add_argument(
        "--parser-readiness-include-supported",
        action="store_true",
        help="Include already supported languages in --parser-readiness output",
    )
    parser.add_argument(
        "--dependencies",
        nargs="?",
        const="summary",
        choices=["summary", "file_deps", "blast_radius", "cycles", "full"],
        help=(
            "Dependency graph analysis "
            "(summary, file_deps, blast_radius, cycles; full aliases summary)"
        ),
    )
    parser.add_argument(
        "--refactor",
        action="store_true",
        help="Refactoring suggestions: extraction plans with line ranges",
    )
    parser.add_argument(
        "--outline",
        action="store_true",
        help=(
            "Hierarchical outline (package → class → method) without "
            "method bodies — the navigation-first view of a file."
        ),
    )
    parser.add_argument(
        "--smart-context",
        action="store_true",
        help="One-call file profile: health, exports, structure, deps, edit risk",
    )
    parser.add_argument(
        "--symbol-lineage",
        metavar="SYMBOL",
        help="Trace symbol lineage: definitions, callers, downstream impact, risk",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Max dependency graph depth for --symbol-lineage (1-5, default: 3)",
    )
    parser.add_argument(
        "--code-patterns",
        action="store_true",
        help="Detect anti-patterns, code smells, and security issues in a file",
    )
    parser.add_argument(
        "--call-graph",
        nargs="?",
        const="summary",
        choices=["summary", "callers", "callees", "chain", "all_functions"],
        help="Function-level call graph analysis (CodeGraph parity)",
    )
    parser.add_argument(
        "--call-graph-function",
        help="Target function name for --call-graph callers/callees/chain modes",
    )
    parser.add_argument(
        "--call-graph-file",
        help="File path to disambiguate for --call-graph",
    )
    parser.add_argument(
        "--call-graph-depth",
        type=int,
        default=5,
        help="Max depth for --call-graph chain mode (default: 5)",
    )
    parser.add_argument(
        "--ast-cache",
        action="store_true",
        help="Pre-indexed AST cache (CodeGraph parity). Index project for instant re-analysis",
    )
    parser.add_argument(
        "--ast-cache-mode",
        choices=[
            "index",
            "lookup",
            "search",
            "sync",
            "changes",
            "watch_start",
            "watch_stop",
            "watch_status",
            "stats",
            "invalidate",
        ],
        default="stats",
        help="AST cache operation mode (default: stats)",
    )
    parser.add_argument(
        "--ast-cache-query",
        help="Symbol search query for --ast-cache search mode",
    )
    parser.add_argument(
        "--ast-cache-language",
        help="Language filter for --ast-cache search mode",
    )
    parser.add_argument(
        "--ast-cache-max-files",
        type=int,
        default=20_000,
        help="Max files to index with --ast-cache (default: 20000)",
    )
    parser.add_argument(
        "--ast-cache-force",
        action="store_true",
        help="Force full re-index with --ast-cache",
    )
    parser.add_argument(
        "--ast-cache-include-activation",
        action="store_true",
        help=(
            "Compute temporal git activation during project indexing "
            "(slower; default keeps warm-cache indexing fast)"
        ),
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Start background file watcher for auto-sync (shortcut for --ast-cache --ast-cache-mode watch_start)",
    )
    parser.add_argument(
        "--watch-poll-interval",
        type=float,
        default=5.0,
        help="Poll interval in seconds for --watch (default: 5.0)",
    )
    parser.add_argument(
        "--watch-backend",
        choices=["poll", "watchdog"],
        default="poll",
        help="File watcher backend for --watch (default: poll)",
    )
    # Feature 4 (Homeostasis) — health-grade watching daemon. Reuses the
    # --watch infra but fires alerts when a file's grade drops or crosses
    # below threshold instead of just re-indexing.
    parser.add_argument(
        "--watch-health",
        action="store_true",
        help="Start a daemon that watches health grades and alerts on degradation",
    )
    parser.add_argument(
        "--threshold-grade",
        choices=["A", "B", "C", "D", "F"],
        default="C",
        help="Alert threshold grade for --watch-health (default: C)",
    )
    parser.add_argument(
        "--watch-interval",
        type=int,
        default=300,
        help="Polling interval in seconds for --watch-health (default: 300)",
    )
    parser.add_argument(
        "--watch-debounce",
        type=float,
        default=5.0,
        help="Debounce window in seconds for --watch-health (default: 5)",
    )
    parser.add_argument(
        "--notify-channel",
        default="stdout",
        help="Comma-separated alert channels: stdout|file|webhook (default: stdout)",
    )
    parser.add_argument(
        "--notify-file",
        type=str,
        default=None,
        help="JSONL log path when --notify-channel includes 'file'",
    )
    parser.add_argument(
        "--notify-webhook",
        type=str,
        default=None,
        help="Webhook URL when --notify-channel includes 'webhook' (post-MVP)",
    )
    parser.add_argument(
        "--on-degradation",
        type=str,
        default=None,
        help="Shell-command template fired on grade drop; tokens: {file} {grade} {previous_grade} {delta_score} {recommendation} {timestamp_iso}",
    )
    parser.add_argument(
        "--watch-cooldown",
        type=float,
        default=120.0,
        help="Per-file cooldown seconds between alerts for --watch-health (default: 120)",
    )
    parser.add_argument(
        "--history-keep",
        type=int,
        default=50,
        help="Number of history entries kept per file in health_score_history (default: 50)",
    )
    parser.add_argument(
        "--min-grade",
        default="D",
        choices=["A", "B", "C", "D", "F"],
        help="Minimum grade for --project-health detail list (default: D)",
    )
    parser.add_argument(
        "--detect-routes",
        action="store_true",
        help="Detect HTTP routes (Flask, Django, FastAPI, Express, Spring) — CodeGraph parity",
    )
    parser.add_argument(
        "--detect-routes-mode",
        choices=["all", "summary", "lookup", "prefix", "file"],
        default="summary",
        help="Mode for --detect-routes (default: summary)",
    )
    parser.add_argument(
        "--detect-routes-url",
        help="URL or prefix for --detect-routes lookup/prefix modes",
    )
    parser.add_argument(
        "--detect-routes-file",
        help="File path for --detect-routes file mode",
    )
    parser.add_argument(
        "--detect-routes-framework",
        choices=["flask", "django", "fastapi", "express", "spring", "all"],
        default="all",
        help="Framework filter for --detect-routes (default: all)",
    )
    parser.add_argument(
        "--ast-diff",
        action="store_true",
        help="Structural AST diff — tree-level code change understanding",
    )
    parser.add_argument(
        "--ast-diff-mode",
        choices=["diff_files", "diff_strings", "diff_git"],
        default="diff_files",
        help="AST diff mode (default: diff_files)",
    )
    parser.add_argument(
        "--ast-diff-old-file",
        help="Path to old file version for --ast-diff diff_files mode",
    )
    parser.add_argument(
        "--ast-diff-new-file",
        help="Path to new file version for --ast-diff diff_files mode",
    )
    parser.add_argument(
        "--ast-diff-old-source",
        help="Old source code string for --ast-diff diff_strings mode",
    )
    parser.add_argument(
        "--ast-diff-new-source",
        help="New source code string for --ast-diff diff_strings mode",
    )
    parser.add_argument(
        "--ast-diff-file",
        help="File path for --ast-diff diff_git mode",
    )
    parser.add_argument(
        "--ast-diff-old-ref",
        default="HEAD~1",
        help="Old git ref for --ast-diff diff_git mode (default: HEAD~1)",
    )
    parser.add_argument(
        "--ast-diff-new-ref",
        default="HEAD",
        help="New git ref for --ast-diff diff_git mode (default: HEAD)",
    )
    parser.add_argument(
        "--ast-diff-language",
        help="Language override for --ast-diff (auto-detected from file extension if omitted)",
    )
    # AST-path, codegraph-navigate/explore/query, callers, call-path, import-graph,
    # dead-code, doc-sync, symbol-search, code-similarity —
    # extracted to _analysis_graph_nav.py to keep this file under 500 lines.
    _add_mcp_graph_nav_options(parser)
    # Sitemap, xref, complexity, symbol-search, class-hierarchy, visualize, UML —
    # extracted to _analysis_codegraph.py to keep this file under 500 lines.
    _add_mcp_codegraph_map_options(parser)
