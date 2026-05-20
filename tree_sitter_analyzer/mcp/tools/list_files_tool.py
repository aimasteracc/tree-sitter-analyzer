#!/usr/bin/env python3
"""
list_files MCP Tool (fd wrapper)

Safely list files/directories based on name patterns and constraints, using fd.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from ..utils.gitignore_detector import get_default_detector
from . import fd_rg_utils
from .base_tool import BaseMCPTool
from .list_files_helpers import (
    TOOL_SCHEMA,
    CountResponseContext,
    DetailedResponseContext,
    _build_agent_summary,
    _build_fd_command,
    _decode_lines,
    _missing_fd_response,
    _resolve_effective_types,
    _respond_detailed,
)
from .list_files_helpers import (
    _respond_count_only as _build_count_only_response,
)

logger = logging.getLogger(__name__)

__all__ = ["ListFilesTool", "_build_agent_summary"]


class ListFilesTool(BaseMCPTool):
    """MCP tool that wraps fd to list files with safety limits."""

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "list_files",
            "description": (
                "Map: fd-based file listing. Discover structure before deeper analysis."
            ),
            "inputSchema": TOOL_SCHEMA,
        }

    def _validate_roots(self, roots: list[str]) -> list[str]:
        """Resolve and validate each root directory path."""
        if not roots or not isinstance(roots, list):
            raise ValueError("roots must be a non-empty array of strings")
        validated: list[str] = []
        for r in roots:
            if not isinstance(r, str) or not r.strip():
                raise ValueError("root entries must be non-empty strings")
            try:
                resolved = self.resolve_and_validate_directory_path(r)
                validated.append(resolved)
            except ValueError as e:
                raise ValueError(f"Invalid root '{r}': {e}") from e
        return validated

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate roots and all option types.

        ``roots`` is optional: when omitted (or empty), the tool falls
        back to ``self.project_root`` so callers don't have to repeat
        the project path they already configured on the tool instance.
        """
        if "roots" not in arguments or arguments["roots"] in (None, [], ""):
            if not self.project_root:
                raise ValueError(
                    "roots is required when the tool has no project_root configured"
                )
            arguments["roots"] = [self.project_root]
        roots = arguments["roots"]
        if not isinstance(roots, list):
            raise ValueError("roots must be an array")
        for key in ["pattern", "changed_within", "changed_before"]:
            if key in arguments and not isinstance(arguments[key], str):
                raise ValueError(f"{key} must be a string")
        for key in [
            "glob",
            "follow_symlinks",
            "hidden",
            "no_ignore",
            "full_path_match",
            "absolute",
        ]:
            if key in arguments and not isinstance(arguments[key], bool):
                raise ValueError(f"{key} must be a boolean")
        if "depth" in arguments and not isinstance(arguments["depth"], int):
            raise ValueError("depth must be an integer")
        if "limit" in arguments and not isinstance(arguments["limit"], int):
            raise ValueError("limit must be an integer")
        for arr in ["types", "extensions", "exclude", "size"]:
            if arr in arguments and not (
                isinstance(arguments[arr], list)
                and all(isinstance(x, str) for x in arguments[arr])
            ):
                raise ValueError(f"{arr} must be an array of strings")
        return True

    @handle_mcp_errors("list_files")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute fd-based file listing with safety limits."""
        if not fd_rg_utils.check_external_command("fd"):
            return _missing_fd_response()

        self.validate_arguments(arguments)
        roots = self._validate_roots(arguments["roots"])

        limit = fd_rg_utils.clamp_int(
            arguments.get("limit"),
            fd_rg_utils.DEFAULT_RESULTS_LIMIT,
            fd_rg_utils.MAX_RESULTS_HARD_CAP,
        )

        effective_types = _resolve_effective_types(arguments)
        no_ignore = self._resolve_no_ignore(arguments)

        cmd = _build_fd_command(arguments, roots, limit, effective_types, no_ignore)

        started = time.time()
        rc, out, err = await fd_rg_utils.run_command_capture(cmd)
        elapsed_ms = int((time.time() - started) * 1000)

        if rc != 0:
            message = err.decode("utf-8", errors="replace").strip() or "fd failed"
            return {"success": False, "error": message, "returncode": rc}

        lines = _decode_lines(out)

        if arguments.get("count_only", False):
            return self._respond_count_only(lines, elapsed_ms, arguments, limit)

        return _respond_detailed(
            DetailedResponseContext(
                lines=lines,
                elapsed_ms=elapsed_ms,
                arguments=arguments,
                limit=limit,
                no_ignore=no_ignore,
                effective_types=effective_types,
                project_root=self.project_root,
            )
        )

    def _resolve_no_ignore(self, arguments: dict[str, Any]) -> bool:
        """Determine no_ignore flag with smart gitignore detection."""
        no_ignore = bool(arguments.get("no_ignore", False))
        if no_ignore:
            return no_ignore

        detector = get_default_detector()
        original_roots = arguments.get("roots", [])
        should_ignore = detector.should_use_no_ignore(original_roots, self.project_root)
        if should_ignore:
            detection_info = detector.get_detection_info(
                original_roots, self.project_root
            )
            logger.info(
                f"Auto-enabled --no-ignore due to .gitignore interference: {detection_info['reason']}"
            )
            return True
        return False

    def _respond_count_only(
        self,
        lines: list[str],
        elapsed_ms: int,
        arguments: dict[str, Any],
        limit: int,
    ) -> dict[str, Any]:
        """Return count-only response through the shared response helper."""
        return _build_count_only_response(
            CountResponseContext(
                lines=lines,
                elapsed_ms=elapsed_ms,
                arguments=arguments,
                limit=limit,
                project_root=self.project_root,
            )
        )
