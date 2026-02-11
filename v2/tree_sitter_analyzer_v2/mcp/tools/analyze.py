"""
MCP Tool for analyzing code structure.

This module provides the analyze_code_structure tool that analyzes a code file
and returns structured information in TOON or Markdown format.
"""

from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.detector import LanguageDetector
from tree_sitter_analyzer_v2.core.parser_registry import get_all_parsers
from tree_sitter_analyzer_v2.formatters import get_default_registry
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class AnalyzeTool(BaseTool):
    """
    MCP tool for analyzing code structure.

    Analyzes a code file and returns structured information about its elements
    (classes, functions, imports, etc.) in TOON or Markdown format.
    """

    def __init__(self) -> None:
        """Initialize the analyze tool."""
        self._detector = LanguageDetector()
        self._formatter_registry = get_default_registry()
        # Initialize encoding detector for multi-encoding support
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        self._encoding_detector = EncodingDetector()

        # Resolve parsers via registry (DIP: no hardcoded language imports)
        self._parsers: dict[str, Any] = get_all_parsers()

    def get_name(self) -> str:
        """Get tool name."""
        return "analyze_code_structure"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Analyze a code file and extract structured information about its elements "
            "(classes, functions, imports, etc.). Returns results in TOON (token-optimized) "
            "or Markdown (human-readable) format."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the code file to analyze"},
                "output_format": {
                    "type": "string",
                    "enum": ["toon", "markdown"],
                    "description": "Output format: 'toon' (token-optimized, default) or 'markdown' (human-readable)",
                    "default": "toon",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the analyze tool.

        Args:
            arguments: Tool arguments containing:
                - file_path: Path to file to analyze
                - output_format: 'toon' or 'markdown' (default: 'toon')

        Returns:
            Dict containing:
                - success: Whether analysis succeeded
                - language: Detected language
                - output_format: Output format used
                - data: Formatted analysis results
                - error: Error message if failed, None otherwise
        """
        file_path = arguments.get("file_path", "")
        output_format = arguments.get("output_format", "toon").lower()

        # Validate output format
        if output_format not in ["toon", "markdown"]:
            return {
                **self._error(
                    f"Invalid output format: {output_format}. Must be 'toon' or 'markdown'.",
                    error_code="INVALID_ARGUMENT",
                ),
                "language": None, "output_format": output_format, "data": None,
            }

        # Check file exists
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return {
                **self._error(f"File not found: {file_path}", error_code="FILE_NOT_FOUND"),
                "language": None, "output_format": output_format, "data": None,
            }

        try:
            # Read file content with automatic encoding detection
            content = self._encoding_detector.read_file_safe(file_path_obj)

            # Detect language
            detection_result = self._detector.detect_from_content(
                content=content, filename=str(file_path_obj)
            )

            # Check if detection succeeded
            if detection_result is None:
                return {
                    **self._error(
                        f"Could not detect language for file: {file_path}",
                        error_code="UNSUPPORTED_LANGUAGE",
                    ),
                    "language": None, "output_format": output_format, "data": None,
                }

            # Get language from detection result
            language = detection_result["language"].lower()
            if language not in self._parsers:
                supported = ", ".join(self._parsers.keys())
                return {
                    **self._error(
                        f"Unsupported language: {language}. Supported: {supported}",
                        error_code="UNSUPPORTED_LANGUAGE",
                    ),
                    "language": language, "output_format": output_format, "data": None,
                }

            # Parse file
            parser = self._parsers[language]
            parse_result = parser.parse(content, str(file_path_obj))

            # Format output
            formatter = self._formatter_registry.get(output_format)
            formatted_data = formatter.format(parse_result)

            return {
                "success": True,
                "language": language,
                "output_format": output_format,
                "data": formatted_data,
                "error": None,
            }

        except Exception as e:
            return {
                **self._error(f"Error analyzing file: {e}", error_code="ANALYSIS_ERROR"),
                "language": None, "output_format": output_format, "data": None,
            }
