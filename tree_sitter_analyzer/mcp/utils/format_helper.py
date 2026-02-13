#!/usr/bin/env python3
"""
Format Helper for MCP Tools

Provides utility functions for formatting MCP tool output in different formats
(JSON, TOON) with consistent behavior across all tools.
"""

import json
import warnings
from typing import Any

from ...utils import setup_logger

logger = setup_logger(__name__)

# Scalar types allowed in TOON metadata fields
# Only these types are preserved alongside toon_content to prevent:
# 1. Data duplication (complex types already in toon_content)
# 2. Token explosion from nested structures
# 3. Circular reference issues
SCALAR_TYPES = (str, int, float, bool, type(None))

# Whitelist of metadata fields preserved in TOON responses
# Criteria for inclusion:
# 1. Must be scalar (str, int, float, bool, None)
# 2. Must be metadata about the operation, not the data itself
# 3. Must have bounded size (no unbounded strings)
# 4. Should be useful for client-side logic without parsing toon_content
_METADATA_WHITELIST = frozenset({
    # Status / control
    "success",      # bool: operation success status
    "error",        # str|None: error message if failed
    "status",       # str: operation status code
    # Counts (scalar)
    "count",        # int: number of results/matches
    "total_count",  # int: total count across all pages
    "total_matches",  # int: total search matches
    "count_only",   # bool: whether only count was requested
    # Identity
    "file_path",    # str: file being processed
    "language",     # str: programming language
    "query",        # str: search/query pattern
    "pattern",      # str: search pattern
    "tool",         # str: tool name
    "format_type",  # str: format identifier
    # Flags
    "truncated",    # bool: whether results were truncated
    "cache_hit",    # bool: whether result was cached
    # Timing
    "elapsed_ms",   # int: operation duration in milliseconds
    # Process status
    "returncode",   # int: process return code
    # File output
    "output_file",       # str: output file name
    "output_file_path",  # str: output file path
    "file_saved",        # bool: whether file was saved
    "file_save_error",   # str|None: file save error if any
})


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

    When output_format is 'toon', formats the result as TOON and preserves
    only small scalar metadata fields alongside toon_content. All data-bearing
    fields are omitted because they are already fully represented inside
    toon_content. This whitelist approach prevents field duplication and
    token explosion.

    Args:
        result: Original result dictionary from MCP tool
        output_format: Output format ('json' or 'toon')

    Returns:
        Modified result dict with TOON content if requested, otherwise original

    Example:
        >>> result = {"success": True, "count": 5, "results": [...]}
        >>> toon_result = apply_toon_format_to_response(result, "toon")
        >>> # Returns: {"format": "toon", "toon_content": "...", "success": True, "count": 5}
        >>> # Note: "results" is excluded (not in whitelist, and it's in toon_content)
    """
    if output_format != "toon":
        return result

    try:
        # Format the full result as TOON string
        toon_content = format_as_toon(result)

        # Create minimal response with TOON content and whitelisted scalar metadata
        toon_response: dict[str, Any] = {
            "format": "toon",
            "toon_content": toon_content,
        }

        # Preserve only whitelisted scalar metadata fields
        # Exclude dict/list types even if whitelisted to prevent:
        # 1. Data duplication (already in toon_content)
        # 2. Token explosion from nested structures
        # 3. Circular reference issues
        # 4. Inconsistent serialization behavior
        for key, value in result.items():
            if key in _METADATA_WHITELIST and isinstance(value, SCALAR_TYPES):
                toon_response[key] = value

        return toon_response

    except Exception as e:
        logger.warning(
            f"Failed to apply TOON format to result with keys "
            f"{list(result.keys())[:5]}{'...' if len(result) > 5 else ''}, "
            f"returning original JSON. Error: {e}",
            exc_info=True
        )
        return result


def attach_toon_content_to_response(result: dict[str, Any]) -> dict[str, Any]:
    """
    Apply TOON format to a response, keeping only scalar metadata.

    This delegates to apply_toon_format_to_response() to ensure consistent
    behaviour: toon_content contains the full data and only small scalar
    metadata fields are preserved alongside it. This prevents the token
    explosion that occurred when all original fields were kept next to
    toon_content.

    .. deprecated:: 1.10.5
        This function now behaves identically to
        ``apply_toon_format_to_response(result, "toon")``.
        Use that function directly instead. This function will be
        removed in version 2.0.0.

    Args:
        result: Original result dictionary from MCP tool

    Returns:
        Modified result dict with TOON content and whitelisted scalar metadata
    """
    warnings.warn(
        "attach_toon_content_to_response() is deprecated and will be removed in v2.0.0. "
        "Use apply_toon_format_to_response(result, 'toon') instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return apply_toon_format_to_response(result, "toon")
