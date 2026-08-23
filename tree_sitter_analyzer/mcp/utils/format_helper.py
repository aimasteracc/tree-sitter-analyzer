#!/usr/bin/env python3
"""
Format Helper for MCP Tools

Provides utility functions for formatting MCP tool output in different formats
(JSON, TOON) with consistent behavior across all tools.
"""

import json
from collections.abc import Callable
from typing import Any

from ...utils import setup_logger

logger = setup_logger(__name__)


#: RFC-0012: the minimal scalar control surface an agent branches on WITHOUT
#: parsing the ``toon_content`` blob. Everything else in a TOON response is
#: recoverable from ``toon_content``, so under ``compact_only`` we keep only
#: these keys alongside the blob and drop the duplicated metadata.
#:
#: ``summary_line`` is included deliberately: the MCP boundary's
#: ``ensure_canonical_success_envelope`` re-populates it on every success
#: anyway (so dropping it is futile), it is a single cheap scalar, and it is
#: the highest-value one-line triage signal.
def reduce_to_control_surface(result: dict[str, Any]) -> dict[str, Any]:
    """Passthrough — TOON removed."""
    return result


def format_output(data: dict[str, Any], output_format: str = "json") -> str:
    """
    Format data according to the specified output format.

    Args:
        data: Dictionary data to format
        output_format: Output format ('json' or 'toon')

    Returns:
        Formatted string representation of the data
    """
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
    """Passthrough — TOON removed. Returns JSON."""
    return format_as_json(data)


def _get_formatter_for_toon() -> Any:
    """Passthrough — TOON removed. Returns JsonFormatter."""
    return JsonFormatter()


def get_formatter(output_format: str = "json") -> Any:
    """
    Get a formatter instance for the specified format.

    Args:
        output_format: Output format ('json' or 'toon')

    Returns:
        Formatter instance with format() method
    """
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
    content = format_as_json(data)
    extension = ".json"
    return content, extension


DIFF_SNAPSHOT_PUBLISH_ERROR_CODES: tuple[str, ...] = (
    "DIFF_SNAPSHOT_SOURCE_CHANGED",
    "DIFF_SNAPSHOT_EXPIRED",
    "DIFF_SNAPSHOT_ROOT_MISMATCH",
    "DIFF_SNAPSHOT_NOT_FOUND",
    "DIFF_SNAPSHOT_WRONG_THREAD",
    "DIFF_SNAPSHOT_IN_USE",
    "DIFF_SNAPSHOT_CAPACITY",
    "DIFF_SNAPSHOT_GIT_ERROR",
    "DIFF_SNAPSHOT_TIMEOUT",
    "DIFF_SNAPSHOT_ROOT_INVALID",
    "DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED",
    "DIFF_SNAPSHOT_UNSAFE_PATH",
    "DIFF_SNAPSHOT_INVALID_PATH",
    "DIFF_SNAPSHOT_SPECIAL_FILE",
    "DIFF_SNAPSHOT_UNSUPPORTED_INDEX",
    "DIFF_SNAPSHOT_UNSUPPORTED_FILTER",
    "DIFF_SNAPSHOT_UNSUPPORTED_MODE",
    "DIFF_SNAPSHOT_CAPTURE_ERROR",
    "DIFF_SNAPSHOT_CLEANUP_FAILED",
    "DIFF_SNAPSHOT_UNSAFE_TEMP",
)


def preformat_diff_snapshot_publish_errors(
    output_format: str,
    formatter: Callable[[dict[str, Any], str], dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Format every stable final-validation failure before validation runs."""

    def envelope(code: str) -> dict[str, Any]:
        return formatter(
            {
                "success": False,
                "verdict": "ERROR",
                "error_code": code,
                "error": code,
            },
            output_format,
        )

    errors = {code: envelope(code) for code in DIFF_SNAPSHOT_PUBLISH_ERROR_CODES}
    return errors, envelope("DIFF_SNAPSHOT_VALIDATION_ERROR")


def apply_toon_format_to_response(
    result: dict[str, Any],
    output_format: str = "json",
    *,
    compact_only: bool = False,
) -> dict[str, Any]:
    """Passthrough — TOON removed. Injects verdict=INFO on success responses."""
    is_dict = isinstance(result, dict)
    is_success = is_dict and result.get("success") is True
    no_verdict = is_dict and "verdict" not in result
    if is_dict and is_success and no_verdict:
        result = {**result, "verdict": "INFO"}
    return result


def attach_toon_content_to_response(result: dict[str, Any]) -> dict[str, Any]:
    """Passthrough — TOON removed."""
    return result
