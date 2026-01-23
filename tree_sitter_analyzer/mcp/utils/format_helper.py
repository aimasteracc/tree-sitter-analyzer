#!/usr/bin/env python3
"""
Format Helper for MCP Tools

Provides utility functions for formatting MCP tool output in different formats
(JSON, TOON) with consistent behavior across all tools.

Design Principles:
- TOON format only outputs {"format": "toon", "toon_content": "..."} to avoid duplication
- JSON format outputs the original dict structure
"""

import json
from typing import Any

from ...utils import setup_logger

logger = setup_logger(__name__)


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


def format_output(data: dict[str, Any], output_format: str = "json") -> str:
    """
    Format data as string according to the specified format.

    Args:
        data: Dictionary data to format
        output_format: 'json' or 'toon'

    Returns:
        Formatted string
    """
    if output_format == "toon":
        return format_as_toon(data)
    return format_as_json(data)


def get_formatter(output_format: str = "json") -> Any:
    """
    Get a formatter instance for the specified format.

    Returns:
        Formatter instance with format() method
    """
    if output_format == "toon":
        try:
            from ...formatters.toon_formatter import ToonFormatter

            return ToonFormatter()
        except ImportError:
            logger.warning("ToonFormatter not available, using JSON formatter")
    return JsonFormatter()


def apply_toon_format_to_response(
    result: dict[str, Any], output_format: str = "json"
) -> dict[str, Any]:
    """
    Apply output format to MCP tool response.

    When output_format='toon':
      1. Formats the full result as TOON.
      2. Removes large redundant data fields to save tokens.
      3. Preserves core metadata (success, file_path, etc.) for compatibility.

    Args:
        result: Original result dictionary from MCP tool
        output_format: 'json' or 'toon'

    Returns:
        Formatted result dict
    """
    if output_format != "toon":
        return result

    try:
        # 1. Generate TOON content first while we have all data
        toon_content = format_as_toon(result)

        # 2. Define large fields that are redundant because they are in toon_content
        redundant_fields = {
            "results",
            "matches",
            "content",
            "partial_content_result",
            "data",
            "items",
            "files",
            "lines",
            "table_output",
            "structural_overview",
            "llm_guidance",
            "ast_info",
            "available_queries",
            "analysis_result",
            "detailed_analysis",
        }

        # 3. Create response by removing redundant large fields
        # Keep metadata like success, file_path, language, status, etc.
        toon_response = {k: v for k, v in result.items() if k not in redundant_fields}
        toon_response["format"] = "toon"
        toon_response["toon_content"] = toon_content

        return toon_response

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
    data: dict[str, Any], output_format: str = "json"
) -> tuple[str, str]:
    """
    Format data for file output with appropriate extension.

    Returns:
        Tuple of (formatted_content, file_extension)
    """
    if output_format == "toon":
        return format_as_toon(data), ".toon"
    return format_as_json(data), ".json"


def apply_output_format(
    result: dict[str, Any],
    output_format: str = "json",
    return_formatted_string: bool = False,
) -> dict[str, Any] | str:
    """
    Apply output format to result.

    Args:
        result: Result dictionary
        output_format: 'json' or 'toon'
        return_formatted_string: If True, return formatted string

    Returns:
        Dict or formatted string depending on return_formatted_string
    """
    if return_formatted_string:
        return format_output(result, output_format)
    return result
