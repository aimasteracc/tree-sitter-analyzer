"""MCP equivalent, index management, constraints, and clean-state argument groups."""

from __future__ import annotations

import argparse


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
        default=20_000,
        help="Max files to index when --autoindex-mode=warm (default: 20000)",
    )
    parser.add_argument(
        "--full-index",
        action="store_true",
        help=(
            "Force a complete project-wide AST re-index "
            "(codegraph_full_index). Use after pulls, rebases, or large "
            "refactors. Default mode 'incremental'."
        ),
    )
    parser.add_argument(
        "--full-index-mode",
        choices=["full", "incremental"],
        default="incremental",
        help="'full' re-indexes all; 'incremental' processes changes only (default)",
    )
    parser.add_argument(
        "--full-index-max-files",
        type=int,
        default=20_000,
        help="Max files to index per --full-index run (default: 20000)",
    )
    parser.add_argument(
        "--full-index-include-activation",
        action="store_true",
        help=(
            "Compute temporal git activation during --full-index "
            "(slower; default keeps warm-cache indexing fast)"
        ),
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
        default=20_000,
        help="Max files for --incremental-sync (default: 20000)",
    )
    parser.add_argument(
        "--knowledge-graph-index",
        action="store_true",
        help=(
            "Build/update the whole-project code+docs knowledge graph sidecar "
            "(JSON by default, optional LadybugDB mirror)."
        ),
    )
    parser.add_argument(
        "--knowledge-graph-index-mode",
        choices=["build", "update", "status"],
        default="update",
        help="Mode for --knowledge-graph-index (default: update)",
    )
    parser.add_argument(
        "--knowledge-graph-backend",
        choices=["auto", "json", "ladybug", "hybrid"],
        default="auto",
        help=(
            "Persistence backend for --knowledge-graph-index "
            "(default: auto; writes LadybugDB when installed plus JSON fallback)"
        ),
    )
    parser.add_argument(
        "--knowledge-graph-max-files",
        type=int,
        default=1_000_000,
        help=(
            "Max files for --knowledge-graph-index-mode build; update mode "
            "uses a safe full-project scan (default: 1000000)"
        ),
    )
    parser.add_argument(
        "--knowledge-graph-max-nodes",
        type=int,
        default=0,
        help=(
            "Max nodes to materialize into the knowledge graph; 0 means no cap "
            "(default: 0)"
        ),
    )
    parser.add_argument(
        "--knowledge-graph-max-edges",
        type=int,
        default=0,
        help=(
            "Max edges to materialize into the knowledge graph; 0 means no cap "
            "(default: 0)"
        ),
    )
    parser.add_argument(
        "--knowledge-graph-no-docs",
        action="store_true",
        help="Skip Markdown doc link extraction during --knowledge-graph-index",
    )
    parser.add_argument(
        "--knowledge-graph-serve",
        action="store_true",
        help=(
            "Start a local interactive knowledge graph service. The browser "
            "view loads callers, callees, imports, inheritance, and doc links "
            "on demand from the materialized graph sidecar."
        ),
    )
    parser.add_argument(
        "--knowledge-graph-host",
        default="127.0.0.1",
        help="Host for --knowledge-graph-serve (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--knowledge-graph-port",
        type=int,
        default=8765,
        help="Port for --knowledge-graph-serve (default: 8765)",
    )
    parser.add_argument(
        "--knowledge-graph-no-browser",
        action="store_true",
        help="Do not open a browser automatically for --knowledge-graph-serve",
    )
    parser.add_argument(
        "--knowledge-graph-watch",
        action="store_true",
        help="Watch for file changes and keep the knowledge graph up to date.",
    )
    parser.add_argument(
        "--knowledge-graph-watch-backend",
        default="poll",
        choices=["poll", "watchdog"],
        help="File watching backend (default: poll)",
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
