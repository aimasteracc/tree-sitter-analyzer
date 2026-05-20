"""Severity helpers for analyze_differences."""

from collections.abc import Callable
from typing import Any

FieldSeverityFunc = Callable[[str, Any, Any], str]

BREAKING_FIELDS = {
    "capture_name",
    "node_type",
    "name",
    "type",
    "id",
    "start_line",
    "end_line",
    "start_column",
    "end_column",
}

PERFORMANCE_FIELDS = {
    "elapsed_ms",
    "execution_time",
    "fd_elapsed_ms",
    "rg_elapsed_ms",
    "processing_time",
    "duration",
}


def determine_field_severity(field_name: str, old_value: Any, new_value: Any) -> str:
    """Determine severity from a changed field name and values."""
    if field_name in BREAKING_FIELDS:
        return "high"
    if field_name in PERFORMANCE_FIELDS:
        return "low"
    if _is_removed_string_value(old_value, new_value):
        return "high"
    if _is_large_string_change(old_value, new_value):
        return "medium"
    return "medium"


def determine_severity(differences: list[dict[str, Any]]) -> str:
    """Determine overall severity from a difference list."""
    severities = {diff["severity"] for diff in differences}
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def _is_large_string_change(old_value: Any, new_value: Any) -> bool:
    return (
        isinstance(old_value, str)
        and isinstance(new_value, str)
        and len(old_value) > 0
        and abs(len(old_value) - len(new_value)) > len(old_value) * 0.5
    )


def _is_removed_string_value(old_value: Any, new_value: Any) -> bool:
    return (
        isinstance(old_value, str)
        and isinstance(new_value, str)
        and bool(old_value)
        and not new_value
    )
