#!/usr/bin/env python3
"""
Standalone CLI for search_content (ripgrep wrapper)

Maps CLI flags to the MCP SearchContentTool and prints JSON/text.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from ...mcp.tools.search_content_tool import SearchContentTool
from ...output_manager import output_data, output_error, set_output_mode
from ...project_detector import detect_project_root


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search text content in files using ripgrep via MCP wrapper.",
    )

    roots_or_files = parser.add_mutually_exclusive_group(required=True)
    roots_or_files.add_argument(
        "--roots",
        nargs="+",
        help="Directory roots to search recursively",
    )
    roots_or_files.add_argument(
        "--files",
        nargs="+",
        help="Explicit file list to search",
    )

    parser.add_argument("--query", required=True, help="Search pattern")

    # Output
    parser.add_argument(
        "--output-format",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )

    # rg options
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

    # project root
    parser.add_argument(
        "--project-root",
        help="Project root directory for security boundary (auto-detected if omitted)",
    )

    return parser


async def _run(args: argparse.Namespace) -> int:
    set_output_mode(quiet=bool(args.quiet), json_output=(args.output_format == "json"))

    project_root = detect_project_root(None, args.project_root)
    tool = SearchContentTool(project_root)

    payload: dict[str, Any] = {
        "query": args.query,
    }
    if args.roots:
        payload["roots"] = list(args.roots)
    if args.files:
        payload["files"] = list(args.files)

    # Options mapping
    if args.case:
        payload["case"] = args.case
    if args.fixed_strings:
        payload["fixed_strings"] = True
    if args.word:
        payload["word"] = True
    if args.multiline:
        payload["multiline"] = True
    if args.include_globs:
        payload["include_globs"] = args.include_globs
    if args.exclude_globs:
        payload["exclude_globs"] = args.exclude_globs
    if args.follow_symlinks:
        payload["follow_symlinks"] = True
    if args.hidden:
        payload["hidden"] = True
    if args.no_ignore:
        payload["no_ignore"] = True
    if args.max_filesize:
        payload["max_filesize"] = args.max_filesize
    if args.context_before is not None:
        payload["context_before"] = int(args.context_before)
    if args.context_after is not None:
        payload["context_after"] = int(args.context_after)
    if args.encoding:
        payload["encoding"] = args.encoding
    if args.max_count is not None:
        payload["max_count"] = int(args.max_count)
    if args.timeout_ms is not None:
        payload["timeout_ms"] = int(args.timeout_ms)
    if args.count_only_matches:
        payload["count_only_matches"] = True
    if args.summary_only:
        payload["summary_only"] = True
    if args.optimize_paths:
        payload["optimize_paths"] = True
    if args.group_by_file:
        payload["group_by_file"] = True
    if args.total_only:
        payload["total_only"] = True

    try:
        result = await tool.execute(payload)
        output_data(result, args.output_format)
        return 0 if (isinstance(result, dict) or isinstance(result, int)) else 0
    except Exception as e:
        output_error(str(e))
        return 1


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        rc = asyncio.run(_run(args))
    except KeyboardInterrupt:
        rc = 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
