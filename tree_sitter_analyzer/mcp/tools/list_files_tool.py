#!/usr/bin/env python3
"""
list_files MCP Tool (fd wrapper)

Safely list files/directories based on name patterns and constraints, using fd.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from . import fd_rg_utils
from .base_tool import BaseMCPTool


class ListFilesTool(BaseMCPTool):
    """MCP tool that wraps fd to list files with safety limits."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "list_files",
            "description": "List files/directories using fd with glob/regex filters and safety limits",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "roots": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Search roots (must be within project boundary)",
                    },
                    "pattern": {"type": "string"},
                    "glob": {"type": "boolean", "default": False},
                    "types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "fd -t values (f,d,l,x,e)",
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "exclude": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "depth": {"type": "integer"},
                    "follow_symlinks": {"type": "boolean"},
                    "hidden": {"type": "boolean"},
                    "no_ignore": {"type": "boolean"},
                    "size": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "fd -S size filters like +10M",
                    },
                    "changed_within": {"type": "string"},
                    "changed_before": {"type": "string"},
                    "full_path_match": {"type": "boolean"},
                    "absolute": {"type": "boolean"},
                    "limit": {"type": "integer"},
                    "count_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return only the total count of files instead of file details",
                    },
                },
                "required": ["roots"],
                "additionalProperties": False,
            },
        }

    def _validate_roots(self, roots: list[str]) -> list[str]:
        if not roots or not isinstance(roots, list):
            raise ValueError("roots must be a non-empty array of strings")
        validated: list[str] = []
        for r in roots:
            if not isinstance(r, str) or not r.strip():
                raise ValueError("root entries must be non-empty strings")
            # Resolve and enforce boundary
            resolved = self.path_resolver.resolve(r)
            is_valid, error = self.security_validator.validate_directory_path(
                resolved, must_exist=True
            )
            if not is_valid:
                raise ValueError(f"Invalid root '{r}': {error}")
            validated.append(resolved)
        return validated

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "roots" not in arguments:
            raise ValueError("roots is required")
        roots = arguments["roots"]
        if not isinstance(roots, list):
            raise ValueError("roots must be an array")
        # Basic type checks for optional fields
        for key in [
            "pattern",
            "changed_within",
            "changed_before",
        ]:
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
        self.validate_arguments(arguments)
        roots = self._validate_roots(arguments["roots"])  # normalized absolutes

        limit = fd_rg_utils.clamp_int(
            arguments.get("limit"),
            fd_rg_utils.DEFAULT_RESULTS_LIMIT,
            fd_rg_utils.MAX_RESULTS_HARD_CAP,
        )

        cmd = fd_rg_utils.build_fd_command(
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
            absolute=True,  # unify output to absolute paths
            limit=limit,
            roots=roots,
        )

        # Use fd default path format (one per line). We'll determine is_dir and ext via Path
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
        
        # Check if count_only mode is requested
        if arguments.get("count_only", False):
            total_count = len(lines)
            # Apply hard cap for counting as well
            if total_count > fd_rg_utils.MAX_RESULTS_HARD_CAP:
                total_count = fd_rg_utils.MAX_RESULTS_HARD_CAP
                truncated = True
            else:
                truncated = False
                
            return {
                "success": True,
                "count_only": True,
                "total_count": total_count,
                "truncated": truncated,
                "elapsed_ms": elapsed_ms,
            }

        # Truncate defensively even if fd didn't
        truncated = False
        if len(lines) > fd_rg_utils.MAX_RESULTS_HARD_CAP:
            lines = lines[: fd_rg_utils.MAX_RESULTS_HARD_CAP]
            truncated = True

        results: list[dict[str, Any]] = []
        for p in lines:
            try:
                path_obj = Path(p)
                is_dir = path_obj.is_dir()
                ext = path_obj.suffix[1:] if path_obj.suffix else None
                size_bytes = None
                mtime = None
                try:
                    if not is_dir and path_obj.exists():
                        size_bytes = path_obj.stat().st_size
                        mtime = int(path_obj.stat().st_mtime)
                except (OSError, ValueError):  # nosec B110
                    pass
                results.append(
                    {
                        "path": str(path_obj.resolve()),
                        "is_dir": is_dir,
                        "size_bytes": size_bytes,
                        "mtime": mtime,
                        "ext": ext,
                    }
                )
            except (OSError, ValueError):  # nosec B112
                continue

        return {
            "success": True,
            "count": len(results),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "results": results,
        }
