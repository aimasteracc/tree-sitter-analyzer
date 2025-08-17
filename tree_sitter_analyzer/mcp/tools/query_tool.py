#!/usr/bin/env python3
"""
Query Tool for MCP

MCP tool providing tree-sitter query functionality using unified QueryService.
Supports both predefined query keys and custom query strings.
"""

import logging
from typing import Any

from ...core.query_service import QueryService
from ...language_detector import detect_language_from_file
from ...security import SecurityValidator
from ..utils.error_handler import handle_mcp_errors
from ..utils.path_resolver import PathResolver

logger = logging.getLogger(__name__)


class QueryTool:
    """MCP query tool providing tree-sitter query functionality"""

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize query tool"""
        self.project_root = project_root
        self.query_service = QueryService(project_root)
        self.security_validator = SecurityValidator(project_root)
        self.path_resolver = PathResolver(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get MCP tool definition

        Returns:
            Tool definition dictionary
        """
        return {
            "name": "query_code",
            "description": "Execute tree-sitter queries on code files to extract specific code elements",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the code file to query (relative to project root or absolute path)",
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (optional, auto-detected if not provided)",
                    },
                    "query_key": {
                        "type": "string",
                        "description": "Predefined query key (e.g., 'methods', 'class', 'functions')",
                    },
                    "query_string": {
                        "type": "string",
                        "description": "Custom tree-sitter query string (e.g., '(method_declaration) @method')",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Filter expression to refine results (e.g., 'name=main', 'name=~get*,public=true')",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["json", "summary"],
                        "default": "json",
                        "description": "Output format",
                    },
                },
                "required": ["file_path"],
                "anyOf": [
                    {"required": ["query_key"]},
                    {"required": ["query_string"]},
                ],
            },
        }

    @handle_mcp_errors("query_code")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute query tool

        Args:
            arguments: Tool arguments

        Returns:
            Query results
        """
        # Validate input parameters
        file_path = arguments.get("file_path")
        if not file_path:
            raise ValueError("file_path is required")

        # Resolve file path to absolute path
        resolved_file_path = self.path_resolver.resolve(file_path)
        logger.info(f"Querying file: {file_path} (resolved to: {resolved_file_path})")

        # Security validation using resolved path
        is_valid, error_msg = self.security_validator.validate_file_path(
            resolved_file_path
        )
        if not is_valid:
            raise ValueError(
                f"Invalid or unsafe file path: {error_msg or resolved_file_path}"
            )

        # Get query parameters
        query_key = arguments.get("query_key")
        query_string = arguments.get("query_string")
        filter_expression = arguments.get("filter")
        output_format = arguments.get("output_format", "json")

        if not query_key and not query_string:
            raise ValueError("Either query_key or query_string must be provided")

        if query_key and query_string:
            raise ValueError("Cannot provide both query_key and query_string")

        # Detect language
        language = arguments.get("language")
        if not language:
            language = detect_language_from_file(resolved_file_path)
            if not language:
                raise ValueError(f"Could not detect language for file: {file_path}")

        try:
            # Execute query
            results = await self.query_service.execute_query(
                resolved_file_path, language, query_key, query_string, filter_expression
            )

            if not results:
                return {
                    "success": True,
                    "message": "No results found matching the query",
                    "results": [],
                    "count": 0,
                }

            # Format output
            if output_format == "summary":
                return self._format_summary(results, query_key or "custom", language)
            else:
                return {
                    "success": True,
                    "results": results,
                    "count": len(results),
                    "file_path": file_path,
                    "language": language,
                    "query": query_key or query_string,
                }

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_path": file_path,
                "language": language,
            }

    def _format_summary(
        self, results: list[dict[str, Any]], query_type: str, language: str
    ) -> dict[str, Any]:
        """
        Format summary output

        Args:
            results: Query results
            query_type: Query type
            language: Programming language

        Returns:
            Summary formatted results
        """
        # Group by capture name
        by_capture = {}
        for result in results:
            capture_name = result["capture_name"]
            if capture_name not in by_capture:
                by_capture[capture_name] = []
            by_capture[capture_name].append(result)

        # Create summary
        summary = {
            "success": True,
            "query_type": query_type,
            "language": language,
            "total_count": len(results),
            "captures": {},
        }

        for capture_name, items in by_capture.items():
            summary["captures"][capture_name] = {
                "count": len(items),
                "items": [
                    {
                        "name": self._extract_name_from_content(item["content"]),
                        "line_range": f"{item['start_line']}-{item['end_line']}",
                        "node_type": item["node_type"],
                    }
                    for item in items
                ],
            }

        return summary

    def _extract_name_from_content(self, content: str) -> str:
        """
        Extract name from content (simple heuristic method)

        Args:
            content: Code content

        Returns:
            Extracted name
        """
        # Simple name extraction logic, can be improved as needed
        lines = content.strip().split("\n")
        if lines:
            first_line = lines[0].strip()
            # Extract method names, class names, etc.
            import re

            # Match common declaration patterns
            patterns = [
                r"(?:public|private|protected)?\s*(?:static)?\s*(?:class|interface)\s+(\w+)",  # class/interface
                r"(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(",  # method
                r"(\w+)\s*\(",  # simple function call
            ]

            for pattern in patterns:
                match = re.search(pattern, first_line)
                if match:
                    return match.group(1)

        return "unnamed"

    def get_available_queries(self, language: str) -> list[str]:
        """
        Get available query keys

        Args:
            language: Programming language

        Returns:
            List of available query keys
        """
        return self.query_service.get_available_queries(language)
