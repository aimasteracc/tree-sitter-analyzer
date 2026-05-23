#!/usr/bin/env python3
"""Shared helpers for read_partial_tool — extracted schema and utility functions."""

import json
from pathlib import Path
from typing import Any

from ..utils.format_helper import format_for_file_output

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


def count_file_lines(file_path: str) -> int | None:
    """Count total newline-delimited lines in ``file_path``.

    Returns the line count (>= 0), or ``None`` if the file cannot be
    read (missing, unreadable, binary decode failure). Streams the file
    so it stays cheap even for large inputs.
    """
    path = Path(file_path)
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return None


def _resolve_range_state(
    start_line: int,
    end_line: int | None,
    file_lines: int | None,
) -> tuple[bool, bool, list[int] | None]:
    """Classify the requested range against the file's true line count.

    Returns ``(out_of_range, partial_range, clamped_to)``:
    - ``out_of_range`` — start_line is past EOF, nothing readable.
    - ``partial_range`` — start_line is in bounds but end_line is past
      EOF (caller asked for more than the file holds).
    - ``clamped_to`` — ``[start, eof_line]`` when partial overlap, else
      ``None``.
    """
    if file_lines is None or file_lines <= 0:
        # Unknown or empty file — only flag fully out-of-range when we
        # can be certain (file_lines == 0 with start_line >= 1).
        if file_lines == 0 and start_line >= 1:
            return True, False, None
        return False, False, None
    if start_line > file_lines:
        return True, False, None
    if end_line is not None and end_line > file_lines:
        return False, True, [start_line, file_lines]
    return False, False, None


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
    file_lines: int | None = None,
    out_of_range: bool = False,
    partial_range: bool = False,
    clamped_to: list[int] | None = None,
) -> dict[str, Any]:
    """Summarize a partial read for immediate agent decision-making.

    When ``out_of_range`` is True (the request lies entirely past EOF)
    or ``partial_range`` is True (the request extends past EOF), the
    summary surfaces the situation as an INPUT issue instead of a
    content judgment so an agent does not treat ``risk: low`` as a
    healthy read.
    """
    is_range_anomaly = out_of_range or partial_range
    risk = _summary_risk(lines_extracted, content_length, out_of_range=out_of_range)
    verdict = _summary_verdict(out_of_range, partial_range)
    summary: dict[str, Any] = {
        "risk": risk,
        "verdict": verdict,
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
        "next_step": _summary_next_step(
            risk,
            content_format,
            start_column,
            end_column,
            out_of_range=out_of_range,
            partial_range=partial_range,
            start_line=start_line,
            end_line=end_line,
            file_lines=file_lines,
        ),
        "suggested_tool": _summary_suggested_tool(
            risk, lines_extracted, out_of_range=out_of_range
        ),
        "stop_condition": _summary_stop_condition(
            risk, out_of_range=out_of_range, partial_range=partial_range
        ),
        "summary_line": _summary_line(
            start_line=start_line,
            end_line=end_line,
            lines_extracted=lines_extracted,
            content_length=content_length,
            file_lines=file_lines,
            out_of_range=out_of_range,
            partial_range=partial_range,
        ),
    }
    if is_range_anomaly:
        summary["out_of_range"] = out_of_range
        summary["partial_range"] = partial_range
        if clamped_to is not None:
            summary["clamped_to"] = clamped_to
    if file_lines is not None:
        summary["file_lines"] = file_lines
    return summary


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
        file_lines=result.get("file_lines"),
        out_of_range=bool(result.get("out_of_range", False)),
        partial_range=bool(result.get("partial_range", False)),
        clamped_to=result.get("clamped_to"),
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


def _summary_risk(
    lines_extracted: int,
    content_length: int,
    *,
    out_of_range: bool = False,
) -> str:
    # Out-of-range is an INPUT problem, not a content judgment. Keep
    # ``risk=low`` so it never reads as a "great result" but flag the
    # situation explicitly through ``verdict``/``out_of_range``.
    if out_of_range:
        return "low"
    if lines_extracted >= 200 or content_length >= 20_000:
        return "high"
    if lines_extracted >= 50 or content_length >= 5_000:
        return "medium"
    return "low"


def _summary_verdict(out_of_range: bool, partial_range: bool) -> str:
    # PM-fix (post-PL-A audit): align with _LEGAL_VERDICTS frozenset in
    # base_tool.py. Previously returned non-canonical "N/A" and "OK", which
    # failed test_every_tool_response_honours_envelope:
    #   N/A → NOT_FOUND (line range outside file)
    #   OK  → INFO (informational extraction success)
    #   WARN stays (already canonical).
    if out_of_range:
        return "NOT_FOUND"
    if partial_range:
        return "WARN"
    return "INFO"


def _summary_next_step(
    risk: str,
    content_format: str,
    start_column: int | None,
    end_column: int | None,
    *,
    out_of_range: bool = False,
    partial_range: bool = False,
    start_line: int | None = None,
    end_line: int | None = None,
    file_lines: int | None = None,
) -> str:
    if out_of_range:
        file_part = (
            f"file has {file_lines} lines"
            if file_lines is not None
            else "file is shorter"
        )
        suggested_end = (
            min(file_lines, 100) if file_lines is not None and file_lines >= 1 else 100
        )
        return (
            f"Range {start_line}-{end_line if end_line is not None else start_line} "
            f"is past EOF ({file_part}). Try start_line=1 end_line={suggested_end}."
        )
    if partial_range:
        file_part = (
            f"file ends at line {file_lines}"
            if file_lines is not None
            else "file ends earlier"
        )
        return (
            f"Requested range extends past EOF ({file_part}); "
            f"narrow end_line to {file_lines if file_lines is not None else 'the file length'} "
            f"or omit it to read to EOF."
        )
    if risk == "high":
        return "Narrow the range or use query_code for symbol-level context."
    if start_column is not None or end_column is not None:
        return "Use surrounding lines if the column slice lacks enough context."
    if content_format == "json":
        return "Use line metadata to choose the next exact range or query_code target."
    return (
        "Inspect the content, then use query_code or search_content for related code."
    )


def _summary_suggested_tool(
    risk: str, lines_extracted: int, *, out_of_range: bool = False
) -> str:
    if out_of_range:
        # Reading the start of the file is the natural recovery action.
        return "extract_code_section"
    if risk == "high":
        return "extract_code_section"
    if lines_extracted <= 25:
        return "query_code"
    return "search_content"


def _summary_stop_condition(
    risk: str, *, out_of_range: bool = False, partial_range: bool = False
) -> str:
    if out_of_range or partial_range:
        return "The requested range falls inside the file's actual line range."
    if risk == "high":
        return "A narrower extraction is below 200 lines and contains the target block."
    return "The extracted range contains the complete symbol or block needed."


def _summary_line(
    *,
    start_line: int,
    end_line: int | None,
    lines_extracted: int,
    content_length: int,
    file_lines: int | None,
    out_of_range: bool,
    partial_range: bool,
) -> str:
    """One-line human-readable summary for the agent."""
    range_str = (
        f"{start_line}-{end_line}" if end_line is not None else f"{start_line}-EOF"
    )
    file_part = f"file_lines={file_lines}" if file_lines is not None else "file_lines=?"
    if out_of_range:
        return f"partial_read empty range={range_str} {file_part} out_of_range=true"
    if partial_range:
        return (
            f"partial_read partial range={range_str} lines_extracted={lines_extracted} "
            f"{file_part} partial_range=true"
        )
    return (
        f"partial_read range={range_str} lines_extracted={lines_extracted} "
        f"chars={content_length}"
    )


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


# ---------------------------------------------------------------------------
# r37dp (dogfood): Lifted pure formatters from ReadPartialTool to shrink
# the class below the 500-line god_class threshold. These functions touch
# no ``self`` state — they only convert primitive args + dict payloads.
# ---------------------------------------------------------------------------


def format_partial_content(
    content: str,
    content_format: str,
    file_path: str,
    start_line: int,
    end_line: int | None,
    start_column: int | None,
    end_column: int | None,
    lines_extracted: int,
) -> Any:
    """Format extracted content as JSON-lines dict or text header + body.

    ``content_format="json"`` returns a structured ``{lines, metadata}``
    dict (delegates to ``format_partial_content_as_json_lines``);
    everything else returns the legacy ``--- Partial Read Result ---``
    text envelope with metadata header followed by a JSON dump of the
    range + content.
    """
    range_info = f"Line {start_line}"
    if end_line:
        range_info += f"-{end_line}"

    result_data = {
        "file_path": file_path,
        "range": {
            "start_line": start_line,
            "end_line": end_line,
            "start_column": start_column,
            "end_column": end_column,
        },
        "content": content,
        "content_length": len(content),
    }

    if content_format == "json":
        return format_partial_content_as_json_lines(
            content,
            file_path,
            start_line,
            end_line,
            start_column,
            end_column,
            lines_extracted,
        )

    json_output = json.dumps(result_data, indent=2, ensure_ascii=False)
    return (
        f"--- Partial Read Result ---\n"
        f"File: {file_path}\n"
        f"Range: {range_info}\n"
        f"Characters read: {len(content)}\n"
        f"{json_output}"
    )


def format_partial_content_as_json_lines(
    content: str,
    file_path: str,
    start_line: int,
    end_line: int | None,
    start_column: int | None,
    end_column: int | None,
    lines_extracted: int,
) -> dict[str, Any]:
    """Format content as a JSON line array with range metadata.

    Pads / truncates the line list to match ``lines_extracted`` when
    ``end_line`` is provided — agents always see the same shape they
    asked for, even on past-EOF reads.
    """
    lines = content.split("\n")
    if end_line and len(lines) > lines_extracted:
        lines = lines[:lines_extracted]
    elif end_line and len(lines) < lines_extracted:
        pad = lines_extracted - len(lines)
        lines.extend([""] * pad)
    return {
        "lines": lines,
        "metadata": {
            "file_path": file_path,
            "range": {
                "start_line": start_line,
                "end_line": end_line,
                "start_column": start_column,
                "end_column": end_column,
            },
            "content_length": len(content),
            "lines_count": len(lines),
        },
    }


def prepare_partial_save_content(
    content_format: str,
    content: str,
    result: dict[str, Any],
    file_path: str,
    output_format: str,
) -> str:
    """Prepare extracted content for file output based on ``content_format``.

    ``raw`` returns the body untouched. ``json`` wraps body + range
    metadata and emits either a TOON blob (when ``output_format=='toon'``)
    or pretty-printed JSON. Any other format falls back to the already-
    rendered ``result['partial_content_result']`` string.
    """
    if content_format == "raw":
        return content
    if content_format == "json":
        result_data = {
            "file_path": file_path,
            "range": result["range"],
            "content": content,
            "content_length": len(content),
        }
        if output_format == "toon":
            content_to_save, _ = format_for_file_output(result_data, "toon")
            return content_to_save
        return json.dumps(result_data, indent=2, ensure_ascii=False)
    return str(result.get("partial_content_result", content))


def apply_partial_file_output(
    *,
    result: dict[str, Any],
    file_path: str,
    content: str,
    content_format: str,
    output_format: str,
    output_file: str | None,
    file_output_manager: Any,
    logger: Any,
) -> None:
    """Persist extracted content to ``output_file`` when requested.

    No-op when ``output_file`` is falsy. On success, mutates ``result``
    with ``output_file_path`` + ``file_saved=True``. On failure, sets
    ``file_save_error`` + ``file_saved=False`` and logs the exception.
    Caller threads in its ``file_output_manager`` and ``logger`` so the
    helper stays dependency-light (no module-level globals).
    """
    if not output_file:
        return
    try:
        base_name = (
            output_file.strip()
            if output_file.strip()
            else Path(file_path).stem + "_extract"
        )
        content_to_save = prepare_partial_save_content(
            content_format, content, result, file_path, output_format
        )
        saved_file_path = file_output_manager.save_to_file(
            content=content_to_save, base_name=base_name
        )
        result["output_file_path"] = saved_file_path
        result["file_saved"] = True
        logger.info(f"Extract output saved to: {saved_file_path}")
    except Exception as e:
        logger.error(f"Failed to save output to file: {e}")
        result["file_save_error"] = str(e)
        result["file_saved"] = False
