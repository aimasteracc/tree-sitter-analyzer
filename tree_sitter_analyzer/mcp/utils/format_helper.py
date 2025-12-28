#!/usr/bin/env python3
"""
Format Helper for MCP Tools

Provides utility functions for formatting MCP tool output in different formats
(JSON, TOON) with consistent behavior across all tools.
"""

import json
from typing import Any

from ...utils import setup_logger

logger = setup_logger(__name__)


def format_output(data: dict[str, Any], output_format: str = "json") -> str:
    """
    Format data according to the specified output format.

    Args:
        data: Dictionary data to format
        output_format: Output format ('json' or 'toon')

    Returns:
        Formatted string representation of the data
    """
    if output_format == "toon":
        return format_as_toon(data)
    else:
        return format_as_json(data)


def format_as_json(data: dict[str, Any]) -> str:
    """
    Format data as JSON string.

    Args:
        data: Dictionary data to format

    Returns:
        JSON formatted string
    """
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_as_toon(data: dict[str, Any]) -> str:
    """
    Format data as TOON string.

    Args:
        data: Dictionary data to format

    Returns:
        TOON formatted string
    """
    try:
        from ...formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        return formatter.format(data)
    except ImportError as e:
        logger.warning(f"ToonFormatter not available, falling back to JSON: {e}")
        return format_as_json(data)
    except Exception as e:
        logger.warning(f"TOON formatting failed, falling back to JSON: {e}")
        return format_as_json(data)


def get_formatter(output_format: str = "json") -> Any:
    """
    Get a formatter instance for the specified format.

    Args:
        output_format: Output format ('json' or 'toon')

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
    return JsonFormatter()


class JsonFormatter:
    """Simple JSON formatter implementing the format() interface."""

    def format(self, data: Any) -> str:
        """Format data as JSON string."""
        return json.dumps(data, indent=2, ensure_ascii=False)


def apply_output_format(
    result: dict[str, Any],
    output_format: str = "json",
    return_formatted_string: bool = False,
) -> dict[str, Any] | str:
    """
    Apply output format to a result dictionary.

    This function can either:
    1. Return the original dict (for MCP protocol compatibility)
    2. Return a formatted string (for file output or direct display)

    Args:
        result: Result dictionary from MCP tool execution
        output_format: Output format ('json' or 'toon')
        return_formatted_string: If True, return formatted string instead of dict

    Returns:
        Either the original dict or a formatted string
    """
    if return_formatted_string:
        return format_output(result, output_format)
    else:
        # For MCP protocol, we return the dict as-is
        # The format is applied when saving to file or displaying
        return result


def format_for_file_output(
    data: dict[str, Any], output_format: str = "json"
) -> tuple[str, str]:
    """
    Format data for file output and return content with appropriate extension.

    Args:
        data: Dictionary data to format
        output_format: Output format ('json' or 'toon')

    Returns:
        Tuple of (formatted_content, file_extension)
    """
    if output_format == "toon":
        content = format_as_toon(data)
        extension = ".toon"
    else:
        content = format_as_json(data)
        extension = ".json"

    return content, extension


def apply_toon_format_to_response(
    result: dict[str, Any], output_format: str = "json"
) -> dict[str, Any]:
    """
    Apply TOON format to MCP tool response if requested.

    When output_format is 'toon', formats the result as TOON and removes
    redundant data fields (results, matches, content, etc.) to maximize
    token savings. Only metadata fields are preserved alongside toon_content.

    Args:
        result: Original result dictionary from MCP tool
        output_format: Output format ('json' or 'toon')

    Returns:
        Modified result dict with TOON content if requested, otherwise original
    """
    if output_format != "toon":
        return result

    try:
        # Format the full result as TOON
        toon_content = format_as_toon(result)

        # Create minimal response with only metadata and TOON content
        # Remove redundant data fields to maximize token savings
        # These fields are already included in toon_content, so keeping them
        # would duplicate data and waste tokens
        redundant_fields = {
            "results",  # Search/query results
            "matches",  # Search matches
            "content",  # File content
            "partial_content_result",  # Partial read results
            "analysis_result",  # Code analysis results
            "data",  # Generic data field
            "items",  # List items
            "files",  # File listings
            "lines",  # Line content
            "table_output",  # Formatted table output
        }

        toon_response: dict[str, Any] = {
            "format": "toon",
            "toon_content": toon_content,
        }

        # Preserve only metadata fields (not redundant data)
        for key, value in result.items():
            if key not in redundant_fields:
                toon_response[key] = value

        return toon_response

    except Exception as e:
        logger.warning(f"Failed to apply TOON format, returning JSON: {e}")
        return result


def attach_toon_content_to_response(result: dict[str, Any]) -> dict[str, Any]:
    """
    Attach TOON formatted content to a response *without removing* any existing fields.

    This is useful for structured outputs (e.g. group_by_file) where callers/tests rely
    on the original JSON structure, while still allowing clients to display TOON.
    """
    try:
        toon_content = format_as_toon(result)
        enriched = result.copy()
        enriched["format"] = "toon"
        enriched["toon_content"] = toon_content
        return enriched
    except Exception as e:
        logger.warning(f"Failed to attach TOON content, returning JSON: {e}")
        return result
