#!/usr/bin/env python3
"""
Shared helpers for find_and_grep tool.

Extracted from the monolithic tool file to reduce duplication.
"""

import logging
from dataclasses import dataclass
from typing import Any

from ..utils.format_helper import (
    attach_toon_content_to_response,
    format_for_file_output,
)
from .find_and_grep_agent_summary import build_agent_summary_from_meta

logger = logging.getLogger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "roots": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Search dirs. ['src/', 'tests/']",
        },
        "pattern": {
            "type": "string",
            "description": "Filename pattern. '*.{py,js}'",
        },
        "glob": {
            "type": "boolean",
            "default": False,
            "description": "Use glob syntax",
        },
        "types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "fd types: f/d/l/x",
        },
        "extensions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "File extensions, no dots",
        },
        "exclude": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exclude patterns",
        },
        "depth": {
            "type": "integer",
            "description": "Max search depth. 1=here only",
        },
        "follow_symlinks": {"type": "boolean", "default": False},
        "hidden": {"type": "boolean", "default": False},
        "no_ignore": {"type": "boolean", "default": False},
        "size": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Size filter: +10M, -1K",
        },
        "changed_within": {"type": "string", "description": "Modified within: 1d, 2h"},
        "changed_before": {"type": "string", "description": "Modified before"},
        "full_path_match": {"type": "boolean", "default": False},
        "file_limit": {
            "type": "integer",
            "description": "Max files before grep (def 2000)",
        },
        "sort": {
            "type": "string",
            "enum": ["path", "mtime", "size"],
        },
        "query": {
            "type": "string",
            "description": "Content search pattern (regex)",
        },
        "case": {
            "type": "string",
            "enum": ["smart", "insensitive", "sensitive"],
            "default": "smart",
        },
        "fixed_strings": {"type": "boolean", "default": False},
        "word": {"type": "boolean", "default": False},
        "multiline": {"type": "boolean", "default": False},
        "include_globs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Content include globs",
        },
        "exclude_globs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Content exclude globs",
        },
        "max_filesize": {"type": "string"},
        "encoding": {
            "type": "string",
            "description": "File encoding for ripgrep (e.g. 'utf-8', 'latin1')",
        },
        "context_before": {"type": "integer"},
        "context_after": {"type": "integer"},
        "max_count": {"type": "integer"},
        "timeout_ms": {"type": "integer"},
        "count_only_matches": {"type": "boolean", "default": False},
        "summary_only": {"type": "boolean", "default": False},
        "optimize_paths": {"type": "boolean", "default": False},
        "group_by_file": {"type": "boolean", "default": False},
        "total_only": {
            "type": "boolean",
            "default": False,
            "description": "Return only match count",
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
            "description": "If true with output_file, suppress detailed output",
        },
    },
    "required": ["roots", "query"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class FindAndGrepFullMatchContext:
    """State needed to build full, summary, or grouped match responses."""

    arguments: dict[str, Any]
    rg_out: bytes
    fd_elapsed_ms: int
    rg_elapsed_ms: int
    searched_file_count: int
    truncated_fd: bool
    output_format: str


@dataclass(frozen=True)
class FindAndGrepCountOnlyContext:
    """State needed to build a count-only find_and_grep response."""

    arguments: dict[str, Any]
    count_data: dict[str, int]
    output_format: str
    searched_file_count: int
    truncated: bool
    fd_elapsed_ms: int
    rg_elapsed_ms: int


@dataclass(frozen=True)
class FindAndGrepRgModeContext:
    """State needed after fd has produced candidate files."""

    arguments: dict[str, Any]
    files: list[str]
    fd_elapsed_ms: int
    truncated_fd: bool
    output_format: str


def build_missing_commands_response(
    missing_commands: list[str],
) -> dict[str, Any] | None:
    """Return an install hint when required fd/rg commands are missing."""
    if not missing_commands:
        return None
    return {
        "success": False,
        "error": f"Required commands not found: {', '.join(missing_commands)}. Please install fd and ripgrep.",
        "count": 0,
        "results": [],
    }


def build_search_meta(
    *,
    searched_file_count: int,
    truncated: bool,
    fd_elapsed_ms: int,
    rg_elapsed_ms: int,
    case: str | None = None,
) -> dict[str, Any]:
    """Build the shared metadata block for find_and_grep responses.

    ``elapsed_ms`` is the wall-clock sum of the fd and rg phases, exposed for
    consumers that just want a single timing number alongside the per-phase
    breakdown.

    ``case_sensitive`` is echoed as a strict ``bool`` (never ``None``):
    ``True`` only when ``case == "sensitive"``; ``False`` for ``"smart"``,
    ``"insensitive"``, ``None``/missing, or any other value. This makes the
    actually-honored case mode visible to callers (N1).
    """
    return {
        "searched_file_count": searched_file_count,
        "truncated": truncated,
        "fd_elapsed_ms": fd_elapsed_ms,
        "rg_elapsed_ms": rg_elapsed_ms,
        "elapsed_ms": int(fd_elapsed_ms) + int(rg_elapsed_ms),
        "case_sensitive": case == "sensitive",
    }


def build_empty_response(
    arguments: dict[str, Any],
    *,
    truncated: bool,
    fd_elapsed_ms: int,
) -> dict[str, Any]:
    """Build the response returned when fd finds no candidate files."""
    from .search_envelope import normalize_envelope

    meta = build_search_meta(
        searched_file_count=0,
        truncated=truncated,
        fd_elapsed_ms=fd_elapsed_ms,
        rg_elapsed_ms=0,
        case=arguments.get("case"),
    )
    result = {
        "success": True,
        "results": [],
        "count": 0,
        "meta": meta,
        "output_format": arguments.get("output_format", "toon"),
        "agent_summary": build_agent_summary_from_meta(
            arguments,
            mode="empty",
            count=0,
            meta=meta,
            file_count=0,
        ),
    }
    normalize_envelope(result, total_count=0)
    return result


def build_count_only_response(context: FindAndGrepCountOnlyContext) -> dict[str, Any]:
    """Build a count-only response from parsed ripgrep count output."""
    from .search_envelope import normalize_envelope

    file_counts = dict(context.count_data)
    total_matches = file_counts.pop("__total__", 0)
    meta = build_search_meta(
        searched_file_count=context.searched_file_count,
        truncated=context.truncated,
        fd_elapsed_ms=context.fd_elapsed_ms,
        rg_elapsed_ms=context.rg_elapsed_ms,
        case=context.arguments.get("case"),
    )
    result = {
        "success": True,
        "count_only": True,
        "count": int(total_matches),
        "results": [],
        "total_matches": total_matches,
        "file_counts": file_counts,
        "meta": meta,
        "output_format": context.output_format,
        "agent_summary": build_agent_summary_from_meta(
            context.arguments,
            mode="count_only",
            count=total_matches,
            total_matches=total_matches,
            meta=meta,
            file_count=len(file_counts),
        ),
    }
    normalize_envelope(result, total_count=int(total_matches))
    if context.output_format == "toon":
        return attach_toon_content_to_response(result)
    return result


def handle_output(
    result: dict[str, Any],
    arguments: dict[str, Any],
    file_output_manager: Any,
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Handle output_file and suppress_output logic.

    Returns a minimal result if suppress_output is triggered, None otherwise.
    Mutates result in-place for file output cases.
    """
    output_file = arguments.get("output_file")
    suppress_output = arguments.get("suppress_output", False)

    if output_file:
        return _handle_file_output(
            result,
            output_file,
            suppress_output,
            arguments,
            file_output_manager,
            matches,
        )

    if suppress_output:
        return _make_minimal(result, include_summary=True)

    return None


def _handle_file_output(
    result: dict[str, Any],
    output_file: str,
    suppress_output: bool,
    arguments: dict[str, Any],
    file_output_manager: Any,
    matches: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Handle saving results to a file."""
    output_format = arguments.get("output_format", "toon")

    try:
        # Build content for file output
        if arguments.get("summary_only", False):
            file_content = result
        elif matches:
            from . import fd_rg_utils

            file_content = {
                "success": True,
                "results": matches,
                "count": len(matches),
                "files": (
                    fd_rg_utils.group_matches_by_file(matches).get("files", [])
                    if matches
                    else []
                ),
                "summary": fd_rg_utils.summarize_search_results(matches),
                "meta": result.get("meta", {}),
                "agent_summary": result.get("agent_summary", {}),
            }
        else:
            file_content = result

        formatted_content, _ = format_for_file_output(file_content, output_format)
        saved_path = file_output_manager.save_to_file(
            content=formatted_content, base_name=output_file
        )

        if suppress_output:
            return {
                "success": result.get("success", True),
                "count": result.get("count", 0),
                "output_file": output_file,
                "file_saved": f"Results saved to {saved_path}",
                "agent_summary": result.get("agent_summary", {}),
            }

        result["output_file"] = output_file
        result["file_saved"] = f"Results saved to {saved_path}"
        logger.info(f"Search results saved to: {saved_path}")

    except Exception as e:
        logger.error(f"Failed to save output to file: {e}")
        result["file_save_error"] = str(e)
        result["file_saved"] = False

    return None


def _make_minimal(
    result: dict[str, Any], include_summary: bool = False
) -> dict[str, Any]:
    """Create a minimal response for suppress_output mode."""
    minimal: dict[str, Any] = {
        "success": result.get("success", True),
        "count": result.get("count", 0),
        "meta": result.get("meta", {}),
    }
    if include_summary:
        minimal["summary"] = result.get("summary", {})
    if "agent_summary" in result:
        minimal["agent_summary"] = result["agent_summary"]
    return minimal
