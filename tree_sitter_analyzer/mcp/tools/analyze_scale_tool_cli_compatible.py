#!/usr/bin/env python3
"""
CLI-Compatible Analyze Code Scale MCP Tool

This tool provides code scale analysis with output format
that matches the CLI --advanced --statistics output exactly.
"""

import time
from pathlib import Path
from typing import Any

from ...core.analysis_engine import get_analysis_engine
from ...language_detector import detect_language_from_file
from ...utils import setup_logger

# Set up logging
logger = setup_logger(__name__)


def _build_cli_compatible_result(
    file_path: str, analysis_result: Any, start_time: float
) -> dict[str, Any]:
    """CLI-compatible element_counts + metadata (matches --advanced --statistics).

    r37bs: extracted from ``execute`` so the element-type tallying lives
    next to the dict-shape it produces. Output bytes match the CLI's
    legacy envelope so cross-tool comparators stay green.
    """
    element_types = [
        getattr(e, "element_type", type(e).__name__.lower())
        for e in analysis_result.elements
    ]
    package_name = None
    if analysis_result.package and hasattr(analysis_result.package, "name"):
        package_name = analysis_result.package.name

    return {
        "file_path": file_path,
        "success": analysis_result.success,
        "package_name": package_name,
        "element_counts": {
            "imports": element_types.count("import"),
            "classes": element_types.count("class"),
            "methods": element_types.count("function") + element_types.count("method"),
            "fields": element_types.count("variable") + element_types.count("field"),
            "annotations": element_types.count("annotation"),
        },
        "analysis_time_ms": round((time.time() - start_time) * 1000, 2),
        "error_message": (
            analysis_result.error_message if not analysis_result.success else None
        ),
    }


def _cli_compatible_error_result(file_path: str, error_message: str) -> dict[str, Any]:
    """Zero-count CLI-compatible envelope returned on analysis failure."""
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
        "error_message": error_message,
    }


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
        """Execute the analyze_code_scale tool with CLI-compatible output.

        r37bs (dogfood): tool flagged this at 107 lines. Split argument
        validation + analysis + result assembly + error envelope. Output
        format unchanged (exact-match CLI --advanced --statistics).
        """
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")

        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not language:
            language = detect_language_from_file(file_path)
            if language == "unknown":
                raise ValueError(f"Could not detect language for file: {file_path}")

        logger.info(f"Analyzing code scale for {file_path} (language: {language})")
        try:
            return await self._run_analysis_and_build_result(file_path, language)
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            return _cli_compatible_error_result(file_path, str(e))

    async def _run_analysis_and_build_result(
        self, file_path: str, language: str
    ) -> dict[str, Any]:
        """Call the analysis engine and produce the CLI-compatible envelope."""
        from ...core.analysis_engine import AnalysisRequest

        start_time = time.time()
        request = AnalysisRequest(
            file_path=file_path,
            language=language,
            include_complexity=True,
            include_details=False,
        )
        analysis_result = await self.analysis_engine.analyze(request)
        result = _build_cli_compatible_result(file_path, analysis_result, start_time)

        if not result["success"] and not result["error_message"]:
            result["error_message"] = f"Failed to analyze file: {file_path}"

        logger.info(
            f"Successfully analyzed {file_path}: "
            f"{result['element_counts']['classes']} classes, "
            f"{result['element_counts']['methods']} methods, "
            f"{result['analysis_time_ms']}ms"
        )
        return result

    # validate_arguments: implementation
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

    # get_tool_definition: implementation
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
