"""Argument parser construction for the tree-sitter-analyzer CLI."""

from __future__ import annotations

import argparse

from .. import __version__

CLI_EPILOG = (
    "Examples:\n"
    "  tree-sitter-analyzer file.java --table=full         Markdown table of classes/methods\n"
    "  tree-sitter-analyzer file.java --query-key class    Extract all class definitions\n"
    "  tree-sitter-analyzer file.java --advanced            Full analysis with all elements\n"
    "  tree-sitter-analyzer file.java --structure           Structure overview in JSON\n"
    "  tree-sitter-analyzer file.java --summary             Quick summary of classes/methods\n"
    "  tree-sitter-analyzer file.java --partial-read --start-line 10 --end-line 20\n"
    "  tree-sitter-analyzer file.py --file-health           A-F health grade + signal + smells\n"
    "  tree-sitter-analyzer file.py --safe-to-edit --edit-type refactor\n"
    "  tree-sitter-analyzer file.py --refactor              Refactoring suggestions with plans\n"
    "  tree-sitter-analyzer file.py --smart-context         One-call file profile\n"
    "  tree-sitter-analyzer agent-skills                    Project-local agent skill inventory\n"
    "  tree-sitter-analyzer agent-workflow file.py           SMART workflow command pack\n"
    "  tree-sitter-analyzer parser-readiness swift           Parser/plugin readiness advisor\n"
    "  tree-sitter-analyzer file-health file.py             Agent-friendly alias for --file-health\n"
    "  tree-sitter-analyzer change-impact --change-impact-mode staged --agent-summary-only\n"
    "  tree-sitter-analyzer --dependencies summary           Project dependency summary\n"
    "  tree-sitter-analyzer file.py --dependencies file_deps  File dependency graph\n"
    "  tree-sitter-analyzer --change-impact                 Git diff impact analysis\n"
    "  tree-sitter-analyzer --detect-routes                 URL→handler routes (Flask/Django/FastAPI/Express/Spring)\n"
    "  tree-sitter-analyzer detect-routes --detect-routes-mode all\n"
    "  tree-sitter-analyzer --project-health                Score ALL project files\n"
    "  tree-sitter-analyzer --overview                      Project portrait + health summary\n"
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
        help="For --change-impact, output only the compact agent decision surface",
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
        choices=["index", "lookup", "search", "sync", "changes", "stats", "invalidate"],
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
