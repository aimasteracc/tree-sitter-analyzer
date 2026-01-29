"""Content search strategy using ripgrep.

This module implements the main content search strategy that uses ripgrep
to search for text patterns in files.
"""

import logging
import time
from typing import Any

from tree_sitter_analyzer.mcp.tools.fd_rg import (
    MAX_RESULTS_HARD_CAP,
    RgCommandBuilder,
    RgCommandConfig,
    RgResultParser,
    group_matches_by_file,
    merge_command_results,
    optimize_match_paths,
    run_command_capture,
    run_parallel_commands,
    sanitize_error_message,
    split_roots_for_parallel_processing,
    summarize_search_results,
)
from tree_sitter_analyzer.mcp.tools.search_strategies.base import (
    SearchContext,
    SearchStrategy,
)
from tree_sitter_analyzer.mcp.utils.format_helper import (
    apply_toon_format_to_response,
    format_for_file_output,
)
from tree_sitter_analyzer.mcp.utils.gitignore_detector import get_default_detector

logger = logging.getLogger(__name__)


class ContentSearchStrategy(SearchStrategy):
    """Strategy for searching content using ripgrep.

    This strategy handles the main content search functionality, including:
    - Building ripgrep commands
    - Executing searches (single or parallel)
    - Parsing and formatting results
    - Handling different output modes (total_only, count_only, summary, etc.)
    """

    def __init__(
        self,
        cache: Any = None,
        file_output_manager: Any = None,
        path_resolver: Any = None,
    ) -> None:
        """Initialize the content search strategy.

        Args:
            cache: Optional cache service for caching results
            file_output_manager: Optional manager for saving results to files
            path_resolver: Optional path resolver for validating file paths
        """
        self.cache = cache
        self.file_output_manager = file_output_manager
        self.path_resolver = path_resolver

    async def execute(self, context: SearchContext) -> dict[str, Any] | int:
        """Execute content search using ripgrep.

        Args:
            context: SearchContext containing all search parameters

        Returns:
            Search results as a dictionary, or an integer for total_only mode
        """
        # Check cache first
        if self.cache and context.cache_key:
            cached_result = self._check_cache(context)
            if cached_result is not None:
                return cached_result

        # Auto-detect .gitignore interference
        no_ignore = self._detect_gitignore_interference(context)

        # Determine execution mode (parallel or single)
        use_parallel = self._should_use_parallel(context)

        # Execute search
        started = time.time()
        if use_parallel and context.roots:
            rc, out, err = await self._execute_parallel_search(context, no_ignore)
        else:
            rc, out, err = await self._execute_single_search(context, no_ignore)
        elapsed_ms = int((time.time() - started) * 1000)

        # Handle errors
        if rc not in (0, 1):
            raw_message = (
                err.decode("utf-8", errors="replace").strip() or "ripgrep failed"
            )
            # Sanitize error message to prevent information leakage
            sanitized_message = sanitize_error_message(raw_message)
            return {"success": False, "error": sanitized_message, "returncode": rc}

        # Process results based on output mode
        return await self._process_results(context, out, elapsed_ms)

    def _check_cache(self, context: SearchContext) -> dict[str, Any] | int | None:
        """Check cache for existing results.

        Args:
            context: SearchContext containing cache key

        Returns:
            Cached result if found, None otherwise
        """
        cached_result = self.cache.get(context.cache_key)
        if cached_result is None:
            return None

        # Handle total_only mode
        if context.total_only:
            if isinstance(cached_result, int):
                return cached_result
            elif isinstance(cached_result, dict) and "total_matches" in cached_result:
                total_matches = cached_result["total_matches"]
                return (
                    int(total_matches) if isinstance(total_matches, int | float) else 0
                )
            elif isinstance(cached_result, dict) and "count" in cached_result:
                count = cached_result["count"]
                return int(count) if isinstance(count, int | float) else 0
            else:
                return 0
        else:
            # For non-total_only modes, return dict format
            if isinstance(cached_result, dict):
                cached_result = cached_result.copy()
                cached_result["cache_hit"] = True
                return cached_result
            elif isinstance(cached_result, int):
                # Convert integer to dict format
                return {
                    "success": True,
                    "count": cached_result,
                    "total_matches": cached_result,
                    "cache_hit": True,
                }
            else:
                return {
                    "success": True,
                    "cached_result": cached_result,
                    "cache_hit": True,
                }

    def _detect_gitignore_interference(self, context: SearchContext) -> bool:
        """Detect if .gitignore might interfere with search.

        Args:
            context: SearchContext containing search parameters

        Returns:
            True if --no-ignore should be used, False otherwise
        """
        no_ignore = context.no_ignore

        # Only auto-detect for roots mode, not files mode
        if not no_ignore and context.roots:
            detector = get_default_detector()
            should_ignore = detector.should_use_no_ignore(
                context.roots, str(context.project_root)
            )
            if should_ignore:
                no_ignore = True
                detection_info = detector.get_detection_info(
                    context.roots, str(context.project_root)
                )
                logger.info(
                    f"Auto-enabled --no-ignore due to .gitignore interference: {detection_info['reason']}"
                )

        return no_ignore

    async def _execute_parallel_search(
        self, context: SearchContext, no_ignore: bool
    ) -> tuple[int, bytes, bytes]:
        """Execute search in parallel across multiple roots.

        Args:
            context: SearchContext containing search parameters
            no_ignore: Whether to use --no-ignore flag

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        # Split roots for parallel processing
        root_chunks = split_roots_for_parallel_processing(
            context.roots or [], max_chunks=4
        )

        # Build commands for each chunk
        commands = []
        count_only = context.count_only_matches or context.total_only

        for chunk in root_chunks:
            config = RgCommandConfig(
                query=context.query,
                case=context.case or "smart",
                fixed_strings=context.fixed_strings,
                word=context.word,
                multiline=context.multiline,
                include_globs=tuple(context.include_globs)
                if context.include_globs
                else None,
                exclude_globs=tuple(context.exclude_globs)
                if context.exclude_globs
                else None,
                follow_symlinks=context.follow_symlinks,
                hidden=context.hidden,
                no_ignore=no_ignore,
                max_filesize=context.max_filesize,
                context_before=context.context_before,
                context_after=context.context_after,
                encoding=context.encoding,
                max_count=context.max_count,
                timeout_ms=context.timeout_ms,
                roots=tuple(chunk),
                files_from=None,
                count_only_matches=count_only,
            )
            cmd = RgCommandBuilder().build(config)
            commands.append(cmd)

        # Execute commands in parallel
        results = await run_parallel_commands(
            commands, timeout_ms=context.timeout_ms, max_concurrent=4
        )

        # Merge results
        return merge_command_results(results, count_only)

    async def _execute_single_search(
        self, context: SearchContext, no_ignore: bool
    ) -> tuple[int, bytes, bytes]:
        """Execute a single search command.

        Args:
            context: SearchContext containing search parameters
            no_ignore: Whether to use --no-ignore flag

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        count_only = context.count_only_matches or context.total_only

        config = RgCommandConfig(
            query=context.query,
            case=context.case or "smart",
            fixed_strings=context.fixed_strings,
            word=context.word,
            multiline=context.multiline,
            include_globs=tuple(context.include_globs)
            if context.include_globs
            else None,
            exclude_globs=tuple(context.exclude_globs)
            if context.exclude_globs
            else None,
            follow_symlinks=context.follow_symlinks,
            hidden=context.hidden,
            no_ignore=no_ignore,
            max_filesize=context.max_filesize,
            context_before=context.context_before,
            context_after=context.context_after,
            encoding=context.encoding,
            max_count=context.max_count,
            timeout_ms=context.timeout_ms,
            roots=tuple(context.roots) if context.roots else None,
            files_from=None,
            count_only_matches=count_only,
        )
        cmd = RgCommandBuilder().build(config)

        return await run_command_capture(cmd, timeout_ms=context.timeout_ms)

    async def _process_results(
        self, context: SearchContext, output: bytes, elapsed_ms: int
    ) -> dict[str, Any] | int:
        """Process search results based on output mode.

        Args:
            context: SearchContext containing output mode flags
            output: Raw output from ripgrep
            elapsed_ms: Elapsed time in milliseconds

        Returns:
            Processed results in the requested format
        """
        # Handle total_only mode (highest priority)
        if context.total_only:
            return self._process_total_only(context, output, elapsed_ms)

        # Handle count_only_matches mode
        if context.count_only_matches:
            return self._process_count_only(context, output, elapsed_ms)

        # Parse matches for other modes
        parser = RgResultParser()
        matches = parser.parse_json_matches(output)

        # Apply max_count limit if specified
        truncated = False
        if context.max_count is not None and len(matches) > context.max_count:
            matches = matches[: context.max_count]
            truncated = True
        elif len(matches) >= MAX_RESULTS_HARD_CAP:
            matches = matches[:MAX_RESULTS_HARD_CAP]
            truncated = True

        # Handle optimize_paths mode
        if context.optimize_paths:
            return self._process_optimized_paths(
                context, matches, truncated, elapsed_ms
            )

        # Handle group_by_file mode
        if context.group_by_file:
            return self._process_grouped_by_file(
                context, matches, truncated, elapsed_ms
            )

        # Handle summary_only mode
        if context.summary_only:
            return self._process_summary_only(context, matches, truncated, elapsed_ms)

        # Handle normal mode
        return self._process_normal_mode(context, matches, truncated, elapsed_ms)

    def _process_total_only(
        self, context: SearchContext, output: bytes, elapsed_ms: int
    ) -> int:
        """Process results for total_only mode.

        Args:
            context: SearchContext
            output: Raw output from ripgrep
            elapsed_ms: Elapsed time in milliseconds

        Returns:
            Total match count as integer
        """
        parser = RgResultParser()
        file_counts = parser.parse_count_output(output)
        total_matches = file_counts.get("__total__", 0)

        # Cache the result
        if self.cache and context.cache_key:
            self.cache.set(context.cache_key, total_matches)

            # Also cache for count_only_matches mode (cross-format optimization)
            count_only_cache_key = self._create_count_only_cache_key(
                context.cache_key, context.arguments
            )
            if count_only_cache_key:
                file_counts_copy = {
                    k: v for k, v in file_counts.items() if k != "__total__"
                }
                detailed_count_result = {
                    "success": True,
                    "count_only": True,
                    "total_matches": total_matches,
                    "file_counts": file_counts_copy,
                    "elapsed_ms": elapsed_ms,
                    "derived_from_total_only": True,
                }
                self.cache.set(count_only_cache_key, detailed_count_result)
                logger.debug(
                    "Cross-cached total_only result as count_only_matches for future optimization"
                )

        return int(total_matches)

    def _process_count_only(
        self, context: SearchContext, output: bytes, elapsed_ms: int
    ) -> dict[str, Any]:
        """Process results for count_only_matches mode.

        Args:
            context: SearchContext
            output: Raw output from ripgrep
            elapsed_ms: Elapsed time in milliseconds

        Returns:
            Dictionary with file counts
        """
        parser = RgResultParser()
        file_counts = parser.parse_count_output(output)
        total_matches = file_counts.pop("__total__", 0)
        result = {
            "success": True,
            "count_only": True,
            "total_matches": total_matches,
            "file_counts": file_counts,
            "elapsed_ms": elapsed_ms,
        }

        # Cache the result
        if self.cache and context.cache_key:
            self.cache.set(context.cache_key, result)

        if context.output_format == "toon":
            return apply_toon_format_to_response(result, "toon")
        return result

    def _process_optimized_paths(
        self, context: SearchContext, matches: list, truncated: bool, elapsed_ms: int
    ) -> dict[str, Any]:
        """Process results with path optimization.

        Args:
            context: SearchContext
            matches: List of match dictionaries
            truncated: Whether results were truncated
            elapsed_ms: Elapsed time in milliseconds

        Returns:
            Dictionary with optimized paths
        """
        if matches:
            matches = optimize_match_paths(matches)

        result = {
            "success": True,
            "count": len(matches),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "results": matches,
        }

        # Handle file output and suppression
        result = self._handle_file_output(context, result)

        # Cache the result
        if self.cache and context.cache_key:
            self.cache.set(context.cache_key, result)

        if context.output_format == "toon":
            return apply_toon_format_to_response(result, "toon")
        return result

    def _process_grouped_by_file(
        self, context: SearchContext, matches: list, truncated: bool, elapsed_ms: int
    ) -> dict[str, Any]:
        """Process results grouped by file.

        Args:
            context: SearchContext
            matches: List of match dictionaries
            truncated: Whether results were truncated
            elapsed_ms: Elapsed time in milliseconds

        Returns:
            Dictionary with results grouped by file
        """
        result = group_matches_by_file(matches)

        # Handle file output and suppression
        result = self._handle_file_output(context, result)

        # Cache the result
        if self.cache and context.cache_key:
            self.cache.set(context.cache_key, result)

        if context.output_format == "toon":
            return apply_toon_format_to_response(result, "toon")
        return result

    def _process_summary_only(
        self, context: SearchContext, matches: list, truncated: bool, elapsed_ms: int
    ) -> dict[str, Any]:
        """Process results for summary_only mode.

        Args:
            context: SearchContext
            matches: List of match dictionaries
            truncated: Whether results were truncated
            elapsed_ms: Elapsed time in milliseconds

        Returns:
            Dictionary with summary
        """
        summary = summarize_search_results(matches)
        result = {
            "success": True,
            "count": len(matches),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "summary": summary,
        }

        # Handle file output and suppression
        result = self._handle_file_output(context, result)

        # Cache the result
        if self.cache and context.cache_key:
            self.cache.set(context.cache_key, result)

        if context.output_format == "toon":
            return apply_toon_format_to_response(result, "toon")
        return result

    def _process_normal_mode(
        self, context: SearchContext, matches: list, truncated: bool, elapsed_ms: int
    ) -> dict[str, Any]:
        """Process results for normal mode.

        Args:
            context: SearchContext
            matches: List of match dictionaries
            truncated: Whether results were truncated
            elapsed_ms: Elapsed time in milliseconds

        Returns:
            Dictionary with full results
        """
        result = {
            "success": True,
            "count": len(matches),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "results": matches,
        }

        # Handle file output and suppression
        result = self._handle_file_output(context, result)

        # Cache the result
        if self.cache and context.cache_key:
            self.cache.set(context.cache_key, result)

        return apply_toon_format_to_response(result, context.output_format)

    def _handle_file_output(
        self, context: SearchContext, result: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle file output and output suppression.

        Args:
            context: SearchContext
            result: Result dictionary

        Returns:
            Modified result dictionary (may be minimal if suppressed)
        """
        if not context.output_file and not context.suppress_output:
            return result

        # Handle file output
        if context.output_file and self.file_output_manager:
            try:
                formatted_content, _ = format_for_file_output(
                    result, context.output_format
                )
                file_path = self.file_output_manager.save_to_file(
                    content=formatted_content, base_name=context.output_file
                )

                if context.suppress_output:
                    # Return minimal result
                    return {
                        "success": result.get("success", True),
                        "count": result.get("count", 0),
                        "output_file": context.output_file,
                        "file_saved": f"Results saved to {file_path}",
                    }
                else:
                    # Include file info in full response
                    result["output_file"] = context.output_file
                    result["file_saved"] = f"Results saved to {file_path}"
            except Exception as e:
                logger.error(f"Failed to save output to file: {e}")
                result["file_save_error"] = str(e)
                result["file_saved"] = False
        elif context.suppress_output:
            # Suppress output without file
            minimal_keys = {"success", "count", "elapsed_ms", "summary", "meta"}
            return {k: v for k, v in result.items() if k in minimal_keys}

        return result

    def _create_count_only_cache_key(
        self, base_cache_key: str, arguments: dict[str, Any]
    ) -> str | None:
        """Create cache key for count_only_matches mode.

        Args:
            base_cache_key: Base cache key
            arguments: Original arguments

        Returns:
            Cache key for count_only_matches mode, or None
        """
        # This is a simplified version - the actual implementation would
        # need to properly modify the cache key
        if not self.cache:
            return None

        # Create a modified arguments dict with count_only_matches=True
        count_only_args = arguments.copy()
        count_only_args["count_only_matches"] = True
        count_only_args.pop("total_only", None)

        # Use the cache's create_cache_key method if available
        if hasattr(self.cache, "create_cache_key"):
            return str(
                self.cache.create_cache_key(
                    query=arguments.get("query", ""),
                    roots=arguments.get("roots", []),
                    **{
                        k: v
                        for k, v in count_only_args.items()
                        if k not in ["query", "roots", "output_file", "suppress_output"]
                    },
                )
            )

        return None
