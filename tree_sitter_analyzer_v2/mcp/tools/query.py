"""
MCP Tool for querying code elements.

This module provides the query_code tool that queries code files for specific
elements (classes, functions, methods, imports) with optional filtering.
"""

import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.detector import LanguageDetector
from tree_sitter_analyzer_v2.formatters import get_default_registry
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class QueryTool(BaseTool):
    """
    MCP tool for querying code elements.

    Queries code files for specific elements (classes, functions, methods, imports)
    and supports filtering by name, visibility, and other attributes.
    """

    def __init__(self):
        """Initialize the query tool."""
        self._detector = LanguageDetector()
        self._formatter_registry = get_default_registry()

        # Initialize language-specific parsers
        self._parsers = self._create_parsers()

    @staticmethod
    def _create_parsers() -> dict:
        """Create language-specific parsers."""
        from tree_sitter_analyzer_v2.languages import PythonParser, JavaParser, TypeScriptParser

        return {
            "python": PythonParser(),
            "java": JavaParser(),
            "typescript": TypeScriptParser(),
            "javascript": TypeScriptParser(),
        }

    def get_name(self) -> str:
        """Get tool name."""
        return "query_code"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Query code elements (classes, functions, methods, imports) from a file. "
            "Supports filtering by name (with regex), visibility, and other attributes. "
            "Returns matching elements with their details (name, location, etc.)."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the code file to query"},
                "element_type": {
                    "type": "string",
                    "description": (
                        "Type of elements to query: 'classes', 'functions', 'methods', "
                        "'imports', or omit to return all elements"
                    ),
                    "enum": ["classes", "functions", "methods", "imports"],
                },
                "filters": {
                    "type": "object",
                    "description": "Filters to apply to query results",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Filter by name (exact match or regex if use_regex=true)",
                        },
                        "use_regex": {
                            "type": "boolean",
                            "description": "Use regex pattern matching for name filter",
                        },
                        "visibility": {
                            "type": "string",
                            "description": "Filter by visibility (public, private, protected)",
                        },
                        "class_name": {
                            "type": "string",
                            "description": "Filter methods by their class name",
                        },
                    },
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format: 'toon' (default) or 'markdown'",
                    "enum": ["toon", "markdown"],
                    "default": "toon",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute query_code tool.

        Args:
            arguments: Dictionary with:
                - file_path: Path to file to query
                - element_type: Optional element type filter
                - filters: Optional filters (name, visibility, etc.)
                - output_format: Optional output format (toon, markdown)

        Returns:
            Dictionary with:
                - success: True if successful, False otherwise
                - language: Detected language
                - elements: List of matching elements (or formatted string)
                - count: Number of elements found
                - output_format: Output format used
                - error: Error message (if success=False)
        """
        try:
            # Extract arguments
            file_path = arguments["file_path"]
            element_type = arguments.get("element_type")
            filters = arguments.get("filters", {})
            output_format = arguments.get("output_format", "toon").lower()

            # Validate file exists
            if not Path(file_path).exists():
                return {"success": False, "error": f"File not found: {file_path}"}

            # Read file content
            content = Path(file_path).read_text(encoding="utf-8")

            # Detect language
            detection_result = self._detector.detect_from_content(
                filename=file_path, content=content
            )
            language = detection_result["language"].lower()

            if language not in self._parsers:
                return {"success": False, "error": f"Unsupported language: {language}"}

            # Parse file
            parser = self._parsers[language]
            parse_result = parser.parse(content, file_path)

            # Extract elements based on type
            elements = self._extract_elements(parse_result, element_type)

            # Apply filters
            filtered_elements = self._apply_filters(elements, filters)

            # Format output
            # Special case: "raw" format for internal testing (not in public schema)
            if output_format == "raw":
                return {
                    "success": True,
                    "language": language,
                    "elements": filtered_elements,
                    "count": len(filtered_elements),
                    "output_format": "raw",
                }

            # Format using TOON or Markdown (default is TOON)
            formatter = self._formatter_registry.get(output_format)
            formatted_data = formatter.format(filtered_elements)

            return {
                "success": True,
                "language": language,
                "elements": formatted_data,
                "count": len(filtered_elements),
                "output_format": output_format,
            }

        except Exception as e:
            return {"success": False, "error": f"Query failed: {str(e)}"}

    def _extract_elements(
        self, parse_result: dict[str, Any], element_type: str | None
    ) -> list[dict[str, Any]]:
        """
        Extract elements from parse result.

        Args:
            parse_result: Parse result from language parser
            element_type: Type of elements to extract (or None for all)

        Returns:
            List of element dictionaries
        """
        elements = []

        if element_type == "methods" or element_type is None:
            # Extract methods from classes
            methods = self._extract_methods_from_classes(parse_result.get("classes", []))
            if element_type == "methods":
                # Only return methods
                return self._normalize_elements(methods, "methods")
            else:
                # Include methods in all elements
                elements.extend(self._normalize_elements(methods, "methods"))

        # Map element types to parse result keys
        type_mapping = {"classes": "classes", "functions": "functions", "imports": "imports"}

        if element_type and element_type != "methods":
            # Extract specific type
            key = type_mapping.get(element_type)
            if key and key in parse_result:
                raw_elements = parse_result[key]
                if isinstance(raw_elements, list):
                    elements.extend(self._normalize_elements(raw_elements, element_type))
        elif element_type is None:
            # Extract all types (except methods, already added)
            for elem_type, key in type_mapping.items():
                if key in parse_result:
                    raw_elements = parse_result[key]
                    if isinstance(raw_elements, list):
                        elements.extend(self._normalize_elements(raw_elements, elem_type))

        return elements

    def _extract_methods_from_classes(self, classes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Extract methods from class definitions.

        Args:
            classes: List of class dictionaries

        Returns:
            List of method dictionaries
        """
        methods = []
        for cls in classes:
            if isinstance(cls, dict) and "methods" in cls:
                class_name = cls.get("name", "Unknown")
                for method in cls["methods"]:
                    if isinstance(method, dict):
                        # Add class_name to method for filtering
                        method_copy = method.copy()
                        method_copy["class_name"] = class_name
                        methods.append(method_copy)
        return methods

    def _normalize_elements(
        self, raw_elements: list[Any], element_type: str
    ) -> list[dict[str, Any]]:
        """
        Normalize elements to consistent format.

        Args:
            raw_elements: Raw elements from parser
            element_type: Type of elements

        Returns:
            List of normalized element dictionaries
        """
        normalized = []

        for elem in raw_elements:
            if isinstance(elem, dict):
                # Add element_type field
                normalized_elem = elem.copy()
                normalized_elem["element_type"] = element_type
                normalized.append(normalized_elem)
            elif isinstance(elem, str):
                # Simple string (e.g., import)
                normalized.append({"name": elem, "element_type": element_type})

        return normalized

    def _apply_filters(
        self, elements: list[dict[str, Any]], filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Apply filters to elements.

        Args:
            elements: List of elements
            filters: Filter criteria

        Returns:
            Filtered list of elements
        """
        if not filters:
            return elements

        filtered = elements

        # Filter by name
        if "name" in filters:
            name_filter = filters["name"]
            use_regex = filters.get("use_regex", False)

            if use_regex:
                # Regex pattern matching
                pattern = re.compile(name_filter)
                filtered = [
                    elem for elem in filtered if "name" in elem and pattern.search(elem["name"])
                ]
            else:
                # Exact match
                filtered = [elem for elem in filtered if elem.get("name") == name_filter]

        # Filter by visibility (for Java/TypeScript)
        if "visibility" in filters:
            visibility_filter = filters["visibility"]
            filtered = [
                elem
                for elem in filtered
                if elem.get("visibility") == visibility_filter
                or visibility_filter in elem.get("modifiers", [])
            ]

        # Filter by class_name (for methods)
        if "class_name" in filters:
            class_name_filter = filters["class_name"]
            filtered = [
                elem
                for elem in filtered
                if elem.get("class_name") == class_name_filter
                or elem.get("class") == class_name_filter
            ]

        return filtered
