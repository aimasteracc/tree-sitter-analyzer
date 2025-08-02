#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Table Format MCP Tool

This tool provides table-formatted output for code analysis results through the MCP protocol,
equivalent to the CLI --table=full option functionality.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ...core.analysis_engine import get_analysis_engine, AnalysisRequest
from ...language_detector import detect_language_from_file
from ...table_formatter import TableFormatter
from ...utils import setup_logger
from ..utils import get_performance_monitor

# Set up logging
logger = setup_logger(__name__)


class TableFormatTool:
    """
    MCP Tool for formatting code analysis results as tables.

    This tool integrates with existing table_formatter and analyzer components
    to provide table-formatted output through the MCP protocol, equivalent to
    the CLI --table=full option.
    """

    def __init__(self) -> None:
        """Initialize the table format tool."""
        self.logger = logger
        self.analysis_engine = get_analysis_engine()
        logger.info("TableFormatTool initialized")

    def get_tool_schema(self) -> Dict[str, Any]:
        """
        Get the MCP tool schema for analyze_code_structure.

        Returns:
            Dictionary containing the tool schema
        """
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the code file to analyze and format",
                },
                "format_type": {
                    "type": "string",
                    "description": "Table format type",
                    "enum": ["full", "compact", "csv"],
                    "default": "full",
                },
                "language": {
                    "type": "string",
                    "description": "Programming language (optional, auto-detected if not specified)",
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: Dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Dictionary of arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        # Check required fields
        if "file_path" not in arguments:
            raise ValueError("Required field 'file_path' is missing")

        # Validate file_path
        file_path = arguments["file_path"]
        if not isinstance(file_path, str):
            raise ValueError("file_path must be a string")
        if not file_path.strip():
            raise ValueError("file_path cannot be empty")

        # Validate format_type if provided
        if "format_type" in arguments:
            format_type = arguments["format_type"]
            if not isinstance(format_type, str):
                raise ValueError("format_type must be a string")
            if format_type not in ["full", "compact", "csv"]:
                raise ValueError("format_type must be one of: full, compact, csv")

        # Validate language if provided
        if "language" in arguments:
            language = arguments["language"]
            if not isinstance(language, str):
                raise ValueError("language must be a string")

        return True

    def _convert_parameters(self, parameters):
        """Convert parameters to expected format"""
        result = []
        for param in parameters:
            if isinstance(param, dict):
                result.append({
                    "name": param.get('name', 'param'),
                    "type": param.get('type', 'Object')
                })
            else:
                result.append({
                    "name": getattr(param, 'name', 'param'),
                    "type": getattr(param, 'param_type', 'Object')
                })
        return result

    def _get_method_modifiers(self, method) -> list:
        """Extract method modifiers as a list"""
        modifiers = []
        if getattr(method, 'is_static', False):
            modifiers.append('static')
        if getattr(method, 'is_final', False):
            modifiers.append('final')
        if getattr(method, 'is_abstract', False):
            modifiers.append('abstract')
        return modifiers

    def _get_method_parameters(self, method):
        """Get method parameters in the correct format for TableFormatter"""
        parameters = getattr(method, 'parameters', [])
        
        # If parameters is already a list of strings (like "int value"), convert to dict format
        if parameters and isinstance(parameters[0], str):
            result = []
            for param_str in parameters:
                parts = param_str.strip().split()
                if len(parts) >= 2:
                    param_type = ' '.join(parts[:-1])  # Everything except last part is type
                    param_name = parts[-1]  # Last part is name
                    result.append({
                        "name": param_name,
                        "type": param_type
                    })
                elif len(parts) == 1:
                    # Only type, no name
                    result.append({
                        "name": "param",
                        "type": parts[0]
                    })
            return result
        
        # Fallback to original conversion method
        return self._convert_parameters(parameters)

    def _get_field_modifiers(self, field) -> list:
        """Extract field modifiers as a list"""
        modifiers = []
        
        # Add visibility to modifiers for CLI compatibility
        visibility = getattr(field, 'visibility', 'private')
        if visibility and visibility != 'package':
            modifiers.append(visibility)
        
        if getattr(field, 'is_static', False):
            modifiers.append('static')
        if getattr(field, 'is_final', False):
            modifiers.append('final')
        return modifiers

    def _convert_analysis_result_to_dict(self, result) -> Dict[str, Any]:
        """Convert AnalysisResult to dictionary format expected by TableFormatter"""
        # Extract elements by type
        classes = [e for e in result.elements if e.__class__.__name__ == 'Class']
        methods = [e for e in result.elements if e.__class__.__name__ == 'Function']
        fields = [e for e in result.elements if e.__class__.__name__ == 'Variable']
        imports = [e for e in result.elements if e.__class__.__name__ == 'Import']
        packages = [e for e in result.elements if e.__class__.__name__ == 'Package']
        
        # Convert package to expected format
        package_info = None
        if packages:
            package_info = {"name": packages[0].name}
        
        return {
            "file_path": result.file_path,
            "language": result.language,
            "package": package_info,
            "classes": [
                {
                    "name": getattr(cls, 'name', 'unknown'),
                    "line_range": {
                        "start": getattr(cls, 'start_line', 0),
                        "end": getattr(cls, 'end_line', 0)
                    },
                    "type": getattr(cls, 'class_type', 'class'),
                    "visibility": "public",  # Force all classes to public for CLI compatibility
                    "extends": getattr(cls, 'extends_class', None),
                    "implements": getattr(cls, 'implements_interfaces', []),
                    "annotations": []
                } for cls in classes
            ],
            "methods": [
                {
                    "name": getattr(method, 'name', 'unknown'),
                    "line_range": {
                        "start": getattr(method, 'start_line', 0),
                        "end": getattr(method, 'end_line', 0)
                    },
                    "return_type": getattr(method, 'return_type', 'void'),
                    "parameters": self._get_method_parameters(method),
                    "visibility": getattr(method, 'visibility', 'public'),
                    "is_static": getattr(method, 'is_static', False),
                    "is_constructor": getattr(method, 'is_constructor', False),
                    "complexity_score": getattr(method, 'complexity_score', 0),
                    "modifiers": self._get_method_modifiers(method),
                    "annotations": []
                } for method in methods
            ],
            "fields": [
                {
                    "name": getattr(field, 'name', 'unknown'),
                    "type": getattr(field, 'field_type', 'Object'),
                    "line_range": {
                        "start": getattr(field, 'start_line', 0),
                        "end": getattr(field, 'end_line', 0)
                    },
                    "visibility": getattr(field, 'visibility', 'private'),
                    "modifiers": self._get_field_modifiers(field),
                    "annotations": []
                } for field in fields
            ],
            "imports": [
                {
                    "name": getattr(imp, 'name', 'unknown'),
                    "statement": getattr(imp, 'name', ''),  # Use name for CLI compatibility
                    "is_static": getattr(imp, 'is_static', False),
                    "is_wildcard": getattr(imp, 'is_wildcard', False)
                } for imp in imports
            ],
            "statistics": {
                "class_count": len(classes),
                "method_count": len(methods),
                "field_count": len(fields),
                "import_count": len(imports),
                "total_lines": result.line_count
            }
        }

    async def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute code structure analysis tool."""
        try:
            # Validate arguments first
            if "file_path" not in args:
                raise ValueError("file_path is required")

            file_path = args["file_path"]
            format_type = args.get("format_type", "full")
            language = args.get("language")

            # Validate file exists
            if not Path(file_path).exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            # Detect language if not provided
            if not language:
                language = detect_language_from_file(file_path)

            # Use performance monitoring
            monitor = get_performance_monitor()
            with monitor.measure_operation("code_structure_analysis"):
                # Analyze structure using the unified analysis engine
                request = AnalysisRequest(
                    file_path=file_path,
                    language=language,
                    include_complexity=True,
                    include_details=True
                )
                structure_result = await self.analysis_engine.analyze(request)

                if structure_result is None:
                    raise RuntimeError(
                        f"Failed to analyze structure for file: {file_path}"
                    )

                # Create table formatter
                formatter = TableFormatter(format_type)

                # Convert AnalysisResult to dict format for TableFormatter
                structure_dict = self._convert_analysis_result_to_dict(structure_result)
                
                # Format table
                table_output = formatter.format_structure(structure_dict)

                # Ensure output format matches CLI exactly
                # Fix line ending differences: normalize to Unix-style LF (\n)
                table_output = table_output.replace("\r\n", "\n").replace("\r", "\n")

                # CLI uses sys.stdout.buffer.write() which doesn't add trailing newline
                # Ensure MCP output matches this behavior exactly
                # Remove any trailing whitespace and newlines to match CLI output
                table_output = table_output.rstrip()

                # Extract metadata from structure dict
                metadata = {}
                if "statistics" in structure_dict:
                    stats = structure_dict["statistics"]
                    metadata = {
                        "classes_count": stats.get("class_count", 0),
                        "methods_count": stats.get("method_count", 0),
                        "fields_count": stats.get("field_count", 0),
                        "total_lines": stats.get("total_lines", 0),
                    }

                return {
                    "table_output": table_output,
                    "format_type": format_type,
                    "file_path": file_path,
                    "language": language,
                    "metadata": metadata,
                }

        except Exception as e:
            self.logger.error(f"Error in code structure analysis tool: {e}")
            raise

    def get_tool_definition(self) -> Any:
        """
        Get the MCP tool definition for analyze_code_structure.

        Returns:
            Tool definition object compatible with MCP server
        """
        try:
            from mcp.types import Tool

            return Tool(
                name="analyze_code_structure",
                description="Analyze code structure and generate detailed overview tables (classes, methods, fields) for large files",
                inputSchema=self.get_tool_schema(),
            )
        except ImportError:
            # Fallback for when MCP is not available
            return {
                "name": "analyze_code_structure",
                "description": "Analyze code structure and generate detailed overview tables (classes, methods, fields) for large files",
                "inputSchema": self.get_tool_schema(),
            }


# Tool instance for easy access
table_format_tool = TableFormatTool()
