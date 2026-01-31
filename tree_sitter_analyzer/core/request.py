#!/usr/bin/env python3
"""
Analysis Request Model.

This module provides the AnalysisRequest dataclass for representing
analysis operation parameters with validation and factory methods.

Key Features:
    - Immutable request configuration with dataclass
    - MCP argument conversion support
    - Query list management
    - Include flags for selective analysis
    - Format type specification (toon, json)

Classes:
    AnalysisRequest: Request configuration for analysis operations

Version: 1.10.5
Date: 2026-01-28
Author: tree-sitter-analyzer team
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Type checking imports
__all__ = ["AnalysisRequest"]


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
    format_type: str = "toon"

    @classmethod
    def from_mcp_arguments(cls, arguments: dict[str, Any]) -> AnalysisRequest:
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
            format_type=arguments.get("format_type", "toon"),
        )
