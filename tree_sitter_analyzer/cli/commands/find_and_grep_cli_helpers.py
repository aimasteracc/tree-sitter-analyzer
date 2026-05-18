"""Helpers for the find_and_grep standalone CLI."""

from __future__ import annotations

import argparse
from typing import Any


def add_output_options(parser: argparse.ArgumentParser) -> None:
    """Register shared output flags."""
    parser.add_argument(
        "--output-format",
        choices=["json", "text", "toon"],
        default="json",
        help="Output format: 'json' (default), 'text', or 'toon' (50-70%% token reduction)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )


def add_fd_options(parser: argparse.ArgumentParser) -> None:
    """Register fd-stage filtering flags."""
    parser.add_argument("--pattern")
    parser.add_argument("--glob", action="store_true")
    parser.add_argument("--types", nargs="+")
    parser.add_argument("--extensions", nargs="+")
    parser.add_argument("--exclude", nargs="+")
    parser.add_argument("--depth", type=int)
    parser.add_argument("--follow-symlinks", action="store_true")
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--no-ignore", action="store_true")
    parser.add_argument("--size", nargs="+")
    parser.add_argument("--changed-within")
    parser.add_argument("--changed-before")
    parser.add_argument("--full-path-match", action="store_true")
    parser.add_argument("--file-limit", type=int)
    parser.add_argument("--sort", choices=["path", "mtime", "size"])


def add_rg_options(parser: argparse.ArgumentParser) -> None:
    """Register ripgrep-stage content matching flags."""
    parser.add_argument(
        "--case", choices=["smart", "insensitive", "sensitive"], default="smart"
    )
    parser.add_argument("--fixed-strings", action="store_true")
    parser.add_argument("--word", action="store_true")
    parser.add_argument("--multiline", action="store_true")
    parser.add_argument("--include-globs", nargs="+")
    parser.add_argument("--exclude-globs", nargs="+")
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


def build_find_and_grep_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Map CLI arguments to FindAndGrepTool arguments."""
    payload: dict[str, Any] = {
        "roots": list(args.roots),
        "query": args.query,
        "output_format": args.output_format,
    }
    _add_fd_payload_options(payload, args)
    _add_rg_payload_options(payload, args)
    return payload


def _add_fd_payload_options(payload: dict[str, Any], args: argparse.Namespace) -> None:
    """Add fd-stage payload options when present."""
    optional_values = {
        "pattern": args.pattern,
        "types": args.types,
        "extensions": args.extensions,
        "exclude": args.exclude,
        "size": args.size,
        "changed_within": args.changed_within,
        "changed_before": args.changed_before,
        "sort": args.sort,
    }
    for key, value in optional_values.items():
        if value:
            payload[key] = value

    optional_ints = {"depth": args.depth, "file_limit": args.file_limit}
    for key, value in optional_ints.items():
        if value is not None:
            payload[key] = int(value)

    flag_options = [
        "glob",
        "follow_symlinks",
        "hidden",
        "no_ignore",
        "full_path_match",
    ]
    for key in flag_options:
        if getattr(args, key):
            payload[key] = True


def _add_rg_payload_options(payload: dict[str, Any], args: argparse.Namespace) -> None:
    """Add ripgrep-stage payload options when present."""
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
        "count_only_matches",
        "summary_only",
        "optimize_paths",
        "group_by_file",
        "total_only",
    ]
    for key in flag_options:
        if getattr(args, key):
            payload[key] = True
