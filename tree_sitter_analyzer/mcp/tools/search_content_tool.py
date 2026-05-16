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
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import (
    apply_toon_format_to_response,
    attach_toon_content_to_response,
)
from ..utils.gitignore_detector import get_default_detector
from ..utils.search_cache import get_default_cache
from . import fd_rg_utils
from .base_tool import BaseMCPTool
from .output_format_validator import get_default_validator
from .search_content_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .search_content_helpers import (
    build_next_steps,
    handle_output_and_cache,
    save_enriched_output,
)

logger = logging.getLogger(__name__)


class SearchContentTool(BaseMCPTool):
    """MCP tool that wraps ripgrep to search content with safety limits."""

    def __init__(
        self, project_root: str | None = None, enable_cache: bool = True
    ) -> None:
        super().__init__(project_root)
        self.cache = get_default_cache() if enable_cache else None
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

    def set_project_path(self, project_path: str) -> None:
        super().set_project_path(project_path)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)
        logger.info(f"SearchContentTool project path updated to: {project_path}")

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "search_content",
            "description": (
                "Ripgrep search with total_only (~10 tok) and summary modes. "
                "Prefer over built-in Grep for: existence checks (total_only), "
                "counts (count_only), structured results (summary)."
            ),
            "inputSchema": _TOOL_SCHEMA,
        }

    def _determine_requested_format(self, arguments: dict[str, Any]) -> str:
        """Determine the requested output format based on arguments."""
        if arguments.get("total_only", False):
            return "total_only"
        if arguments.get("count_only_matches", False):
            return "count_only"
        if arguments.get("summary_only", False):
            return "summary"
        if arguments.get("group_by_file", False):
            return "group_by_file"
        return "normal"

    def _validate_roots(self, roots: list[str]) -> list[str]:
        validated: list[str] = []
        for r in roots:
            try:
                resolved = self.resolve_and_validate_directory_path(r)
                validated.append(resolved)
            except ValueError as e:
                raise ValueError(f"Invalid root '{r}': {e}") from e
        return validated

    def _validate_files(self, files: list[str]) -> list[str]:
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

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        validator = get_default_validator()
        validator.validate_output_format_exclusion(arguments)

        if (
            "query" not in arguments
            or not isinstance(arguments["query"], str)
            or not arguments["query"].strip()
        ):
            raise ValueError("query is required and must be a non-empty string")
        if "roots" not in arguments and "files" not in arguments:
            raise ValueError("Either roots or files must be provided")
        for key in ["case", "encoding", "max_filesize"]:
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
            "enable_parallel",
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

        if "roots" in arguments:
            self._validate_roots(arguments["roots"])
        if "files" in arguments:
            self._validate_files(arguments["files"])

        return True

    @handle_mcp_errors("search_content")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any] | int:
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
        max_count = self._resolve_max_count(arguments)

        # Build and execute ripgrep command
        rg_args = self._build_rg_args(arguments, max_count, no_ignore)
        rc, out, err, elapsed_ms = await self._run_search(
            arguments, rg_args, roots, files, max_count, no_ignore
        )

        if rc not in (0, 1):
            message = err.decode("utf-8", errors="replace").strip() or "ripgrep failed"
            return {"success": False, "error": message, "returncode": rc}

        # Dispatch to mode-specific handler
        total_only = arguments.get("total_only", False)
        count_only = arguments.get("count_only_matches", False)
        summary_only = arguments.get("summary_only", False)
        group_by_file = arguments.get("group_by_file", False)

        if total_only:
            return self._respond_total_only(out, elapsed_ms, cache_key, arguments)
        if count_only:
            return self._respond_count_only(out, elapsed_ms, output_format, cache_key)

        matches = fd_rg_utils.parse_rg_json_lines_to_matches(out)
        matches, truncated = self._apply_limits(matches, arguments)

        if arguments.get("optimize_paths", False) and matches:
            matches = fd_rg_utils.optimize_match_paths(matches)

        if group_by_file and matches:
            return self._respond_grouped(
                matches, truncated, elapsed_ms, output_format, cache_key, arguments
            )
        if summary_only:
            return self._respond_summary(
                matches, truncated, elapsed_ms, output_format, cache_key, arguments
            )
        return self._respond_full(
            matches, truncated, elapsed_ms, output_format, cache_key, arguments
        )

    def _resolve_inputs(
        self, arguments: dict[str, Any]
    ) -> tuple[list[str] | None, list[str] | None]:
        """Resolve and validate roots/files inputs."""
        roots = arguments.get("roots")
        files = arguments.get("files")
        if roots:
            roots = self._validate_roots(roots)
        if files:
            files = self._validate_files(files)
        return roots, files

    def _resolve_no_ignore(
        self, arguments: dict[str, Any], roots: list[str] | None
    ) -> bool:
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

    def _resolve_max_count(self, arguments: dict[str, Any]) -> int | None:
        """Clamp user-specified max_count."""
        max_count = arguments.get("max_count")
        if max_count is not None:
            return fd_rg_utils.clamp_int(
                max_count, 1, fd_rg_utils.DEFAULT_RESULTS_LIMIT
            )
        return max_count

    def _make_cache_key(
        self, arguments: dict[str, Any], roots: list[str] | None
    ) -> str | None:
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

    def _check_cache(
        self, cache_key: str | None, arguments: dict[str, Any]
    ) -> dict[str, Any] | int | None:
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

    @staticmethod
    def _build_rg_args(
        arguments: dict[str, Any],
        max_count: int | None,
        no_ignore: bool,
    ) -> dict[str, Any]:
        """Build the shared ripgrep command keyword arguments."""
        return {
            "query": arguments["query"],
            "case": arguments.get("case", "smart"),
            "fixed_strings": bool(arguments.get("fixed_strings", False)),
            "word": bool(arguments.get("word", False)),
            "multiline": bool(arguments.get("multiline", False)),
            "include_globs": arguments.get("include_globs"),
            "exclude_globs": arguments.get("exclude_globs"),
            "follow_symlinks": bool(arguments.get("follow_symlinks", False)),
            "hidden": bool(arguments.get("hidden", False)),
            "no_ignore": no_ignore,
            "max_filesize": arguments.get("max_filesize"),
            "context_before": arguments.get("context_before"),
            "context_after": arguments.get("context_after"),
            "encoding": arguments.get("encoding"),
            "max_count": max_count,
            "timeout_ms": arguments.get("timeout_ms"),
            "files_from": None,
        }

    async def _run_search(
        self,
        arguments: dict[str, Any],
        rg_args: dict[str, Any],
        roots: list[str] | None,
        files: list[str] | None,
        max_count: int | None,
        no_ignore: bool,
    ) -> tuple[int, bytes, bytes, int]:
        """Execute the ripgrep search (parallel or single). Returns (rc, out, err, elapsed_ms)."""
        # Handle files mode: convert file list to parent dirs + globs
        search_roots = roots
        if files:
            parent_dirs: set[str] = set()
            file_globs: list[str] = []
            for file_path in files:
                resolved = self.path_resolver.resolve(file_path)
                parent_dirs.add(str(Path(resolved).parent))
                escaped = Path(resolved).name.replace("[", "[[]").replace("]", "[]]")
                file_globs.append(escaped)
            search_roots = list(parent_dirs)
            if not arguments.get("include_globs"):
                arguments["include_globs"] = []
            arguments["include_globs"].extend(file_globs)
            rg_args["include_globs"] = arguments["include_globs"]

        count_only_matches = bool(arguments.get("count_only_matches", False)) or bool(
            arguments.get("total_only", False)
        )
        timeout_ms = arguments.get("timeout_ms")

        use_parallel = (
            search_roots is not None
            and len(search_roots) > 1
            and arguments.get("enable_parallel", True)
        )

        started = time.time()

        if use_parallel and search_roots is not None:
            root_chunks = fd_rg_utils.split_roots_for_parallel_processing(
                search_roots, max_chunks=4
            )
            commands = []
            for chunk in root_chunks:
                cmd = fd_rg_utils.build_rg_command(
                    roots=chunk, count_only_matches=count_only_matches, **rg_args
                )
                commands.append(cmd)
            results = await fd_rg_utils.run_parallel_rg_searches(
                commands, timeout_ms=timeout_ms, max_concurrent=4
            )
            rc, out, err = fd_rg_utils.merge_rg_results(results, count_only_matches)
        else:
            cmd = fd_rg_utils.build_rg_command(
                roots=search_roots,
                count_only_matches=count_only_matches,
                **rg_args,
            )
            rc, out, err = await fd_rg_utils.run_command_capture(
                cmd, timeout_ms=timeout_ms
            )

        elapsed_ms = int((time.time() - started) * 1000)
        return rc, out, err, elapsed_ms

    def _respond_total_only(
        self,
        out: bytes,
        elapsed_ms: int,
        cache_key: str | None,
        arguments: dict[str, Any],
    ) -> int:
        """Handle total_only mode: return just the count as int."""
        file_counts = fd_rg_utils.parse_rg_count_output(out)
        total_matches = file_counts.get("__total__", 0)

        if self.cache and cache_key:
            self.cache.set(cache_key, total_matches)
            count_key = self._create_count_only_cache_key(cache_key, arguments)
            if count_key:
                file_counts_copy = {
                    k: v for k, v in file_counts.items() if k != "__total__"
                }
                self.cache.set(
                    count_key,
                    {
                        "success": True,
                        "count_only": True,
                        "total_matches": total_matches,
                        "file_counts": file_counts_copy,
                        "elapsed_ms": elapsed_ms,
                        "derived_from_total_only": True,
                    },
                )

        return int(total_matches)

    def _respond_count_only(
        self,
        out: bytes,
        elapsed_ms: int,
        output_format: str,
        cache_key: str | None,
    ) -> dict[str, Any]:
        """Handle count_only mode."""
        file_counts = fd_rg_utils.parse_rg_count_output(out)
        total_matches = file_counts.pop("__total__", 0)
        result: dict[str, Any] = {
            "success": True,
            "count_only": True,
            "total_matches": total_matches,
            "file_counts": file_counts,
            "elapsed_ms": elapsed_ms,
        }
        if self.cache and cache_key:
            self.cache.set(cache_key, result)
        if output_format == "toon":
            return attach_toon_content_to_response(result)
        return result

    def _respond_grouped(
        self,
        matches: list[dict[str, Any]],
        truncated: bool,
        elapsed_ms: int,
        output_format: str,
        cache_key: str | None,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle group_by_file mode."""
        result = fd_rg_utils.group_matches_by_file(matches)
        result["truncated"] = truncated
        result["elapsed_ms"] = elapsed_ms

        suppressed = handle_output_and_cache(
            result,
            arguments,
            self.file_output_manager,
            self.cache,
            cache_key,
            output_format,
        )
        if suppressed:
            return suppressed

        if output_format == "toon":
            return attach_toon_content_to_response(result)
        return result

    def _respond_summary(
        self,
        matches: list[dict[str, Any]],
        truncated: bool,
        elapsed_ms: int,
        output_format: str,
        cache_key: str | None,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle summary_only mode."""
        result: dict[str, Any] = {
            "success": True,
            "count": len(matches),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "summary": fd_rg_utils.summarize_search_results(matches),
        }

        suppressed = handle_output_and_cache(
            result,
            arguments,
            self.file_output_manager,
            self.cache,
            cache_key,
            output_format,
        )
        if suppressed:
            return suppressed

        if output_format == "toon":
            return attach_toon_content_to_response(result)
        return result

    def _respond_full(
        self,
        matches: list[dict[str, Any]],
        truncated: bool,
        elapsed_ms: int,
        output_format: str,
        cache_key: str | None,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle normal full-result mode."""
        result: dict[str, Any] = {
            "success": True,
            "count": len(matches),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "results": matches,
        }

        if matches and not arguments.get("suppress_output", False):
            steps = build_next_steps(matches)
            if steps:
                result["next_steps"] = steps

        save_enriched_output(
            result,
            matches,
            arguments,
            output_format,
            self.file_output_manager,
            fd_rg_utils,
        )

        suppressed = handle_output_and_cache(
            result,
            arguments,
            self.file_output_manager,
            self.cache,
            cache_key,
            output_format,
        )
        if suppressed:
            return suppressed

        return apply_toon_format_to_response(result, output_format)

    @staticmethod
    def _apply_limits(
        matches: list[dict[str, Any]], arguments: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], bool]:
        """Apply match count limits."""
        user_max = arguments.get("max_count")
        if user_max is not None and len(matches) > user_max:
            return matches[:user_max], True
        if len(matches) >= fd_rg_utils.MAX_RESULTS_HARD_CAP:
            return matches[: fd_rg_utils.MAX_RESULTS_HARD_CAP], True
        return matches, False

    def _create_count_only_cache_key(
        self, total_only_cache_key: str, arguments: dict[str, Any]
    ) -> str | None:
        """Create a count_only_matches cache key from a total_only cache key."""
        if not self.cache:
            return None
        count_only_args = arguments.copy()
        count_only_args.pop("total_only", None)
        count_only_args["count_only_matches"] = True
        cache_params = {
            k: v
            for k, v in count_only_args.items()
            if k not in ["query", "roots", "files"]
        }
        return self.cache.create_cache_key(
            query=arguments["query"], roots=arguments.get("roots", []), **cache_params
        )
