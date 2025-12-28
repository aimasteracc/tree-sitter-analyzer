#!/usr/bin/env python3
"""
Analysis Request Model
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=False)
class AnalysisRequest:
    """
    Analysis request

    Attributes:
        file_path: Path to target file to analyze
        language: Programming language (auto-detected if None)
        queries: List of query names to execute
        include_elements: Whether to extract code elements
        include_queries: Whether to execute queries
        include_complexity: Whether to include complexity metrics
        include_details: Whether to include detailed structure info
        format_type: Output format
    """

    file_path: str
    language: str | None = None
    queries: list[str] | None = None
    include_elements: bool = True
    include_queries: bool = True
    include_complexity: bool = True
    include_details: bool = False
    format_type: str = "json"

    @classmethod
    def from_mcp_arguments(cls, arguments: dict[str, Any]) -> "AnalysisRequest":
        """
        Create analysis request from MCP tool arguments

        Args:
            arguments: MCP argument dictionary

        Returns:
            AnalysisRequest
        """
        return cls(
            file_path=arguments.get("file_path", ""),
            language=arguments.get("language"),
            include_complexity=arguments.get("include_complexity", True),
            include_details=arguments.get("include_details", False),
            format_type=arguments.get("format_type", "json"),
        )
