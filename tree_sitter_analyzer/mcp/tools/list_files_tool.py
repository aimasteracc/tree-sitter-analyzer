#!/usr/bin/env python3
"""
list_files MCP Tool (fd wrapper)

Safely list files/directories based on name patterns and constraints, using fd.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import apply_toon_format_to_response, format_for_file_output
from ..utils.gitignore_detector import get_default_detector
from . import fd_rg_utils
from .base_tool import BaseMCPTool
from .list_files_helpers import TOOL_SCHEMA, build_query_info

logger = logging.getLogger(__name__)


class ListFilesTool(BaseMCPTool):
    """MCP tool that wraps fd to list files with safety limits."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "list_files",
            "description": (
                "SMART 'Map': fd-based file listing with filtering. "
                "Discover structure, locate targets before analysis."
            ),
            "inputSchema": TOOL_SCHEMA,
        }

    def _validate_roots(self, roots: list[str]) -> list[str]:
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
        if "roots" not in arguments:
            raise ValueError("roots is required")
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
        if not fd_rg_utils.check_external_command("fd"):
            return {
                "success": False,
                "error": "fd command not found. Please install fd (https://github.com/sharkdp/fd) to use this tool.",
                "count": 0,
                "results": [],
            }

        self.validate_arguments(arguments)
        roots = self._validate_roots(arguments["roots"])

        limit = fd_rg_utils.clamp_int(
            arguments.get("limit"),
            fd_rg_utils.DEFAULT_RESULTS_LIMIT,
            fd_rg_utils.MAX_RESULTS_HARD_CAP,
        )

        effective_types = self._resolve_effective_types(arguments)
        no_ignore = self._resolve_no_ignore(arguments)

        cmd = fd_rg_utils.build_fd_command(
            pattern=arguments.get("pattern"),
            glob=bool(arguments.get("glob", False)),
            types=effective_types,
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
            limit=limit,
            roots=roots,
        )

        started = time.time()
        rc, out, err = await fd_rg_utils.run_command_capture(cmd)
        elapsed_ms = int((time.time() - started) * 1000)

        if rc != 0:
            message = err.decode("utf-8", errors="replace").strip() or "fd failed"
            return {"success": False, "error": message, "returncode": rc}

        lines = [
            line.strip()
            for line in out.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        ]

        if arguments.get("count_only", False):
            return self._respond_count_only(lines, elapsed_ms, arguments, limit)

        return self._respond_detailed(
            lines, elapsed_ms, arguments, limit, no_ignore, effective_types
        )

    def _resolve_effective_types(self, arguments: dict[str, Any]) -> list[str] | None:
        effective_types = arguments.get("types")
        if effective_types is None and arguments.get("extensions"):
            return ["f"]
        return effective_types

    def _resolve_no_ignore(self, arguments: dict[str, Any]) -> bool:
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
        total_count = min(len(lines), fd_rg_utils.MAX_RESULTS_HARD_CAP)
        truncated = len(lines) > fd_rg_utils.MAX_RESULTS_HARD_CAP

        result: dict[str, Any] = {
            "success": True,
            "count_only": True,
            "total_count": total_count,
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
        }

        output_file = arguments.get("output_file")
        if output_file:
            file_manager = FileOutputManager(self.project_root)
            file_content = {
                "count_only": True,
                "total_count": total_count,
                "truncated": truncated,
                "elapsed_ms": elapsed_ms,
                "query_info": build_query_info(arguments, limit, False),
            }
            suppress = arguments.get("suppress_output", False)
            output_format = arguments.get("output_format", "toon")
            saved = self._save_to_file(
                file_manager, file_content, output_file, output_format
            )
            if saved:
                result["output_file"] = saved
                if suppress:
                    return {
                        "success": True,
                        "count_only": True,
                        "total_count": total_count,
                        "output_file": saved,
                        "message": f"Count results saved to {saved}",
                    }
            else:
                result["output_file_error"] = "Failed to save output file"

        output_format = arguments.get("output_format", "toon")
        return apply_toon_format_to_response(result, output_format)

    def _respond_detailed(
        self,
        lines: list[str],
        elapsed_ms: int,
        arguments: dict[str, Any],
        limit: int,
        no_ignore: bool,
        effective_types: list[str] | None,
    ) -> dict[str, Any]:
        truncated = len(lines) > fd_rg_utils.MAX_RESULTS_HARD_CAP
        if truncated:
            lines = lines[: fd_rg_utils.MAX_RESULTS_HARD_CAP]

        results = self._parse_fd_output(lines, effective_types)

        final_result: dict[str, Any] = {
            "success": True,
            "count": len(results),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "results": results,
        }

        output_file = arguments.get("output_file")
        if output_file:
            file_manager = FileOutputManager(self.project_root)
            file_content = {
                "count": len(results),
                "truncated": truncated,
                "elapsed_ms": elapsed_ms,
                "results": results,
                "query_info": build_query_info(arguments, limit, no_ignore),
            }
            suppress = arguments.get("suppress_output", False)
            output_format = arguments.get("output_format", "toon")
            saved = self._save_to_file(
                file_manager, file_content, output_file, output_format
            )
            if saved:
                final_result["output_file"] = saved
                if suppress:
                    return {
                        "success": True,
                        "count": len(results),
                        "output_file": saved,
                        "message": f"File list results saved to {saved}",
                    }
            else:
                final_result["output_file_error"] = "Failed to save output file"

        output_format = arguments.get("output_format", "toon")
        return apply_toon_format_to_response(final_result, output_format)

    def _parse_fd_output(
        self, lines: list[str], effective_types: list[str] | None
    ) -> list[dict[str, Any]]:
        types_only_files = effective_types == ["f"]
        results: list[dict[str, Any]] = []
        for p in lines:
            try:
                path_obj = Path(p)
                ext = path_obj.suffix[1:] if path_obj.suffix else None
                is_dir = False if types_only_files else path_obj.is_dir()
                size_bytes = None
                mtime = None
                if not is_dir:
                    try:
                        st = os.stat(p)
                        size_bytes = st.st_size
                        mtime = int(st.st_mtime)
                    except (OSError, ValueError):
                        pass
                results.append(
                    {
                        "path": p,
                        "is_dir": is_dir,
                        "size_bytes": size_bytes,
                        "mtime": mtime,
                        "ext": ext,
                    }
                )
            except (OSError, ValueError):
                continue
        return results

    def _save_to_file(
        self,
        file_manager: FileOutputManager,
        content: dict[str, Any],
        output_file: str,
        output_format: str,
    ) -> str | None:
        try:
            formatted, _ = format_for_file_output(content, output_format)
            return file_manager.save_to_file(content=formatted, base_name=output_file)
        except Exception as e:
            logger.warning(f"Failed to save output file: {e}")
            return None
