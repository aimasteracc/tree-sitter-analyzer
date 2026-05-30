#!/usr/bin/env python3
"""
Query Tool for MCP

MCP tool providing tree-sitter query functionality using unified QueryService.
Supports both predefined query keys and custom query strings.
"""

import logging
import time
from typing import Any, cast

from ...core.query_service import QueryService
from ...language_detector import detect_language_from_file
from ..utils.error_sanitizer import safe_error_message
from ..utils.file_output_manager import FileOutputManager
from .base_tool import (
    BaseMCPTool,
    detect_language_mismatch,
    language_mismatch_error_response,
)
from .query_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .query_helpers import (
    build_next_steps,
    build_query_agent_summary,
    format_summary,
    handle_query_output,
    validate_query_arguments,
)
from .query_symbol_search import (
    categorize_queries,
    execute_find_references,
    execute_symbol_search,
)
from .search_envelope import normalize_envelope

logger = logging.getLogger(__name__)


class QueryTool(BaseMCPTool):
    """MCP query tool providing tree-sitter query functionality"""

    def __init__(self, project_root: str | None = None) -> None:
        # ARCH-A4: super().__init__() calls _on_project_root_changed which
        # populates these fields synchronously. The None placeholder is
        # never observable from outside __init__, so cast to the real
        # type to spare every call site a None-check.
        self.query_service: QueryService = cast("QueryService", None)
        self.file_output_manager: FileOutputManager = cast("FileOutputManager", None)
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self.query_service = QueryService(project_root)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

    def get_tool_schema(self) -> dict[str, Any]:
        return _TOOL_SCHEMA

    # get_tool_definition: implementation
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "query_code",
            "description": (
                "AST-aware symbol search across the indexed project. "
                "Unlike grep, this matches against parsed declarations "
                "(class / function / method / variable) so results are "
                "semantic, not text-coincidence. Supports glob wildcards "
                "(``*Service``, ``handle_*``), fuzzy matching (``~analyz`` "
                "to allow typos), and type filters (only classes, only "
                "functions). Cross-file by default; pass ``file_path`` to "
                "scope to a single file.\n\n"
                "WHEN TO USE:\n"
                "- Finding a class/function definition by partial name\n"
                "- Locating all symbols matching a pattern (``handle_*``)\n"
                "- Fuzzy search when you don't remember the exact spelling\n"
                "- Type-filtered queries (give me all the class names only)\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- To search arbitrary text (comments, strings, errors) — "
                "use search_content\n"
                "- To find usages / callers of a symbol — use trace_impact\n"
                "- For a hierarchical file outline — use get_code_outline\n"
                "- To search file names — use list_files"
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    # execute: implementation
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a single-file query or cross-file symbol search."""
        try:
            return await self._dispatch(arguments)
        except Exception as e:
            from ..utils.error_handler import AnalysisError

            if isinstance(e, AnalysisError):
                raise
            logger.error("Query execution failed: %s", e)
            return _build_query_error_response(e, self.project_root, arguments)

    async def _dispatch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Route to cross-file search or single-file query."""
        if not arguments:
            raise _analysis_error("file_path or symbol is required")
        symbol = arguments.get("symbol")
        is_cross_file = symbol and not arguments.get("file_path")
        if is_cross_file:
            return await self._execute_cross_file(arguments)
        return await self._execute_file_query(arguments)

    async def _execute_cross_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch cross-file query: symbol search or find-references."""
        if arguments.get("find_references"):
            return await self._execute_find_references(arguments)
        return await self._execute_symbol_search(arguments)

    async def _execute_file_query(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a single-file query.

        r37bn (dogfood): tool flagged this at 128 lines. Split into
        argument validation + mismatch gate + query execution + envelope
        assembly. O3 mismatch / truncation / agent_summary preserved.
        """
        file_path = arguments.get("file_path")
        if not file_path:
            raise _analysis_error("file_path or symbol is required")

        validation = self._validate_query_arguments(arguments)
        if validation is not None:
            return validation

        resolved = self.resolve_and_validate_file_path(file_path)
        logger.info(f"Querying file: {file_path} (resolved to: {resolved})")

        mismatch_response = self._check_query_language_mismatch(
            resolved, file_path, arguments
        )
        if mismatch_response is not None:
            return mismatch_response

        language = self._detect_language(resolved, arguments)
        if not language:
            return {
                "success": False,
                "error": f"Could not detect language for file: {file_path}",
            }

        query_key = arguments.get("query_key")
        query_string = arguments.get("query_string")
        unknown_key = self._reject_unknown_query_key(query_key, language)
        if unknown_key is not None:
            return unknown_key

        filter_val = arguments.get("filter")
        started = time.perf_counter()
        results = await self.query_service.execute_query(
            resolved, language, query_key, query_string, filter_val
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        output_format = arguments.get("output_format", "json")
        if not results:
            return await self._empty_result(
                file_path,
                language,
                query_key,
                query_string,
                resolved,
                elapsed_ms=elapsed_ms,
                output_format=output_format,
            )

        results, truncated, total_results = _apply_max_count_cap(
            results, arguments.get("max_count")
        )
        query_used = query_key or query_string or ""
        formatted = _format_query_results(
            results, arguments, file_path, language, query_used
        )
        _attach_query_envelope_extras(
            formatted,
            arguments=arguments,
            file_path=file_path,
            language=language,
            query_used=query_used,
            results=results,
            elapsed_ms=elapsed_ms,
            truncated=truncated,
            total_results=total_results,
        )
        return self._handle_output(
            formatted, arguments, file_path, language, query_used
        )

    @staticmethod
    def _validate_query_arguments(
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Reject missing / mutually-exclusive ``query_key`` + ``query_string``."""
        query_key = arguments.get("query_key")
        query_string = arguments.get("query_string")
        output_fmt = arguments.get("output_format", "json")
        if not query_key and not query_string:
            raise _analysis_error("Either query_key or query_string must be provided")
        if query_key and query_string:
            return {
                "success": False,
                "error": "Cannot provide both query_key and query_string",
                "output_format": output_fmt,
            }
        return None

    def _check_query_language_mismatch(
        self,
        resolved: str,
        file_path: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        """O3 (round-30): refuse ``--language java`` on a ``.py`` file."""
        explicit_language = arguments.get("language")
        if not (isinstance(explicit_language, str) and explicit_language.strip()):
            return None
        mismatch = detect_language_mismatch(
            resolved,
            explicit_language,
            project_root=self.project_root,
        )
        if not mismatch:
            return None
        response = language_mismatch_error_response(
            tool_name="query_code",
            file_path=file_path,
            warning=mismatch,
        )
        response["output_format"] = arguments.get("output_format", "json")
        return response

    def _reject_unknown_query_key(
        self, query_key: str | None, language: str
    ) -> dict[str, Any] | None:
        """Return an error envelope when ``query_key`` isn't registered for ``language``."""
        if not query_key:
            return None
        available = self.query_service.get_available_queries(language)
        if query_key in available:
            return None
        err = f"Query key '{query_key}' not found for {language}. Available: {sorted(available)}"
        return {
            "success": False,
            "error": err,
            "available_queries": categorize_queries(available, language),
            "language": language,
            "hint": "Use one of the available query keys, or provide query_string for a custom tree-sitter query.",
        }

    # _detect_language: implementation
    def _detect_language(self, resolved: str, arguments: dict[str, Any]) -> str | None:
        """Detect language from file or argument."""
        language = arguments.get("language")
        project_root = self.project_root
        if not language:
            language = detect_language_from_file(resolved, project_root=project_root)
        return language

    # _empty_result: implementation
    async def _empty_result(
        self,
        file_path: str,
        language: str,
        query_key: str | None,
        query_string: str | None,
        resolved: str,
        *,
        elapsed_ms: float | None = None,
        output_format: str = "json",
    ) -> dict[str, Any]:
        """Build helpful response for empty query results."""
        productive = await self._find_productive_queries(resolved, language)
        query_used = query_key or query_string or ""
        response: dict[str, Any] = {
            "success": True,
            "message": f"No results for query '{query_used}' in this {language} file",
            "results": [],
            "count": 0,
            "file_path": file_path,
            "language": language,
            "elapsed_ms": float(elapsed_ms) if elapsed_ms is not None else 0.0,
            "truncated": False,
            "output_format": output_format,
        }
        if productive:
            response["productive_queries"] = productive
            response["hint"] = (
                f"This file has no '{query_used}' elements. Queries with results: {productive}"
            )
        response["agent_summary"] = build_query_agent_summary(
            file_path=file_path,
            language=language,
            query=query_used,
            count=0,
            elapsed_ms=response["elapsed_ms"],
            truncated=False,
        )
        normalize_envelope(response, total_count=0)
        return response

    # _find_productive_queries: implementation
    async def _find_productive_queries(self, resolved: str, language: str) -> list[str]:
        """Find which common queries produce results for a file."""
        try:
            return await _probe_query_keys(
                self.query_service, resolved, language, _PROBE_QUERY_KEYS
            )
        except Exception:
            logger.debug("Failed to scan productive queries for empty result context")
        return []

    # _handle_output: delegates to shared helper
    def _handle_output(
        self,
        formatted: dict[str, Any],
        arguments: dict[str, Any],
        file_path: str,
        language: str,
        query: str | None,
    ) -> dict[str, Any]:
        """Handle file output and suppress logic."""
        return handle_query_output(
            formatted, arguments, file_path, language, query, self.file_output_manager
        )

    # Delegates to helpers for backward-compatible test access
    def _format_summary(
        self, results: list[Any], query_type: str, language: str
    ) -> dict[str, Any]:
        return format_summary(results, query_type, language)

    # _extract_name_from_content: implementation
    def _extract_name_from_content(self, content: str) -> str:
        from .query_helpers import extract_name_from_content

        return extract_name_from_content(content)

    # _build_next_steps: implementation
    def _build_next_steps(
        self, results: list[Any], file_path: str, query_used: str
    ) -> list[str]:
        return build_next_steps(results, file_path, query_used)

    # get_available_queries: implementation
    def get_available_queries(self, language: str) -> list[str]:
        """Return available query keys for a language."""
        return self.query_service.get_available_queries(language)

    # _execute_symbol_search: implementation
    async def _execute_symbol_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Delegate cross-file symbol search to helper."""
        return await execute_symbol_search(self.project_root, arguments)

    async def _execute_find_references(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Delegate cross-file reference search to helper."""
        return await execute_find_references(self.project_root, arguments)

    # validate_arguments: delegates to shared helper
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate file_path/symbol, query_key/query_string, and options."""
        return validate_query_arguments(arguments)


_PROBE_QUERY_KEYS: tuple[str, ...] = (
    "classes",
    "methods",
    "functions",
    "imports",
    "variables",
)


def _build_query_error_response(
    exc: Exception, project_root: str | None, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Build a standardised error response dict for a query execution failure."""
    return {
        "success": False,
        "error": safe_error_message(exc, project_root),
        "file_path": arguments.get("file_path", "unknown"),
        "language": arguments.get("language", "unknown"),
        "output_format": arguments.get("output_format", "json"),
    }


def _apply_max_count_cap(
    results: list[Any], max_count: Any
) -> tuple[list[Any], bool, int]:
    """Return (capped_results, truncated, total) — caps if ``max_count`` set."""
    total = len(results)
    if isinstance(max_count, int) and max_count > 0 and total > max_count:
        return results[:max_count], True, total
    return results, False, total


def _attach_query_envelope_extras(
    formatted: dict[str, Any],
    *,
    arguments: dict[str, Any],
    file_path: str,
    language: str,
    query_used: str,
    results: list[Any],
    elapsed_ms: float,
    truncated: bool,
    total_results: int,
) -> None:
    """Attach elapsed/truncated/output_format/agent_summary + next_steps in place."""
    formatted["elapsed_ms"] = elapsed_ms
    formatted["truncated"] = truncated
    formatted["output_format"] = arguments.get("output_format", "json")
    formatted["agent_summary"] = build_query_agent_summary(
        file_path=file_path,
        language=language,
        query=query_used,
        count=len(results),
        elapsed_ms=elapsed_ms,
        truncated=truncated,
    )
    steps = build_next_steps(results, file_path, query_used)
    if steps:
        formatted["next_steps"] = steps
    normalize_envelope(formatted, total_count=total_results)


async def _probe_query_keys(
    query_service: Any,
    resolved: str,
    language: str,
    keys: tuple[str, ...],
) -> list[str]:
    """Return which query keys produce non-empty results for a file."""
    found = []
    for qk in keys:
        results = await query_service.execute_query(resolved, language, query_key=qk)
        if results:
            found.append(qk)
    return found


def _format_query_results(
    results: list[Any],
    arguments: dict[str, Any],
    file_path: str,
    language: str,
    query_used: str,
) -> dict[str, Any]:
    """Pick the result envelope shape based on ``result_format``."""
    result_format = arguments.get("result_format", "json")
    if result_format == "summary":
        qk_raw = arguments.get("query_key")
        qk_used = qk_raw if qk_raw else "custom"
        formatted = format_summary(results, qk_used, language)
        formatted.setdefault("results", results)
        return formatted
    return {
        "success": True,
        "results": results,
        "count": len(results),
        "file_path": file_path,
        "language": language,
        "query": query_used,
    }


# _analysis_error: implementation
def _analysis_error(msg: str) -> Exception:
    from ..utils.error_handler import AnalysisError

    return AnalysisError(msg, operation="query_code")


# Backward-compatible re-export for tests
_categorize_queries = categorize_queries
