"""Helpers for the search_content standalone CLI."""

from __future__ import annotations

import argparse
from typing import Any


def add_output_options(parser: argparse.ArgumentParser) -> None:
    """Register shared output flags.

    F2: ``--format`` is accepted as an alias for ``--output-format`` so that
    callers can use the same flag name across the main CLI and subcommands.
    Both flags target the same ``output_format`` destination.
    """
    parser.add_argument(
        "--output-format",
        "--format",
        dest="output_format",
        choices=["json", "text", "toon"],
        default="json",
        help="Output format: 'json' (default), 'text', or 'toon' (50-70%% token reduction). Alias: --format",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )


def add_rg_options(parser: argparse.ArgumentParser) -> None:
    """Register ripgrep matching flags."""
    parser.add_argument(
        "--case", choices=["smart", "insensitive", "sensitive"], default="smart"
    )
    parser.add_argument("--fixed-strings", action="store_true")
    parser.add_argument("--word", action="store_true")
    parser.add_argument("--multiline", action="store_true")
    parser.add_argument("--include-globs", nargs="+")
    parser.add_argument("--exclude-globs", nargs="+")
    parser.add_argument("--follow-symlinks", action="store_true")
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--no-ignore", action="store_true")
    parser.add_argument("--max-filesize")
    parser.add_argument("--context-before", type=int)
    parser.add_argument("--context-after", type=int)
    parser.add_argument("--encoding")
    parser.add_argument("--max-count", type=int)
    parser.add_argument("--timeout-ms", type=int)
    parser.add_argument("--count-only-matches", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--optimize-paths", action="store_true")
    parser.add_argument("--group-by-file", action="store_true")
    parser.add_argument("--total-only", action="store_true")


def build_search_content_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Map CLI arguments to SearchContentTool arguments."""
    payload: dict[str, Any] = {
        "query": args.query,
        "output_format": args.output_format,
    }
    if args.roots:
        payload["roots"] = list(args.roots)
    if args.files:
        payload["files"] = list(args.files)

    _add_rg_payload_options(payload, args)
    return payload


def _add_rg_payload_options(payload: dict[str, Any], args: argparse.Namespace) -> None:
    """Add ripgrep payload options when present."""
    optional_values = {
        "case": args.case,
        "include_globs": args.include_globs,
        "exclude_globs": args.exclude_globs,
        "max_filesize": args.max_filesize,
        "encoding": args.encoding,
    }
    for key, value in optional_values.items():
        if value:
            payload[key] = value

    optional_ints = {
        "context_before": args.context_before,
        "context_after": args.context_after,
        "max_count": args.max_count,
        "timeout_ms": args.timeout_ms,
    }
    for key, value in optional_ints.items():
        if value is not None:
            payload[key] = int(value)

    flag_options = [
        "fixed_strings",
        "word",
        "multiline",
        "follow_symlinks",
        "hidden",
        "no_ignore",
        "count_only_matches",
        "summary_only",
        "optimize_paths",
        "group_by_file",
        "total_only",
    ]
    for key in flag_options:
        if getattr(args, key):
            payload[key] = True
