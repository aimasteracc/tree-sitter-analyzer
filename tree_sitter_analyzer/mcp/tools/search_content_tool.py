#!/usr/bin/env python3
"""
search_content MCP Tool (ripgrep wrapper)

Search content in files under roots or an explicit file list using ripgrep --json.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from . import fd_rg_utils
from .base_tool import BaseMCPTool


class SearchContentTool(BaseMCPTool):
    """MCP tool that wraps ripgrep to search content with safety limits."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "search_content",
            "description": "Search file contents using ripgrep with JSON output and safety limits",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "roots": {"type": "array", "items": {"type": "string"}},
                    "files": {"type": "array", "items": {"type": "string"}},
                    "query": {"type": "string"},
                    "case": {
                        "type": "string",
                        "enum": ["smart", "insensitive", "sensitive"],
                        "default": "smart",
                    },
                    "fixed_strings": {"type": "boolean", "default": False},
                    "word": {"type": "boolean", "default": False},
                    "multiline": {"type": "boolean", "default": False},
                    "include_globs": {"type": "array", "items": {"type": "string"}},
                    "exclude_globs": {"type": "array", "items": {"type": "string"}},
                    "follow_symlinks": {"type": "boolean", "default": False},
                    "hidden": {"type": "boolean", "default": False},
                    "no_ignore": {"type": "boolean", "default": False},
                    "max_filesize": {"type": "string"},
                    "context_before": {"type": "integer"},
                    "context_after": {"type": "integer"},
                    "encoding": {"type": "string"},
                    "max_count": {"type": "integer"},
                    "timeout_ms": {"type": "integer"},
                    "count_only_matches": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return only match counts per file instead of full match details",
                    },
                    "summary_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return a summarized view of results to reduce context size",
                    },
                },
                "required": ["query"],
                "anyOf": [
                    {"required": ["roots"]},
                    {"required": ["files"]},
                ],
                "additionalProperties": False,
            },
        }

    def _validate_roots(self, roots: list[str]) -> list[str]:
        validated: list[str] = []
        for r in roots:
            resolved = self.path_resolver.resolve(r)
            is_valid, error = self.security_validator.validate_directory_path(
                resolved, must_exist=True
            )
            if not is_valid:
                raise ValueError(f"Invalid root '{r}': {error}")
            validated.append(resolved)
        return validated

    def _validate_files(self, files: list[str]) -> list[str]:
        validated: list[str] = []
        for p in files:
            if not isinstance(p, str) or not p.strip():
                raise ValueError("files entries must be non-empty strings")
            resolved = self.path_resolver.resolve(p)
            ok, err = self.security_validator.validate_file_path(resolved)
            if not ok:
                raise ValueError(f"Invalid file path '{p}': {err}")
            if not Path(resolved).exists() or not Path(resolved).is_file():
                raise ValueError(f"File not found: {p}")
            validated.append(resolved)
        return validated

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if (
            "query" not in arguments
            or not isinstance(arguments["query"], str)
            or not arguments["query"].strip()
        ):
            raise ValueError("query is required and must be a non-empty string")
        if "roots" not in arguments and "files" not in arguments:
            raise ValueError("Either roots or files must be provided")
        for key in [
            "case",
            "encoding",
            "max_filesize",
        ]:
            if key in arguments and not isinstance(arguments[key], str):
                raise ValueError(f"{key} must be a string")
        for key in [
            "fixed_strings",
            "word",
            "multiline",
            "follow_symlinks",
            "hidden",
            "no_ignore",
        ]:
            if key in arguments and not isinstance(arguments[key], bool):
                raise ValueError(f"{key} must be a boolean")
        for key in ["context_before", "context_after", "max_count", "timeout_ms"]:
            if key in arguments and not isinstance(arguments[key], int):
                raise ValueError(f"{key} must be an integer")
        for key in ["include_globs", "exclude_globs"]:
            if key in arguments:
                v = arguments[key]
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    raise ValueError(f"{key} must be an array of strings")
        return True

    @handle_mcp_errors("search_content")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        roots = arguments.get("roots")
        files = arguments.get("files")
        if roots:
            roots = self._validate_roots(roots)
        if files:
            files = self._validate_files(files)

        # Clamp counts to safety limits
        max_count = fd_rg_utils.clamp_int(
            arguments.get("max_count"),
            fd_rg_utils.DEFAULT_RESULTS_LIMIT,
            fd_rg_utils.MAX_RESULTS_HARD_CAP,
        )
        timeout_ms = arguments.get("timeout_ms")

        # Note: --files-from is not supported in this ripgrep version
        # For files mode, we'll search in the parent directories of the files
        if files:
            # Extract unique parent directories from file paths
            parent_dirs = set()
            for file_path in files:
                resolved = self.path_resolver.resolve(file_path)
                parent_dirs.add(str(Path(resolved).parent))

            # Use parent directories as roots for compatibility
            roots = list(parent_dirs)

        # Roots mode
        cmd = fd_rg_utils.build_rg_command(
            query=arguments["query"],
            case=arguments.get("case", "smart"),
            fixed_strings=bool(arguments.get("fixed_strings", False)),
            word=bool(arguments.get("word", False)),
            multiline=bool(arguments.get("multiline", False)),
            include_globs=arguments.get("include_globs"),
            exclude_globs=arguments.get("exclude_globs"),
            follow_symlinks=bool(arguments.get("follow_symlinks", False)),
            hidden=bool(arguments.get("hidden", False)),
            no_ignore=bool(arguments.get("no_ignore", False)),
            max_filesize=arguments.get("max_filesize"),
            context_before=arguments.get("context_before"),
            context_after=arguments.get("context_after"),
            encoding=arguments.get("encoding"),
            max_count=max_count,
            timeout_ms=timeout_ms,
            roots=roots,
            files_from=None,
        )

        started = time.time()
        rc, out, err = await fd_rg_utils.run_command_capture(cmd)
        elapsed_ms = int((time.time() - started) * 1000)

        if rc not in (0, 1):
            message = err.decode("utf-8", errors="replace").strip() or "ripgrep failed"
            return {"success": False, "error": message, "returncode": rc}

        matches = fd_rg_utils.parse_rg_json_lines_to_matches(out)
        truncated = len(matches) >= fd_rg_utils.MAX_RESULTS_HARD_CAP
        if truncated:
            matches = matches[: fd_rg_utils.MAX_RESULTS_HARD_CAP]

        return {
            "success": True,
            "count": len(matches),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "results": matches,
        }
