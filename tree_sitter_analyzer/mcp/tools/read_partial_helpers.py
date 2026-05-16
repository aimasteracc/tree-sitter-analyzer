#!/usr/bin/env python3
"""Shared helpers for read_partial_tool — extracted schema and utility functions."""

from typing import Any

# JSON Schema: input validation for extract_code_section tool
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # Batch mode: multiple ranges/files (exclusive with file_path)
        "requests": {
            "type": "array",
            "description": "Batch: multiple ranges/files (exclusive with file_path)",
            "items": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "start_line": {"type": "integer", "minimum": 1},
                                "end_line": {"type": "integer", "minimum": 1},
                                "label": {"type": "string"},
                            },
                            "required": ["start_line"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["file_path", "sections"],
                "additionalProperties": False,
            },
        },
        # Single-file extraction parameters
        "file_path": {"type": "string"},
        "start_line": {"type": "integer", "minimum": 1},
        "end_line": {"type": "integer", "minimum": 1},
        "start_column": {"type": "integer", "minimum": 0},
        "end_column": {"type": "integer", "minimum": 0},
        # Output format options
        "format": {
            "type": "string",
            "enum": ["text", "json", "raw"],
            "default": "text",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
        "output_file": {
            "type": "string",
            "description": "Optional filename to save output to file",
        },
        "suppress_output": {
            "type": "boolean",
            "default": False,
            "description": "Suppress detailed output when output_file is provided",
        },
        "allow_truncate": {"type": "boolean", "default": False},
        "fail_fast": {"type": "boolean", "default": False},
    },
    "additionalProperties": False,
}


# Format extracted content into standard response envelope
def build_read_response(
    file_path: str,
    content: str,
    start_line: int,
    end_line: int | None,
    start_column: int | None,
    end_column: int | None,
    resolved_path: str,
    line_count: int,
    truncated: bool,
) -> dict[str, Any]:
    """Build the standard response for a partial read result."""
    response: dict[str, Any] = {
        "success": True,
        "file_path": file_path,
        "resolved_path": resolved_path,
        "start_line": start_line,
        "end_line": end_line or start_line,
        "line_count": line_count,
        "content": content,
        "truncated": truncated,
    }
    if start_column is not None:
        response["start_column"] = start_column
    if end_column is not None:
        response["end_column"] = end_column
    return response


# Validate line range arguments
def validate_line_range(
    start_line: Any, end_line: Any, start_column: Any, end_column: Any
) -> str | None:
    """Validate line/column ranges. Returns error message or None."""
    if not isinstance(start_line, int) or start_line < 1:
        return "start_line must be a positive integer"
    if end_line is not None and (not isinstance(end_line, int) or end_line < 1):
        return "end_line must be a positive integer or omitted"
    if start_column is not None and (
        not isinstance(start_column, int) or start_column < 0
    ):
        return "start_column must be a non-negative integer or omitted"
    if end_column is not None and (not isinstance(end_column, int) or end_column < 0):
        return "end_column must be a non-negative integer or omitted"
    if end_line is not None and end_line < start_line:
        return "end_line must be >= start_line"
    if (
        end_column is not None
        and start_column is not None
        and end_column < start_column
    ):
        return "end_column must be >= start_column"
    return None


# Build error response for validation failures
def build_validation_error(field: str, message: str) -> dict[str, Any]:
    """Build a standard error response for input validation failures."""
    return {
        "success": False,
        "error": f"Validation error: {message}",
        "field": field,
    }
