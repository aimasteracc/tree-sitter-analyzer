#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Get Code Positions MCP Tool

This tool provides precise position information for code elements
like classes, methods, fields, and imports through the MCP protocol.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.analysis_engine import get_analysis_engine, AnalysisRequest
from ...language_detector import detect_language_from_file
from ...utils import log_performance, setup_logger

# Set up logging
logger = setup_logger(__name__)


class GetPositionsTool:
    """
    MCP Tool for getting precise position information of code elements.

    This tool integrates with existing analyzer components to provide
    detailed location data for various code elements.
    """

    def __init__(self) -> None:
        """Initialize the get positions tool."""
        self.analysis_engine = get_analysis_engine()
        logger.info("GetPositionsTool initialized")

    def get_tool_schema(self) -> Dict[str, Any]:
        """
        Get the MCP tool schema for get_code_positions.

        Returns:
            Dictionary containing the tool schema
        """
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the code file to analyze",
                },
                "language": {
                    "type": "string",
                    "description": "Programming language (optional, auto-detected if not specified)",
                },
                "element_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "classes",
                            "methods",
                            "fields",
                            "imports",
                            "annotations",
                        ],
                    },
                    "description": "Types of code elements to get positions for",
                    "default": ["classes", "methods"],
                },
                "include_details": {
                    "type": "boolean",
                    "description": "Include detailed information like signatures and visibility",
                    "default": False,
                },
                "format": {
                    "type": "string",
                    "description": "Output format for the position data",
                    "enum": ["json", "text"],
                    "default": "json",
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the get_code_positions tool.

        Args:
            arguments: Tool arguments containing file_path and analysis options

        Returns:
            Dictionary containing position information for requested elements

        Raises:
            ValueError: If required arguments are missing or invalid
            FileNotFoundError: If the specified file doesn't exist
        """
        # Validate required arguments
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")
        element_types = arguments.get("element_types", ["classes", "methods"])
        include_details = arguments.get("include_details", False)
        output_format = arguments.get("format", "json")

        # Validate file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Detect language if not specified
        if not language:
            language = detect_language_from_file(file_path)
            if language == "unknown":
                raise ValueError(f"Could not detect language for file: {file_path}")

        logger.info(f"Getting positions for {file_path} (language: {language})")

        try:
            # Use AdvancedAnalyzer for comprehensive analysis
            # Use performance monitoring with proper context manager
            from ...mcp.utils import get_performance_monitor

            with get_performance_monitor().measure_operation("get_code_positions"):
                # Use unified analysis engine instead of deprecated advanced_analyzer
                request = AnalysisRequest(
                    file_path=file_path,
                    language=language,
                    include_complexity=True,
                    include_details=True
                )
                analysis_result = await self.analysis_engine.analyze(request)

                if analysis_result is None:
                    raise RuntimeError(f"Failed to analyze file: {file_path}")

                # Extract position information for requested element types
                positions = {}

                for element_type in element_types:
                    positions[element_type] = self._get_element_positions(
                        analysis_result, element_type, include_details
                    )

                # Build result structure
                result = {
                    "file_path": file_path,
                    "language": language,
                    "element_types": element_types,
                    "include_details": include_details,
                    "format": output_format,
                    "total_elements": sum(
                        len(pos_list) for pos_list in positions.values()
                    ),
                }

                # Format output based on requested format
                if output_format == "text":
                    # Text format: human-readable representation
                    result["content"] = self._format_positions_as_text(
                        positions, include_details
                    )
                else:
                    # JSON format: structured position data
                    result["positions"] = positions

                logger.info(
                    f"Successfully extracted positions for {result['total_elements']} elements from {file_path}"
                )
                return result

        except Exception as e:
            logger.error(f"Error getting positions from {file_path}: {e}")
            raise

    def _get_element_positions(
        self, analysis_result: Any, element_type: str, include_details: bool
    ) -> List[Dict[str, Any]]:
        """
        Extract position information for a specific element type.

        Args:
            analysis_result: Result from AdvancedAnalyzer
            element_type: Type of elements to extract
            include_details: Whether to include detailed information

        Returns:
            List of position dictionaries for the element type
        """
        positions = []

        if element_type == "classes":
            classes = [e for e in analysis_result.elements if e.__class__.__name__ == 'Class']
            for cls in classes:
                position = {
                    "name": cls.name,
                    "start_line": cls.start_line,
                    "end_line": cls.end_line,
                    "start_column": 0,  # Tree-sitter provides line-based positions
                    "end_column": 0,
                }

                if include_details:
                    position.update(
                        {
                            "type": cls.class_type,
                            "visibility": cls.visibility,
                            "extends": cls.extends_class,
                            "implements": cls.implements_interfaces,
                            "annotations": [ann.name for ann in cls.annotations],
                        }
                    )

                positions.append(position)

        elif element_type == "methods":
            methods = [e for e in analysis_result.elements if e.__class__.__name__ == 'Function']
            for method in methods:
                position = {
                    "name": method.name,
                    "start_line": method.start_line,
                    "end_line": method.end_line,
                    "start_column": 0,
                    "end_column": 0,
                }

                if include_details:
                    position.update(
                        {
                            "signature": f"{method.name}({', '.join(method.parameters)})",
                            "return_type": method.return_type,
                            "visibility": method.visibility,
                            "is_static": method.is_static,
                            "is_constructor": method.is_constructor,
                            "complexity": method.complexity_score,
                            "annotations": [ann.name for ann in method.annotations],
                        }
                    )

                positions.append(position)

        elif element_type == "fields":
            fields = [e for e in analysis_result.elements if e.__class__.__name__ == 'Variable']
            for field in fields:
                position = {
                    "name": field.name,
                    "start_line": field.start_line,
                    "end_line": field.end_line,
                    "start_column": 0,
                    "end_column": 0,
                }

                if include_details:
                    position.update(
                        {
                            "type": field.field_type,
                            "visibility": field.visibility,
                            "is_static": field.is_static,
                            "is_final": field.is_final,
                            "annotations": [ann.name for ann in field.annotations],
                        }
                    )

                positions.append(position)

        elif element_type == "imports":
            imports = [e for e in analysis_result.elements if e.__class__.__name__ == 'Import']
            for imp in imports:
                position = {
                    "name": imp.imported_name,
                    "start_line": imp.line_number,
                    "end_line": imp.line_number,
                    "start_column": 0,
                    "end_column": 0,
                }

                if include_details:
                    position.update(
                        {
                            "statement": imp.import_statement,
                            "is_static": imp.is_static,
                            "is_wildcard": imp.is_wildcard,
                        }
                    )

                positions.append(position)

        elif element_type == "annotations":
            for ann in analysis_result.annotations:
                position = {
                    "name": ann.name,
                    "start_line": ann.line_number,
                    "end_line": ann.line_number,
                    "start_column": 0,
                    "end_column": 0,
                }

                if include_details:
                    position.update(
                        {
                            "parameters": ann.parameters,
                        }
                    )

                positions.append(position)

        return positions

    def _format_positions_as_text(
        self, positions: Dict[str, List[Dict[str, Any]]], include_details: bool
    ) -> str:
        """
        Format position data as human-readable text.

        Args:
            positions: Position data for all element types
            include_details: Whether to include detailed information

        Returns:
            Formatted text representation
        """
        lines = []

        for element_type, elements in positions.items():
            if not elements:
                continue

            lines.append(f"\n{element_type.upper()}:")
            lines.append("=" * (len(element_type) + 1))

            for element in elements:
                name = element["name"]
                start_line = element["start_line"]
                end_line = element["end_line"]

                if start_line == end_line:
                    location = f"line {start_line}"
                else:
                    location = f"lines {start_line}-{end_line}"

                lines.append(f"  {name} ({location})")

                if include_details:
                    for key, value in element.items():
                        if key not in [
                            "name",
                            "start_line",
                            "end_line",
                            "start_column",
                            "end_column",
                        ]:
                            if value:  # Only show non-empty values
                                lines.append(f"    {key}: {value}")

        return "\n".join(lines)

    def validate_arguments(self, arguments: Dict[str, Any]) -> bool:
        """
        Validate tool arguments against the schema.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        schema = self.get_tool_schema()
        required_fields = schema.get("required", [])

        # Check required fields
        for field in required_fields:
            if field not in arguments:
                raise ValueError(f"Required field '{field}' is missing")

        # Validate file_path
        if "file_path" in arguments:
            file_path = arguments["file_path"]
            if not isinstance(file_path, str):
                raise ValueError("file_path must be a string")
            if not file_path.strip():
                raise ValueError("file_path cannot be empty")

        # Validate element_types
        if "element_types" in arguments:
            element_types = arguments["element_types"]
            if not isinstance(element_types, list):
                raise ValueError("element_types must be a list")
            if not element_types:
                raise ValueError("element_types cannot be empty")

            valid_types = ["classes", "methods", "fields", "imports", "annotations"]
            for element_type in element_types:
                if element_type not in valid_types:
                    raise ValueError(
                        f"Invalid element_type: {element_type}. Must be one of {valid_types}"
                    )

        # Validate optional fields
        if "language" in arguments:
            language = arguments["language"]
            if not isinstance(language, str):
                raise ValueError("language must be a string")

        if "include_details" in arguments:
            include_details = arguments["include_details"]
            if not isinstance(include_details, bool):
                raise ValueError("include_details must be a boolean")

        if "format" in arguments:
            format_value = arguments["format"]
            if not isinstance(format_value, str):
                raise ValueError("format must be a string")
            if format_value not in ["json", "text"]:
                raise ValueError("format must be 'json' or 'text'")

        return True

    def get_tool_definition(self) -> Any:
        """
        Get the MCP tool definition for get_code_positions.

        Returns:
            Tool definition object compatible with MCP server
        """
        try:
            from mcp.types import Tool

            return Tool(
                name="get_code_positions",
                description="Get precise position information for code elements like classes, methods, fields, and imports",
                inputSchema=self.get_tool_schema(),
            )
        except ImportError:
            # Fallback for when MCP is not available
            return {
                "name": "get_code_positions",
                "description": "Get precise position information for code elements like classes, methods, fields, and imports",
                "inputSchema": self.get_tool_schema(),
            }


# Tool instance for easy access
get_positions_tool = GetPositionsTool()
