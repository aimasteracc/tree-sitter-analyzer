#!/usr/bin/env python3
"""JSON formatting helpers shared by MCP tools."""

import json
from collections.abc import Callable
from typing import Any


def format_as_json(data: Any) -> str:
    """Serialize data as readable UTF-8 JSON."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_output(data: dict[str, Any], output_format: str = "json") -> str:
    """Serialize a tool payload as JSON; the format argument is compatibility-only."""
    del output_format
    return format_as_json(data)


class JsonFormatter:
    """Simple JSON formatter implementing the shared formatter interface."""

    def format(self, data: Any) -> str:
        """Serialize data as readable UTF-8 JSON."""
        return format_as_json(data)


def get_formatter(output_format: str = "json") -> JsonFormatter:
    """Return the sole supported JSON formatter."""
    del output_format
    return JsonFormatter()


def apply_output_format(
    result: dict[str, Any],
    output_format: str = "json",
    return_formatted_string: bool = False,
) -> dict[str, Any] | str:
    """Return a response dict or its JSON representation."""
    if return_formatted_string:
        return format_output(result, output_format)
    return result


def apply_output_format_to_response(
    result: Any,  # noqa: ARG001 — intentionally permissive for legacy callers
    output_format: str = "json",
) -> Any:
    """Normalize every MCP response to the canonical JSON response shape."""
    if not isinstance(result, dict):
        return result
    if result.get("success") is True and "verdict" not in result:
        return {**result, "verdict": "INFO"}
    return result


def format_for_file_output(
    data: dict[str, Any], output_format: str = "json"
) -> tuple[str, str]:
    """Return JSON file content and the fixed ``.json`` extension."""
    del output_format
    return format_as_json(data), ".json"


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
    """Build all stable snapshot-validation failure envelopes."""

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

    return (
        {code: envelope(code) for code in DIFF_SNAPSHOT_PUBLISH_ERROR_CODES},
        envelope("DIFF_SNAPSHOT_VALIDATION_ERROR"),
    )
