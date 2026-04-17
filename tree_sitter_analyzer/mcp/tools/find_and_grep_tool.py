#!/usr/bin/env python3
"""
find_and_grep MCP Tool (fd → ripgrep)

First narrow files with fd, then search contents with ripgrep, with caps & meta.
"""

from __future__ import annotations

import logging
import pathlib
import time
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import (
    apply_toon_format_to_response,
    attach_toon_content_to_response,
    format_for_file_output,
)
from ..utils.gitignore_detector import get_default_detector
from . import fd_rg_utils
from .base_tool import BaseMCPTool

logger = logging.getLogger(__name__)


class FindAndGrepTool(BaseMCPTool):
    """MCP tool that composes fd and ripgrep with safety limits and metadata."""

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the find and grep tool."""
        super().__init__(project_root)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

    def set_project_path(self, project_path: str) -> None:
        """
        Update the project path for all components.

        Args:
            project_path: New project root directory
        """
        super().set_project_path(project_path)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)
        logger.info(f"FindAndGrepTool project path updated to: {project_path}")

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "find_and_grep",
            "description": (
                "Two-stage search: fd filters files by name/type, then ripgrep searches content within matched files. "
                "\n\n"
                "USE for: large codebases (>1000 files) needing both file-type AND content filters. "
                "NOT for: small projects or content-only/filename-only searches (use search_content/list_files).\n"
                "\n"
                "DIFFERENCE from search_content: find_and_grep pre-filters files via fd before ripgrep, "
                "reducing noise. search_content runs ripgrep directly across all files.\n"
                "\n"
                "Both 'pattern' (file stage) and 'query' (content stage) are optional; both yields best results."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    # === FILE DISCOVERY STAGE (fd parameters) ===
                    "roots": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Search directories. Must be within project boundaries.",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "[FD] Filename pattern. Use with glob=true for shell patterns.",
                    },
                    "glob": {
                        "type": "boolean",
                        "default": False,
                        "description": "[FD] Treat pattern as glob vs regex.",
                    },
                    "types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "[FD] File types: f=files, d=dirs, l=symlinks, x=executable, e=empty",
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "[FD] Extensions without dots. Ex: ['py', 'js']",
                    },
                    "exclude": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "[FD] Patterns to exclude. Ex: ['*.tmp', '__pycache__']",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "[FD] Max directory depth. 1=current level only.",
                    },
                    "follow_symlinks": {
                        "type": "boolean",
                        "default": False,
                        "description": "[FD] Follow symlinks. May cause loops.",
                    },
                    "hidden": {
                        "type": "boolean",
                        "default": False,
                        "description": "[FD] Include hidden files (dot-prefixed).",
                    },
                    "no_ignore": {
                        "type": "boolean",
                        "default": False,
                        "description": "[FD] Ignore .gitignore rules.",
                    },
                    "size": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "[FD] Size filters: '+10M'=gt 10MB, '-1K'=lt 1KB. Units: B/K/M/G",
                    },
                    "changed_within": {
                        "type": "string",
                        "description": "[FD] Modified within: '1d', '2h', '30m', '1w'",
                    },
                    "changed_before": {
                        "type": "string",
                        "description": "[FD] Modified before. Same format as changed_within.",
                    },
                    "full_path_match": {
                        "type": "boolean",
                        "default": False,
                        "description": "[FD] Match against full path vs filename.",
                    },
                    "file_limit": {
                        "type": "integer",
                        "description": "[FD] Max files before content search. Default 2000.",
                    },
                    "sort": {
                        "type": "string",
                        "enum": ["path", "mtime", "size"],
                        "description": "[FD] Sort: 'path', 'mtime', or 'size'",
                    },
                    # === CONTENT SEARCH STAGE (ripgrep parameters) ===
                    "query": {
                        "type": "string",
                        "description": "[RG] Text/regex pattern to search in found files.",
                    },
                    "case": {
                        "type": "string",
                        "enum": ["smart", "insensitive", "sensitive"],
                        "default": "smart",
                        "description": "[RG] Case: 'smart' (default), 'insensitive', 'sensitive'",
                    },
                    "fixed_strings": {
                        "type": "boolean",
                        "default": False,
                        "description": "[RG] Treat query as literal string vs regex.",
                    },
                    "word": {
                        "type": "boolean",
                        "default": False,
                        "description": "[RG] Match whole words only.",
                    },
                    "multiline": {
                        "type": "boolean",
                        "default": False,
                        "description": "[RG] Allow multi-line pattern matching.",
                    },
                    "include_globs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "[RG] Additional include patterns. Ex: ['*.py', '*.js']",
                    },
                    "exclude_globs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "[RG] Exclude patterns. Ex: ['*.log', '__pycache__/*']",
                    },
                    "max_filesize": {
                        "type": "string",
                        "description": "[RG] Max file size. Ex: '10M', '500K'",
                    },
                    "context_before": {
                        "type": "integer",
                        "description": "[RG] Lines before match for context.",
                    },
                    "context_after": {
                        "type": "integer",
                        "description": "[RG] Lines after match for context.",
                    },
                    "encoding": {
                        "type": "string",
                        "description": "[RG] File encoding. Default: auto-detect.",
                    },
                    "max_count": {
                        "type": "integer",
                        "description": "[RG] Max matches per file.",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "[RG] Timeout in ms.",
                    },
                    "count_only_matches": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return match counts per file only. Faster for statistics.",
                    },
                    "summary_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return condensed summary with top files and sample matches.",
                    },
                    "optimize_paths": {
                        "type": "boolean",
                        "default": False,
                        "description": "Shorten paths by removing common prefixes. Saves tokens.",
                    },
                    "group_by_file": {
                        "type": "boolean",
                        "default": False,
                        "description": "Group by file to deduplicate paths. Reduces tokens.",
                    },
                    "total_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return total count only. Most token-efficient. Overrides other formats.",
                    },
                    "output_file": {
                        "type": "string",
                        "description": "Save output to file. Extension auto-detected.",
                    },
                    "suppress_output": {
                        "type": "boolean",
                        "description": "Suppress detailed output when output_file is set.",
                        "default": False,
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["json", "toon"],
                        "description": "'toon' (default, 50-70% token savings) or 'json'",
                        "default": "toon",
                    },
                },
                "required": ["roots", "query"],
                "examples": [
                    {"roots": ["/project/src"], "extensions": ["java"], "query": "deprecated"},
                    {"roots": ["/project"], "pattern": "*.py", "glob": True, "query": "import os"},
                    {"roots": ["/project/tests"], "extensions": ["py"], "query": "assert", "summary_only": True},
                ],
                "additionalProperties": False,
            },
        }

    def _validate_roots(self, roots: list[str]) -> list[str]:
        validated: list[str] = []
        for r in roots:
            try:
                resolved = self.resolve_and_validate_directory_path(r)
                validated.append(resolved)
            except ValueError as e:
                raise ValueError(f"Invalid root '{r}': {e}") from e
        return validated

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        # Normalize path aliases before validation
        if "path" in arguments and "roots" not in arguments:
            path_val = arguments.pop("path")
            arguments["roots"] = (
                [path_val] if isinstance(path_val, str) else path_val
            )

        if "roots" not in arguments:
            raise ValueError(
                "roots is required. Example: roots=['.'] to search from project root"
            )
        if not isinstance(arguments["roots"], list):
            raise ValueError(
                "roots is required and must be an array (list) of directory paths. "
                "Example: roots=['.']"
            )
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
        # Check if both fd and rg commands are available
        missing_commands = fd_rg_utils.get_missing_commands()
        if missing_commands:
            return {
                "success": False,
                "error": f"Required commands not found: {', '.join(missing_commands)}. Please install fd (https://github.com/sharkdp/fd) and ripgrep (https://github.com/BurntSushi/ripgrep) to use this tool.",
                "count": 0,
                "results": [],
            }

        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "json")
        roots = self._validate_roots(arguments["roots"])  # absolute validated

        # fd step
        fd_limit = fd_rg_utils.clamp_int(
            arguments.get("file_limit"),
            fd_rg_utils.DEFAULT_RESULTS_LIMIT,
            fd_rg_utils.MAX_RESULTS_HARD_CAP,
        )

        # Smart .gitignore detection for fd stage
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

        fd_started = time.time()
        fd_rc, fd_out, fd_err = await fd_rg_utils.run_command_capture(fd_cmd)
        fd_elapsed_ms = int((time.time() - fd_started) * 1000)

        if fd_rc != 0:
            return {
                "success": False,
                "error": (
                    fd_err.decode("utf-8", errors="replace").strip() or "fd failed"
                ),
                "returncode": fd_rc,
            }

        files = [
            line.strip()
            for line in fd_out.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        ]

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

                    def get_mtime(p: str) -> float:
                        path_obj = pathlib.Path(p)
                        return path_obj.stat().st_mtime if path_obj.exists() else 0

                    files.sort(key=get_mtime, reverse=True)
                elif sort_mode == "size":

                    def get_size(p: str) -> int:
                        path_obj = pathlib.Path(p)
                        return path_obj.stat().st_size if path_obj.exists() else 0

                    files.sort(key=get_size, reverse=True)
            except (OSError, ValueError):  # nosec B110
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
        # Create specific file globs to limit search to only the files found by fd
        from pathlib import Path

        parent_dirs = set()
        file_globs = []

        for file_path in files:
            parent_dir = str(Path(file_path).parent)
            parent_dirs.add(parent_dir)

            # Create a specific glob pattern for this exact file
            file_name = Path(file_path).name
            # Escape special characters in filename for glob pattern
            escaped_name = file_name.replace("[", "[[]").replace("]", "[]]")
            file_globs.append(escaped_name)

        # Use parent directories as roots but limit to specific files via globs
        rg_roots = list(parent_dirs)

        # Combine user-provided include_globs with our file-specific globs
        combined_include_globs = arguments.get("include_globs", []) or []
        combined_include_globs.extend(file_globs)

        rg_cmd = fd_rg_utils.build_rg_command(
            query=arguments["query"],
            case=arguments.get("case", "smart"),
            fixed_strings=bool(arguments.get("fixed_strings", False)),
            word=bool(arguments.get("word", False)),
            multiline=bool(arguments.get("multiline", False)),
            include_globs=combined_include_globs,
            exclude_globs=arguments.get("exclude_globs"),
            follow_symlinks=bool(arguments.get("follow_symlinks", False)),
            hidden=bool(arguments.get("hidden", False)),
            no_ignore=no_ignore,  # Use the same no_ignore flag from fd stage
            max_filesize=arguments.get("max_filesize"),
            context_before=arguments.get("context_before"),
            context_after=arguments.get("context_after"),
            encoding=arguments.get("encoding"),
            max_count=arguments.get("max_count"),
            timeout_ms=arguments.get("timeout_ms"),
            roots=rg_roots,
            files_from=None,
            count_only_matches=bool(arguments.get("count_only_matches", False))
            or bool(arguments.get("total_only", False)),
        )

        rg_started = time.time()
        rg_rc, rg_out, rg_err = await fd_rg_utils.run_command_capture(
            rg_cmd, timeout_ms=arguments.get("timeout_ms")
        )
        rg_elapsed_ms = int((time.time() - rg_started) * 1000)

        if rg_rc not in (0, 1):
            return {
                "success": False,
                "error": (
                    rg_err.decode("utf-8", errors="replace").strip() or "ripgrep failed"
                ),
                "returncode": rg_rc,
            }

        # Handle total-only mode (highest priority for count queries)
        if arguments.get("total_only", False):
            # Parse count output and return only the total
            count_data = fd_rg_utils.parse_rg_count_output(rg_out)
            total_matches = count_data.pop("__total__", 0)
            return total_matches

        if arguments.get("count_only_matches", False):
            # Parse count-only output
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
        else:
            # Parse full match details
            matches = fd_rg_utils.parse_rg_json_lines_to_matches(rg_out)

            # Apply user-specified max_count limit if provided
            # Note: ripgrep's -m option limits matches per file, not total matches
            # So we need to apply the total limit here in post-processing
            user_max_count = arguments.get("max_count")
            if user_max_count is not None and len(matches) > user_max_count:
                matches = matches[:user_max_count]
                truncated_rg = True
            else:
                truncated_rg = len(matches) >= fd_rg_utils.MAX_RESULTS_HARD_CAP
                if truncated_rg:
                    matches = matches[: fd_rg_utils.MAX_RESULTS_HARD_CAP]

            # Apply path optimization if requested
            optimize_paths = arguments.get("optimize_paths", False)
            if optimize_paths and matches:
                matches = fd_rg_utils.optimize_match_paths(matches)

            # Apply file grouping if requested (takes priority over other formats)
            group_by_file = arguments.get("group_by_file", False)
            if group_by_file and matches:
                grouped_result = fd_rg_utils.group_matches_by_file(matches)

                # If summary_only is also requested, add summary to grouped result
                if arguments.get("summary_only", False):
                    summary = fd_rg_utils.summarize_search_results(matches)
                    grouped_result["summary"] = summary

                grouped_result["meta"] = {
                    "searched_file_count": searched_file_count,
                    "truncated": (truncated_fd or truncated_rg),
                    "fd_elapsed_ms": fd_elapsed_ms,
                    "rg_elapsed_ms": rg_elapsed_ms,
                }

                # Handle output suppression and file output for grouped results
                output_file = arguments.get("output_file")
                suppress_output = arguments.get("suppress_output", False)
                output_format = arguments.get("output_format", "json")

                # Handle file output if requested
                if output_file:
                    try:
                        # Format content based on output_format
                        formatted_content, _ = format_for_file_output(
                            grouped_result, output_format
                        )
                        file_path = self.file_output_manager.save_to_file(
                            content=formatted_content, base_name=output_file
                        )

                        # If suppress_output is True, return minimal response
                        if suppress_output:
                            minimal_result = {
                                "success": grouped_result.get("success", True),
                                "count": grouped_result.get("count", 0),
                                "output_file": output_file,
                                "file_saved": f"Results saved to {file_path}",
                            }
                            return minimal_result
                        else:
                            # Include file info in full response
                            grouped_result["output_file"] = output_file
                            grouped_result["file_saved"] = (
                                f"Results saved to {file_path}"
                            )
                    except Exception as e:
                        logger.error(f"Failed to save output to file: {e}")
                        grouped_result["file_save_error"] = str(e)
                        grouped_result["file_saved"] = False
                elif suppress_output:
                    # If suppress_output is True but no output_file, remove detailed results
                    minimal_result = {
                        "success": grouped_result.get("success", True),
                        "count": grouped_result.get("count", 0),
                        "summary": grouped_result.get("summary", {}),
                        "meta": grouped_result.get("meta", {}),
                    }
                    return minimal_result

                if output_format == "toon":
                    return attach_toon_content_to_response(grouped_result)
                return grouped_result

            # Check if summary_only mode is requested
            if arguments.get("summary_only", False):
                summary = fd_rg_utils.summarize_search_results(matches)
                result = {
                    "success": True,
                    "summary_only": True,
                    "summary": summary,
                    "meta": {
                        "searched_file_count": searched_file_count,
                        "truncated": (truncated_fd or truncated_rg),
                        "fd_elapsed_ms": fd_elapsed_ms,
                        "rg_elapsed_ms": rg_elapsed_ms,
                    },
                }

                # Handle output suppression and file output for summary results
                output_file = arguments.get("output_file")
                suppress_output = arguments.get("suppress_output", False)
                output_format = arguments.get("output_format", "json")

                # Handle file output if requested
                if output_file:
                    try:
                        # Format content based on output_format
                        formatted_content, _ = format_for_file_output(
                            result, output_format
                        )
                        file_path = self.file_output_manager.save_to_file(
                            content=formatted_content, base_name=output_file
                        )

                        # If suppress_output is True, return minimal response
                        if suppress_output:
                            minimal_result = {
                                "success": result.get("success", True),
                                "count": len(matches),
                                "output_file": output_file,
                                "file_saved": f"Results saved to {file_path}",
                            }
                            return minimal_result
                        else:
                            # Include file info in full response
                            result["output_file"] = output_file
                            result["file_saved"] = f"Results saved to {file_path}"
                    except Exception as e:
                        logger.error(f"Failed to save output to file: {e}")
                        result["file_save_error"] = str(e)
                        result["file_saved"] = False
                elif suppress_output:
                    # If suppress_output is True but no output_file, remove detailed results
                    minimal_result = {
                        "success": result.get("success", True),
                        "count": len(matches),
                        "summary": result.get("summary", {}),
                        "meta": result.get("meta", {}),
                    }
                    return minimal_result

                return result
            else:
                result = {
                    "success": True,
                    "count": len(matches),
                    "meta": {
                        "searched_file_count": searched_file_count,
                        "truncated": (truncated_fd or truncated_rg),
                        "fd_elapsed_ms": fd_elapsed_ms,
                        "rg_elapsed_ms": rg_elapsed_ms,
                    },
                }

                # Handle output suppression and file output
                output_file = arguments.get("output_file")
                suppress_output = arguments.get("suppress_output", False)

                # Get output format
                output_format = arguments.get("output_format", "json")

                # Add results to response unless suppressed
                # Only suppress results if both suppress_output is True AND output_file is provided
                if not (suppress_output and output_file):
                    result["results"] = matches

                # Handle file output if requested
                if output_file:
                    try:
                        # Create detailed output for file
                        file_content = {
                            "success": True,
                            "results": matches,
                            "count": len(matches),
                            "files": (
                                fd_rg_utils.group_matches_by_file(matches)["files"]
                                if matches
                                else []
                            ),
                            "summary": fd_rg_utils.summarize_search_results(matches),
                            "meta": result["meta"],
                        }

                        # Format content based on output_format
                        formatted_content, _ = format_for_file_output(
                            file_content, output_format
                        )
                        file_path = self.file_output_manager.save_to_file(
                            content=formatted_content, base_name=output_file
                        )

                        # Check if suppress_output is enabled
                        suppress_output = arguments.get("suppress_output", False)
                        if suppress_output:
                            # Return minimal response to save tokens
                            minimal_result = {
                                "success": result.get("success", True),
                                "count": result.get("count", 0),
                                "output_file": output_file,
                                "file_saved": f"Results saved to {file_path}",
                            }
                            return minimal_result
                        else:
                            # Include file info in full response
                            result["output_file"] = output_file
                            result["file_saved"] = f"Results saved to {file_path}"

                        logger.info(f"Search results saved to: {file_path}")

                    except Exception as e:
                        logger.error(f"Failed to save output to file: {e}")
                        result["file_save_error"] = str(e)
                        result["file_saved"] = False
                else:
                    # Handle suppress_output without file output
                    suppress_output = arguments.get("suppress_output", False)
                    if suppress_output:
                        # Return minimal response without detailed match results
                        minimal_result = {
                            "success": result.get("success", True),
                            "count": result.get("count", 0),
                            "summary": result.get("summary", {}),
                            "meta": result.get("meta", {}),
                        }
                        return minimal_result

                # Apply TOON format to direct output if requested
                return apply_toon_format_to_response(result, output_format)
