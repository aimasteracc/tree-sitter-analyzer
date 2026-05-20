#!/usr/bin/env python3
"""
find_and_grep MCP Tool (fd → ripgrep)

First narrow files with fd, then search contents with ripgrep, with caps & meta.
"""

from __future__ import annotations

import time
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from ..utils.file_output_manager import FileOutputManager
from ..utils.gitignore_detector import get_default_detector
from . import fd_rg_utils
from .base_tool import BaseMCPTool
from .find_and_grep_execution import (
    apply_match_limits,
    build_fd_command_from_arguments,
    build_fd_error_response,
    build_rg_command_from_arguments,
    build_rg_error_response,
    parse_fd_output,
    resolve_fd_no_ignore,
    sort_files,
)
from .find_and_grep_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .find_and_grep_helpers import (
    FindAndGrepCountOnlyContext,
    FindAndGrepFullMatchContext,
    FindAndGrepRgModeContext,
    build_count_only_response,
    build_empty_response,
    build_missing_commands_response,
    build_search_meta,
)
from .find_and_grep_response import FindAndGrepRespondMixin


class FindAndGrepTool(FindAndGrepRespondMixin, BaseMCPTool):
    """MCP tool that composes fd and ripgrep with safety limits and metadata.

    First narrows files with fd, then searches contents with ripgrep.
    Supports total_only, count_only, summary, and group_by_file modes.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize with optional project root for path resolution."""
        self.file_output_manager: FileOutputManager | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "find_and_grep",
            "description": (
                "Map+Trace: find files by name then grep inside them. "
                "Prefer total_only/count_only/summary over full results."
            ),
            "inputSchema": _TOOL_SCHEMA,
        }

    def _validate_roots(self, roots: list[str]) -> list[str]:
        """Resolve and validate each root directory path."""
        validated: list[str] = []
        for r in roots:
            try:
                resolved = self.resolve_and_validate_directory_path(r)
                validated.append(resolved)
            except ValueError as e:
                raise ValueError(f"Invalid root '{r}': {e}") from e
        return validated

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate roots and query arguments."""
        if "roots" not in arguments or not isinstance(arguments["roots"], list):
            raise ValueError("roots is required and must be an array")
        if (
            "query" not in arguments
            or not isinstance(arguments["query"], str)
            or not arguments["query"].strip()
        ):
            raise ValueError("query is required and must be a non-empty string")
        if "file_limit" in arguments and not isinstance(arguments["file_limit"], int):
            raise ValueError("file_limit must be an integer")
        return True

    @handle_mcp_errors("find_and_grep")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any] | int:
        """Execute fd+rg pipeline: find files then grep contents."""
        missing_response = build_missing_commands_response(
            fd_rg_utils.get_missing_commands()
        )
        if missing_response:
            return missing_response

        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "toon")
        roots = self._validate_roots(arguments["roots"])

        files, fd_elapsed_ms, truncated_fd = await self._run_fd(arguments, roots)
        if isinstance(files, dict):
            return files  # error response

        return await self._execute_rg_modes(
            FindAndGrepRgModeContext(
                arguments=arguments,
                files=files,
                fd_elapsed_ms=fd_elapsed_ms,
                truncated_fd=truncated_fd,
                output_format=output_format,
            )
        )

    async def _execute_rg_modes(
        self,
        context: FindAndGrepRgModeContext,
    ) -> dict[str, Any] | int:
        """Run ripgrep and dispatch count or match response modes."""
        arguments = context.arguments
        searched_file_count = len(context.files)
        if searched_file_count == 0:
            return build_empty_response(
                arguments,
                truncated=context.truncated_fd,
                fd_elapsed_ms=context.fd_elapsed_ms,
            )
        rg_result = await self._run_rg(arguments, context.files)
        if isinstance(rg_result, dict) and "error" in rg_result:
            return rg_result
        rg_rc, rg_out, rg_elapsed_ms = rg_result
        if not isinstance(rg_out, bytes):  # nosec B101
            rg_out = rg_out.encode("utf-8") if isinstance(rg_out, str) else b""
        if arguments.get("total_only", False):
            count_data = fd_rg_utils.parse_rg_count_output(rg_out)
            return count_data.pop("__total__", 0)
        if arguments.get("count_only_matches", False):
            count_data = fd_rg_utils.parse_rg_count_output(rg_out)
            count_context = _build_count_only_context(
                context,
                count_data,
                searched_file_count,
                rg_elapsed_ms,
            )
            return build_count_only_response(count_context)
        return self._execute_full_match_mode(
            FindAndGrepFullMatchContext(
                arguments=arguments,
                rg_out=rg_out,
                fd_elapsed_ms=context.fd_elapsed_ms,
                rg_elapsed_ms=rg_elapsed_ms,
                searched_file_count=searched_file_count,
                truncated_fd=context.truncated_fd,
                output_format=context.output_format,
            )
        )

    def _execute_full_match_mode(
        self,
        context: FindAndGrepFullMatchContext,
    ) -> dict[str, Any]:
        """Parse rg matches and dispatch the selected response mode."""
        arguments = context.arguments
        matches = fd_rg_utils.parse_rg_json_lines_to_matches(context.rg_out)
        matches, truncated_rg = apply_match_limits(matches, arguments)

        if arguments.get("optimize_paths", False) and matches:
            matches = fd_rg_utils.optimize_match_paths(matches)

        meta = build_search_meta(
            searched_file_count=context.searched_file_count,
            truncated=context.truncated_fd or truncated_rg,
            fd_elapsed_ms=context.fd_elapsed_ms,
            rg_elapsed_ms=context.rg_elapsed_ms,
        )

        if arguments.get("group_by_file", False) and matches:
            return self._respond_grouped(arguments, matches, meta)
        if arguments.get("summary_only", False):
            return self._respond_summary(arguments, matches, meta)
        return self._respond_full(arguments, matches, meta, context.output_format)

    async def _run_fd(
        self, arguments: dict[str, Any], roots: list[str]
    ) -> tuple[list[str] | dict[str, Any], int, bool]:
        """Run fd command. Returns (files, elapsed_ms, truncated) or (error_dict, 0, False)."""
        fd_limit = fd_rg_utils.clamp_int(
            arguments.get("file_limit"),
            fd_rg_utils.DEFAULT_RESULTS_LIMIT,
            fd_rg_utils.MAX_RESULTS_HARD_CAP,
        )
        fd_cmd = build_fd_command_from_arguments(
            arguments,
            roots,
            fd_limit=fd_limit,
            no_ignore=resolve_fd_no_ignore(
                arguments,
                self.project_root,
                detector_factory=get_default_detector,
            ),
        )

        started = time.time()
        rc, out, err = await fd_rg_utils.run_command_capture(fd_cmd)
        elapsed = int((time.time() - started) * 1000)

        if rc != 0:
            return build_fd_error_response(err, rc), 0, False

        files, truncated = parse_fd_output(out, fd_limit)
        sort_files(files, arguments.get("sort"))
        return files, elapsed, truncated

    # Execute ripgrep on discovered files
    async def _run_rg(
        self, arguments: dict[str, Any], files: list[str]
    ) -> tuple[int, bytes, int] | dict[str, Any]:
        """Run ripgrep on found files. Returns (rc, output, elapsed_ms) or error dict."""
        rg_cmd = build_rg_command_from_arguments(arguments, files)

        started = time.time()
        rc, out, err = await fd_rg_utils.run_command_capture(
            rg_cmd, timeout_ms=arguments.get("timeout_ms")
        )
        elapsed = int((time.time() - started) * 1000)

        if rc not in (0, 1):
            return build_rg_error_response(err, rc)

        return rc, out, elapsed


def _build_count_only_context(
    context: FindAndGrepRgModeContext,
    count_data: dict[str, int],
    searched_file_count: int,
    rg_elapsed_ms: int,
) -> FindAndGrepCountOnlyContext:
    """Build the count-only response context for the current rg run."""
    return FindAndGrepCountOnlyContext(
        arguments=context.arguments,
        count_data=count_data,
        output_format=context.output_format,
        searched_file_count=searched_file_count,
        truncated=context.truncated_fd,
        fd_elapsed_ms=context.fd_elapsed_ms,
        rg_elapsed_ms=rg_elapsed_ms,
    )
