#!/usr/bin/env python3
"""
Standalone CLI for list_files (fd wrapper)

Maps CLI flags to the MCP ListFilesTool and prints JSON/text via OutputManager.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from ...mcp.tools.list_files_tool import ListFilesTool
from ...output_manager import output_data, output_error, set_output_mode
from ...project_detector import detect_project_root


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List files and directories using fd via MCP wrapper.",
    )

    # Roots
    parser.add_argument(
        "roots",
        nargs="+",
        help="One or more root directories to search in",
    )

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

    # fd options
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
    parser.add_argument("--limit", type=int)
    parser.add_argument("--count-only", action="store_true")

    # project root
    parser.add_argument(
        "--project-root",
        help="Project root directory for security boundary (auto-detected if omitted)",
    )

    return parser


async def _run(args: argparse.Namespace) -> int:
    set_output_mode(quiet=bool(args.quiet), json_output=(args.output_format == "json"))

    project_root = detect_project_root(None, args.project_root)
    tool = ListFilesTool(project_root)

    payload: dict[str, Any] = {
        "roots": list(args.roots),
    }

    # Optional mappings
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
    if args.limit is not None:
        payload["limit"] = int(args.limit)
    if args.count_only:
        payload["count_only"] = True

    try:
        result = await tool.execute(payload)
        output_data(result, args.output_format)
        return 0 if (isinstance(result, dict) and result.get("success", True)) else 0
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
