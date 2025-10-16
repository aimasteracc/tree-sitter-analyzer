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
from .base_tool import BaseMCPTool

logger = logging.getLogger(__name__)


class QueryTool(BaseMCPTool):
    """MCP query tool providing tree-sitter query functionality"""

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize query tool"""
        super().__init__(project_root)
        self.query_service = QueryService(project_root)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

    def set_project_path(self, project_path: str) -> None:
        """
        Update the project path for all components.

        Args:
            project_path: New project root directory
        """
        super().set_project_path(project_path)
        self.query_service = QueryService(project_path)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)
        logger.info(f"QueryTool project path updated to: {project_path}")

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get MCP tool definition

        Returns:
            Tool definition dictionary
        """
        return {
            "name": "query_code",
            "description": "Execute tree-sitter queries on code files to extract specific code elements with filtering, multiple output formats, and optional file saving with token optimization",
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
                    "output_file": {
                        "type": "string",
                        "description": "Optional filename to save output to file (extension auto-detected based on content)",
                    },
                    "suppress_output": {
                        "type": "boolean",
                        "description": "When true and output_file is specified, suppress detailed output in response to save tokens",
                        "default": False,
                    },
                },
                "required": ["file_path"],
                "anyOf": [
                    {"required": ["query_key"]},
                    {"required": ["query_string"]},
                ],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute query tool

        Args:
            arguments: Tool arguments

        Returns:
            Query results
        """
        try:
            # Validate input parameters - check for empty arguments first
            if not arguments:
                from ..utils.error_handler import AnalysisError

                raise AnalysisError("file_path is required", operation="query_code")

            file_path = arguments.get("file_path")
            if not file_path:
                from ..utils.error_handler import AnalysisError

                raise AnalysisError("file_path is required", operation="query_code")

            # Check that either query_key or query_string is provided early
            query_key = arguments.get("query_key")
            query_string = arguments.get("query_string")

            if not query_key and not query_string:
                from ..utils.error_handler import AnalysisError

                raise AnalysisError(
                    "Either query_key or query_string must be provided",
                    operation="query_code",
                )

            # Security validation BEFORE path resolution to catch symlinks
            is_valid, error_msg = self.security_validator.validate_file_path(file_path)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"Invalid or unsafe file path: {error_msg or file_path}",
                }

            # Resolve file path to absolute path
            resolved_file_path = self.path_resolver.resolve(file_path)
            logger.info(
                f"Querying file: {file_path} (resolved to: {resolved_file_path})"
            )

            # Additional security validation on resolved path
            is_valid, error_msg = self.security_validator.validate_file_path(
                resolved_file_path
            )
            if not is_valid:
                return {
                    "success": False,
                    "error": f"Invalid or unsafe resolved path: {error_msg or resolved_file_path}",
                }

            # Get query parameters (already validated above)
            filter_expression = arguments.get("filter")
            output_format = arguments.get("output_format", "json")
            output_file = arguments.get("output_file")
            suppress_output = arguments.get("suppress_output", False)

            if query_key and query_string:
                return {
                    "success": False,
                    "error": "Cannot provide both query_key and query_string",
                }

            # Detect language
            language = arguments.get("language")
            if not language:
                language = detect_language_from_file(resolved_file_path)
                if not language:
                    return {
                        "success": False,
                        "error": f"Could not detect language for file: {file_path}",
                    }

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
                formatted_result = self._format_summary(
                    results, query_key or "custom", language
                )
            else:
                formatted_result = {
                    "success": True,
                    "results": results,
                    "count": len(results),
                    "file_path": file_path,
                    "language": language,
                    "query": query_key or query_string,
                }

            # Handle file output if requested
            if output_file:
                try:
                    import json

                    # Generate base name from original file path if not provided
                    if not output_file or output_file.strip() == "":
                        base_name = (
                            f"{Path(file_path).stem}_query_{query_key or 'custom'}"
                        )
                    else:
                        base_name = output_file

                    # Convert result to JSON string for file output
                    json_content = json.dumps(
                        formatted_result, indent=2, ensure_ascii=False
                    )

                    # Save to file with automatic extension detection
                    saved_file_path = self.file_output_manager.save_to_file(
                        content=json_content, base_name=base_name
                    )

                    # Add file output info to result
                    formatted_result["output_file_path"] = saved_file_path
                    formatted_result["file_saved"] = True

                    logger.info(f"Query output saved to: {saved_file_path}")

                except Exception as e:
                    logger.error(f"Failed to save output to file: {e}")
                    formatted_result["file_save_error"] = str(e)
                    formatted_result["file_saved"] = False

            # Apply suppress_output logic
            if suppress_output and output_file:
                # Create minimal result when output is suppressed
                minimal_result = {
                    "success": formatted_result.get("success", True),
                    "count": formatted_result.get("count", len(results)),
                    "file_path": file_path,
                    "language": language,
                    "query": query_key or query_string,
                }

                # Include file output info if present
                if "output_file_path" in formatted_result:
                    minimal_result["output_file_path"] = formatted_result[
                        "output_file_path"
                    ]
                    minimal_result["file_saved"] = formatted_result["file_saved"]
                if "file_save_error" in formatted_result:
                    minimal_result["file_save_error"] = formatted_result[
                        "file_save_error"
                    ]
                    minimal_result["file_saved"] = formatted_result["file_saved"]

                return minimal_result
            else:
                return formatted_result

        except Exception as e:
            from ..utils.error_handler import AnalysisError

            # Re-raise AnalysisError to maintain proper error handling
            if isinstance(e, AnalysisError):
                raise

            logger.error(f"Query execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_path": arguments.get("file_path", "unknown"),
                "language": arguments.get("language", "unknown"),
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
        by_capture: dict[str, list[dict[str, Any]]] = {}
        for result in results:
            capture_name = result["capture_name"]
            if capture_name not in by_capture:
                by_capture[capture_name] = []
            by_capture[capture_name].append(result)

        # Create summary
        summary: dict[str, Any] = {
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
                # Markdown headers
                r"^#{1,6}\s+(.+)$",  # Markdown headers (# Title, ## Subtitle, etc.)
                # Programming language patterns
                r"(?:public|private|protected)?\s*(?:static)?\s*(?:class|interface)\s+(\w+)",  # class/interface
                r"(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(",  # method
                r"(\w+)\s*\(",  # simple function call
            ]

            for pattern in patterns:
                match = re.search(pattern, first_line)
                if match:
                    return match.group(1).strip()

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

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        # Check required fields
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        # Validate file_path
        file_path = arguments["file_path"]
        if not isinstance(file_path, str):
            raise ValueError("file_path must be a string")
        if not file_path.strip():
            raise ValueError("file_path cannot be empty")

        # Check that either query_key or query_string is provided
        query_key = arguments.get("query_key")
        query_string = arguments.get("query_string")

        if not query_key and not query_string:
            raise ValueError("Either query_key or query_string must be provided")

        # Validate query_key if provided
        if query_key and not isinstance(query_key, str):
            raise ValueError("query_key must be a string")

        # Validate query_string if provided
        if query_string and not isinstance(query_string, str):
            raise ValueError("query_string must be a string")

        # Validate optional fields
        if "language" in arguments:
            language = arguments["language"]
            if not isinstance(language, str):
                raise ValueError("language must be a string")

        if "filter" in arguments:
            filter_expr = arguments["filter"]
            if not isinstance(filter_expr, str):
                raise ValueError("filter must be a string")

        if "output_format" in arguments:
            output_format = arguments["output_format"]
            if not isinstance(output_format, str):
                raise ValueError("output_format must be a string")
            if output_format not in ["json", "summary"]:
                raise ValueError("output_format must be one of: json, summary")

        # Validate output_file if provided
        if "output_file" in arguments:
            output_file = arguments["output_file"]
            if not isinstance(output_file, str):
                raise ValueError("output_file must be a string")
            if not output_file.strip():
                raise ValueError("output_file cannot be empty")

        # Validate suppress_output if provided
        if "suppress_output" in arguments:
            suppress_output = arguments["suppress_output"]
            if not isinstance(suppress_output, bool):
                raise ValueError("suppress_output must be a boolean")

        return True
