# Limits and validation for batch extraction operations
"""Batch execution logic for ReadPartialTool — extracted from read_partial_tool.py."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

BATCH_LIMITS = {
    "max_files": 20,
    "max_sections_per_file": 50,
    "max_sections_total": 200,
    "max_total_bytes": 1024 * 1024,
    "max_total_lines": 5000,
    "max_file_size_bytes": 5 * 1024 * 1024,
}


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
        if fail_fast:
            raise ValueError("requests[].file_path must be a non-empty string")
        return (
            file_path or "",
            [],
            _make_error_result(file_path or "", "", "Invalid file_path"),
            False,
        )

    if not isinstance(sections, list):
        if fail_fast:
            raise ValueError("requests[].sections must be a list")
        return (
            file_path,
            [],
            _make_error_result(file_path, "", "Invalid sections"),
            False,
        )

    truncated = False
    if len(sections) > BATCH_LIMITS["max_sections_per_file"]:
        if not allow_truncate:
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
    try:
        resolved = tool.resolve_and_validate_file_path(file_path)
    except ValueError as e:
        if fail_fast:
            raise
        return None, _make_error_result(file_path, "", str(e))

    p = Path(resolved)
    if not p.exists():
        msg = "Invalid file path: file does not exist"
        if fail_fast:
            raise ValueError(msg)
        return None, _make_error_result(file_path, resolved, msg)

    try:
        if p.stat().st_size > BATCH_LIMITS["max_file_size_bytes"]:
            msg = f"File too large: {p.stat().st_size} > max_file_size_bytes={BATCH_LIMITS['max_file_size_bytes']}"
            if fail_fast:
                raise ValueError(msg)
            return None, _make_error_result(file_path, resolved, msg)
    except OSError as e:
        msg = f"Could not stat file: {e}"
        if fail_fast:
            raise ValueError(msg) from e
        return None, _make_error_result(file_path, resolved, msg)

    # Main batch execution loop
    return resolved, None


async def execute_batch(
    tool: BaseMCPTool,
    arguments: dict[str, Any],
    read_file_partial_fn: Callable[..., str | None],
) -> dict[str, Any]:
    """Execute batch extraction: validate, resolve, read, and aggregate results."""
    """Batch mode for extracting multiple ranges from multiple files."""
    output_format = arguments.get("output_format", "toon")
    content_format = arguments.get("format", "text")
    allow_truncate = bool(arguments.get("allow_truncate", False))
    fail_fast = bool(arguments.get("fail_fast", False))

    requests = _validate_batch_top_level(arguments)
    requests, truncated = _clamp_requests(requests, allow_truncate)

    results: list[dict[str, Any]] = []
    total_bytes = 0
    total_lines = 0
    ok_sections = 0
    sections_seen_total = 0
    error_count = 0

    for file_req in requests:
        file_path, sections, err_result, req_truncated = _validate_file_request(
            file_req, fail_fast, allow_truncate
        )
        if req_truncated:
            truncated = True
        if err_result:
            results.append(err_result)
            error_count += 1
            continue

        resolved, err_result = _resolve_file(tool, file_path, fail_fast)
        if err_result:
            results.append(err_result)
            error_count += 1
            continue

        file_result: dict[str, Any] = {
            "file_path": file_path,
            "resolved_path": resolved,
            "sections": [],
            "errors": [],
        }

        for sec in sections:
            if not isinstance(sec, dict):
                error_count += 1
                file_result["errors"].append({"error": "Invalid section entry"})
                if fail_fast:
                    break
                continue

            label = sec.get("label")
            start_line = sec.get("start_line")
            end_line = sec.get("end_line")
            if not isinstance(start_line, int) or start_line < 1:
                error_count += 1
                file_result["errors"].append(
                    {"label": label, "error": "start_line must be an integer >= 1"}
                )
                if fail_fast:
                    break
                continue
            if end_line is not None and (
                not isinstance(end_line, int) or end_line < start_line
            ):
                error_count += 1
                file_result["errors"].append(
                    {
                        "label": label,
                        "error": "end_line must be an integer >= start_line",
                    }
                )
                if fail_fast:
                    break
                continue

            sections_seen_total += 1
            if sections_seen_total > BATCH_LIMITS["max_sections_total"]:
                if not allow_truncate:
                    raise ValueError(
                        f"Too many sections in requests: > max_sections_total={BATCH_LIMITS['max_sections_total']}"
                    )
                truncated = True
                break

            content = read_file_partial_fn(resolved, start_line, end_line)
            if not content or content.strip() == "":
                error_count += 1
                file_result["errors"].append(
                    {
                        "label": label,
                        "error": f"Invalid line range or empty content: start_line={start_line}, end_line={end_line}",
                    }
                )
                if fail_fast:
                    break
                continue

            content_bytes = len(content.encode("utf-8"))
            content_lines = len(content.split("\n")) if content else 0
            if end_line is not None:
                content_lines = max(0, end_line - start_line + 1)

            would_bytes = total_bytes + content_bytes
            would_lines = total_lines + content_lines
            if (
                would_bytes > BATCH_LIMITS["max_total_bytes"]
                or would_lines > BATCH_LIMITS["max_total_lines"]
            ):
                if not allow_truncate:
                    raise ValueError(
                        "Batch extract exceeds limits: "
                        f"max_total_bytes={BATCH_LIMITS['max_total_bytes']}, max_total_lines={BATCH_LIMITS['max_total_lines']}"
                    )
                truncated = True
                break

            total_bytes = would_bytes
            total_lines = would_lines
            ok_sections += 1

            section_result: dict[str, Any] = {
                "label": label,
                "range": {"start_line": start_line, "end_line": end_line},
                "content_length": len(content),
            }
            if content_format == "raw":
                section_result["content"] = content
            else:
                section_result["content"] = content

            file_result["sections"].append(section_result)

        results.append(file_result)

    response: dict[str, Any] = {
        "success": ok_sections > 0 and (error_count == 0 or not fail_fast),
        "count_files": len(results),
        "count_sections": ok_sections,
        "truncated": truncated,
        "limits": dict(BATCH_LIMITS),
        "errors_summary": {"errors": error_count},
        "results": results,
    }

    return apply_toon_format_to_response(response, output_format)




