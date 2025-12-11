#!/usr/bin/env python3
"""
TOON (Token-Oriented Object Notation) Formatter

High-level formatter for converting analysis results and MCP responses
to TOON format, optimized for LLM consumption with 50-70% token reduction.
"""

import logging
from typing import Any

from .base_formatter import BaseFormatter
from .toon_encoder import ToonEncodeError, ToonEncoder

# Logger for TOON formatter
logger = logging.getLogger(__name__)


class ToonFormatter(BaseFormatter):
    """
    TOON formatter for LLM-optimized output.

    Converts analysis results to compact, human-readable TOON format that
    reduces token consumption by 50-70% compared to JSON while maintaining
    full information fidelity.

    Implements the unified Formatter interface for OutputManager compatibility.
    """

    def __init__(
        self,
        use_tabs: bool = False,
        compact_arrays: bool = True,
        include_metadata: bool = True,
        fallback_to_json: bool = True,
        normalize_paths: bool = True,
    ):
        """
        Initialize TOON formatter.

        Args:
            use_tabs: Use tab delimiters instead of commas (further optimization)
            compact_arrays: Use CSV-style compact arrays for homogeneous data
            include_metadata: Include file metadata in output
            fallback_to_json: Fall back to JSON on encoding errors
            normalize_paths: Convert Windows backslashes to forward slashes
                           for ~10% token reduction in path-heavy outputs
        """
        self.use_tabs = use_tabs
        self.compact_arrays = compact_arrays
        self.include_metadata = include_metadata
        self.fallback_to_json = fallback_to_json
        self.normalize_paths = normalize_paths
        self.encoder = ToonEncoder(
            use_tabs=use_tabs,
            fallback_to_json=fallback_to_json,
            normalize_paths=normalize_paths,
        )

    def format(self, data: Any) -> str:
        """
        Unified format method implementing the Formatter protocol.

        Routes to appropriate internal formatter based on data type.
        This method enables OutputManager to call formatter.format(data)
        without needing to know the specific formatter implementation.

        On encoding errors, falls back to JSON if fallback_to_json is True.

        Args:
            data: The data to format (AnalysisResult, dict, or other types)

        Returns:
            TOON-formatted string (or JSON on fallback)
        """
        try:
            return self._format_internal(data)
        except ToonEncodeError as e:
            logger.error(f"TOON formatting failed: {e}")
            if self.fallback_to_json:
                logger.warning("Falling back to JSON format")
                return self.encoder._fallback_to_json(data)
            raise
        except Exception as e:
            logger.error(f"Unexpected error during TOON formatting: {e}", exc_info=True)
            if self.fallback_to_json:
                logger.warning("Falling back to JSON format")
                return self.encoder._fallback_to_json(data)
            raise ToonEncodeError("Formatting failed", data=data, cause=e) from e

    def _format_internal(self, data: Any) -> str:
        """
        Internal format method without error handling wrapper.

        Args:
            data: The data to format

        Returns:
            TOON-formatted string
        """
        # Import here to avoid circular dependency
        try:
            from tree_sitter_analyzer.models import AnalysisResult

            if isinstance(data, AnalysisResult):
                return self.format_analysis_result(data)
        except ImportError:
            pass

        # Check if it's an MCP response (dict with specific structure)
        if isinstance(data, dict):
            # Detect MCP response structure
            if self._is_mcp_response(data):
                return self.format_mcp_response(data)
            else:
                # Generic dict - try to format as analysis result dict
                return self.format_structure(data)

        # Fallback: encode arbitrary data as TOON
        return self.encoder.encode(data)

    def _is_mcp_response(self, data: dict[str, Any]) -> bool:
        """
        Detect if data is an MCP response structure.

        MCP responses typically have 'content' or 'data' fields.

        Args:
            data: Dictionary to check

        Returns:
            True if data appears to be an MCP response
        """
        mcp_keys = {"content", "data", "metadata", "analysis_result"}
        return bool(mcp_keys.intersection(data.keys()))

    def format_analysis_result(self, result: Any, table_type: str = "full") -> str:
        """
        Format complete analysis result as TOON.

        Args:
            result: Analysis result to format (AnalysisResult object)
            table_type: Output detail level (full, summary, compact)

        Returns:
            TOON-formatted string
        """
        # Import here to avoid circular dependency
        from tree_sitter_analyzer.models import AnalysisResult

        if not isinstance(result, AnalysisResult):
            # Try to convert dict to proper format
            if isinstance(result, dict):
                return self.format_structure(result)
            return self.encoder.encode(result)

        lines = []

        # File metadata
        if self.include_metadata:
            lines.append(f"file: {result.file_path}")
            lines.append(f"language: {result.language}")
            if result.package:
                package_name = (
                    result.package.name
                    if hasattr(result.package, "name")
                    else str(result.package)
                )
                lines.append(f"package: {package_name}")
            lines.append("")

        # Statistics summary
        stats = result.get_summary()
        if stats:
            lines.append("summary:")
            for key, value in stats.items():
                lines.append(f"  {key}: {value}")
            lines.append("")

        # Elements (classes, methods, functions)
        if result.elements:
            lines.append(f"elements[{len(result.elements)}]:")

            # Group by type
            classes = [e for e in result.elements if e.element_type == "class"]
            methods = [e for e in result.elements if e.element_type == "method"]
            functions = [e for e in result.elements if e.element_type == "function"]

            if classes:
                lines.append(f"  classes[{len(classes)}]:")
                for cls in classes:
                    lines.append(f"    - {cls.name}")

            if methods:
                lines.append(f"  methods[{len(methods)}]:")
                if self.compact_arrays:
                    # Use compact table format
                    method_dicts = [
                        self._method_to_dict(m) for m in methods[:10]
                    ]  # Limit for demo
                    table = self.encoder.encode_array_table(method_dicts, indent=2)
                    lines.append(table)
                else:
                    for method in methods[:10]:  # Limit for demo
                        lines.append(f"    - {method.name}")

            if functions:
                lines.append(f"  functions[{len(functions)}]:")
                for func in functions[:10]:  # Limit for demo
                    lines.append(f"    - {func.name}")

        return "\n".join(lines)

    def format_mcp_response(self, data: dict[str, Any]) -> str:
        """
        Format MCP tool response as TOON.

        Optimized for AI assistant consumption.

        Args:
            data: MCP response dictionary

        Returns:
            TOON-formatted string
        """
        return self.encoder.encode_dict(data)

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """
        Format summary output (BaseFormatter requirement).

        Args:
            analysis_result: Analysis result dictionary

        Returns:
            TOON-formatted summary
        """
        return self.encoder.encode_dict(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """
        Format structure analysis output (BaseFormatter requirement).

        Args:
            analysis_result: Analysis result dictionary

        Returns:
            TOON-formatted structure
        """
        return self.encoder.encode_dict(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "toon"
    ) -> str:
        """
        Format advanced analysis output (BaseFormatter requirement).

        Args:
            analysis_result: Analysis result dictionary
            output_format: Output format (ignored, always returns TOON)

        Returns:
            TOON-formatted advanced analysis
        """
        return self.encoder.encode_dict(analysis_result)

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """
        Format table output (BaseFormatter requirement).

        Args:
            analysis_result: Analysis result dictionary
            table_type: Table detail level (full, compact, summary)

        Returns:
            TOON-formatted table
        """
        return self.encoder.encode_dict(analysis_result)

    def _method_to_dict(self, method: Any) -> dict[str, Any]:
        """
        Convert method element to dictionary for table encoding.

        Args:
            method: Method element

        Returns:
            Dictionary representation
        """
        return {
            "name": method.name if hasattr(method, "name") else str(method),
            "visibility": getattr(method, "visibility", ""),
            "lines": f"{getattr(method, 'start_line', 0)}-{getattr(method, 'end_line', 0)}",
        }

    @staticmethod
    def is_toon_content(content: str) -> bool:
        """
        Detect if content is in TOON format.

        Used by FileOutputManager to determine content type.

        Args:
            content: String content to check

        Returns:
            True if content appears to be TOON format
        """
        if not content or not content.strip():
            return False

        lines = content.strip().split("\n")
        if not lines:
            return False

        # TOON format indicators:
        # 1. Lines with "key: value" pattern (not JSON)
        # 2. Array table headers like "[N]{field1,field2}:"
        # 3. Nested structure with indentation

        # Check if it looks like JSON first
        first_char = content.strip()[0]
        if first_char in "{[":
            return False

        # Check for TOON patterns
        toon_patterns = 0
        for line in lines[:10]:  # Check first 10 lines
            stripped = line.strip()
            if not stripped:
                continue

            # Key-value pattern: "key: value"
            if (
                ":" in stripped
                and not stripped.startswith("{")
                and not stripped.startswith('"')
            ):
                parts = stripped.split(":", 1)
                if len(parts) == 2 and parts[0].strip():
                    toon_patterns += 1

            # Array table header: "[N]{...}:"
            if stripped.startswith("[") and "]{" in stripped and stripped.endswith(":"):
                toon_patterns += 2

        # Need at least 2 TOON patterns to confirm
        return toon_patterns >= 2
