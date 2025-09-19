#!/usr/bin/env python3
"""
Standalone CLI for find_and_grep (fd → ripgrep composition)

Maps CLI flags to the MCP FindAndGrepTool and prints JSON/text.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from ...mcp.tools.find_and_grep_tool import FindAndGrepTool
from ...output_manager import output_data, output_error, set_output_mode
from ...project_detector import detect_project_root


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Two-stage search: fd for files, then ripgrep for content.",
    )

    # Required
    parser.add_argument("--roots", nargs="+", required=True, help="Search roots")
    parser.add_argument("--query", required=True, help="Content query")

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

    # fd options (subset mirrors ListFiles)
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

    # rg options (subset mirrors SearchContent)
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

    # project root
    parser.add_argument(
        "--project-root",
        help="Project root directory for security boundary (auto-detected if omitted)",
    )

    return parser


async def _run(args: argparse.Namespace) -> int:
    set_output_mode(quiet=bool(args.quiet), json_output=(args.output_format == "json"))

    project_root = detect_project_root(None, args.project_root)
    tool = FindAndGrepTool(project_root)

    payload: dict[str, Any] = {
        "roots": list(args.roots),
        "query": args.query,
    }

    # fd stage mappings
    if args.pattern:
        payload["pattern"] = args.pattern
    if args.glob:
        payload["glob"] = True
    if args.types:
        payload["types"] = args.types
    if args.extensions:
        payload["extensions"] = args.extensions
    if args.exclude:
        payload["exclude"] = args.exclude
    if args.depth is not None:
        payload["depth"] = int(args.depth)
    if args.follow_symlinks:
        payload["follow_symlinks"] = True
    if args.hidden:
        payload["hidden"] = True
    if args.no_ignore:
        payload["no_ignore"] = True
    if args.size:
        payload["size"] = args.size
    if args.changed_within:
        payload["changed_within"] = args.changed_within
    if args.changed_before:
        payload["changed_before"] = args.changed_before
    if args.full_path_match:
        payload["full_path_match"] = True
    if args.file_limit is not None:
        payload["file_limit"] = int(args.file_limit)
    if args.sort:
        payload["sort"] = args.sort

    # rg stage mappings
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
