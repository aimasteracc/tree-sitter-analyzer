#!/usr/bin/env python3
"""
Standalone CLI for search_content (ripgrep wrapper)

Maps CLI flags to the MCP SearchContentTool and prints JSON/text.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from ...mcp.tools.search_content_tool import SearchContentTool
from ...output_manager import output_data, output_error, set_output_mode
from ...project_detector import detect_project_root
from ._case_resolution import warn_on_duplicate_case
from .search_content_cli_helpers import (
    add_output_options,
    add_rg_options,
    build_search_content_payload,
)


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

    add_output_options(parser)
    add_rg_options(parser)

    # project root
    parser.add_argument(
        "--project-root",
        help="Project root directory for security boundary (auto-detected if omitted)",
    )

    return parser


async def _run(args: argparse.Namespace) -> int:
    set_output_mode(quiet=bool(args.quiet), json_output=(args.output_format == "json"))

    # N1: surface ``--case`` last-wins behavior so callers know which value
    # actually won when the flag was passed more than once. Argparse keeps
    # the final value; this just makes the override visible on stderr.
    warn_on_duplicate_case(args.case)

    project_root = detect_project_root(None, args.project_root)
    tool = SearchContentTool(project_root)
    payload = build_search_content_payload(args)

    try:
        result = await tool.execute(payload)
        output_data(result, args.output_format)
        # Honour ``success`` in the response envelope so ``set -e`` and CI
        # steps see a non-zero exit when the tool reports failure.
        # ``result.get("success", True)`` default-True keeps int/other
        # non-dict shapes (e.g. count-only mode) at RC=0.
        if isinstance(result, dict) and result.get("success", True) is False:
            return 1
        return 0
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
