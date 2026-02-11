"""
MCP Tool for checking code scale and complexity.

This module provides the check_code_scale tool that analyzes code files
and returns metrics about size, complexity, and structure to help LLMs
efficiently analyze code.
"""

from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.detector import LanguageDetector
from tree_sitter_analyzer_v2.core.parser_registry import get_all_parsers
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class CheckCodeScaleTool(BaseTool):
    """
    MCP tool for checking code scale and complexity metrics.

    Analyzes code files and returns:
    - File metrics (lines, characters, size)
    - Structure counts (classes, functions, imports)
    - LLM guidance for efficient analysis
    - Optional detailed element information
    """

    def __init__(self) -> None:
        """Initialize the check code scale tool."""
        self._detector = LanguageDetector()
        # Initialize encoding detector for multi-encoding support
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        self._encoding_detector = EncodingDetector()

        # Resolve parsers via registry (DIP: no hardcoded language imports)
        self._parsers: dict[str, Any] = get_all_parsers()

    def get_name(self) -> str:
        """Get tool name."""
        return "check_code_scale"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Analyze code scale, complexity, and structure metrics with LLM-optimized "
            "guidance for efficient large file analysis and token-aware workflow recommendations."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the code file to analyze"},
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Batch mode: list of file paths to compute metrics for (requires metrics_only=true)",
                },
                "metrics_only": {
                    "type": "boolean",
                    "description": "Batch mode: when true, compute file metrics only (no structural analysis)",
                    "default": False,
                },
                "include_details": {
                    "type": "boolean",
                    "description": "Include detailed element information (classes, functions, imports)",
                    "default": False,
                },
                "include_guidance": {
                    "type": "boolean",
                    "description": "Include LLM analysis guidance",
                    "default": True,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["toon", "markdown"],
                    "description": "Output format: 'toon' (token-optimized, default) or 'markdown' (human-readable)",
                    "default": "toon",
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the check_code_scale tool.

        Args:
            arguments: Tool arguments containing:
                - file_path: Path to file to analyze (single mode)
                - file_paths: List of paths (batch mode)
                - metrics_only: If True, only return metrics
                - include_details: If True, include element details
                - include_guidance: If True, include LLM guidance
                - output_format: 'toon' or 'markdown'

        Returns:
            Dict containing:
                - success: Whether analysis succeeded
                - file_metrics: File size and line metrics
                - structure: Structure element counts
                - guidance: LLM guidance (if include_guidance=True)
                - error: Error message if failed
        """
        # Batch mode
        if "file_paths" in arguments and arguments.get("file_paths"):
            return self._execute_batch_mode(arguments)

        # Single file mode
        file_path = arguments.get("file_path", "")
        include_details = arguments.get("include_details", False)
        include_guidance = arguments.get("include_guidance", True)
        output_format = arguments.get("output_format", "toon")

        # Validate file exists
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return self._error(f"File not found: {file_path}", error_code="FILE_NOT_FOUND")

        try:
            # Calculate file metrics
            file_metrics = self._calculate_file_metrics(file_path_obj)

            # Read file content with automatic encoding detection
            content = self._encoding_detector.read_file_safe(file_path_obj)

            # Detect language
            detection_result = self._detector.detect_from_content(
                content=content, filename=str(file_path_obj)
            )

            # If language detection failed or unsupported, return metrics only
            if detection_result is None:
                return {
                    "success": True,
                    "file_metrics": file_metrics,
                    "structure": {"total_classes": 0, "total_functions": 0, "total_imports": 0},
                    "output_format": output_format,
                }

            language = detection_result["language"].lower()
            if language not in self._parsers:
                # Return metrics only for unsupported languages
                return {
                    "success": True,
                    "file_metrics": file_metrics,
                    "structure": {"total_classes": 0, "total_functions": 0, "total_imports": 0},
                    "output_format": output_format,
                }

            # Parse file
            parser = self._parsers[language]
            parse_result = parser.parse(content, str(file_path_obj))

            # Extract structure counts
            structure = self._extract_structure(parse_result, include_details)

            # Build result
            result: dict[str, Any] = {
                "success": True,
                "file_metrics": file_metrics,
                "structure": structure,
                "output_format": output_format,
            }

            # Add LLM guidance if requested
            if include_guidance:
                guidance = self._generate_guidance(file_metrics, structure)
                result["guidance"] = guidance

            return result

        except Exception as e:
            return self._error(f"Error analyzing file: {e}", error_code="ANALYSIS_ERROR")

    def _execute_batch_mode(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute batch mode analysis.

        Args:
            arguments: Tool arguments with file_paths

        Returns:
            Dict containing list of file results
        """
        file_paths = arguments.get("file_paths", [])
        metrics_only = arguments.get("metrics_only", False)

        results = []
        for file_path_str in file_paths:
            file_path = Path(file_path_str)

            if not file_path.exists():
                results.append({"file_path": file_path_str, "error": "File not found"})
                continue

            try:
                metrics = self._calculate_file_metrics(file_path)
                file_result: dict[str, Any] = {"file_path": file_path_str, "metrics": metrics}

                # If not metrics_only, include structure
                if not metrics_only:
                    content = self._encoding_detector.read_file_safe(file_path)
                    detection_result = self._detector.detect_from_content(
                        content=content, filename=str(file_path)
                    )

                    if detection_result:
                        language = detection_result["language"].lower()
                        if language in self._parsers:
                            parser = self._parsers[language]
                            parse_result = parser.parse(content, str(file_path))
                            structure = self._extract_structure(parse_result, False)
                            file_result["structure"] = structure

                results.append(file_result)

            except Exception as e:
                results.append({"file_path": file_path_str, "error": str(e)})

        return {"success": True, "files": results}

    def _calculate_file_metrics(self, file_path: Path) -> dict[str, Any]:
        """
        Calculate file metrics.

        Args:
            file_path: Path to file

        Returns:
            Dict with total_lines, total_characters, file_size
        """
        content = self._encoding_detector.read_file_safe(file_path)
        lines = content.splitlines()

        return {
            "total_lines": len(lines),
            "total_characters": len(content),
            "file_size": file_path.stat().st_size,
        }

    def _extract_structure(
        self, parse_result: dict[str, Any], include_details: bool
    ) -> dict[str, Any]:
        """
        Extract structure information from parse result.

        Args:
            parse_result: Result from parser
            include_details: Whether to include detailed element info

        Returns:
            Dict with structure counts and optionally details
        """
        structure: dict[str, Any] = {
            "total_classes": len(parse_result.get("classes", [])),
            "total_functions": len(parse_result.get("functions", [])),
            "total_imports": len(parse_result.get("imports", [])),
        }

        # Add details if requested
        if include_details:
            structure["classes"] = parse_result.get("classes", [])
            structure["functions"] = parse_result.get("functions", [])
            structure["imports"] = parse_result.get("imports", [])

        return structure

    def _generate_guidance(
        self, file_metrics: dict[str, Any], structure: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate LLM guidance for efficient file analysis.

        Args:
            file_metrics: File metrics
            structure: Structure information

        Returns:
            Dict with guidance information
        """
        total_lines = file_metrics["total_lines"]

        # Determine size category
        if total_lines < 100:
            size_category = "small"
            strategy = "This is a small file that can be analyzed in full detail."
        elif total_lines < 500:
            size_category = "medium"
            strategy = "This is a medium-sized file. Consider focusing on key classes and methods."
        elif total_lines < 1500:
            size_category = "large"
            strategy = "This is a large file. Use targeted analysis with extract_code_section."
        else:
            size_category = "very_large"
            strategy = "This is a very large file. Strongly recommend using structural analysis first, then targeted deep-dives."

        return {"size_category": size_category, "analysis_strategy": strategy}
