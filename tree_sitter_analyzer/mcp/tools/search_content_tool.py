#!/usr/bin/env python3
"""
search_content MCP Tool (ripgrep wrapper)

Search content in files under roots or an explicit file list using ripgrep --json.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from ..utils.gitignore_detector import get_default_detector
from ..utils.search_cache import get_default_cache
from . import fd_rg_utils
from .base_tool import BaseMCPTool

logger = logging.getLogger(__name__)


class SearchContentTool(BaseMCPTool):
    """MCP tool that wraps ripgrep to search content with safety limits."""

    def __init__(
        self, project_root: str | None = None, enable_cache: bool = True
    ) -> None:
        """
        Initialize the search content tool.

        Args:
            project_root: Optional project root directory
            enable_cache: Whether to enable search result caching (default: True)
        """
        super().__init__(project_root)
        self.cache = get_default_cache() if enable_cache else None

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "search_content",
            "description": "Search text content inside files using ripgrep. Supports regex patterns, case sensitivity, context lines, and various output formats. Can search in directories or specific files.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "roots": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Directory paths to search in recursively. Alternative to 'files'. Example: ['.', 'src/', 'tests/']",
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific file paths to search in. Alternative to 'roots'. Example: ['main.py', 'config.json']",
                    },
                    "query": {
                        "type": "string",
                        "description": "Text pattern to search for. Can be literal text or regex depending on settings. Example: 'function', 'class\\s+\\w+', 'TODO:'",
                    },
                    "case": {
                        "type": "string",
                        "enum": ["smart", "insensitive", "sensitive"],
                        "default": "smart",
                        "description": "Case sensitivity mode. 'smart'=case-insensitive unless uppercase letters present, 'insensitive'=always ignore case, 'sensitive'=exact case match",
                    },
                    "fixed_strings": {
                        "type": "boolean",
                        "default": False,
                        "description": "Treat query as literal string instead of regex. True for exact text matching, False for regex patterns",
                    },
                    "word": {
                        "type": "boolean",
                        "default": False,
                        "description": "Match whole words only. True finds 'test' but not 'testing', False finds both",
                    },
                    "multiline": {
                        "type": "boolean",
                        "default": False,
                        "description": "Allow patterns to match across multiple lines. Useful for finding multi-line code blocks or comments",
                    },
                    "include_globs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File patterns to include in search. Example: ['*.py', '*.js'] to search only Python and JavaScript files",
                    },
                    "exclude_globs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File patterns to exclude from search. Example: ['*.log', '__pycache__/*'] to skip log files and cache directories",
                    },
                    "follow_symlinks": {
                        "type": "boolean",
                        "default": False,
                        "description": "Follow symbolic links during search. False=safer, True=may cause infinite loops",
                    },
                    "hidden": {
                        "type": "boolean",
                        "default": False,
                        "description": "Search in hidden files (starting with dot). False=skip .git, .env files, True=search all",
                    },
                    "no_ignore": {
                        "type": "boolean",
                        "default": False,
                        "description": "Ignore .gitignore and similar ignore files. False=respect ignore rules, True=search all files",
                    },
                    "max_filesize": {
                        "type": "string",
                        "description": "Maximum file size to search. Format: '10M'=10MB, '500K'=500KB, '1G'=1GB. Prevents searching huge files",
                    },
                    "context_before": {
                        "type": "integer",
                        "description": "Number of lines to show before each match. Useful for understanding match context. Example: 3 shows 3 lines before",
                    },
                    "context_after": {
                        "type": "integer",
                        "description": "Number of lines to show after each match. Useful for understanding match context. Example: 3 shows 3 lines after",
                    },
                    "encoding": {
                        "type": "string",
                        "description": "Text encoding to assume for files. Default is auto-detect. Example: 'utf-8', 'latin1', 'ascii'",
                    },
                    "max_count": {
                        "type": "integer",
                        "description": "Maximum number of matches per file. Useful to prevent overwhelming output from files with many matches",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Search timeout in milliseconds. Prevents long-running searches. Example: 5000 for 5 second timeout",
                    },
                    "count_only_matches": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return only match counts per file instead of full match details. Useful for statistics and performance",
                    },
                    "summary_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return a condensed summary of results to reduce context size. Shows top files and sample matches",
                    },
                    "optimize_paths": {
                        "type": "boolean",
                        "default": False,
                        "description": "Optimize file paths in results by removing common prefixes and shortening long paths. Saves tokens in output",
                    },
                    "group_by_file": {
                        "type": "boolean",
                        "default": False,
                        "description": "Group results by file to eliminate file path duplication when multiple matches exist in the same file. Significantly reduces tokens",
                    },
                    "total_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return only the total match count as a number. Most token-efficient option for count queries. Takes priority over all other formats",
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
            "count_only_matches",
            "summary_only",
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

    def _determine_requested_format(self, arguments: dict[str, Any]) -> str:
        """Determine the requested output format based on arguments."""
        if arguments.get("total_only", False):
            return "total_only"
        elif arguments.get("count_only_matches", False):
            return "count_only"
        elif arguments.get("summary_only", False):
            return "summary"
        elif arguments.get("group_by_file", False):
            return "group_by_file"
        else:
            return "normal"

    def _create_count_only_cache_key(
        self, total_only_cache_key: str, arguments: dict[str, Any]
    ) -> str | None:
        """
        Create a count_only_matches cache key from a total_only cache key.

        This enables cross-format caching where total_only results can serve
        future count_only_matches queries.
        """
        if not self.cache:
            return None

        # Create modified arguments with count_only_matches instead of total_only
        count_only_args = arguments.copy()
        count_only_args.pop("total_only", None)
        count_only_args["count_only_matches"] = True

        # Generate cache key for count_only_matches version
        cache_params = {
            k: v
            for k, v in count_only_args.items()
            if k not in ["query", "roots", "files"]
        }

        roots = arguments.get("roots", [])
        return self.cache.create_cache_key(
            query=arguments["query"], roots=roots, **cache_params
        )

    @handle_mcp_errors("search_content")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any] | int:
        self.validate_arguments(arguments)

        roots = arguments.get("roots")
        files = arguments.get("files")
        if roots:
            roots = self._validate_roots(roots)
        if files:
            files = self._validate_files(files)

        # Check cache if enabled
        cache_key = None
        if self.cache:
            # Create cache key with relevant parameters (excluding 'query' and 'roots' from kwargs)
            cache_params = {
                k: v
                for k, v in arguments.items()
                if k not in ["query", "roots", "files"]
            }
            cache_key = self.cache.create_cache_key(
                query=arguments["query"], roots=roots or [], **cache_params
            )

            # Try smart cross-format caching first
            requested_format = self._determine_requested_format(arguments)
            cached_result = self.cache.get_compatible_result(
                cache_key, requested_format
            )
            if cached_result is not None:
                # Add cache hit indicator to result
                if isinstance(cached_result, dict):
                    cached_result = cached_result.copy()
                    cached_result["cache_hit"] = True
                return cached_result

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

        # Check for count-only mode (total_only also requires count mode)
        total_only = bool(arguments.get("total_only", False))
        count_only_matches = (
            bool(arguments.get("count_only_matches", False)) or total_only
        )
        summary_only = bool(arguments.get("summary_only", False))

        # Smart .gitignore detection
        no_ignore = bool(arguments.get("no_ignore", False))
        if not no_ignore and roots:  # Only for roots mode, not files mode
            # Auto-detect if we should use --no-ignore
            detector = get_default_detector()
            original_roots = arguments.get("roots", [])
            should_ignore = detector.should_use_no_ignore(
                original_roots, self.project_root
            )
            if should_ignore:
                no_ignore = True
                # Log the auto-detection for debugging
                # Logger already defined at module level
                detection_info = detector.get_detection_info(
                    original_roots, self.project_root
                )
                logger.info(
                    f"Auto-enabled --no-ignore due to .gitignore interference: {detection_info['reason']}"
                )

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
            no_ignore=no_ignore,  # Use the potentially auto-detected value
            max_filesize=arguments.get("max_filesize"),
            context_before=arguments.get("context_before"),
            context_after=arguments.get("context_after"),
            encoding=arguments.get("encoding"),
            max_count=max_count,
            timeout_ms=timeout_ms,
            roots=roots,
            files_from=None,
            count_only_matches=count_only_matches,
        )

        started = time.time()
        rc, out, err = await fd_rg_utils.run_command_capture(cmd, timeout_ms=timeout_ms)
        elapsed_ms = int((time.time() - started) * 1000)

        if rc not in (0, 1):
            message = err.decode("utf-8", errors="replace").strip() or "ripgrep failed"
            return {"success": False, "error": message, "returncode": rc}

        # Handle total-only mode (highest priority for count queries)
        total_only = arguments.get("total_only", False)
        if total_only:
            # Parse count output and return only the total
            file_counts = fd_rg_utils.parse_rg_count_output(out)
            total_matches = file_counts.get("__total__", 0)

            # Cache the FULL count data for future cross-format optimization
            # This allows count_only_matches queries to be served from this cache
            if self.cache and cache_key:
                # Cache both the simple total and the detailed count structure
                self.cache.set(cache_key, total_matches)

                # Also cache the equivalent count_only_matches result for cross-format optimization
                count_only_cache_key = self._create_count_only_cache_key(
                    cache_key, arguments
                )
                if count_only_cache_key:
                    # Create a copy of file_counts without __total__ for the detailed result
                    file_counts_copy = {
                        k: v for k, v in file_counts.items() if k != "__total__"
                    }
                    detailed_count_result = {
                        "success": True,
                        "count_only": True,
                        "total_matches": total_matches,
                        "file_counts": file_counts_copy,  # Keep the file-level data (without __total__)
                        "elapsed_ms": elapsed_ms,
                        "derived_from_total_only": True,  # Mark as derived
                    }
                    self.cache.set(count_only_cache_key, detailed_count_result)
                    logger.debug(
                        "Cross-cached total_only result as count_only_matches for future optimization"
                    )

            return total_matches

        # Handle count-only mode
        if count_only_matches:
            file_counts = fd_rg_utils.parse_rg_count_output(out)
            total_matches = file_counts.pop("__total__", 0)
            result = {
                "success": True,
                "count_only": True,
                "total_matches": total_matches,
                "file_counts": file_counts,
                "elapsed_ms": elapsed_ms,
            }

            # Cache the result
            if self.cache and cache_key:
                self.cache.set(cache_key, result)

            return result

        # Handle normal mode
        matches = fd_rg_utils.parse_rg_json_lines_to_matches(out)
        truncated = len(matches) >= fd_rg_utils.MAX_RESULTS_HARD_CAP
        if truncated:
            matches = matches[: fd_rg_utils.MAX_RESULTS_HARD_CAP]

        # Apply path optimization if requested
        optimize_paths = arguments.get("optimize_paths", False)
        if optimize_paths and matches:
            matches = fd_rg_utils.optimize_match_paths(matches)

        # Apply file grouping if requested (takes priority over other formats)
        group_by_file = arguments.get("group_by_file", False)
        if group_by_file and matches:
            result = fd_rg_utils.group_matches_by_file(matches)

            # Cache the result
            if self.cache and cache_key:
                self.cache.set(cache_key, result)

            return result

        # Handle summary mode
        if summary_only:
            summary = fd_rg_utils.summarize_search_results(matches)
            result = {
                "success": True,
                "count": len(matches),
                "truncated": truncated,
                "elapsed_ms": elapsed_ms,
                "summary": summary,
            }

            # Cache the result
            if self.cache and cache_key:
                self.cache.set(cache_key, result)

            return result

        result = {
            "success": True,
            "count": len(matches),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "results": matches,
        }

        # Cache the result
        if self.cache and cache_key:
            self.cache.set(cache_key, result)

        return result
