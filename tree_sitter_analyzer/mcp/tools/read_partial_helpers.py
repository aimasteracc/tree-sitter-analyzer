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


def build_agent_summary(
    *,
    file_path: str,
    start_line: int,
    end_line: int | None,
    start_column: int | None,
    end_column: int | None,
    content_length: int,
    lines_extracted: int,
    content_format: str,
    output_file: str | None = None,
    suppress_output: bool = False,
) -> dict[str, Any]:
    """Summarize a partial read for immediate agent decision-making."""
    risk = _summary_risk(lines_extracted, content_length)
    return {
        "risk": risk,
        "file_path": file_path,
        "range": {
            "start_line": start_line,
            "end_line": end_line or start_line,
            "start_column": start_column,
            "end_column": end_column,
        },
        "lines_extracted": lines_extracted,
        "content_length": content_length,
        "content_format": content_format,
        "output_saved": bool(output_file),
        "suppress_output": suppress_output,
        "next_step": _summary_next_step(risk, content_format, start_column, end_column),
        "suggested_tool": _summary_suggested_tool(risk, lines_extracted),
        "stop_condition": _summary_stop_condition(risk),
    }


def build_agent_summary_for_result(
    result: dict[str, Any],
    content_format: str,
    output_file: str | None = None,
    suppress_output: bool = False,
) -> dict[str, Any]:
    """Build an agent summary from the standard partial-read result envelope."""
    range_info = result["range"]
    return build_agent_summary(
        file_path=result["file_path"],
        start_line=range_info["start_line"],
        end_line=range_info["end_line"],
        start_column=range_info["start_column"],
        end_column=range_info["end_column"],
        content_length=result["content_length"],
        lines_extracted=result["lines_extracted"],
        content_format=content_format,
        output_file=output_file,
        suppress_output=suppress_output,
    )


def build_batch_agent_summary(
    *,
    count_files: int,
    count_sections: int,
    truncated: bool,
    error_count: int,
) -> dict[str, Any]:
    """Summarize a batch partial read for immediate agent decision-making."""
    risk = _batch_summary_risk(count_sections, truncated, error_count)
    return {
        "risk": risk,
        "mode": "batch",
        "count_files": count_files,
        "count_sections": count_sections,
        "truncated": truncated,
        "error_count": error_count,
        "next_step": _batch_next_step(risk, truncated, error_count),
        "suggested_tool": "extract_code_section" if risk == "high" else "query_code",
        "stop_condition": _batch_stop_condition(risk),
    }


def _summary_risk(lines_extracted: int, content_length: int) -> str:
    if lines_extracted >= 200 or content_length >= 20_000:
        return "high"
    if lines_extracted >= 50 or content_length >= 5_000:
        return "medium"
    return "low"


def _summary_next_step(
    risk: str,
    content_format: str,
    start_column: int | None,
    end_column: int | None,
) -> str:
    if risk == "high":
        return "Narrow the range or use query_code for symbol-level context."
    if start_column is not None or end_column is not None:
        return "Use surrounding lines if the column slice lacks enough context."
    if content_format == "json":
        return "Use line metadata to choose the next exact range or query_code target."
    return (
        "Inspect the content, then use query_code or search_content for related code."
    )


def _summary_suggested_tool(risk: str, lines_extracted: int) -> str:
    if risk == "high":
        return "extract_code_section"
    if lines_extracted <= 25:
        return "query_code"
    return "search_content"


def _summary_stop_condition(risk: str) -> str:
    if risk == "high":
        return "A narrower extraction is below 200 lines and contains the target block."
    return "The extracted range contains the complete symbol or block needed."


def _batch_summary_risk(count_sections: int, truncated: bool, error_count: int) -> str:
    if truncated or error_count:
        return "high"
    if count_sections > 20:
        return "medium"
    return "low"


def _batch_next_step(risk: str, truncated: bool, error_count: int) -> str:
    if truncated:
        return "Split the batch into smaller requests or enable narrower sections."
    if error_count:
        return "Fix invalid batch entries, then rerun only failed sections."
    if risk == "medium":
        return "Inspect the highest-value sections first, then narrow follow-up reads."
    return "Use the extracted sections to continue with query_code or search_content."


def _batch_stop_condition(risk: str) -> str:
    if risk == "high":
        return "The batch completes without truncation or validation errors."
    return "All requested sections are available for the current task."
