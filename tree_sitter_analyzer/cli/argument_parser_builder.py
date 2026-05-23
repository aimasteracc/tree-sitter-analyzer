"""Argument parser construction for the tree-sitter-analyzer CLI."""

from __future__ import annotations

import argparse

from .. import __version__

CLI_EPILOG = (
    "Examples:  (grouped by task)\n"
    "\n"
    "Cold-start  (1 call, full file picture — use these first):\n"
    "  tree-sitter-analyzer file.py --smart-context         Killer 1-call: health, exports, structure, deps, edit risk\n"
    "  tree-sitter-analyzer --overview                      Project portrait + health summary\n"
    "  tree-sitter-analyzer agent-skills                    Project-local agent skill inventory\n"
    "  tree-sitter-analyzer agent-workflow file.py          SMART workflow command pack\n"
    "\n"
    "Read code  (extract content from a single file):\n"
    "  tree-sitter-analyzer file.java --table=full          Markdown table of classes/methods\n"
    "  tree-sitter-analyzer file.java --structure           Structure overview in JSON\n"
    "  tree-sitter-analyzer file.java --summary             Quick summary of classes/methods\n"
    "  tree-sitter-analyzer file.java --advanced            Full analysis with all elements\n"
    "  tree-sitter-analyzer file.java --query-key class     Extract all class definitions\n"
    "  tree-sitter-analyzer file.java --partial-read --start-line 10 --end-line 20\n"
    "\n"
    "Health  (per-file or project-wide grading):\n"
    "  tree-sitter-analyzer file.py --file-health           A-F health grade + signal + smells\n"
    "  tree-sitter-analyzer file-health file.py             Agent-friendly alias for --file-health\n"
    "  tree-sitter-analyzer --project-health                Score ALL project files\n"
    "  tree-sitter-analyzer --watch-health                  Daemon: alert when health grades drop\n"
    "\n"
    "Edit safety  (risk + impact before/after a change):\n"
    "  tree-sitter-analyzer file.py --safe-to-edit --edit-type refactor\n"
    "  tree-sitter-analyzer file.py --refactor              Refactoring suggestions with plans\n"
    "  tree-sitter-analyzer --change-impact                 Git diff impact (trimmed surface by default)\n"
    "  tree-sitter-analyzer --change-impact --change-impact-full   Full verbose envelope (~145 KB)\n"
    "  tree-sitter-analyzer change-impact --change-impact-mode staged\n"
    "\n"
    "Graph & deps  (cross-file relationships):\n"
    "  tree-sitter-analyzer --dependencies summary          Project dependency summary\n"
    "  tree-sitter-analyzer file.py --dependencies file_deps  File dependency graph\n"
    "  tree-sitter-analyzer --detect-routes                 URL→handler routes (Flask/Django/FastAPI/Express/Spring)\n"
    "  tree-sitter-analyzer detect-routes --detect-routes-mode all\n"
    "  tree-sitter-analyzer --codegraph-overview            Entry points, dead code, hubs, coupling\n"
    "  tree-sitter-analyzer --codegraph-navigate SYMBOL     Go-to-def + refs + call hierarchy\n"
    "\n"
    "Architecture rules  (constraint DSL):\n"
    "  tree-sitter-analyzer --check-constraints             Evaluate architectural-constraints.yml\n"
    "  tree-sitter-analyzer --check-constraints --severity-min error\n"
    "\n"
    "Cache ops  (manage the pre-indexed AST cache):\n"
    "  tree-sitter-analyzer --autoindex                     Idempotent cache status / warm\n"
    "  tree-sitter-analyzer --autoindex --autoindex-mode warm\n"
    "  tree-sitter-analyzer --full-index                    Force a fresh full re-index\n"
    "  tree-sitter-analyzer --codegraph-metrics             Cross-domain project dashboard\n"
    "  tree-sitter-analyzer --clean-state                   Remove ephemeral workspace state\n"
    "  tree-sitter-analyzer --clean-state-dry-run           Preview what --clean-state would remove\n"
    "\n"
    "Discovery  (what does this CLI know?):\n"
    "  tree-sitter-analyzer parser-readiness swift          Parser/plugin readiness advisor\n"
    "  tree-sitter-analyzer --list-queries                  Show available query keys\n"
    "  tree-sitter-analyzer --show-supported-languages      List supported languages\n"
)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Analyze code using Tree-sitter and extract structured information.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EPILOG,
    )
    _add_core_options(parser)
    _add_query_options(parser)
    _add_output_options(parser)
    _add_analysis_options(parser)
    _add_sql_platform_options(parser)
    _add_project_and_logging_options(parser)
    _add_partial_read_options(parser)
    _add_batch_options(parser)
    _add_mcp_equivalent_options(parser)
    return parser


def _add_core_options(parser: argparse.ArgumentParser) -> None:
    """Add version and target-file options."""
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument("file_path", nargs="?", help="Path to the file to analyze")


def _add_query_options(parser: argparse.ArgumentParser) -> None:
    """Add query selection and informational options."""
    query_group = parser.add_mutually_exclusive_group(required=False)
    query_group.add_argument(
        "--query-key", help="Available query key (e.g., class, method)"
    )
    query_group.add_argument(
        "--query-string", help="Directly specify Tree-sitter query to execute"
    )
    parser.add_argument(
        "--filter",
        help="Filter query results (e.g., 'name=main', 'name=~get*,public=true')",
    )
    parser.add_argument(
        "--list-queries",
        action="store_true",
        help="Display list of available query keys",
    )
    parser.add_argument(
        "--filter-help",
        action="store_true",
        help="Display help for query filter syntax",
    )
    parser.add_argument(
        "--describe-query",
        help="Display description of specified query key (requires --language or target file)",
    )
    parser.add_argument(
        "--show-supported-languages",
        action="store_true",
        help="Display list of supported languages",
    )
    parser.add_argument(
        "--show-supported-extensions",
        action="store_true",
        help="Display list of supported file extensions",
    )
    parser.add_argument(
        "--show-common-queries",
        action="store_true",
        help="Display list of common queries across multiple languages",
    )
    parser.add_argument(
        "--show-query-languages",
        action="store_true",
        help="Display list of languages with query support",
    )


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    """Add output formatting options."""
    parser.add_argument(
        "--output-format",
        choices=["json", "text", "toon"],
        default="json",
        help="Specify output format: 'json' (default), 'text', or 'toon' (50-70%% token reduction)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "toon"],
        help="Alias for --output-format (json or toon)",
    )
    parser.add_argument(
        "--toon-use-tabs",
        action="store_true",
        help="Use tab delimiters instead of commas in TOON format (further compression)",
    )
    parser.add_argument(
        "--table",
        choices=["full", "compact", "csv", "json", "toon"],
        help="Output in table format (toon format provides 50-70%% token reduction)",
    )
    parser.add_argument(
        "--include-javadoc",
        action="store_true",
        help="Include JavaDoc/documentation comments in output",
    )


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


def _add_sql_platform_options(parser: argparse.ArgumentParser) -> None:
    """Add SQL platform compatibility options."""
    parser.add_argument(
        "--sql-platform-info",
        action="store_true",
        help="Show current SQL platform detection details",
    )
    parser.add_argument(
        "--record-sql-profile",
        action="store_true",
        help="Record a new SQL behavior profile for the current platform",
    )
    parser.add_argument(
        "--compare-sql-profiles",
        nargs=2,
        metavar=("PROFILE1", "PROFILE2"),
        help="Compare two SQL behavior profiles",
    )


def _add_project_and_logging_options(parser: argparse.ArgumentParser) -> None:
    """Add project and logging options."""
    parser.add_argument(
        "--project-root",
        help="Project root directory for security validation (auto-detected if not specified)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress INFO level logs (show errors only)",
    )


def _add_partial_read_options(parser: argparse.ArgumentParser) -> None:
    """Add single and batch partial-read options."""
    parser.add_argument(
        "--partial-read",
        action="store_true",
        help="Enable partial file reading mode",
    )
    parser.add_argument(
        "--partial-read-requests-json",
        help="Batch partial read: JSON string containing either {'requests': [...]} or a list of requests[]",
    )
    parser.add_argument(
        "--partial-read-requests-file",
        help="Batch partial read: path to a JSON file containing either {'requests': [...]} or a list of requests[]",
    )
    parser.add_argument(
        "--start-line", type=int, help="Starting line number for reading (1-based)"
    )
    parser.add_argument(
        "--end-line", type=int, help="Ending line number for reading (1-based)"
    )
    parser.add_argument(
        "--start-column", type=int, help="Starting column number for reading (0-based)"
    )
    parser.add_argument(
        "--end-column", type=int, help="Ending column number for reading (0-based)"
    )
    parser.add_argument(
        "--allow-truncate",
        action="store_true",
        help="Batch mode: allow truncation of results to fit limits (default: fail on limit exceed)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Batch mode: stop on first error (default: partial success)",
    )


def _add_batch_options(parser: argparse.ArgumentParser) -> None:
    """Add batch project-health and metrics options."""
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Project health: score all source files and report grade distribution, worst files, and refactoring targets",
    )
    parser.add_argument(
        "--metrics-only",
        action="store_true",
        help="Batch metrics: compute file metrics only (no structural analysis). Requires --file-paths or --files-from.",
    )
    parser.add_argument(
        "--file-paths",
        nargs="+",
        help="Batch metrics: list of file paths (space-separated). Example: --file-paths a.py b.py",
    )
    parser.add_argument(
        "--files-from",
        help="Batch metrics: read file paths from a text file (one path per line)",
    )


def _add_mcp_equivalent_options(parser: argparse.ArgumentParser) -> None:
    """Add CLI flags that mirror MCP tools."""
    _add_agent_skills_options(parser)
    _add_agent_workflow_options(parser)
    _add_mcp_health_options(parser)
    _add_mcp_change_options(parser)
    _add_mcp_analysis_options(parser)
    _add_mcp_constraints_options(parser)
    # consolidated-only families (ported during merge of feat/autonomous-dev)
    _add_trace_impact_options(parser)
    _add_environment_probe_options(parser)
    _add_modification_guard_options(parser)
    _add_decision_journal_options(parser)
    _add_batch_search_options(parser)
    # PL-C sprint additions
    _add_mcp_index_management_options(parser)
    _add_clean_state_options(parser)


def _add_mcp_index_management_options(parser: argparse.ArgumentParser) -> None:
    """Add cache/index management flags (codegraph_autoindex / full_index / metrics).

    These three tools used to be MCP-only — CLI agents had no way to reach
    them without spawning the MCP server. The flags ship together because
    they share the same auto-index plumbing.
    """
    parser.add_argument(
        "--autoindex",
        action="store_true",
        help=(
            "Transparent AST cache auto-indexing (codegraph_autoindex). "
            "Default mode 'status' — also accepts 'warm' / 'reset' via "
            "--autoindex-mode."
        ),
    )
    parser.add_argument(
        "--autoindex-mode",
        choices=["status", "warm", "reset"],
        default="status",
        help="Mode for --autoindex (default: status)",
    )
    parser.add_argument(
        "--autoindex-max-files",
        type=int,
        default=5000,
        help="Max files to index when --autoindex-mode=warm (default: 5000)",
    )
    parser.add_argument(
        "--full-index",
        action="store_true",
        help=(
            "Force a complete project-wide AST re-index "
            "(codegraph_full_index). Use after pulls, rebases, or large "
            "refactors. Default mode 'rebuild'."
        ),
    )
    parser.add_argument(
        "--full-index-mode",
        choices=["rebuild", "stats", "clear"],
        default="rebuild",
        help="Mode for --full-index (default: rebuild)",
    )
    parser.add_argument(
        "--full-index-max-files",
        type=int,
        default=5000,
        help="Max files for --full-index rebuild (default: 5000)",
    )
    parser.add_argument(
        "--codegraph-metrics",
        action="store_true",
        help=(
            "Aggregated project intelligence dashboard (codegraph_metrics). "
            "Single-call: cache stats, call-graph metrics, complexity "
            "bands, route counts, file-health distribution."
        ),
    )
    parser.add_argument(
        "--codegraph-metrics-sections",
        nargs="+",
        choices=["cache", "call_graph", "complexity", "routes", "health"],
        default=None,
        metavar="SECTION",
        help=(
            "Subset of metric sections for --codegraph-metrics "
            "(default: all five). Example: --codegraph-metrics-sections "
            "cache call_graph"
        ),
    )
    parser.add_argument(
        "--incremental-sync",
        action="store_true",
        help=(
            "Incremental AST cache sync using content-hash comparison "
            "(codegraph_incremental_sync). Only re-parses files whose "
            "SHA-256 hash differs. Default mode 'sync'."
        ),
    )
    parser.add_argument(
        "--incremental-sync-mode",
        choices=["sync", "changes", "status"],
        default="sync",
        help="Mode for --incremental-sync (default: sync)",
    )
    parser.add_argument(
        "--incremental-sync-max-files",
        type=int,
        default=5000,
        help="Max files for --incremental-sync (default: 5000)",
    )


def _add_clean_state_options(parser: argparse.ArgumentParser) -> None:
    """Add --clean-state subcommand and dry-run companion."""
    parser.add_argument(
        "--clean-state",
        action="store_true",
        help=(
            "Remove ephemeral workspace state files: .ast-cache/, "
            ".tree-sitter-cache/, ruvector.db, agentdb.rvf*, ':memory:'/, "
            "tests/temp_cli_test_large/."
        ),
    )
    parser.add_argument(
        "--clean-state-dry-run",
        action="store_true",
        help=("Print what --clean-state would remove without touching the filesystem."),
    )


def _add_mcp_constraints_options(parser: argparse.ArgumentParser) -> None:
    """Add constraint-DSL flags (Feature 3 — check_constraints MCP parity)."""
    parser.add_argument(
        "--check-constraints",
        action="store_true",
        help=(
            "Evaluate architectural-constraints.yml against the cached call "
            "graph; returns violations + UNSAFE/CAUTION/SAFE verdict"
        ),
    )
    parser.add_argument(
        "--constraint-file",
        metavar="PATH",
        default=None,
        help=(
            "Path to a constraint YAML file (overrides default discovery of "
            "architectural-constraints.yml under --project-root)"
        ),
    )
    parser.add_argument(
        "--no-constraints",
        action="store_true",
        default=False,
        help=(
            "Opt out of constraint auto-evaluation for tools that bundle it "
            "(safe_to_edit, change_impact)"
        ),
    )
    parser.add_argument(
        "--severity-min",
        choices=["error", "warn", "info"],
        default="warn",
        help=(
            "Minimum severity to include for --check-constraints (default: "
            "warn — suppresses info-level rules)"
        ),
    )
    parser.add_argument(
        "--constraint-path-filter",
        default="",
        metavar="GLOB",
        help=(
            "Optional fnmatch-style glob applied to caller_file for "
            "--check-constraints (e.g. 'mcp/**')"
        ),
    )


def _add_agent_skills_options(parser: argparse.ArgumentParser) -> None:
    """Add the project-local agent skill inventory entrypoint."""
    parser.add_argument(
        "--agent-skills",
        action="store_true",
        help="List project-local .agents/skills metadata, gaps, and read order",
    )
    parser.add_argument(
        "--agent-skills-root",
        help="Override the skills root for --agent-skills (default: .agents/skills)",
    )


def _add_agent_workflow_options(parser: argparse.ArgumentParser) -> None:
    """Add the agent workflow pack entrypoint."""
    parser.add_argument(
        "--agent-workflow",
        action="store_true",
        help="Print a SMART workflow command pack for agent-guided code work",
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
        default=5000,
        help="Max files to index with --ast-cache (default: 5000)",
    )
    parser.add_argument(
        "--ast-cache-force",
        action="store_true",
        help="Force full re-index with --ast-cache",
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
    parser.add_argument(
        "--codegraph-sitemap",
        action="store_true",
        help="Generate hierarchical project code map: directory→file→class→function (CodeGraph parity)",
    )
    parser.add_argument(
        "--codegraph-sitemap-mode",
        choices=["full", "api", "module", "flat"],
        default="full",
        help="Mode for --codegraph-sitemap (default: full)",
    )
    parser.add_argument(
        "--codegraph-sitemap-language",
        help="Language filter for --codegraph-sitemap",
    )
    parser.add_argument(
        "--codegraph-sitemap-directory",
        help="Directory filter for --codegraph-sitemap (relative path)",
    )
    parser.add_argument(
        "--codegraph-sitemap-max-files",
        type=int,
        default=200,
        help="Max files for --codegraph-sitemap (default: 200)",
    )
    parser.add_argument(
        "--codegraph-xref",
        metavar="SYMBOL",
        help="Instant cross-reference: definition + callers + callees + import deps "
        "(CodeGraph parity). Requires ast_cache index.",
    )
    parser.add_argument(
        "--codegraph-xref-mode",
        choices=["symbol", "file"],
        default="symbol",
        help="Mode for --codegraph-xref: symbol or file (default: symbol)",
    )
    parser.add_argument(
        "--codegraph-xref-file",
        help="File path to disambiguate (symbol mode) or target (file mode)",
    )
    parser.add_argument(
        "--codegraph-complexity-heatmap",
        nargs="?",
        const="project",
        choices=["project", "file", "function"],
        help="Cyclomatic complexity heatmap (CodeGraph parity). "
        "project=full heatmap, file=per-file, function=specific function",
    )
    parser.add_argument(
        "--codegraph-complexity-file",
        help="File path for file/function mode (relative to project root)",
    )
    parser.add_argument(
        "--codegraph-complexity-function",
        help="Function name for function mode",
    )
    parser.add_argument(
        "--codegraph-complexity-language",
        help="Language filter for complexity heatmap",
    )
    parser.add_argument(
        "--codegraph-complexity-directory",
        help="Directory filter for complexity heatmap (relative path)",
    )
    parser.add_argument(
        "--codegraph-complexity-max-files",
        type=int,
        default=200,
        help="Max files to scan in project mode (default: 200)",
    )
    parser.add_argument(
        "--symbol-search-language",
        help="Language filter for --symbol-search",
    )
    parser.add_argument(
        "--symbol-search-kind",
        choices=["function", "class", "variable", "import", "any"],
        default="any",
        help="Symbol kind filter for --symbol-search (default: any)",
    )
    parser.add_argument(
        "--symbol-search-limit",
        type=int,
        default=50,
        help="Max results for --symbol-search (default: 50)",
    )
    parser.add_argument(
        "--symbol-resolve",
        metavar="SYMBOL",
        help="Go-to-definition: find where a symbol is defined (CodeGraph parity). "
        "Supports dotted names like module.Class.method",
    )
    parser.add_argument(
        "--symbol-resolve-mode",
        choices=["resolve", "references"],
        default="resolve",
        help="Mode for --symbol-resolve: resolve=go-to-def, references=find-all-refs (default: resolve)",
    )
    parser.add_argument(
        "--class-hierarchy",
        action="store_true",
        help="Class inheritance hierarchy analysis: subclasses, superclasses, impact (CodeGraph parity)",
    )
    parser.add_argument(
        "--class-hierarchy-mode",
        choices=["subclasses", "superclasses", "tree", "impact", "all", "summary"],
        default="summary",
        help="Mode for --class-hierarchy (default: summary)",
    )
    parser.add_argument(
        "--class-hierarchy-class",
        help="Target class name for --class-hierarchy subclasses/superclasses/tree/impact modes",
    )
    parser.add_argument(
        "--class-hierarchy-depth",
        type=int,
        default=10,
        help="Max traversal depth for --class-hierarchy subclasses mode (default: 10)",
    )
    parser.add_argument(
        "--dependency-matrix",
        action="store_true",
        help="Module coupling analysis: pairwise dependency scores, hotspots, unstable modules (CodeGraph parity)",
    )
    parser.add_argument(
        "--dependency-matrix-mode",
        choices=["summary", "matrix", "hotspots", "file", "unstable"],
        default="summary",
        help="Mode for --dependency-matrix (default: summary)",
    )
    parser.add_argument(
        "--dependency-matrix-file",
        help="File path for --dependency-matrix file mode",
    )
    parser.add_argument(
        "--dependency-matrix-top-k",
        type=int,
        default=10,
        help="Top-K coupled pairs for --dependency-matrix hotspots mode (default: 10)",
    )
    parser.add_argument(
        "--codegraph-visualize",
        action="store_true",
        help="Export call graph as Mermaid flowchart diagram (CodeGraph parity)",
    )
    parser.add_argument(
        "--codegraph-visualize-mode",
        choices=["full", "file", "function"],
        default="full",
        help="Mode for --codegraph-visualize (default: full)",
    )
    parser.add_argument(
        "--codegraph-visualize-file",
        help="File path for --codegraph-visualize mode=file",
    )
    parser.add_argument(
        "--codegraph-visualize-function",
        help="Seed function name for --codegraph-visualize mode=function",
    )
    parser.add_argument(
        "--codegraph-visualize-depth",
        type=int,
        default=3,
        help="Max transitive depth for --codegraph-visualize mode=function (default: 3)",
    )
    parser.add_argument(
        "--codegraph-visualize-max-edges",
        type=int,
        default=150,
        help="Max edges to render for --codegraph-visualize (default: 150)",
    )
    parser.add_argument(
        "--codegraph-visualize-direction",
        choices=["TD", "LR", "BT", "RL"],
        default="TD",
        help="Mermaid flowchart direction for --codegraph-visualize (default: TD)",
    )
    parser.add_argument(
        "--dependency-matrix-threshold",
        type=float,
        default=0.7,
        help="Instability threshold for --dependency-matrix unstable mode (default: 0.7)",
    )


def _add_trace_impact_options(parser: argparse.ArgumentParser) -> None:
    """``--trace-impact`` family (symbol caller / usage trace)."""
    parser.add_argument(
        "--trace-impact",
        action="store_true",
        help="Trace symbol impact: find all callers and usage sites of a symbol",
    )
    parser.add_argument(
        "--trace-impact-symbol",
        metavar="NAME",
        help="Symbol name to trace for --trace-impact (required)",
    )
    parser.add_argument(
        "--trace-impact-file",
        metavar="PATH",
        help=(
            "Optional source file for --trace-impact "
            "(filters to the same language to reduce false positives)"
        ),
    )
    parser.add_argument(
        "--trace-impact-roots",
        metavar="PATHS",
        help=(
            "Optional project root(s) for --trace-impact, comma-separated. "
            "Defaults to the project root."
        ),
    )


def _add_environment_probe_options(parser: argparse.ArgumentParser) -> None:
    """``--check-tools`` + ``--build-project-index`` (env probes + index rebuild)."""
    parser.add_argument(
        "--check-tools",
        action="store_true",
        help="Check whether fd and ripgrep are installed and return their versions",
    )
    parser.add_argument(
        "--build-project-index",
        action="store_true",
        help=(
            "Rebuild the persistent project index from scratch and save it to disk. "
            "For full options (per-root indexing, notes), call the MCP tool directly."
        ),
    )
    parser.add_argument(
        "--build-project-index-roots",
        nargs="+",
        metavar="PATH",
        help="Optional directories to index for --build-project-index (defaults to project root)",
    )
    parser.add_argument(
        "--build-project-index-notes",
        metavar="TEXT",
        help="Optional architecture notes to attach to the rebuilt index",
    )


def _add_modification_guard_options(parser: argparse.ArgumentParser) -> None:
    """``--modification-guard`` family (T1 round-37c CLI-MCP parity).

    CLAUDE.md hard requirement — every MCP tool must have a CLI equivalent.
    J12 added trace-impact / check-tools / build-project-index; this
    closes the same gap for modification_guard.
    """
    parser.add_argument(
        "--modification-guard",
        action="store_true",
        help=(
            "Pre-modification safety check: report how many sites depend on "
            "the symbol you are about to modify. Use BEFORE editing any "
            "public symbol."
        ),
    )
    parser.add_argument(
        "--modification-guard-symbol",
        metavar="NAME",
        help=(
            "Symbol name to check for --modification-guard "
            "(required; example: 'processPayment', 'UserService')"
        ),
    )
    parser.add_argument(
        "--modification-guard-type",
        choices=[
            "rename",
            "signature_change",
            "delete",
            "behavior_change",
            "refactor",
        ],
        help=(
            "Type of modification you plan to make for --modification-guard "
            "(required: rename / signature_change / delete / behavior_change / "
            "refactor)"
        ),
    )
    parser.add_argument(
        "--modification-guard-file",
        metavar="PATH",
        help=(
            "Optional source file where the symbol is defined for "
            "--modification-guard (improves accuracy)"
        ),
    )


def _add_decision_journal_options(parser: argparse.ArgumentParser) -> None:
    """``--decision-journal`` family (r37fG CLI-MCP parity).

    Persistent journal of architectural decisions. CLI mirrors the four
    MCP modes (record / get / search / supersede) so agents reading
    ``--help`` get the same affordances they get over MCP.
    """
    _VERDICTS = [
        "SAFE",
        "CAUTION",
        "REVIEW",
        "UNSAFE",
        "INFO",
        "WARN",
        "ERROR",
        "NOT_FOUND",
    ]
    parser.add_argument(
        "--decision-journal",
        action="store_true",
        help=(
            "Persistent journal of architectural decisions. Use to record "
            "rationale + alternatives for non-trivial choices, or search "
            "for prior decisions before re-litigating. Default mode: search."
        ),
    )
    parser.add_argument(
        "--decision-journal-mode",
        choices=["record", "get", "search", "supersede"],
        default="search",
        help="Decision-journal mode (default: search).",
    )
    parser.add_argument(
        "--decision-journal-id", metavar="ID", help="Decision id (for get/supersede)."
    )
    parser.add_argument(
        "--decision-journal-new-id",
        metavar="ID",
        help="Replacement decision id (for supersede).",
    )
    parser.add_argument(
        "--decision-journal-title", metavar="TEXT", help="Decision title (for record)."
    )
    parser.add_argument(
        "--decision-journal-rationale",
        metavar="TEXT",
        help="Decision rationale (for record).",
    )
    parser.add_argument(
        "--decision-journal-verdict",
        choices=_VERDICTS,
        help="Decision verdict (required for record; canonical vocabulary).",
    )
    parser.add_argument(
        "--decision-journal-tags",
        nargs="+",
        metavar="TAG",
        help="Decision tags (for record).",
    )
    parser.add_argument(
        "--decision-journal-query",
        metavar="TEXT",
        help="Substring query (for search).",
    )
    parser.add_argument(
        "--decision-journal-verdict-filter",
        choices=_VERDICTS,
        help="Filter search results by verdict.",
    )
    parser.add_argument(
        "--decision-journal-limit",
        type=int,
        default=20,
        metavar="N",
        help="Max results for search (default: 20, max: 100).",
    )


def _add_batch_search_options(parser: argparse.ArgumentParser) -> None:
    """``--batch-search`` family (T2 round-37d CLI-MCP parity).

    CLAUDE.md hard requirement — every MCP tool must have a CLI equivalent.
    batch_search needs 2-10 queries, each with pattern + optional roots.
    The CLI accepts a JSON file with the queries array, mirroring how the
    MCP tool consumes them.
    """
    parser.add_argument(
        "--batch-search",
        action="store_true",
        help=(
            "Run 2-10 ripgrep searches in parallel and return their results. "
            "Requires --batch-search-queries-json FILE pointing to a JSON "
            "array of {pattern, roots?, literal?, case_sensitive?, label?} "
            "query objects."
        ),
    )
    parser.add_argument(
        "--batch-search-queries-json",
        metavar="PATH",
        help=(
            "Path to JSON file containing the batch_search queries array "
            "(required for --batch-search; 2-10 items, each with at least "
            "a 'pattern' key). See BatchSearchTool inputSchema for the "
            "full per-query shape."
        ),
    )
