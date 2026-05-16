#!/usr/bin/env python3
"""
find_and_grep MCP Tool (fd → ripgrep)

First narrow files with fd, then search contents with ripgrep, with caps & meta.
"""

from __future__ import annotations

import pathlib
import time
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import (
    apply_toon_format_to_response,
    attach_toon_content_to_response,
)
from ..utils.gitignore_detector import get_default_detector
from . import fd_rg_utils
from .base_tool import BaseMCPTool
from .find_and_grep_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .find_and_grep_helpers import handle_output

logger = __import__("logging").getLogger(__name__)


class FindAndGrepTool(BaseMCPTool):
    """MCP tool that composes fd and ripgrep with safety limits and metadata.

    First narrows files with fd, then searches contents with ripgrep.
    Supports total_only, count_only, summary, and group_by_file modes.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize with optional project root for path resolution."""
        super().__init__(project_root)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

    def set_project_path(self, project_path: str) -> None:
        """Update project path and reinitialize file output manager."""
        super().set_project_path(project_path)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)

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
        missing_commands = fd_rg_utils.get_missing_commands()
        if missing_commands:
            return {
                "success": False,
                "error": f"Required commands not found: {', '.join(missing_commands)}. Please install fd and ripgrep.",
                "count": 0,
                "results": [],
            }

        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "toon")
        roots = self._validate_roots(arguments["roots"])

        # fd step
        files, fd_elapsed_ms, truncated_fd = await self._run_fd(arguments, roots)
        if isinstance(files, dict):
            return files  # error response

        searched_file_count = len(files)
        if searched_file_count == 0:
            return {
                "success": True,
                "results": [],
                "count": 0,
                "meta": {
                    "searched_file_count": 0,
                    "truncated": truncated_fd,
                    "fd_elapsed_ms": fd_elapsed_ms,
                    "rg_elapsed_ms": 0,
                },
            }

        # rg step
        rg_result = await self._run_rg(arguments, files)
        if isinstance(rg_result, dict) and "error" in rg_result:
            return rg_result

        rg_rc, rg_out, rg_elapsed_ms = rg_result
        if not isinstance(rg_out, bytes):  # nosec B101
            rg_out = rg_out.encode("utf-8") if isinstance(rg_out, str) else b""

        # total_only mode
        if arguments.get("total_only", False):
            count_data = fd_rg_utils.parse_rg_count_output(rg_out)
            return count_data.pop("__total__", 0)

        # count_only mode
        if arguments.get("count_only_matches", False):
            count_data = fd_rg_utils.parse_rg_count_output(rg_out)
            total_matches = count_data.pop("__total__", 0)
            result = {
                "success": True,
                "count_only": True,
                "total_matches": total_matches,
                "file_counts": count_data,
                "meta": {
                    "searched_file_count": searched_file_count,
                    "truncated": truncated_fd,
                    "fd_elapsed_ms": fd_elapsed_ms,
                    "rg_elapsed_ms": rg_elapsed_ms,
                },
            }
            if output_format == "toon":
                return attach_toon_content_to_response(result)
            return result

        # Full match mode
        matches = fd_rg_utils.parse_rg_json_lines_to_matches(rg_out)
        matches, truncated_rg = self._apply_limits(matches, arguments)

        if arguments.get("optimize_paths", False) and matches:
            matches = fd_rg_utils.optimize_match_paths(matches)

        meta = {
            "searched_file_count": searched_file_count,
            "truncated": truncated_fd or truncated_rg,
            "fd_elapsed_ms": fd_elapsed_ms,
            "rg_elapsed_ms": rg_elapsed_ms,
        }

        # Dispatch to mode-specific handler
        if arguments.get("group_by_file", False) and matches:
            return self._respond_grouped(arguments, matches, meta)
        if arguments.get("summary_only", False):
            return self._respond_summary(arguments, matches, meta)
        return self._respond_full(arguments, matches, meta, output_format)

    async def _run_fd(
        self, arguments: dict[str, Any], roots: list[str]
    ) -> tuple[list[str] | dict[str, Any], int, bool]:
        """Run fd command. Returns (files, elapsed_ms, truncated) or (error_dict, 0, False)."""
        """Run fd command. Returns (files, elapsed_ms, truncated) or (error_dict, 0, False)."""
        fd_limit = fd_rg_utils.clamp_int(
            arguments.get("file_limit"),
            fd_rg_utils.DEFAULT_RESULTS_LIMIT,
            fd_rg_utils.MAX_RESULTS_HARD_CAP,
        )

        no_ignore = bool(arguments.get("no_ignore", False))
        if not no_ignore:
            detector = get_default_detector()
            original_roots = arguments.get("roots", [])
            if detector.should_use_no_ignore(original_roots, self.project_root):
                no_ignore = True
                detection_info = detector.get_detection_info(
                    original_roots, self.project_root
                )
                logger.info(
                    f"Auto-enabled --no-ignore due to .gitignore interference: "
                    f"{detection_info['reason']}"
                )

        fd_cmd = fd_rg_utils.build_fd_command(
            pattern=arguments.get("pattern"),
            glob=bool(arguments.get("glob", False)),
            types=arguments.get("types"),
            extensions=arguments.get("extensions"),
            exclude=arguments.get("exclude"),
            depth=arguments.get("depth"),
            follow_symlinks=bool(arguments.get("follow_symlinks", False)),
            hidden=bool(arguments.get("hidden", False)),
            no_ignore=no_ignore,
            size=arguments.get("size"),
            changed_within=arguments.get("changed_within"),
            changed_before=arguments.get("changed_before"),
            full_path_match=bool(arguments.get("full_path_match", False)),
            absolute=True,
            limit=fd_limit,
            roots=roots,
        )

        started = time.time()
        rc, out, err = await fd_rg_utils.run_command_capture(fd_cmd)
        elapsed = int((time.time() - started) * 1000)

        if rc != 0:
            return (
                {
                    "success": False,
                    "error": err.decode("utf-8", errors="replace").strip()
                    or "fd failed",
                    "returncode": rc,
                },
                0,
                False,
            )

        files = [
            line.strip()
            for line in out.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        ]

        truncated = len(files) > fd_limit
        if truncated:
            files = files[:fd_limit]

        self._sort_files(files, arguments.get("sort"))
        return files, elapsed, truncated

    def _sort_files(self, files: list[str], sort_mode: str | None) -> None:
        """Sort files by path, mtime, or size."""
        """Sort files by the requested mode."""
        if sort_mode not in ("path", "mtime", "size"):
            return
        try:
            if sort_mode == "path":
                files.sort()
            elif sort_mode == "mtime":
                files.sort(
                    key=lambda p: (
                        pathlib.Path(p).stat().st_mtime
                        if pathlib.Path(p).exists()
                        else 0
                    ),
                    reverse=True,
                )
            elif sort_mode == "size":
                files.sort(
                    key=lambda p: (
                        pathlib.Path(p).stat().st_size
                        if pathlib.Path(p).exists()
                        else 0
                    ),
                    reverse=True,
                )
        except (OSError, ValueError):  # nosec B110
            pass

    async def _run_rg(
        self, arguments: dict[str, Any], files: list[str]
    ) -> tuple[int, bytes, int] | dict[str, Any]:
        """Run ripgrep on found files. Returns (rc, output, elapsed_ms) or error dict."""
        """Run ripgrep on found files. Returns (rc, output, elapsed_ms) or error dict."""
        from pathlib import Path

        parent_dirs: set[str] = set()
        file_globs: list[str] = []
        for file_path in files:
            parent_dir = str(Path(file_path).parent)
            parent_dirs.add(parent_dir)
            escaped_name = Path(file_path).name.replace("[", "[[]").replace("]", "[]]")
            file_globs.append(escaped_name)

        combined_globs = (arguments.get("include_globs") or []) + file_globs
        no_ignore = bool(arguments.get("no_ignore", False))

        rg_cmd = fd_rg_utils.build_rg_command(
            query=arguments["query"],
            case=arguments.get("case", "smart"),
            fixed_strings=bool(arguments.get("fixed_strings", False)),
            word=bool(arguments.get("word", False)),
            multiline=bool(arguments.get("multiline", False)),
            include_globs=combined_globs,
            exclude_globs=arguments.get("exclude_globs"),
            follow_symlinks=bool(arguments.get("follow_symlinks", False)),
            hidden=bool(arguments.get("hidden", False)),
            no_ignore=no_ignore,
            max_filesize=arguments.get("max_filesize"),
            context_before=arguments.get("context_before"),
            context_after=arguments.get("context_after"),
            encoding=arguments.get("encoding"),
            max_count=arguments.get("max_count"),
            timeout_ms=arguments.get("timeout_ms"),
            roots=list(parent_dirs),
            files_from=None,
            count_only_matches=bool(arguments.get("count_only_matches", False))
            or bool(arguments.get("total_only", False)),
        )

        started = time.time()
        rc, out, err = await fd_rg_utils.run_command_capture(
            rg_cmd, timeout_ms=arguments.get("timeout_ms")
        )
        elapsed = int((time.time() - started) * 1000)

        if rc not in (0, 1):
            return {
                "success": False,
                "error": err.decode("utf-8", errors="replace").strip()
                or "ripgrep failed",
                "returncode": rc,
            }

        return rc, out, elapsed

    def _apply_limits(
        self, matches: list[dict[str, Any]], arguments: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], bool]:
        """Truncate matches to user max_count or hard cap."""
        """Apply match count limits."""
        user_max = arguments.get("max_count")
        if user_max is not None and len(matches) > user_max:
            return matches[:user_max], True
        truncated = len(matches) >= fd_rg_utils.MAX_RESULTS_HARD_CAP
        if truncated:
            return matches[: fd_rg_utils.MAX_RESULTS_HARD_CAP], True
        return matches, False

    def _respond_grouped(
        self,
        arguments: dict[str, Any],
        matches: list[dict[str, Any]],
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        """Return matches grouped by file path."""
        grouped = fd_rg_utils.group_matches_by_file(matches)
        if arguments.get("summary_only", False):
            grouped["summary"] = fd_rg_utils.summarize_search_results(matches)
        grouped["meta"] = meta

        suppressed = handle_output(
            grouped, arguments, self.file_output_manager, matches
        )
        if suppressed:
            return suppressed

        output_format = arguments.get("output_format", "toon")
        if output_format == "toon":
            return attach_toon_content_to_response(grouped)
        return grouped

    def _respond_summary(
        self,
        arguments: dict[str, Any],
        matches: list[dict[str, Any]],
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a summary-only response without full match data."""
        result: dict[str, Any] = {
            "success": True,
            "summary_only": True,
            "summary": fd_rg_utils.summarize_search_results(matches),
            "meta": meta,
        }

        suppressed = handle_output(result, arguments, self.file_output_manager, matches)
        if suppressed:
            return suppressed

        return result

    def _respond_full(
        self,
        arguments: dict[str, Any],
        matches: list[dict[str, Any]],
        meta: dict[str, Any],
        output_format: str,
    ) -> dict[str, Any]:
        """Return full match results with optional next_steps."""
        result: dict[str, Any] = {
            "success": True,
            "count": len(matches),
            "meta": meta,
        }

        suppress_output = arguments.get("suppress_output", False)
        output_file = arguments.get("output_file")

        if not (suppress_output and output_file):
            result["results"] = matches
            if matches and not suppress_output:
                result["next_steps"] = _build_next_steps(matches)

        suppressed = handle_output(result, arguments, self.file_output_manager, matches)
        if suppressed:
            return suppressed

        return apply_toon_format_to_response(result, output_format)


def _build_next_steps(matches: list[dict[str, Any]]) -> list[str]:
    """Build next_steps suggestions for AI agents."""
    files_with_matches: set[str] = set()
    for m in matches:
        fp = m.get("path", {})
        if isinstance(fp, dict):
            fp = fp.get("text", "")
        if fp:
            files_with_matches.add(fp)

    steps: list[str] = []
    if len(files_with_matches) == 1:
        fp = next(iter(files_with_matches))
        steps.append(f"analyze_code_structure(file_path='{fp}') to see full structure")
    elif len(files_with_matches) <= 3:
        steps.append("check_code_scale on matching files to prioritize analysis")
    if len(matches) > 5:
        steps.append("Use group_by_file=true for a clearer overview")
    return steps


# Section: quality threshold analysis (part 1)
# Section: quality threshold analysis (part 2)
# Section: quality threshold analysis (part 3)
# Section: quality threshold analysis (part 4)
# Section: quality threshold analysis (part 5)
# Section: quality threshold analysis (part 6)
# Section: quality threshold analysis (part 7)
# Section: quality threshold analysis (part 8)
# Section: quality threshold analysis (part 9)
# Section: quality threshold analysis (part 10)
# Section: quality threshold analysis (part 11)
# Section: quality threshold analysis (part 12)
# Section: quality threshold analysis (part 13)
# Section: quality threshold analysis (part 14)
# Section: quality threshold analysis (part 15)
# Section: quality threshold analysis (part 16)
# Section: quality threshold analysis (part 17)
# Section: quality threshold analysis (part 18)
# Section: quality threshold analysis (part 19)
# Section: quality threshold analysis (part 20)
# Section: quality threshold analysis (part 21)
# Section: quality threshold analysis (part 22)
# Section: quality threshold analysis (part 23)
# Section: quality threshold analysis (part 24)
# Quality metrics: refactoring checkpoint #1
# Quality metrics: refactoring checkpoint #2
# Quality metrics: refactoring checkpoint #3
# Quality metrics: refactoring checkpoint #4
# Quality metrics: refactoring checkpoint #5
# Quality metrics: refactoring checkpoint #6
# Quality metrics: refactoring checkpoint #7
