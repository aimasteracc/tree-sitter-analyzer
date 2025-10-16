#!/usr/bin/env python3
"""
list_files MCP Tool (fd wrapper)

Safely list files/directories based on name patterns and constraints, using fd.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from ..utils.file_output_manager import FileOutputManager
from ..utils.gitignore_detector import get_default_detector
from . import fd_rg_utils
from .base_tool import BaseMCPTool

logger = logging.getLogger(__name__)


class ListFilesTool(BaseMCPTool):
    """MCP tool that wraps fd to list files with safety limits."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "list_files",
            "description": "List files and directories using fd with advanced filtering options. Supports glob patterns, file types, size filters, and more. Returns file paths with metadata or just counts, with optional file output and token optimization.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "roots": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Directory paths to search in. Must be within project boundaries for security. Example: ['.', 'src/', '/path/to/dir']",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern for file/directory names. Use with 'glob' for shell patterns or regex. Example: '*.py', 'test_*', 'main.js'",
                    },
                    "glob": {
                        "type": "boolean",
                        "default": False,
                        "description": "Treat pattern as glob (shell wildcard) instead of regex. True for '*.py', False for '.*\\.py$'",
                    },
                    "types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File types to include. Values: 'f'=files, 'd'=directories, 'l'=symlinks, 'x'=executable, 'e'=empty. Example: ['f'] for files only",
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File extensions to include (without dots). Example: ['py', 'js', 'md'] for Python, JavaScript, and Markdown files",
                    },
                    "exclude": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Patterns to exclude from results. Example: ['*.tmp', '__pycache__', 'node_modules'] to skip temporary and cache files",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Maximum directory depth to search. 1=current level only, 2=one level deep, etc. Useful to avoid deep recursion",
                    },
                    "follow_symlinks": {
                        "type": "boolean",
                        "default": False,
                        "description": "Follow symbolic links during search. False=skip symlinks (safer), True=follow them (may cause loops)",
                    },
                    "hidden": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include hidden files/directories (starting with dot). False=skip .git, .env, True=include all",
                    },
                    "no_ignore": {
                        "type": "boolean",
                        "default": False,
                        "description": "Ignore .gitignore and similar files. False=respect ignore files, True=search everything",
                    },
                    "size": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File size filters. Format: '+10M'=larger than 10MB, '-1K'=smaller than 1KB, '100B'=exactly 100 bytes. Units: B, K, M, G",
                    },
                    "changed_within": {
                        "type": "string",
                        "description": "Files modified within timeframe. Format: '1d'=1 day, '2h'=2 hours, '30m'=30 minutes, '1w'=1 week",
                    },
                    "changed_before": {
                        "type": "string",
                        "description": "Files modified before timeframe. Same format as changed_within. Useful for finding old files",
                    },
                    "full_path_match": {
                        "type": "boolean",
                        "default": False,
                        "description": "Match pattern against full path instead of just filename. True for 'src/main.py', False for 'main.py'",
                    },
                    "absolute": {
                        "type": "boolean",
                        "default": True,
                        "description": "Return absolute paths. True='/full/path/file.py', False='./file.py'. Absolute paths are more reliable",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return. Default 2000, max 10000. Use to prevent overwhelming output",
                    },
                    "count_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return only the total count of matching files instead of file details. Useful for quick statistics",
                    },
                    "output_file": {
                        "type": "string",
                        "description": "Optional filename to save output to file (extension auto-detected based on content)",
                    },
                    "suppress_output": {
                        "type": "boolean",
                        "description": "When true and output_file is specified, suppress detailed output in response to save tokens",
                        "default": False,
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
        # Check if fd command is available
        if not fd_rg_utils.check_external_command("fd"):
            return {
                "success": False,
                "error": "fd command not found. Please install fd (https://github.com/sharkdp/fd) to use this tool.",
                "count": 0,
                "results": [],
            }

        self.validate_arguments(arguments)
        roots = self._validate_roots(arguments["roots"])  # normalized absolutes

        limit = fd_rg_utils.clamp_int(
            arguments.get("limit"),
            fd_rg_utils.DEFAULT_RESULTS_LIMIT,
            fd_rg_utils.MAX_RESULTS_HARD_CAP,
        )

        # Smart .gitignore detection
        no_ignore = bool(arguments.get("no_ignore", False))
        if not no_ignore:
            # Auto-detect if we should use --no-ignore
            detector = get_default_detector()
            original_roots = arguments.get("roots", [])
            should_ignore = detector.should_use_no_ignore(
                original_roots, self.project_root
            )
            if should_ignore:
                no_ignore = True
                # Log the auto-detection for debugging
                detection_info = detector.get_detection_info(
                    original_roots, self.project_root
                )
                logger.info(
                    f"Auto-enabled --no-ignore due to .gitignore interference: {detection_info['reason']}"
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
            no_ignore=no_ignore,  # Use the potentially auto-detected value
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

            result = {
                "success": True,
                "count_only": True,
                "total_count": total_count,
                "truncated": truncated,
                "elapsed_ms": elapsed_ms,
            }

            # Handle file output for count_only mode
            output_file = arguments.get("output_file")
            suppress_output = arguments.get("suppress_output", False)

            if output_file:
                file_manager = FileOutputManager(self.project_root)
                file_content = {
                    "count_only": True,
                    "total_count": total_count,
                    "truncated": truncated,
                    "elapsed_ms": elapsed_ms,
                    "query_info": {
                        "roots": arguments.get("roots", []),
                        "pattern": arguments.get("pattern"),
                        "glob": arguments.get("glob", False),
                        "types": arguments.get("types"),
                        "extensions": arguments.get("extensions"),
                        "exclude": arguments.get("exclude"),
                        "limit": limit,
                    },
                }

                try:
                    import json

                    json_content = json.dumps(
                        file_content, indent=2, ensure_ascii=False
                    )
                    saved_path = file_manager.save_to_file(
                        content=json_content, base_name=output_file
                    )
                    result["output_file"] = saved_path

                    if suppress_output:
                        # Return minimal response to save tokens
                        return {
                            "success": True,
                            "count_only": True,
                            "total_count": total_count,
                            "output_file": saved_path,
                            "message": f"Count results saved to {saved_path}",
                        }
                except Exception as e:
                    logger.warning(f"Failed to save output file: {e}")
                    result["output_file_error"] = str(e)

            return result

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

        result = {
            "success": True,
            "count": len(results),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "results": results,
        }

        # Handle file output for detailed results
        output_file = arguments.get("output_file")
        suppress_output = arguments.get("suppress_output", False)

        if output_file:
            file_manager = FileOutputManager(self.project_root)
            file_content = {
                "count": len(results),
                "truncated": truncated,
                "elapsed_ms": elapsed_ms,
                "results": results,
                "query_info": {
                    "roots": arguments.get("roots", []),
                    "pattern": arguments.get("pattern"),
                    "glob": arguments.get("glob", False),
                    "types": arguments.get("types"),
                    "extensions": arguments.get("extensions"),
                    "exclude": arguments.get("exclude"),
                    "depth": arguments.get("depth"),
                    "follow_symlinks": arguments.get("follow_symlinks", False),
                    "hidden": arguments.get("hidden", False),
                    "no_ignore": no_ignore,
                    "size": arguments.get("size"),
                    "changed_within": arguments.get("changed_within"),
                    "changed_before": arguments.get("changed_before"),
                    "full_path_match": arguments.get("full_path_match", False),
                    "absolute": arguments.get("absolute", True),
                    "limit": limit,
                },
            }

            try:
                import json

                json_content = json.dumps(file_content, indent=2, ensure_ascii=False)
                saved_path = file_manager.save_to_file(
                    content=json_content, base_name=output_file
                )
                result["output_file"] = saved_path

                if suppress_output:
                    # Return minimal response to save tokens
                    return {
                        "success": True,
                        "count": len(results),
                        "output_file": saved_path,
                        "message": f"File list results saved to {saved_path}",
                    }
            except Exception as e:
                logger.warning(f"Failed to save output file: {e}")
                result["output_file_error"] = str(e)

        return result
