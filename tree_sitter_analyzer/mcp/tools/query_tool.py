#!/usr/bin/env python3
"""
Query Tool for MCP

MCP tool providing tree-sitter query functionality using unified QueryService.
Supports both predefined query keys and custom query strings.
"""

import logging
from typing import Any, cast

from ...core.query_service import QueryService
from ...language_detector import detect_language_from_file
from ..utils.error_sanitizer import safe_error_message
from ..utils.file_output_manager import FileOutputManager
from .base_tool import BaseMCPTool
from .query_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .query_helpers import (
    build_next_steps,
    format_summary,
    handle_query_output,
    validate_query_arguments,
)
from .query_symbol_search import (
    categorize_queries,
    execute_find_references,
    execute_symbol_search,
)

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

    # get_tool_definition: implementation
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "query_code",
            "description": (
                "AST symbol search (NOT text grep). Wildcards: *Service, handle_*. "
                "Fuzzy: ~analyz. Type filter: class/function. "
                "Cross-file by default. Use instead of Grep for symbol definitions."
            ),
            "inputSchema": _TOOL_SCHEMA,
        }

    # execute: implementation
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a single-file query or cross-file symbol search."""
        try:
            if not arguments:
                raise _analysis_error("file_path or symbol is required")

            # Cross-file symbol search
            symbol = arguments.get("symbol")
            if symbol and not arguments.get("file_path"):
                if arguments.get("find_references"):
                    return await self._execute_find_references(arguments)
                return await self._execute_symbol_search(arguments)

            return await self._execute_file_query(arguments)

        except Exception as e:
            from ..utils.error_handler import AnalysisError

            if isinstance(e, AnalysisError):
                raise
            logger.error(f"Query execution failed: {e}")
            return {
                "success": False,
                "error": safe_error_message(e, self.project_root),
                "file_path": arguments.get("file_path", "unknown"),
                "language": arguments.get("language", "unknown"),
            }

    # _execute_file_query: implementation
    async def _execute_file_query(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a single-file query."""
        file_path = arguments.get("file_path")
        if not file_path:
            raise _analysis_error("file_path or symbol is required")

        query_key = arguments.get("query_key")
        query_string = arguments.get("query_string")
        if not query_key and not query_string:
            raise _analysis_error("Either query_key or query_string must be provided")

        if query_key and query_string:
            return {
                "success": False,
                "error": "Cannot provide both query_key and query_string",
            }

        resolved = self.resolve_and_validate_file_path(file_path)
        logger.info(f"Querying file: {file_path} (resolved to: {resolved})")

        language = self._detect_language(resolved, arguments)
        if not language:
            return {
                "success": False,
                "error": f"Could not detect language for file: {file_path}",
            }

        # Validate query_key
        if query_key:
            available = self.query_service.get_available_queries(language)
            if query_key not in available:
                return {
                    "success": False,
                    "error": f"Query key '{query_key}' not found for {language}. Available: {sorted(available)}",
                    "available_queries": categorize_queries(available, language),
                    "language": language,
                    "hint": "Use one of the available query keys, or provide query_string for a custom tree-sitter query.",
                }

        # Execute query
        results = await self.query_service.execute_query(
            resolved, language, query_key, query_string, arguments.get("filter")
        )

        if not results:
            return await self._empty_result(
                file_path, language, query_key, query_string, resolved
            )

        # Format results
        result_format = arguments.get("result_format", "json")
        if result_format == "summary":
            formatted = format_summary(results, query_key or "custom", language)
        else:
            formatted = {
                "success": True,
                "results": results,
                "count": len(results),
                "file_path": file_path,
                "language": language,
                "query": query_key or query_string,
            }

        steps = build_next_steps(results, file_path, query_key or query_string or "")
        if steps:
            formatted["next_steps"] = steps

        return self._handle_output(
            formatted, arguments, file_path, language, query_key or query_string
        )

    # _detect_language: implementation
    def _detect_language(self, resolved: str, arguments: dict[str, Any]) -> str | None:
        """Detect language from file or argument."""
        language = arguments.get("language")
        if not language:
            language = detect_language_from_file(
                resolved, project_root=self.project_root
            )
        return language

    # _empty_result: implementation
    async def _empty_result(
        self,
        file_path: str,
        language: str,
        query_key: str | None,
        query_string: str | None,
        resolved: str,
    ) -> dict[str, Any]:
        """Build helpful response for empty query results."""
        productive = await self._find_productive_queries(resolved, language)
        response: dict[str, Any] = {
            "success": True,
            "message": f"No results for query '{query_key or query_string}' in this {language} file",
            "results": [],
            "count": 0,
            "file_path": file_path,
            "language": language,
        }
        if productive:
            response["productive_queries"] = productive
            response["hint"] = (
                f"This file has no '{query_key or query_string}' elements. Queries with results: {productive}"
            )
        return response

    # _find_productive_queries: implementation
    async def _find_productive_queries(self, resolved: str, language: str) -> list[str]:
        """Find which common queries produce results for a file."""
        productive = []
        try:
            for qk in ["classes", "methods", "functions", "imports", "variables"]:
                results = await self.query_service.execute_query(
                    resolved, language, query_key=qk
                )
                if results:
                    productive.append(qk)
        except Exception:
            logger.debug("Failed to scan productive queries for empty result context")
        return productive

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
        self, results: list[dict[str, Any]], query_type: str, language: str
    ) -> dict[str, Any]:
        return format_summary(results, query_type, language)

    # _extract_name_from_content: implementation
    def _extract_name_from_content(self, content: str) -> str:
        from .query_helpers import extract_name_from_content

        return extract_name_from_content(content)

    # _build_next_steps: implementation
    def _build_next_steps(
        self, results: list[dict[str, Any]], file_path: str, query_used: str
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


# _analysis_error: implementation
def _analysis_error(msg: str) -> Exception:
    from ..utils.error_handler import AnalysisError

    return AnalysisError(msg, operation="query_code")


# Backward-compatible re-export for tests
_categorize_queries = categorize_queries
