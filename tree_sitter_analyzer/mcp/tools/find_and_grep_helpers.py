#!/usr/bin/env python3
"""
Shared helpers for find_and_grep tool.

Extracted from the monolithic tool file to reduce duplication.
"""

import logging
from typing import Any

from ..utils.format_helper import format_for_file_output

logger = logging.getLogger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "roots": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Dirs to search. E.g. ['src/', 'tests/']",
        },
        "pattern": {
            "type": "string",
            "description": "[FILE] Filename pattern. E.g. '*.py'",
        },
        "glob": {
            "type": "boolean",
            "default": False,
            "description": "[FILE] Treat pattern as glob",
        },
        "types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "[FILE] Types: f=files, d=dirs, l=symlinks, x=executable",
        },
        "extensions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "[FILE] Extensions (no dots). E.g. ['py', 'js']",
        },
        "exclude": {
            "type": "array",
            "items": {"type": "string"},
            "description": "[FILE] Exclude patterns",
        },
        "depth": {
            "type": "integer",
            "description": "[FILE] Max depth. 1=current only",
        },
        "follow_symlinks": {
            "type": "boolean",
            "default": False,
            "description": "[FILE] Follow symlinks",
        },
        "hidden": {
            "type": "boolean",
            "default": False,
            "description": "[FILE] Include hidden files",
        },
        "no_ignore": {
            "type": "boolean",
            "default": False,
            "description": "[FILE] Ignore .gitignore",
        },
        "size": {
            "type": "array",
            "items": {"type": "string"},
            "description": "[FILE] Size filter. E.g. '+10M', '-1K'",
        },
        "changed_within": {
            "type": "string",
            "description": "[FILE] Modified within. E.g. '1d', '2h'",
        },
        "changed_before": {
            "type": "string",
            "description": "[FILE] Modified before. Same format",
        },
        "full_path_match": {
            "type": "boolean",
            "default": False,
            "description": "[FILE] Match full path, not just filename",
        },
        "file_limit": {
            "type": "integer",
            "description": "[FILE] Max files before content search (def 2000)",
        },
        "sort": {
            "type": "string",
            "enum": ["path", "mtime", "size"],
            "description": "[FILE] Sort: path|mtime|size",
        },
        "query": {
            "type": "string",
            "description": "[CONTENT] Text pattern to search (literal or regex)",
        },
        "case": {
            "type": "string",
            "enum": ["smart", "insensitive", "sensitive"],
            "default": "smart",
            "description": "[CONTENT] Case: smart|insensitive|sensitive",
        },
        "fixed_strings": {
            "type": "boolean",
            "default": False,
            "description": "[CONTENT] Literal match, not regex",
        },
        "word": {
            "type": "boolean",
            "default": False,
            "description": "[CONTENT] Whole-word match only",
        },
        "multiline": {
            "type": "boolean",
            "default": False,
            "description": "[CONTENT] Allow multi-line matches",
        },
        "include_globs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "[CONTENT] Include patterns. E.g. ['*.py']",
        },
        "exclude_globs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "[CONTENT] Exclude patterns. E.g. ['*.log']",
        },
        "max_filesize": {
            "type": "string",
            "description": "[CONTENT] Max file size. E.g. '10M'",
        },
        "context_before": {
            "type": "integer",
            "description": "[CONTENT] Lines before match",
        },
        "context_after": {
            "type": "integer",
            "description": "[CONTENT] Lines after match",
        },
        "encoding": {
            "type": "string",
            "description": "[CONTENT] File encoding. E.g. 'utf-8'",
        },
        "max_count": {
            "type": "integer",
            "description": "[CONTENT] Max matches per file",
        },
        "timeout_ms": {
            "type": "integer",
            "description": "[CONTENT] Timeout in ms",
        },
        "count_only_matches": {
            "type": "boolean",
            "default": False,
            "description": "EXCLUSIVE: match counts per file",
        },
        "summary_only": {
            "type": "boolean",
            "default": False,
            "description": "EXCLUSIVE: condensed overview",
        },
        "optimize_paths": {
            "type": "boolean",
            "default": False,
            "description": "EXCLUSIVE: compress paths (10-30% saving)",
        },
        "group_by_file": {
            "type": "boolean",
            "default": False,
            "description": "EXCLUSIVE: group by file, dedupe paths",
        },
        "total_only": {
            "type": "boolean",
            "default": False,
            "description": "EXCLUSIVE: single count number. Top priority.",
        },
        "output_file": {
            "type": "string",
            "description": "Save output to file",
        },
        "suppress_output": {
            "type": "boolean",
            "default": False,
            "description": "Suppress response when output_file set",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
            "description": "'toon' (default, ~60% smaller) or 'json'",
        },
    },
    "required": ["roots", "query"],
    "additionalProperties": False,
}


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
        if matches:
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
    return minimal
