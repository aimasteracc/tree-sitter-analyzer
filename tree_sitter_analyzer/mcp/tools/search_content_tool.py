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
from ._fts_fast_path import try_fts5_fast_path
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


def _try_fts5_fast_path(
    arguments: dict[str, Any],
    project_root: str | None,
    requested_format: str,
) -> dict[str, Any] | int | None:
    try:
        return try_fts5_fast_path(arguments, project_root, requested_format)
    except Exception:
        return None


class SearchContentTool(BaseMCPTool):
    """MCP tool that wraps ripgrep to search content with safety limits.

    Supports total_only, count_only, summary, group_by_file, and normal modes.
    Includes caching, parallel search, gitignore-aware no_ignore, and file output.
    """

    def __init__(
        self, project_root: str | None = None, enable_cache: bool = True
    ) -> None:
        """Initialize with optional project root and cache toggle."""
        # Pre-declare attributes the hook will touch — super().__init__()
        # invokes _on_project_root_changed before this body finishes.
        self.cache = get_default_cache() if enable_cache else None
        self.file_output_manager: FileOutputManager | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

    # MCP tool metadata - name, description, schema
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "search_content",
            "description": (
                "Project-wide content search using ``rg`` with token-saving "
                "modes: ``total_only`` returns just a count (~10 tokens), "
                "``count_only`` returns per-file counts, ``summary`` "
                "returns grouped results, default returns full match lines. "
                "Honors .gitignore by default. Strongly preferred over the "
                "built-in Grep tool for any case where you want a structured "
                "envelope (verdict, agent_summary, truncation flag) instead "
                "of raw text output.\n\n"
                "WHEN TO USE:\n"
                "- Existence check ('does this codebase use X?') — "
                "total_only saves ~99% tokens\n"
                "- Counting matches — count_only for per-file numbers\n"
                "- Structured search results that pipe into other tools\n"
                "- Pattern search that respects .gitignore semantics\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- To find files by NAME — use list_files\n"
                "- To restrict to files matching a glob first — use "
                "find_and_grep (much cheaper on large trees)\n"
                "- For symbol-level queries (class X) — use query\n"
                "- To run multiple searches in parallel — use batch_search"
            ),
            "inputSchema": _TOOL_SCHEMA,
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
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

    # L10: pre-validation hook so file-in-roots emits a canonical envelope
    # instead of a triple-wrapped AnalysisError.
    def _check_file_in_roots(self, arguments: dict[str, Any]) -> dict[str, Any] | None:
        """Detect ``roots=['<file>.py']`` and return a canonical error envelope.

        Users naturally try a file path in ``roots`` because the tool name
        implies it accepts files. The base path validator rejects them with
        ``Invalid directory path: Path is not a directory: ...`` which then
        gets wrapped twice by ``_validate_roots`` and ``handle_mcp_errors``,
        producing an unhelpful ``AnalysisError: Operation failed: ...`` cascade.

        This pre-check intercepts the common case (any root that resolves to
        an existing *file*) and returns a flat envelope that points the agent
        at the ``files=`` parameter instead.

        Returns ``None`` when ``roots`` is absent or every entry is a directory
        (or otherwise invalid — those still go through the normal validator
        so non-file errors keep their existing behavior).
        """
        raw_roots = arguments.get("roots")
        if not isinstance(raw_roots, list) or not raw_roots:
            return None

        file_roots: list[str] = []
        for r in raw_roots:
            if not isinstance(r, str) or not r.strip():
                continue
            # Resolve without raising — we only care about the file-vs-dir
            # outcome, not security policy (the normal validator handles that).
            try:
                resolved = self.path_resolver.resolve(r)
            except Exception:  # nosec B112 — fall through to normal validator
                # Resolution failed — fall through to the normal validator
                # so its error message describes the real problem.
                continue
            resolved_path = Path(resolved)
            if resolved_path.exists() and resolved_path.is_file():
                file_roots.append(r)

        if not file_roots:
            return None

        first = file_roots[0]
        summary_line = "search_content: roots must be directories"
        next_step = f"retry with files=['{first}'] for single-file searches"
        return {
            "success": False,
            "error": (
                "Got file path in 'roots'; pass file paths via the 'files' "
                "parameter instead."
            ),
            "error_type": "validation",
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": next_step,
                "verdict": "ERROR",
            },
            "summary_line": summary_line,
            "roots": raw_roots,
        }

    # Input validation - fail fast with clear error messages
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate query, roots/files, and all option types.

        If neither ``roots`` nor ``files`` was provided but the tool has
        a ``project_root`` configured, default ``roots`` to that root
        so callers don't have to repeat the project path they already
        configured at construction time.
        """
        if "roots" not in arguments and "files" not in arguments and self.project_root:
            arguments["roots"] = [self.project_root]
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

        # L10: detect file-as-root *before* validate_arguments raises a
        # triple-wrapped ``AnalysisError("Operation failed: ... Path is not
        # a directory: ...")``. The canonical envelope tells the agent
        # exactly which parameter to use instead.
        file_root_envelope = self._check_file_in_roots(arguments)
        if file_root_envelope is not None:
            return file_root_envelope

        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "toon")

        roots, files = self._resolve_inputs(arguments)

        cache_key = self._make_cache_key(arguments, roots)
        cached = self._check_cache(cache_key, arguments)
        if cached is not None:
            return cached

        requested_format = determine_requested_format(arguments)
        fts_result = _try_fts5_fast_path(arguments, self.project_root, requested_format)
        if fts_result is not None:
            if output_format == "toon" and isinstance(fts_result, dict):
                return apply_toon_format_to_response(fts_result, output_format)
            return fts_result

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

        return await format_search_response(
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
            rg_args=rg_args,
            roots=roots,
            files=files,
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
