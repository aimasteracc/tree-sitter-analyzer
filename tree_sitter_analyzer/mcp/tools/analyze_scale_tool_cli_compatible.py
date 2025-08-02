#!/usr/bin/env python3
"""
CLI-Compatible Analyze Code Scale MCP Tool

This tool provides code scale analysis with output format
that matches the CLI --advanced --statistics output exactly.
"""

import time
from pathlib import Path
from typing import Any, cast

from ...core.analysis_engine import get_analysis_engine
from ...language_detector import detect_language_from_file
from ...utils import setup_logger

# Set up logging
logger = setup_logger(__name__)


class AnalyzeScaleToolCLICompatible:
    """
    MCP Tool for analyzing code scale with CLI-compatible output format.

    This tool matches the exact output format of CLI --advanced --statistics.
    """

    def __init__(self) -> None:
        """Initialize the CLI-compatible analyze scale tool."""
        self.analysis_engine = get_analysis_engine()
        logger.info("AnalyzeScaleToolCLICompatible initialized")

    def get_tool_schema(self) -> dict[str, Any]:
        """
        Get the MCP tool schema for analyze_code_scale.

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
                "include_complexity": {
                    "type": "boolean",
                    "description": "Include complexity metrics in the analysis",
                    "default": True,
                },
                "include_details": {
                    "type": "boolean",
                    "description": "Include detailed element information",
                    "default": False,
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the analyze_code_scale tool with CLI-compatible output.

        Args:
            arguments: Tool arguments containing file_path and optional parameters

        Returns:
            Dictionary containing analysis results in CLI-compatible format

        Raises:
            ValueError: If required arguments are missing or invalid
            FileNotFoundError: If the specified file doesn't exist
        """
        # Validate required arguments
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")
        # include_complexity = arguments.get("include_complexity", True)  # Not used currently
        # include_details = arguments.get("include_details", False)  # Not used currently

        # Validate file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Detect language if not specified
        if not language:
            language = detect_language_from_file(file_path)
            if language == "unknown":
                raise ValueError(f"Could not detect language for file: {file_path}")

        logger.info(f"Analyzing code scale for {file_path} (language: {language})")

        try:
            start_time = time.time()

            # Use AdvancedAnalyzer for comprehensive analysis
            analysis_result = await self.analysis_engine.analyze_file(file_path)

            # Handle potential None result (for testing purposes with mocked engine)
            # This can only happen in tests where the engine is mocked to return None
            # Use cast to tell MyPy this is possible in testing scenarios
            if cast(Any, analysis_result) is None:
                return {
                    "file_path": file_path,
                    "success": False,
                    "package_name": None,
                    "element_counts": {
                        "imports": 0,
                        "classes": 0,
                        "methods": 0,
                        "fields": 0,
                        "annotations": 0,
                    },
                    "analysis_time_ms": round((time.time() - start_time) * 1000, 2),
                    "error_message": f"Failed to analyze file: {file_path}",
                }

            # Calculate analysis time
            analysis_time_ms = round((time.time() - start_time) * 1000, 2)

            # Build CLI-compatible result structure (exact match with CLI --advanced --statistics)
            result = {
                "file_path": file_path,
                "success": True,
                "package_name": (
                    analysis_result.package.name
                    if analysis_result.package
                    and hasattr(analysis_result.package, "name")
                    else None
                ),
                "element_counts": {
                    "imports": len(analysis_result.imports),
                    "classes": len(analysis_result.classes),
                    "methods": len(analysis_result.methods),
                    "fields": len(analysis_result.fields),
                    "annotations": len(getattr(analysis_result, "annotations", [])),
                },
                "analysis_time_ms": analysis_time_ms,
                "error_message": None,
            }

            logger.info(
                f"Successfully analyzed {file_path}: {len(analysis_result.classes)} classes, "
                f"{len(analysis_result.methods)} methods, {analysis_time_ms}ms"
            )

            return result

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            # Return CLI-compatible error format
            return {
                "file_path": file_path,
                "success": False,
                "package_name": None,
                "element_counts": {
                    "imports": 0,
                    "classes": 0,
                    "methods": 0,
                    "fields": 0,
                    "annotations": 0,
                },
                "analysis_time_ms": 0.0,
                "error_message": str(e),
            }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
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

        # Validate optional fields
        if "language" in arguments:
            language = arguments["language"]
            if not isinstance(language, str):
                raise ValueError("language must be a string")

        if "include_complexity" in arguments:
            include_complexity = arguments["include_complexity"]
            if not isinstance(include_complexity, bool):
                raise ValueError("include_complexity must be a boolean")

        if "include_details" in arguments:
            include_details = arguments["include_details"]
            if not isinstance(include_details, bool):
                raise ValueError("include_details must be a boolean")

        return True

    def get_tool_definition(self) -> Any:
        """
        Get the MCP tool definition for analyze_code_scale.

        Returns:
            Tool definition object compatible with MCP server
        """
        try:
            from mcp.types import Tool

            return Tool(
                name="analyze_code_scale",
                description="Analyze code scale, complexity, and structure metrics with CLI-compatible output format",
                inputSchema=self.get_tool_schema(),
            )
        except ImportError:
            # Fallback for when MCP is not available
            return {
                "name": "analyze_code_scale",
                "description": "Analyze code scale, complexity, and structure metrics with CLI-compatible output format",
                "inputSchema": self.get_tool_schema(),
            }


# Tool instance for easy access
analyze_scale_tool_cli_compatible = AnalyzeScaleToolCLICompatible()
