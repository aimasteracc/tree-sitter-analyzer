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

    When output_format is 'toon', wraps the result in a TOON-formatted string
    under the 'toon_content' key while preserving essential metadata.

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

        # Return a response that includes TOON content
        toon_response: dict[str, Any] = {
            "success": result.get("success", True),
            "format": "toon",
            "toon_content": toon_content,
        }

        # Preserve essential metadata for MCP protocol
        if "count" in result:
            toon_response["count"] = result["count"]
        if "file_path" in result:
            toon_response["file_path"] = result["file_path"]
        if "output_file_path" in result:
            toon_response["output_file_path"] = result["output_file_path"]
        if "file_saved" in result:
            toon_response["file_saved"] = result["file_saved"]
        if "error" in result:
            toon_response["error"] = result["error"]
        if "message" in result:
            toon_response["message"] = result["message"]

        return toon_response

    except Exception as e:
        logger.warning(f"Failed to apply TOON format, returning JSON: {e}")
        return result
