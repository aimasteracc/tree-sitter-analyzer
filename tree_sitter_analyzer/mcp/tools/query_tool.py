#!/usr/bin/env python3
"""
Query Tool for MCP

MCP tool providing tree-sitter query functionality using unified QueryService.
Supports both predefined query keys and custom query strings.
"""

import logging
from pathlib import Path
from typing import Any

from ...core.query_service import QueryService
from ...language_detector import detect_language_from_file
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import apply_toon_format_to_response, format_for_file_output
from .base_tool import BaseMCPTool
from .query_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .query_helpers import build_next_steps, format_summary
from .query_symbol_search import categorize_queries, execute_symbol_search

logger = logging.getLogger(__name__)


class QueryTool(BaseMCPTool):
    """MCP query tool providing tree-sitter query functionality"""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self.query_service = QueryService(project_root)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

    def set_project_path(self, project_path: str) -> None:
        super().set_project_path(project_path)
        self.query_service = QueryService(project_path)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "query_code",
            "description": (
                "AST symbol search (NOT text grep). Wildcards: *Service, handle_*. "
                "Fuzzy: ~analyz. Type filter: class/function. "
                "Cross-file by default. Use instead of Grep for symbol definitions."
            ),
            "inputSchema": _TOOL_SCHEMA,
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if not arguments:
                raise _analysis_error("file_path or symbol is required")

            # Cross-file symbol search
            symbol = arguments.get("symbol")
            if symbol and not arguments.get("file_path"):
                return await self._execute_symbol_search(arguments)

            return await self._execute_file_query(arguments)

        except Exception as e:
            from ..utils.error_handler import AnalysisError

            if isinstance(e, AnalysisError):
                raise
            logger.error(f"Query execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_path": arguments.get("file_path", "unknown"),
                "language": arguments.get("language", "unknown"),
            }

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

    def _detect_language(self, resolved: str, arguments: dict[str, Any]) -> str | None:
        language = arguments.get("language")
        if not language:
            language = detect_language_from_file(
                resolved, project_root=self.project_root
            )
        return language

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

    def _handle_output(
        self,
        formatted: dict[str, Any],
        arguments: dict[str, Any],
        file_path: str,
        language: str,
        query: str | None,
    ) -> dict[str, Any]:
        """Handle file output and suppress logic."""
        output_file = arguments.get("output_file")
        suppress_output = arguments.get("suppress_output", False)
        output_format = arguments.get("output_format", "toon")

        if output_file:
            try:
                base_name = (
                    output_file
                    if output_file.strip()
                    else f"{Path(file_path).stem}_query_{query or 'custom'}"
                )
                content, _ = format_for_file_output(formatted, output_format)
                saved = self.file_output_manager.save_to_file(
                    content=content, base_name=base_name
                )
                formatted["output_file_path"] = saved
                formatted["file_saved"] = True
                logger.info(f"Query output saved to: {saved}")
            except Exception as e:
                logger.error(f"Failed to save output to file: {e}")
                formatted["file_save_error"] = str(e)
                formatted["file_saved"] = False

        if suppress_output and output_file:
            minimal: dict[str, Any] = {
                "success": formatted.get("success", True),
                "count": formatted.get("count", 0),
                "file_path": file_path,
                "language": language,
                "query": query,
            }
            if "output_file_path" in formatted:
                minimal["output_file_path"] = formatted["output_file_path"]
            if "file_saved" in formatted:
                minimal["file_saved"] = formatted["file_saved"]
            if "file_save_error" in formatted:
                minimal["file_save_error"] = formatted["file_save_error"]
            return minimal

        return apply_toon_format_to_response(formatted, output_format)

    # Delegates to helpers for backward-compatible test access
    def _format_summary(
        self, results: list[dict[str, Any]], query_type: str, language: str
    ) -> dict[str, Any]:
        return format_summary(results, query_type, language)

    def _extract_name_from_content(self, content: str) -> str:
        from .query_helpers import extract_name_from_content

        return extract_name_from_content(content)

    def _build_next_steps(
        self, results: list[dict[str, Any]], file_path: str, query_used: str
    ) -> list[str]:
        return build_next_steps(results, file_path, query_used)

    def get_available_queries(self, language: str) -> list[str]:
        return self.query_service.get_available_queries(language)

    async def _execute_symbol_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await execute_symbol_search(self.project_root, arguments)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "file_path" not in arguments and "symbol" not in arguments:
            raise ValueError("file_path or symbol is required")
        if "file_path" in arguments:
            fp = arguments["file_path"]
            if not isinstance(fp, str):
                raise ValueError("file_path must be a string")
            if not fp.strip():
                raise ValueError("file_path cannot be empty")
        if not arguments.get("query_key") and not arguments.get("query_string"):
            raise ValueError("Either query_key or query_string must be provided")
        if "query_key" in arguments and not isinstance(arguments["query_key"], str):
            raise ValueError("query_key must be a string")
        if "query_string" in arguments and not isinstance(
            arguments["query_string"], str
        ):
            raise ValueError("query_string must be a string")
        for key in ["language", "filter"]:
            if key in arguments and not isinstance(arguments[key], str):
                raise ValueError(f"{key} must be a string")
        if "result_format" in arguments:
            if not isinstance(arguments["result_format"], str):
                raise ValueError("result_format must be a string")
            if arguments["result_format"] not in ["json", "summary"]:
                raise ValueError("result_format must be one of: json, summary")
        if "output_format" in arguments:
            if not isinstance(arguments["output_format"], str):
                raise ValueError("output_format must be a string")
            if arguments["output_format"] not in ["json", "toon"]:
                raise ValueError("output_format must be one of: json, toon")
        if "output_file" in arguments:
            if not isinstance(arguments["output_file"], str):
                raise ValueError("output_file must be a string")
            if not arguments["output_file"].strip():
                raise ValueError("output_file cannot be empty")
        if "suppress_output" in arguments and not isinstance(
            arguments["suppress_output"], bool
        ):
            raise ValueError("suppress_output must be a boolean")
        return True


def _analysis_error(msg: str) -> Exception:
    from ..utils.error_handler import AnalysisError

    return AnalysisError(msg, operation="query_code")


# Backward-compatible re-export for tests
_categorize_queries = categorize_queries
