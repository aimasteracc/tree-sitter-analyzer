#!/usr/bin/env python3
"""
Standalone CLI for find_and_grep (fd → ripgrep composition)

Maps CLI flags to the MCP FindAndGrepTool and prints JSON/text.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from ...mcp.tools.find_and_grep_tool import FindAndGrepTool
from ...output_manager import output_data, output_error, set_output_mode
from ...project_detector import detect_project_root
from .find_and_grep_cli_helpers import (
    add_fd_options,
    add_output_options,
    add_rg_options,
    build_find_and_grep_payload,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Two-stage search: fd for files, then ripgrep for content.",
    )

    # Required
    parser.add_argument("--roots", nargs="+", required=True, help="Search roots")
    parser.add_argument("--query", required=True, help="Content query")

    add_output_options(parser)
    add_fd_options(parser)
    add_rg_options(parser)

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
    payload = build_find_and_grep_payload(args)

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
