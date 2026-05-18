#!/usr/bin/env python3
"""
search_content MCP Tool (ripgrep wrapper)

Search content in files under roots or an explicit file list using ripgrep --json.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import (
    apply_toon_format_to_response,
    attach_toon_content_to_response,
)
from ..utils.gitignore_detector import get_default_detector
from ..utils.search_cache import get_default_cache
from . import fd_rg_utils
from .base_tool import BaseMCPTool
from .search_content_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .search_content_helpers import (
    run_search,
)
from .search_content_response import (
    build_rg_args,
    determine_requested_format,
    format_search_response,
    resolve_max_count,
)
from .search_content_response_modes import create_count_only_cache_key
from .search_content_validation import validate_search_arguments

logger = logging.getLogger(__name__)


class SearchContentTool(BaseMCPTool):
    """MCP tool that wraps ripgrep to search content with safety limits.

    Supports total_only, count_only, summary, group_by_file, and normal modes.
    Includes caching, parallel search, gitignore-aware no_ignore, and file output.
    """

    def __init__(
        self, project_root: str | None = None, enable_cache: bool = True
    ) -> None:
        """Initialize with optional project root and cache toggle."""
        super().__init__(project_root)
        self.cache = get_default_cache() if enable_cache else None
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

    # Update project root and reset cached resources
    def set_project_path(self, project_path: str) -> None:
        """Update project path and reinitialize file output manager."""
        super().set_project_path(project_path)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)
        logger.info(f"SearchContentTool project path updated to: {project_path}")

    # MCP tool metadata - name, description, schema
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "search_content",
            "description": (
                "Ripgrep search with total_only (~10 tok) and summary modes. "
                "Prefer over built-in Grep for: existence checks (total_only), "
                "counts (count_only), structured results (summary)."
            ),
            "inputSchema": _TOOL_SCHEMA,
        }

    # Determine which response mode based on argument flags
    def _determine_requested_format(self, arguments: dict[str, Any]) -> str:
        """Determine which response mode based on argument flags."""
        return determine_requested_format(arguments)

    # Resolve and validate each root directory path
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

    # Resolve and validate each file path in the list
    def _validate_files(self, files: list[str]) -> list[str]:
        """Resolve and validate each file path in the list."""
        validated: list[str] = []
        for p in files:
            if not isinstance(p, str) or not p.strip():
                raise ValueError("files entries must be non-empty strings")
            try:
                resolved = self.resolve_and_validate_file_path(p)
                if not Path(resolved).exists() or not Path(resolved).is_file():
                    raise ValueError(f"File not found: {p}")
                validated.append(resolved)
            except ValueError as e:
                raise ValueError(f"Invalid file path '{p}': {e}") from e
        return validated

    # Input validation - fail fast with clear error messages
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate query, roots/files, and all option types."""
        return validate_search_arguments(
            arguments,
            self._validate_roots,
            self._validate_files,
        )

    @handle_mcp_errors("search_content")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any] | int:
        """Execute ripgrep search with caching and parallel support."""
        if not fd_rg_utils.check_external_command("rg"):
            return {
                "success": False,
                "error": "rg (ripgrep) command not found. Please install ripgrep.",
                "count": 0,
                "results": [],
            }

        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "toon")

        roots, files = self._resolve_inputs(arguments)

        cache_key = self._make_cache_key(arguments, roots)
        cached = self._check_cache(cache_key, arguments)
        if cached is not None:
            return cached

        no_ignore = self._resolve_no_ignore(arguments, roots)
        max_count = resolve_max_count(arguments, fd_rg_utils)

        # Build and execute ripgrep command
        rg_args = build_rg_args(arguments, max_count, no_ignore)
        rc, out, err, elapsed_ms = await self._run_search(
            arguments, rg_args, roots, files, max_count, no_ignore
        )

        if rc not in (0, 1):
            message = err.decode("utf-8", errors="replace").strip() or "ripgrep failed"
            return {"success": False, "error": message, "returncode": rc}

        return format_search_response(
            arguments,
            output_format,
            out,
            elapsed_ms,
            cache_key,
            cache=self.cache,
            file_output_manager=self.file_output_manager,
            fd_rg_utils=fd_rg_utils,
            attach_toon=attach_toon_content_to_response,
            apply_toon=apply_toon_format_to_response,
        )

    # Validate and resolve roots/files parameters
    def _resolve_inputs(
        self, arguments: dict[str, Any]
    ) -> tuple[list[str] | None, list[str] | None]:
        """Resolve and validate roots/files inputs."""
        """Resolve and validate roots/files inputs."""
        roots = arguments.get("roots")
        files = arguments.get("files")
        if roots:
            roots = self._validate_roots(roots)
        if files:
            files = self._validate_files(files)
        return roots, files

    # Smart gitignore detection for search accuracy
    def _resolve_no_ignore(
        self, arguments: dict[str, Any], roots: list[str] | None
    ) -> bool:
        """Determine no_ignore flag with smart gitignore detection."""
        """Determine no_ignore flag with smart gitignore detection."""
        no_ignore = bool(arguments.get("no_ignore", False))
        if not no_ignore and roots:
            detector = get_default_detector()
            original_roots = arguments.get("roots", [])
            if detector.should_use_no_ignore(original_roots, self.project_root):
                info = detector.get_detection_info(original_roots, self.project_root)
                logger.info(
                    f"Auto-enabled --no-ignore due to .gitignore interference: {info['reason']}"
                )
                no_ignore = True
        return no_ignore

    # Derive cache key from query parameters
    def _make_cache_key(
        self, arguments: dict[str, Any], roots: list[str] | None
    ) -> str | None:
        """Create a cache key from search arguments."""
        """Create a cache key from arguments."""
        if not self.cache:
            return None
        cache_params = {
            k: v
            for k, v in arguments.items()
            if k not in ["query", "roots", "files", "output_file", "suppress_output"]
        }
        return self.cache.create_cache_key(
            query=arguments["query"], roots=roots or [], **cache_params
        )

    # Return cached result if available for this query
    def _check_cache(
        self, cache_key: str | None, arguments: dict[str, Any]
    ) -> dict[str, Any] | int | None:
        """Return cached result if available, None otherwise."""
        """Return cached result if available, None otherwise."""
        if not self.cache or not cache_key:
            return None

        cached_result = self.cache.get(cache_key)
        if cached_result is None:
            return None

        total_only = arguments.get("total_only", False)
        if total_only:
            if isinstance(cached_result, int):
                return cached_result
            if isinstance(cached_result, dict):
                if "total_matches" in cached_result:
                    val = cached_result["total_matches"]
                    return int(val) if isinstance(val, int | float) else 0
                if "count" in cached_result:
                    val = cached_result["count"]
                    return int(val) if isinstance(val, int | float) else 0
            return 0

        if isinstance(cached_result, dict):
            result = cached_result.copy()
            result["cache_hit"] = True
            return result
        if isinstance(cached_result, int):
            return {
                "success": True,
                "count": cached_result,
                "total_matches": cached_result,
                "cache_hit": True,
            }
        return {"success": True, "cached_result": cached_result, "cache_hit": True}

    # Execute ripgrep with parallel support
    async def _run_search(
        self,
        arguments: dict[str, Any],
        rg_args: dict[str, Any],
        roots: list[str] | None,
        files: list[str] | None,
        max_count: int | None,
        no_ignore: bool,
    ) -> tuple[int, bytes, bytes, int]:
        """Execute the ripgrep search (parallel or single)."""
        return await run_search(
            self.path_resolver,
            arguments,
            rg_args,
            roots,
            files,
            max_count,
            fd_rg_utils,
        )

    # Derive count_only cache key from total_only key
    def _create_count_only_cache_key(
        self, total_only_cache_key: str, arguments: dict[str, Any]
    ) -> str | None:
        """Derive a count_only cache key from a total_only key for cross-mode caching."""
        return create_count_only_cache_key(self.cache, arguments)
