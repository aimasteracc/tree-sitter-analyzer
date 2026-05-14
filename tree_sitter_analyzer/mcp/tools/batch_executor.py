"""Batch execution logic for ReadPartialTool — extracted from read_partial_tool.py."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

_BATCH_LIMITS = {
    "max_files": 20,
    "max_sections_per_file": 50,
    "max_sections_total": 200,
    "max_total_bytes": 1024 * 1024,
    "max_total_lines": 5000,
    "max_file_size_bytes": 5 * 1024 * 1024,
}


async def execute_batch(
    tool: BaseMCPTool,
    arguments: dict[str, Any],
    read_file_partial_fn: Callable[..., str | None],
) -> dict[str, Any]:
    """Batch mode for extracting multiple ranges from multiple files."""
    output_format = arguments.get("output_format", "toon")
    content_format = arguments.get("format", "text")
    allow_truncate = bool(arguments.get("allow_truncate", False))
    fail_fast = bool(arguments.get("fail_fast", False))
    requests = arguments.get("requests")

    single_keys = {
        "file_path",
        "start_line",
        "end_line",
        "start_column",
        "end_column",
    }
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

    truncated = False
    if len(requests) > _BATCH_LIMITS["max_files"]:
        if not allow_truncate:
            raise ValueError(
                f"Too many files in requests: {len(requests)} > max_files={_BATCH_LIMITS['max_files']}"
            )
        requests = requests[: _BATCH_LIMITS["max_files"]]
        truncated = True

    results: list[dict[str, Any]] = []
    total_bytes = 0
    total_lines = 0
    ok_sections = 0
    sections_seen_total = 0
    error_count = 0

    for file_req in requests:
        if not isinstance(file_req, dict):
            if fail_fast:
                raise ValueError("Each requests[] entry must be an object")
            results.append(
                {
                    "file_path": "",
                    "resolved_path": "",
                    "sections": [],
                    "errors": [{"error": "Invalid request entry"}],
                }
            )
            error_count += 1
            continue

        file_path = file_req.get("file_path")
        sections = file_req.get("sections")
        if not isinstance(file_path, str) or not file_path.strip():
            if fail_fast:
                raise ValueError("requests[].file_path must be a non-empty string")
            results.append(
                {
                    "file_path": file_path or "",
                    "resolved_path": "",
                    "sections": [],
                    "errors": [{"error": "Invalid file_path"}],
                }
            )
            error_count += 1
            continue
        if not isinstance(sections, list):
            if fail_fast:
                raise ValueError("requests[].sections must be a list")
            results.append(
                {
                    "file_path": file_path,
                    "resolved_path": "",
                    "sections": [],
                    "errors": [{"error": "Invalid sections"}],
                }
            )
            error_count += 1
            continue

        if len(sections) > _BATCH_LIMITS["max_sections_per_file"]:
            if not allow_truncate:
                if fail_fast:
                    raise ValueError(
                        f"Too many sections for file {file_path}: {len(sections)} > max_sections_per_file={_BATCH_LIMITS['max_sections_per_file']}"
                    )
                results.append(
                    {
                        "file_path": file_path,
                        "resolved_path": "",
                        "sections": [],
                        "errors": [{"error": "Too many sections for file"}],
                    }
                )
                error_count += 1
                continue
            sections = sections[: _BATCH_LIMITS["max_sections_per_file"]]
            truncated = True

        try:
            resolved = tool.resolve_and_validate_file_path(file_path)
        except ValueError as e:
            if fail_fast:
                raise
            results.append(
                {
                    "file_path": file_path,
                    "resolved_path": "",
                    "sections": [],
                    "errors": [{"error": str(e)}],
                }
            )
            error_count += 1
            continue

        p = Path(resolved)
        if not p.exists():
            msg = "Invalid file path: file does not exist"
            if fail_fast:
                raise ValueError(msg)
            results.append(
                {
                    "file_path": file_path,
                    "resolved_path": resolved,
                    "sections": [],
                    "errors": [{"error": msg}],
                }
            )
            error_count += 1
            continue

        try:
            if p.stat().st_size > _BATCH_LIMITS["max_file_size_bytes"]:
                msg = f"File too large: {p.stat().st_size} > max_file_size_bytes={_BATCH_LIMITS['max_file_size_bytes']}"
                if fail_fast:
                    raise ValueError(msg)
                results.append(
                    {
                        "file_path": file_path,
                        "resolved_path": resolved,
                        "sections": [],
                        "errors": [{"error": msg}],
                    }
                )
                error_count += 1
                continue
        except OSError as e:
            msg = f"Could not stat file: {e}"
            if fail_fast:
                raise ValueError(msg) from e
            results.append(
                {
                    "file_path": file_path,
                    "resolved_path": resolved,
                    "sections": [],
                    "errors": [{"error": msg}],
                }
            )
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
            if sections_seen_total > _BATCH_LIMITS["max_sections_total"]:
                if not allow_truncate:
                    raise ValueError(
                        f"Too many sections in requests: > max_sections_total={_BATCH_LIMITS['max_sections_total']}"
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
                would_bytes > _BATCH_LIMITS["max_total_bytes"]
                or would_lines > _BATCH_LIMITS["max_total_lines"]
            ):
                if not allow_truncate:
                    raise ValueError(
                        "Batch extract exceeds limits: "
                        f"max_total_bytes={_BATCH_LIMITS['max_total_bytes']}, max_total_lines={_BATCH_LIMITS['max_total_lines']}"
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
        "limits": {
            "max_files": _BATCH_LIMITS["max_files"],
            "max_sections_per_file": _BATCH_LIMITS["max_sections_per_file"],
            "max_sections_total": _BATCH_LIMITS["max_sections_total"],
            "max_total_bytes": _BATCH_LIMITS["max_total_bytes"],
            "max_total_lines": _BATCH_LIMITS["max_total_lines"],
            "max_file_size_bytes": _BATCH_LIMITS["max_file_size_bytes"],
        },
        "errors_summary": {"errors": error_count},
        "results": results,
    }

    return apply_toon_format_to_response(response, output_format)
