"""AI-agent-friendly error recovery hints and error response builder."""

from typing import Any

from ..utils.error_sanitizer import (
    project_root_from_env,
    safe_error_message,
)

_ERROR_RECOVERY_HINTS: list[tuple[str, str, str, str]] = [
    (
        "not found",
        "file_not_found",
        "The file does not exist at the given path. Verify the path or use list_files to discover files.",
        "list_files",
    ),
    (
        "unsupported language",
        "language_unsupported",
        "The file extension is not recognized. Check supported languages with --show-supported-languages.",
        "",
    ),
    (
        "project root",
        "project_not_set",
        "Project root has not been set. Call set_project_path first.",
        "set_project_path",
    ),
    (
        "outside project boundary",
        "security_violation",
        "The file is outside the project boundary. Use a path relative to the project root.",
        "",
    ),
    (
        "required",
        "missing_parameter",
        "A required parameter is missing. Check the tool schema and provide all required fields.",
        "",
    ),
    (
        "must be",
        "validation_error",
        "A parameter has an invalid value. Check the tool schema for valid options.",
        "",
    ),
    (
        "memory",
        "resource_exhausted",
        "The operation ran out of memory. Try analyzing a smaller scope or use suppress_output=true.",
        "",
    ),
    (
        "timed out",
        "timeout",
        "The operation timed out. Try reducing the scope (limit, max_count) or targeting a specific file.",
        "",
    ),
]


def build_agent_friendly_error(tool_name: str, error: Exception) -> dict[str, Any]:
    """Build an error response that tells the AI agent exactly what to do next."""
    msg = str(error).lower()
    error_type = type(error).__name__

    category = "unknown"
    recovery_hint = "Review the error message and adjust your request."
    suggested_tool = ""

    for pattern, cat, hint, tool in _ERROR_RECOVERY_HINTS:
        if pattern in msg:
            category = cat
            recovery_hint = hint
            suggested_tool = tool
            break

    body: dict[str, Any] = {
        "success": False,
        "error": safe_error_message(error, project_root_from_env()),
        "error_type": error_type,
        "error_category": category,
        "recovery_hint": recovery_hint,
    }
    if suggested_tool:
        body["suggested_tool"] = suggested_tool
    return body
