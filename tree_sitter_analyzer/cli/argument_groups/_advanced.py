"""Advanced argument groups: trace-impact, environment probe, modification guard,
decision journal, and batch search."""

from __future__ import annotations

import argparse

from ...constants import EDIT_KINDS


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
        choices=list(EDIT_KINDS),
        help=(
            "Type of modification you plan to make for --modification-guard "
            "(required; shares the same edit-kind vocabulary as --edit-type: "
            + " / ".join(EDIT_KINDS)
            + ")"
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
