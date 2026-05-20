#!/usr/bin/env python3
"""Shared helpers for list_files_tool — extracted schema and output handling."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import apply_toon_format_to_response, format_for_file_output
from . import fd_rg_utils

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CountResponseContext:
    lines: list[str]
    elapsed_ms: int
    arguments: dict[str, Any]
    limit: int
    project_root: str | None


@dataclass(frozen=True)
class DetailedResponseContext:
    lines: list[str]
    elapsed_ms: int
    arguments: dict[str, Any]
    limit: int
    no_ignore: bool
    effective_types: list[str] | None
    project_root: str | None


# JSON Schema: input validation for list_files tool
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # Required: directories to search in
        "roots": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Search dirs",
        },
        # Filename pattern (supports glob if glob=true)
        "pattern": {
            "type": "string",
            "description": "Filename pattern",
        },
        # Treat pattern as a glob expression
        "glob": {"type": "boolean", "default": False},
        # File type filter: f=file, d=dir, l=symlink, x=executable
        "types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "fd types: f/d/l/x",
        },
        # File extensions without dots (e.g., ["py", "js"])
        "extensions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "File extensions, no dots",
        },
        # Exclude patterns for filtering
        "exclude": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exclude patterns",
        },
        # Maximum search depth (1 = current directory only)
        "depth": {"type": "integer", "description": "Max depth. 1=here only"},
        # Follow symbolic links during traversal
        "follow_symlinks": {"type": "boolean", "default": False},
        # Include hidden files (dotfiles)
        "hidden": {"type": "boolean", "default": False},
        # Bypass .gitignore rules
        "no_ignore": {"type": "boolean", "default": False},
        # Size filter expressions: +10M, -1K, etc.
        "size": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Size filter: +10M, -1K",
        },
        # Time-based filters for file modification
        "changed_within": {"type": "string"},
        "changed_before": {"type": "string"},
        # Match against full path instead of filename
        "full_path_match": {"type": "boolean", "default": False},
        # Return absolute paths
        "absolute": {"type": "boolean", "default": True},
        # Maximum number of results to return
        "limit": {"type": "integer"},
        # Return only the count, not the file list
        "count_only": {"type": "boolean", "default": False},
        # Token-efficient toon format by default
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
    },
    # roots is the only required field
    "required": ["roots"],
    "additionalProperties": False,
}


# build_query_info: implementation
def build_query_info(
    arguments: dict[str, Any], limit: int, no_ignore: bool
) -> dict[str, Any]:
    return {
        "roots": arguments.get("roots", []),
        "pattern": arguments.get("pattern"),
        "glob": arguments.get("glob", False),
        "types": arguments.get("types"),
        "extensions": arguments.get("extensions"),
        "exclude": arguments.get("exclude"),
        "depth": arguments.get("depth"),
        "follow_symlinks": arguments.get("follow_symlinks", False),
        "hidden": arguments.get("hidden", False),
        "no_ignore": no_ignore,
        "size": arguments.get("size"),
        "changed_within": arguments.get("changed_within"),
        "changed_before": arguments.get("changed_before"),
        "full_path_match": arguments.get("full_path_match", False),
        "absolute": arguments.get("absolute", True),
        "limit": limit,
    }


def _missing_fd_response() -> dict[str, Any]:
    return {
        "success": False,
        "error": "fd command not found. Please install fd (https://github.com/sharkdp/fd) to use this tool.",
        "count": 0,
        "results": [],
    }


def _build_fd_command(
    arguments: dict[str, Any],
    roots: list[str],
    limit: int,
    effective_types: list[str] | None,
    no_ignore: bool,
) -> list[str]:
    """Build the fd command from validated list_files arguments."""
    return fd_rg_utils.build_fd_command(
        pattern=arguments.get("pattern"),
        glob=bool(arguments.get("glob", False)),
        types=effective_types,
        extensions=arguments.get("extensions"),
        exclude=arguments.get("exclude"),
        depth=arguments.get("depth"),
        follow_symlinks=bool(arguments.get("follow_symlinks", False)),
        hidden=bool(arguments.get("hidden", False)),
        no_ignore=no_ignore,
        size=arguments.get("size"),
        changed_within=arguments.get("changed_within"),
        changed_before=arguments.get("changed_before"),
        full_path_match=bool(arguments.get("full_path_match", False)),
        absolute=True,
        limit=limit,
        roots=roots,
    )


def _decode_lines(output: bytes) -> list[str]:
    """Decode command output into non-empty stripped lines."""
    return [
        line.strip()
        for line in output.decode("utf-8", errors="replace").splitlines()
        if line.strip()
    ]


def _resolve_effective_types(arguments: dict[str, Any]) -> list[str] | None:
    """Determine effective fd type filter from arguments."""
    effective_types = arguments.get("types")
    if effective_types is None and arguments.get("extensions"):
        return ["f"]
    return effective_types


def _respond_count_only(context: CountResponseContext) -> dict[str, Any]:
    """Return count-only response with optional file output."""
    total_count = min(len(context.lines), fd_rg_utils.MAX_RESULTS_HARD_CAP)
    truncated = len(context.lines) > fd_rg_utils.MAX_RESULTS_HARD_CAP

    result: dict[str, Any] = {
        "success": True,
        "count_only": True,
        "total_count": total_count,
        "truncated": truncated,
        "elapsed_ms": context.elapsed_ms,
        "agent_summary": _build_agent_summary(
            count=total_count,
            truncated=truncated,
            count_only=True,
            limit=context.limit,
            no_ignore=False,
        ),
    }

    file_response = _save_count_output(
        context.project_root, context.arguments, context.limit, result
    )
    if _is_suppressed_file_response(file_response):
        return file_response
    result.update(file_response)

    output_format = context.arguments.get("output_format", "toon")
    return apply_toon_format_to_response(result, output_format)


def _respond_detailed(context: DetailedResponseContext) -> dict[str, Any]:
    """Return detailed file listing with metadata and optional file output."""
    lines = context.lines
    truncated = len(lines) > fd_rg_utils.MAX_RESULTS_HARD_CAP
    if truncated:
        lines = lines[: fd_rg_utils.MAX_RESULTS_HARD_CAP]

    results = _parse_fd_output(lines, context.effective_types)

    final_result: dict[str, Any] = {
        "success": True,
        "count": len(results),
        "truncated": truncated,
        "elapsed_ms": context.elapsed_ms,
        "agent_summary": _build_agent_summary(
            count=len(results),
            truncated=truncated,
            count_only=False,
            limit=context.limit,
            no_ignore=context.no_ignore,
        ),
        "results": results,
    }

    file_response = _save_detailed_output(
        context.project_root,
        context.arguments,
        context.limit,
        context.no_ignore,
        final_result,
    )
    if _is_suppressed_file_response(file_response):
        return file_response
    final_result.update(file_response)

    output_format = context.arguments.get("output_format", "toon")
    return apply_toon_format_to_response(final_result, output_format)


def _save_count_output(
    project_root: str | None,
    arguments: dict[str, Any],
    limit: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Save count-only output and return response additions."""
    output_file = arguments.get("output_file")
    if not output_file:
        return {}
    file_content = {
        "count_only": True,
        "total_count": result["total_count"],
        "truncated": result["truncated"],
        "elapsed_ms": result["elapsed_ms"],
        "query_info": build_query_info(arguments, limit, False),
    }
    saved = _save_to_file(project_root, file_content, output_file, arguments)
    if not saved:
        return {"output_file_error": "Failed to save output file"}
    if arguments.get("suppress_output", False):
        return _suppressed_count_response(result, saved)
    return {"output_file": saved}


def _save_detailed_output(
    project_root: str | None,
    arguments: dict[str, Any],
    limit: int,
    no_ignore: bool,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Save detailed output and return response additions."""
    output_file = arguments.get("output_file")
    if not output_file:
        return {}
    file_content = {
        "count": result["count"],
        "truncated": result["truncated"],
        "elapsed_ms": result["elapsed_ms"],
        "results": result["results"],
        "query_info": build_query_info(arguments, limit, no_ignore),
    }
    saved = _save_to_file(project_root, file_content, output_file, arguments)
    if not saved:
        return {"output_file_error": "Failed to save output file"}
    if arguments.get("suppress_output", False):
        return _suppressed_detailed_response(result, saved)
    return {"output_file": saved}


def _save_to_file(
    project_root: str | None,
    content: dict[str, Any],
    output_file: str,
    arguments: dict[str, Any],
) -> str | None:
    """Save content to output file via FileOutputManager."""
    try:
        output_format = arguments.get("output_format", "toon")
        formatted, _ = format_for_file_output(content, output_format)
        manager = FileOutputManager(project_root)
        return manager.save_to_file(content=formatted, base_name=output_file)
    except Exception as e:
        logger.warning(f"Failed to save output file: {e}")
        return None


def _suppressed_count_response(result: dict[str, Any], saved: str) -> dict[str, Any]:
    return {
        "success": True,
        "count_only": True,
        "total_count": result["total_count"],
        "output_file": saved,
        "message": f"Count results saved to {saved}",
        "agent_summary": result["agent_summary"],
    }


def _suppressed_detailed_response(result: dict[str, Any], saved: str) -> dict[str, Any]:
    return {
        "success": True,
        "count": result["count"],
        "output_file": saved,
        "message": f"File list results saved to {saved}",
        "agent_summary": result["agent_summary"],
    }


def _is_suppressed_file_response(response: dict[str, Any]) -> bool:
    return bool(response.get("message"))


def _parse_fd_output(
    lines: list[str], effective_types: list[str] | None
) -> list[dict[str, Any]]:
    """Parse fd output lines into structured results with file metadata."""
    types_only_files = effective_types == ["f"]
    return [
        result
        for path in lines
        if (result := _parse_fd_path(path, types_only_files)) is not None
    ]


def _parse_fd_path(path: str, types_only_files: bool) -> dict[str, Any] | None:
    """Parse one fd output path."""
    try:
        path_obj = Path(path)
        is_dir = False if types_only_files else path_obj.is_dir()
        size_bytes, mtime = _file_metadata(path, is_dir)
        return {
            "path": path,
            "is_dir": is_dir,
            "size_bytes": size_bytes,
            "mtime": mtime,
            "ext": path_obj.suffix[1:] if path_obj.suffix else None,
        }
    except (OSError, ValueError):
        return None


def _file_metadata(path: str, is_dir: bool) -> tuple[int | None, int | None]:
    """Return size and mtime for files, leaving directories empty."""
    if is_dir:
        return None, None
    try:
        stat_result = os.stat(path)
        return stat_result.st_size, int(stat_result.st_mtime)
    except (OSError, ValueError):
        return None, None


def _build_agent_summary(
    *,
    count: int,
    truncated: bool,
    count_only: bool,
    limit: int,
    no_ignore: bool,
) -> dict[str, Any]:
    """Summarize list_files output for immediate agent decision-making."""
    risk = _summary_risk(count, truncated, limit)
    return {
        "risk": risk,
        "result_count": count,
        "truncated": truncated,
        "count_only": count_only,
        "limit": limit,
        "next_step": _summary_next_step(count, truncated, count_only, limit),
        "suggested_tool": _summary_suggested_tool(count, truncated, count_only, limit),
        "stop_condition": _summary_stop_condition(count, truncated, limit),
        "no_ignore": no_ignore,
    }


def _summary_risk(count: int, truncated: bool, limit: int) -> str:
    if truncated or count >= limit:
        return "high"
    if count == 0:
        return "low"
    if count > 100:
        return "medium"
    return "low"


def _summary_next_step(
    count: int, truncated: bool, count_only: bool, limit: int
) -> str:
    if truncated or count >= limit:
        return "Narrow list_files with pattern, extensions, depth, or exclude filters."
    if count == 0:
        return "Broaden roots or pattern, or use search_content when looking for text."
    if count_only:
        return "Run list_files without count_only for a focused file list."
    return "Open the most relevant files with smart_context or read_partial."


def _summary_suggested_tool(
    count: int, truncated: bool, count_only: bool, limit: int
) -> str:
    if truncated or count >= limit:
        return "list_files"
    if count == 0:
        return "search_content"
    if count_only:
        return "list_files"
    return "smart_context"


def _summary_stop_condition(count: int, truncated: bool, limit: int) -> str:
    if truncated or count >= limit:
        return "Result count is below the limit and small enough to inspect."
    if count == 0:
        return "A broader query returns candidate files or confirms no matches."
    return "Relevant files are identified for the current task."
