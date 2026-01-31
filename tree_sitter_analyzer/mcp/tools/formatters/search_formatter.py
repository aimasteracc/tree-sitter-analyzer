#!/usr/bin/env python3
"""
Result Formatter for SearchContentTool.

This module provides comprehensive formatting logic for search results,
supporting multiple output formats and suppression modes.

Key Features:
    - TOON format conversion for structured output
    - JSON format support for machine-readable results
    - Minimal result creation for suppressed output
    - File output formatting integration
    - Integer result passthrough for total_only mode

Classes:
    SearchResultFormatter: Main formatter for search tool results

Version: 1.10.5
Date: 2026-01-28
Author: tree-sitter-analyzer team
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter_analyzer.mcp.utils.format_helper import (
        apply_toon_format_to_response,
    )
else:
    try:
        from tree_sitter_analyzer.mcp.utils.format_helper import (
            apply_toon_format_to_response,
        )
    except ImportError as e:
        logging.warning(f"Import fallback triggered in search_formatter: {e}")

__all__ = ["SearchResultFormatter"]

logger = logging.getLogger(__name__)


class SearchResultFormatter:
    """Formatter for search tool results.

    This class handles all result formatting logic, including:
    - TOON format conversion
    - JSON format conversion
    - Minimal result creation for suppressed output
    - File output formatting
    """

    def format(
        self,
        result: dict[str, Any] | int,
        output_format: str = "toon",
        suppress_output: bool = False,
    ) -> dict[str, Any] | int:
        """Format search results.

        Args:
            result: Raw search results
            output_format: Output format ('toon' or 'json')
            suppress_output: Whether to suppress detailed output

        Returns:
            Formatted results
        """
        # If result is already an integer (total_only mode), return as-is
        if isinstance(result, int):
            return result

        # Handle suppressed output
        if suppress_output and not result.get("output_file"):
            result = self._create_minimal_result(result)

        # Apply output format
        if output_format == "toon":
            return self._apply_toon_format(result)
        else:
            return result

    def _create_minimal_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Create minimal result for suppressed output.

        Args:
            result: Full result dictionary

        Returns:
            Minimal result dictionary
        """
        # Keep only essential fields
        minimal_keys = {
            "success",
            "count",
            "total_matches",
            "elapsed_ms",
            "summary",
            "meta",
            "output_file",
            "file_saved",
        }

        return {k: v for k, v in result.items() if k in minimal_keys}

    def _apply_toon_format(self, result: dict[str, Any]) -> dict[str, Any]:
        """Apply TOON format to result.

        Args:
            result: Result dictionary

        Returns:
            Result with TOON format applied
        """
        # Check if result has specific format indicators
        if result.get("count_only") or result.get("summary"):
            return apply_toon_format_to_response(result, "toon")
        else:
            return apply_toon_format_to_response(result, "toon")
