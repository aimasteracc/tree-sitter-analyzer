#!/usr/bin/env python3
"""
find_and_grep MCP Tool (fd → ripgrep)

First narrow files with fd, then search contents with ripgrep, with caps & meta.
"""

from __future__ import annotations

import time
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool
from . import fd_rg_utils


class FindAndGrepTool(BaseMCPTool):
    """MCP tool that composes fd and ripgrep with safety limits and metadata."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "find_and_grep",
            "description": "Run fd to select files then ripgrep to search contents; returns matches with meta",
            "inputSchema": {
                "type": "object",
                "properties": {
                    # fd side
                    "roots": {"type": "array", "items": {"type": "string"}},
                    "pattern": {"type": "string"},
                    "glob": {"type": "boolean", "default": False},
                    "types": {"type": "array", "items": {"type": "string"}},
                    "extensions": {"type": "array", "items": {"type": "string"}},
                    "exclude": {"type": "array", "items": {"type": "string"}},
                    "depth": {"type": "integer"},
                    "follow_symlinks": {"type": "boolean"},
                    "hidden": {"type": "boolean"},
                    "no_ignore": {"type": "boolean"},
                    "size": {"type": "array", "items": {"type": "string"}},
                    "changed_within": {"type": "string"},
                    "changed_before": {"type": "string"},
                    "full_path_match": {"type": "boolean"},
                    "file_limit": {"type": "integer"},
                    "sort": {
                        "type": "string",
                        "enum": ["path", "mtime", "size"],
                    },
                    # rg side
                    "query": {"type": "string"},
                    "case": {"type": "string", "enum": ["smart", "insensitive", "sensitive"], "default": "smart"},
                    "fixed_strings": {"type": "boolean", "default": False},
                    "word": {"type": "boolean", "default": False},
                    "multiline": {"type": "boolean", "default": False},
                    "include_globs": {"type": "array", "items": {"type": "string"}},
                    "exclude_globs": {"type": "array", "items": {"type": "string"}},
                    "max_filesize": {"type": "string"},
                    "context_before": {"type": "integer"},
                    "context_after": {"type": "integer"},
                    "encoding": {"type": "string"},
                    "max_count": {"type": "integer"},
                    "timeout_ms": {"type": "integer"},
                },
                "required": ["roots", "query"],
                "additionalProperties": False,
            },
        }

    def _validate_roots(self, roots: list[str]) -> list[str]:
        validated: list[str] = []
        for r in roots:
            resolved = self.path_resolver.resolve(r)
            ok, err = self.security_validator.validate_directory_path(resolved, must_exist=True)
            if not ok:
                raise ValueError(f"Invalid root '{r}': {err}")
            validated.append(resolved)
        return validated

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "roots" not in arguments or not isinstance(arguments["roots"], list):
            raise ValueError("roots is required and must be an array")
        if "query" not in arguments or not isinstance(arguments["query"], str) or not arguments["query"].strip():
            raise ValueError("query is required and must be a non-empty string")
        if "file_limit" in arguments and not isinstance(arguments["file_limit"], int):
            raise ValueError("file_limit must be an integer")
        return True

    @handle_mcp_errors("find_and_grep")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        roots = self._validate_roots(arguments["roots"])  # absolute validated

        # fd step
        fd_limit = fd_rg_utils.clamp_int(arguments.get("file_limit"), fd_rg_utils.DEFAULT_RESULTS_LIMIT, fd_rg_utils.MAX_RESULTS_HARD_CAP)
        fd_cmd = fd_rg_utils.build_fd_command(
            pattern=arguments.get("pattern"),
            glob=bool(arguments.get("glob", False)),
            types=arguments.get("types"),
            extensions=arguments.get("extensions"),
            exclude=arguments.get("exclude"),
            depth=arguments.get("depth"),
            follow_symlinks=bool(arguments.get("follow_symlinks", False)),
            hidden=bool(arguments.get("hidden", False)),
            no_ignore=bool(arguments.get("no_ignore", False)),
            size=arguments.get("size"),
            changed_within=arguments.get("changed_within"),
            changed_before=arguments.get("changed_before"),
            full_path_match=bool(arguments.get("full_path_match", False)),
            absolute=True,
            limit=fd_limit,
            roots=roots,
        )

        fd_started = time.time()
        fd_rc, fd_out, fd_err = await fd_rg_utils.run_command_capture(fd_cmd)
        fd_elapsed_ms = int((time.time() - fd_started) * 1000)

        if fd_rc != 0:
            return {
                "success": False,
                "error": (fd_err.decode("utf-8", errors="replace").strip() or "fd failed"),
                "returncode": fd_rc,
            }

        files = [l.strip() for l in fd_out.decode("utf-8", errors="replace").splitlines() if l.strip()]

        # Truncate by file_limit safety again
        truncated_fd = False
        if len(files) > fd_limit:
            files = files[:fd_limit]
            truncated_fd = True

        # Optional sorting
        sort_mode = arguments.get("sort")
        if sort_mode in ("path", "mtime", "size"):
            try:
                if sort_mode == "path":
                    files.sort()
                elif sort_mode == "mtime":
                    files.sort(key=lambda p: Path(p).stat().st_mtime if Path(p).exists() else 0, reverse=True)
                elif sort_mode == "size":
                    files.sort(key=lambda p: Path(p).stat().st_size if Path(p).exists() else 0, reverse=True)
            except Exception:
                pass

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

        # rg step on files list
        with fd_rg_utils.write_files_to_temp(files) as tmp:
            rg_cmd = fd_rg_utils.build_rg_command(
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
                max_count=fd_rg_utils.clamp_int(arguments.get("max_count"), fd_rg_utils.DEFAULT_RESULTS_LIMIT, fd_rg_utils.MAX_RESULTS_HARD_CAP),
                timeout_ms=arguments.get("timeout_ms"),
                roots=None,
                files_from=tmp.path,
            )

            rg_started = time.time()
            rg_rc, rg_out, rg_err = await fd_rg_utils.run_command_capture(rg_cmd)
            rg_elapsed_ms = int((time.time() - rg_started) * 1000)

            if rg_rc not in (0, 1):
                return {
                    "success": False,
                    "error": (rg_err.decode("utf-8", errors="replace").strip() or "ripgrep failed"),
                    "returncode": rg_rc,
                }

            matches = fd_rg_utils.parse_rg_json_lines_to_matches(rg_out)
            truncated_rg = len(matches) >= fd_rg_utils.MAX_RESULTS_HARD_CAP
            if truncated_rg:
                matches = matches[:fd_rg_utils.MAX_RESULTS_HARD_CAP]

            return {
                "success": True,
                "results": matches,
                "count": len(matches),
                "meta": {
                    "searched_file_count": searched_file_count,
                    "truncated": (truncated_fd or truncated_rg),
                    "fd_elapsed_ms": fd_elapsed_ms,
                    "rg_elapsed_ms": rg_elapsed_ms,
                },
            }

