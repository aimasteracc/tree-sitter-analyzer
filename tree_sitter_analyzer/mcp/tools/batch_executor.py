# Limits and validation for batch extraction operations
"""Batch execution logic for ReadPartialTool — extracted from read_partial_tool.py."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool
from .read_partial_helpers import build_batch_agent_summary

BATCH_LIMITS = {
    "max_files": 20,
    "max_sections_per_file": 50,
    "max_sections_total": 200,
    "max_total_bytes": 1024 * 1024,
    "max_total_lines": 5000,
    "max_file_size_bytes": 5 * 1024 * 1024,
}


# _validate_batch_top_level: implementation
def _validate_batch_top_level(arguments: dict[str, Any]) -> list[Any]:
    """Validate top-level batch arguments for mutual exclusivity."""
    requests = arguments.get("requests")
    single_keys = {"file_path", "start_line", "end_line", "start_column", "end_column"}
    if any(k in arguments for k in single_keys):
        raise ValueError(
            "requests is mutually exclusive with file_path/start_line/end_line/start_column/end_column"
        )
    if "output_file" in arguments or "suppress_output" in arguments:
        raise ValueError(
            "output_file/suppress_output are not supported with requests batch mode"
        )
    if not isinstance(requests, list):
        raise ValueError("requests must be a list")
    return requests


# _clamp_requests: implementation
def _clamp_requests(
    requests: list[Any], allow_truncate: bool
) -> tuple[list[Any], bool]:
    """Truncate request list to max_files limit if allow_truncate is set."""
    truncated = False
    if len(requests) > BATCH_LIMITS["max_files"]:
        if not allow_truncate:
            raise ValueError(
                f"Too many files in requests: {len(requests)} > max_files={BATCH_LIMITS['max_files']}"
            )
        requests = requests[: BATCH_LIMITS["max_files"]]
        truncated = True
    return requests, truncated


# Build a standard error result dict
def _make_error_result(
    file_path: str, resolved_path: str, error: str
) -> dict[str, Any]:
    """Build a standard error result dict for a file request."""
    return {
        "file_path": file_path,
        "resolved_path": resolved_path,
        "sections": [],
        "errors": [{"error": error}],
    }


# Validate a single file request within batch
def _validate_file_request(
    file_req: Any, fail_fast: bool, allow_truncate: bool
) -> tuple[str, list[Any], dict[str, Any] | None, bool]:
    """Validate a single file request. Returns (file_path, sections, error_result, truncated)."""
    if not isinstance(file_req, dict):
        if fail_fast:
            raise ValueError("Each requests[] entry must be an object")
        return "", [], _make_error_result("", "", "Invalid request entry"), False

    file_path = file_req.get("file_path")
    sections = file_req.get("sections")

    if not isinstance(file_path, str) or not file_path.strip():
        # Conditional check
        if fail_fast:
            raise ValueError("requests[].file_path must be a non-empty string")
        return (
            file_path or "",
            [],
            _make_error_result(file_path or "", "", "Invalid file_path"),
            False,
        )

    # Conditional check
    if not isinstance(sections, list):
        # Conditional check
        if fail_fast:
            raise ValueError("requests[].sections must be a list")
        return (
            file_path,
            [],
            _make_error_result(file_path, "", "Invalid sections"),
            False,
        )

    truncated = False
    # Conditional check
    if len(sections) > BATCH_LIMITS["max_sections_per_file"]:
        # Conditional check
        if not allow_truncate:
            # Conditional check
            if fail_fast:
                raise ValueError(
                    f"Too many sections for file {file_path}: {len(sections)} > max_sections_per_file={BATCH_LIMITS['max_sections_per_file']}"
                )
            return (
                file_path,
                [],
                _make_error_result(file_path, "", "Too many sections for file"),
                False,
            )
        sections = sections[: BATCH_LIMITS["max_sections_per_file"]]
        truncated = True

    return file_path, sections, None, truncated


# Resolve file path with security validation
def _resolve_file(
    tool: BaseMCPTool, file_path: str, fail_fast: bool
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve file path. Returns (resolved_path, error_result)."""
    # Error handling
    try:
        resolved = tool.resolve_and_validate_file_path(file_path)
    except ValueError as e:
        # Conditional check
        if fail_fast:
            raise
        return None, _make_error_result(file_path, "", str(e))

    p = Path(resolved)
    # Conditional check
    if not p.exists():
        msg = "Invalid file path: file does not exist"
        # Conditional check
        if fail_fast:
            raise ValueError(msg)
        return None, _make_error_result(file_path, resolved, msg)

    # Error handling
    try:
        # Conditional check
        if p.stat().st_size > BATCH_LIMITS["max_file_size_bytes"]:
            msg = f"File too large: {p.stat().st_size} > max_file_size_bytes={BATCH_LIMITS['max_file_size_bytes']}"
            # Conditional check
            if fail_fast:
                raise ValueError(msg)
            return None, _make_error_result(file_path, resolved, msg)
    except OSError as e:
        msg = f"Could not stat file: {e}"
        # Conditional check
        if fail_fast:
            raise ValueError(msg) from e
        return None, _make_error_result(file_path, resolved, msg)

    # Main batch execution loop
    return resolved, None


@dataclass
class _BatchAccumulator:
    """Running counters threaded through the batch loop.

    r37bt (dogfood): execute_batch was 172 lines critical. The doubly-
    nested loop (files → sections) mutated 5 counters as it went; passing
    them as a dataclass keeps the helper signatures clean without
    sacrificing visibility.
    """

    total_bytes: int = 0
    total_lines: int = 0
    ok_sections: int = 0
    sections_seen_total: int = 0
    error_count: int = 0
    truncated: bool = False


async def execute_batch(
    tool: BaseMCPTool,
    arguments: dict[str, Any],
    read_file_partial_fn: Callable[..., str | None],
) -> dict[str, Any]:
    """Batch mode for extracting multiple ranges from multiple files.

    r37bt (dogfood): tool flagged this at 172 lines. Refactor splits
    input validation + per-file processing + per-section processing +
    response assembly. Behaviour preserved (BATCH_LIMITS,
    allow_truncate/fail_fast semantics, content_format echo).
    """
    output_format = arguments.get("output_format", "toon")
    content_format = arguments.get("format", "text")
    allow_truncate = bool(arguments.get("allow_truncate", False))
    fail_fast = bool(arguments.get("fail_fast", False))

    requests = _validate_batch_top_level(arguments)
    requests, initial_truncated = _clamp_requests(requests, allow_truncate)
    acc = _BatchAccumulator(truncated=initial_truncated)
    results: list[dict[str, Any]] = []

    for file_req in requests:
        file_result = _process_file_request(
            file_req=file_req,
            tool=tool,
            acc=acc,
            fail_fast=fail_fast,
            allow_truncate=allow_truncate,
            content_format=content_format,
            read_file_partial_fn=read_file_partial_fn,
        )
        if file_result is not None:
            results.append(file_result)

    return _build_batch_response(results, acc, output_format, fail_fast=fail_fast)


def _process_file_request(
    *,
    file_req: Any,
    tool: BaseMCPTool,
    acc: _BatchAccumulator,
    fail_fast: bool,
    allow_truncate: bool,
    content_format: str,
    read_file_partial_fn: Callable[..., str | None],
) -> dict[str, Any] | None:
    """Validate one file request, resolve its path, then process every section."""
    file_path, sections, err_result, req_truncated = _validate_file_request(
        file_req, fail_fast, allow_truncate
    )
    if req_truncated:
        acc.truncated = True
    if err_result:
        acc.error_count += 1
        return err_result

    resolved, err_result = _resolve_file(tool, file_path, fail_fast)
    if err_result:
        acc.error_count += 1
        return err_result

    file_result: dict[str, Any] = {
        "file_path": file_path,
        "resolved_path": resolved,
        "sections": [],
        "errors": [],
    }
    for sec in sections:
        should_break = _process_one_section(
            section=sec,
            resolved=resolved,
            file_result=file_result,
            acc=acc,
            fail_fast=fail_fast,
            allow_truncate=allow_truncate,
            content_format=content_format,
            read_file_partial_fn=read_file_partial_fn,
        )
        if should_break:
            break
    return file_result


def _process_one_section(
    *,
    section: Any,
    resolved: str | None,
    file_result: dict[str, Any],
    acc: _BatchAccumulator,
    fail_fast: bool,
    allow_truncate: bool,
    content_format: str,
    read_file_partial_fn: Callable[..., str | None],
) -> bool:
    """Process one section. Return True when the caller should ``break``."""
    if not isinstance(section, dict):
        acc.error_count += 1
        file_result["errors"].append({"error": "Invalid section entry"})
        return fail_fast

    label = section.get("label")
    start_line = section.get("start_line")
    end_line = section.get("end_line")

    range_err = _validate_section_range(label, start_line, end_line)
    if range_err is not None:
        acc.error_count += 1
        file_result["errors"].append(range_err)
        return fail_fast

    acc.sections_seen_total += 1
    if acc.sections_seen_total > BATCH_LIMITS["max_sections_total"]:
        if not allow_truncate:
            raise ValueError(
                f"Too many sections in requests: "
                f"> max_sections_total={BATCH_LIMITS['max_sections_total']}"
            )
        acc.truncated = True
        return True

    content = read_file_partial_fn(resolved, start_line, end_line)
    if not content or content.strip() == "":
        acc.error_count += 1
        file_result["errors"].append(
            {
                "label": label,
                "error": (
                    f"Invalid line range or empty content: "
                    f"start_line={start_line}, end_line={end_line}"
                ),
            }
        )
        return fail_fast

    content_bytes = len(content.encode("utf-8"))
    content_lines = (
        max(0, end_line - start_line + 1)
        if end_line is not None
        else (len(content.split("\n")) if content else 0)
    )
    would_bytes = acc.total_bytes + content_bytes
    would_lines = acc.total_lines + content_lines
    if (
        would_bytes > BATCH_LIMITS["max_total_bytes"]
        or would_lines > BATCH_LIMITS["max_total_lines"]
    ):
        if not allow_truncate:
            raise ValueError(
                "Batch extract exceeds limits: "
                f"max_total_bytes={BATCH_LIMITS['max_total_bytes']}, "
                f"max_total_lines={BATCH_LIMITS['max_total_lines']}"
            )
        acc.truncated = True
        return True

    acc.total_bytes = would_bytes
    acc.total_lines = would_lines
    acc.ok_sections += 1

    section_result: dict[str, Any] = {
        "label": label,
        "range": {"start_line": start_line, "end_line": end_line},
        "content_length": len(content),
        "content": content,
    }
    # ``content_format`` is reserved for future raw-vs-rendered variants;
    # both modes currently emit the verbatim content.
    _ = content_format
    file_result["sections"].append(section_result)
    return False


def _validate_section_range(
    label: Any, start_line: Any, end_line: Any
) -> dict[str, Any] | None:
    """Return an error dict on bad start/end_line, else ``None``."""
    if not isinstance(start_line, int) or start_line < 1:
        return {"label": label, "error": "start_line must be an integer >= 1"}
    if end_line is not None and (
        not isinstance(end_line, int) or end_line < start_line
    ):
        return {"label": label, "error": "end_line must be an integer >= start_line"}
    return None


def _build_batch_response(
    results: list[dict[str, Any]],
    acc: _BatchAccumulator,
    output_format: str,
    *,
    fail_fast: bool,
) -> dict[str, Any]:
    """Compose the canonical batch envelope + apply TOON formatting.

    Success preserved exactly: ``ok_sections > 0 AND (no errors OR fail_fast
    disabled)``. fail_fast=True with any error sinks ``success`` to False
    so callers that opted into strict mode get the legacy strict envelope.
    """
    response: dict[str, Any] = {
        "success": acc.ok_sections > 0 and (acc.error_count == 0 or not fail_fast),
        "count_files": len(results),
        "count_sections": acc.ok_sections,
        "truncated": acc.truncated,
        "limits": dict(BATCH_LIMITS),
        "errors_summary": {"errors": acc.error_count},
        "agent_summary": build_batch_agent_summary(
            count_files=len(results),
            count_sections=acc.ok_sections,
            truncated=acc.truncated,
            error_count=acc.error_count,
        ),
        "results": results,
    }
    return apply_toon_format_to_response(response, output_format)
