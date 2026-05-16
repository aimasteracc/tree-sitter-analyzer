#!/usr/bin/env python3
"""
Shared helpers for search_content tool.

Extracted from the monolithic tool file to reduce duplication.
"""

import logging
from typing import Any

from ..utils.format_helper import (
    attach_toon_content_to_response,
    format_for_file_output,
)

logger = logging.getLogger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "roots": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Search dirs",
        },
        "files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific files",
        },
        "query": {
            "type": "string",
            "description": "Search pattern (regex or literal)",
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
            "description": "Include globs",
        },
        "exclude_globs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exclude globs",
        },
        "follow_symlinks": {"type": "boolean", "default": False},
        "hidden": {"type": "boolean", "default": False},
        "no_ignore": {"type": "boolean", "default": False},
        "max_filesize": {"type": "string"},
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
        "enable_parallel": {"type": "boolean", "default": True},
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
    "required": ["query"],
    "additionalProperties": False,
}


# handle_output_and_cache: implementation
def handle_output_and_cache(
    result: dict[str, Any],
    arguments: dict[str, Any],
    file_output_manager: Any,
    cache: Any,
    cache_key: str | None,
    output_format: str,
) -> dict[str, Any] | None:
    """Handle output_file, suppress_output, and caching.

    Returns a response dict if output is suppressed, None otherwise.
    Mutates result for file output. Caches the full result.
    """
    output_file = arguments.get("output_file")
    suppress_output = arguments.get("suppress_output", False)

    if output_file:
        return _handle_file_output(
            result,
            output_file,
            suppress_output,
            output_format,
            file_output_manager,
            cache,
            cache_key,
        )

    if suppress_output:
        _cache_result(cache, cache_key, result)
        return _make_minimal(result)

    _cache_result(cache, cache_key, result)
    return None


# _handle_file_output: implementation
def _handle_file_output(
    result: dict[str, Any],
    output_file: str,
    suppress_output: bool,
    output_format: str,
    file_output_manager: Any,
    cache: Any,
    cache_key: str | None,
) -> dict[str, Any] | None:
    """Save results to file and optionally suppress output."""
    try:
        formatted_content, _ = format_for_file_output(result, output_format)
        saved_path = file_output_manager.save_to_file(
            content=formatted_content, base_name=output_file
        )

        if suppress_output:
            _cache_result(cache, cache_key, result)
            minimal = {
                "success": result.get("success", True),
                "count": result.get("count", 0),
                "output_file": output_file,
                "file_saved": f"Results saved to {saved_path}",
            }
            if output_format == "toon":
                return attach_toon_content_to_response(minimal)
            return minimal

        result["output_file"] = output_file
        result["file_saved"] = f"Results saved to {saved_path}"
        _cache_result(cache, cache_key, result)
        logger.info(f"Search results saved to: {saved_path}")

    except Exception as e:
        logger.error(f"Failed to save output to file: {e}")
        result["file_save_error"] = str(e)
        result["file_saved"] = False

    return None


# _cache_result: implementation
def _cache_result(cache: Any, cache_key: str | None, result: dict[str, Any]) -> None:
    """Cache the result if cache and key are available."""
    # Conditional check
    if cache and cache_key:
        cache.set(cache_key, result)


# _make_minimal: implementation
def _make_minimal(result: dict[str, Any]) -> dict[str, Any]:
    """Create a minimal response for suppress_output mode."""
    minimal: dict[str, Any] = {
        "success": result.get("success", True),
        "count": result.get("count", 0),
    }
    # Conditional check
    if "summary" in result:
        minimal["summary"] = result["summary"]
    # Conditional check
    if "elapsed_ms" in result:
        minimal["elapsed_ms"] = result["elapsed_ms"]
    # Return result
    return minimal


# save_enriched_output: implementation
def save_enriched_output(
    result: dict[str, Any],
    matches: list[dict[str, Any]],
    arguments: dict[str, Any],
    output_format: str,
    file_output_manager: Any,
    fd_rg_utils: Any,
) -> None:
    """Save enriched search results to file, mutating result with status."""
    output_file = arguments.get("output_file")
    # Conditional check
    if not output_file:
        return
    # Error handling
    try:
        file_content = {
            "success": True,
            "count": len(matches),
            "truncated": result.get("truncated", False),
            "elapsed_ms": result.get("elapsed_ms", 0),
            "results": matches,
            "summary": fd_rg_utils.summarize_search_results(matches),
            "grouped_by_file": (
                fd_rg_utils.group_matches_by_file(matches)["files"] if matches else []
            ),
        }
        formatted_content, _ = format_for_file_output(file_content, output_format)
        saved_path = file_output_manager.save_to_file(
            content=formatted_content, base_name=output_file
        )
        result["output_file"] = output_file
        result["output_file_path"] = saved_path
        result["file_saved"] = True
        logger.info(f"Search results saved to: {saved_path}")
    except Exception as e:
        logger.error(f"Failed to save output to file: {e}")
        result["file_save_error"] = str(e)
        result["file_saved"] = False


# build_next_steps: implementation
def build_next_steps(matches: list[dict[str, Any]]) -> list[str]:
    """Build next_steps suggestions for AI agents."""
    files_with_matches: set[str] = set()
    # Loop iteration
    for m in matches:
        fp = m.get("path", {})
        # Conditional check
        if isinstance(fp, dict):
            fp = fp.get("text", "")
        # Conditional check
        if fp:
            files_with_matches.add(fp)

    steps: list[str] = []
    # Conditional check
    if len(files_with_matches) == 1:
        fp = next(iter(files_with_matches))
        steps.append(
            f"check_code_scale(file_path='{fp}') to understand file complexity"
        )
    elif len(files_with_matches) <= 3:
        steps.append("analyze_code_structure on matching files to understand context")
    # Conditional check
    if len(matches) > 5:
        steps.append("Add query filters or narrower patterns to reduce matches")
    # Return result
    return steps
