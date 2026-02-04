#!/usr/bin/env python3
"""
Format Helper for MCP Tools.

Provides utility functions for formatting MCP tool output in different formats
(JSON, TOON) with consistent behavior across all tools.

Key Features:
    - TOON format conversion with fallback to JSON
    - JSON formatting with proper encoding
    - File output formatting with TOON wrapper
    - apply_toon_format_to_response for MCP protocol responses
    - Consistent format handling across all MCP tools

Design Principles:
    - TOON format only outputs {"format": "toon", "toon_content": "..."}
    - JSON format outputs the original dict structure
    - File output wraps content in appropriate format

Classes:
    JsonFormatter: Simple JSON formatter with format() interface

Functions:
    format_as_json: Format data as JSON string
    format_as_toon: Format data as TOON string with fallback
    format_output: Unified formatting function
    apply_toon_format_to_response: MCP response formatting
    format_for_file_output: File output formatting

Version: 1.10.5
Date: 2026-01-28
Author: tree-sitter-analyzer team
"""

from __future__ import annotations

import json
from typing import Any

from ...utils import setup_logger

__all__ = [
    "JsonFormatter",
    "format_as_json",
    "format_as_toon",
    "format_output",
    "apply_toon_format_to_response",
    "format_for_file_output",
]

logger = setup_logger(__name__)  # type: ignore


class JsonFormatter:
    """Simple JSON formatter implementing the format() interface."""

    def format(self, data: Any) -> str:
        """Format data as JSON string."""
        return json.dumps(data, indent=2, ensure_ascii=False)


def format_as_json(data: dict[str, Any]) -> str:
    """Format data as JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_as_toon(data: dict[str, Any]) -> str:
    """
    Format data as TOON string.

    Falls back to JSON if ToonFormatter is not available.
    """
    try:
        from ...formatters.toon_formatter import ToonFormatter

        return ToonFormatter().format(data)
    except ImportError as e:
        logger.warning(f"ToonFormatter not available, falling back to JSON: {e}")
        return format_as_json(data)
    except Exception as e:
        logger.warning(f"TOON formatting failed, falling back to JSON: {e}")
        return format_as_json(data)


def format_output(data: dict[str, Any], output_format: str = "toon") -> str:
    """
    Format data as string according to the specified format.

    Args:
        data: Dictionary data to format
        output_format: 'toon'

    Returns:
        Formatted string
    """
    return format_as_toon(data)


def get_formatter(output_format: str = "toon") -> Any:
    """
    Get a formatter instance for the specified format.

    Returns:
        Formatter instance with format() method
    """
    try:
        from ...formatters.toon_formatter import ToonFormatter

        return ToonFormatter()
    except ImportError:
        logger.warning("ToonFormatter not available, using JSON fallback formatter")
        return JsonFormatter()


def apply_toon_format_to_response(
    result: dict[str, Any], output_format: str = "toon"
) -> dict[str, Any]:
    """
    Apply output format to MCP tool response.

    When output_format='toon':
      Returns pure TOON format with only format marker and toon_content.
      All data is contained in toon_content to avoid duplication.

    Args:
        result: Original result dictionary from MCP tool
        output_format: 'toon' (default)

    Returns:
        Formatted result dict with only format and toon_content fields
    """
    try:
        # Generate TOON content from full result
        toon_content = format_as_toon(result)

        # Return pure TOON format (no redundant fields)
        return {
            "format": "toon",
            "toon_content": toon_content,
        }

    except Exception as e:
        logger.warning(f"Failed to apply TOON format, returning JSON: {e}")
        return result


# Alias for backward compatibility
# Use apply_toon_format_to_response(result, "toon") instead
def attach_toon_content_to_response(result: dict[str, Any]) -> dict[str, Any]:
    """
    Deprecated: Use apply_toon_format_to_response(result, "toon") instead.

    Format result as TOON and return minimal response.
    """
    return apply_toon_format_to_response(result, "toon")


def format_for_file_output(
    data: dict[str, Any], output_format: str = "toon"
) -> tuple[str, str]:
    """
    Format data for file output with appropriate extension.

    Returns:
        Tuple of (formatted_content, file_extension)
    """
    return format_as_toon(data), ".toon"


def apply_output_format(
    result: dict[str, Any],
    output_format: str = "toon",
    return_formatted_string: bool = False,
) -> dict[str, Any] | str:
    """
    Apply output format to result.

    Args:
        result: Result dictionary
        output_format: 'toon'
        return_formatted_string: If True, return formatted string

    Returns:
        Dict or formatted string depending on return_formatted_string
    """
    if return_formatted_string:
        return format_output(result, output_format)
    return result
