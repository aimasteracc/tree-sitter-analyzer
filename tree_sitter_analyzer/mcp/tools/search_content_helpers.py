#!/usr/bin/env python3
"""
Shared helpers for search_content tool.

Extracted from the monolithic tool file to reduce duplication.
"""

import logging
import time
from pathlib import Path
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
        "extensions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "File extensions (no dots) to limit search to",
        },
        "encoding": {
            "type": "string",
            "description": "File encoding for ripgrep (e.g. 'utf-8', 'latin1')",
        },
        "follow_symlinks": {"type": "boolean", "default": False},
        "hidden": {
            "type": "boolean",
            "default": False,
            "description": (
                "Search hidden files/directories (rg --hidden). Default: skip them. "
                "(Previously this flag silently did nothing — see RG_FD_GAP_AUDIT.md.)"
            ),
        },
        "no_ignore": {"type": "boolean", "default": False},
        "max_filesize": {"type": "string"},
        "context_before": {"type": "integer", "description": "rg -B N"},
        "context_after": {"type": "integer", "description": "rg -A N"},
        "context": {
            "type": "integer",
            "description": (
                "Lines of context on BOTH sides (rg -C N). "
                "Ignored if context_before or context_after is set."
            ),
        },
        "max_count": {
            "type": "integer",
            "description": (
                "Maximum matches to list in normal mode (default 50). "
                "When exceeded, response includes total_matches, listed_cap, "
                "and a next_step narrowing hint. Raise for a deeper sweep."
            ),
        },
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
        # rg native power flags (RG_FD_GAP_AUDIT.md). All default to off
        # so existing callers see identical behavior; agents opt in.
        "file_types": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "rg built-in type filters (-t TYPE). E.g. ['py','rs'] is "
                "cleaner than -g '*.py' -g '*.rs'. Run `rg --type-list` "
                "to see the 100+ built-in types."
            ),
        },
        "exclude_types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "rg type exclusions (-T TYPE). Inverse of file_types.",
        },
        "files_with_matches": {
            "type": "boolean",
            "default": False,
            "description": (
                "Return only filenames that contain a match (rg -l). "
                "10-100× smaller output than full match content — "
                "use when you only need 'which files mention X'."
            ),
        },
        "only_matching": {
            "type": "boolean",
            "default": False,
            "description": (
                "Print only the matched substring (rg -o), one per line. "
                "Useful for symbol/identifier extraction."
            ),
        },
        "pcre2": {
            "type": "boolean",
            "default": False,
            "description": (
                "Use PCRE2 engine (rg -P) to enable lookahead/lookbehind, "
                "named groups, backreferences, and atomic groups. Required for "
                "regex like (?<!\\.)await\\b."
            ),
        },
        "max_depth": {
            "type": "integer",
            "description": "Limit directory recursion depth (rg --max-depth N).",
        },
        "sort": {
            "type": "string",
            "enum": ["path", "modified", "accessed", "created", "none"],
            "description": (
                "Sort result order (rg --sort). 'path' gives deterministic "
                "output — preferred for test stability and diff-friendly output."
            ),
        },
        "invert_match": {
            "type": "boolean",
            "default": False,
            "description": (
                "Return lines that do NOT match the pattern (rg -v). "
                "Pair with files_with_matches to find 'files without X'."
            ),
        },
        "include_stats": {
            "type": "boolean",
            "default": False,
            "description": (
                "Append rg --stats summary (files searched, bytes scanned, "
                "duration). Cheap diagnostic for 'did we actually scan what we expected'."
            ),
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
    "required": ["query"],
    "additionalProperties": False,
}


async def run_search(
    path_resolver: Any,
    arguments: dict[str, Any],
    rg_args: dict[str, Any],
    roots: list[str] | None,
    files: list[str] | None,
    max_count: int | None,
    fd_rg_utils: Any,
) -> tuple[int, bytes, bytes, int]:
    """Execute ripgrep in file, single-root, or parallel-root mode."""
    search_roots = _prepare_search_roots(
        path_resolver, arguments, rg_args, roots, files
    )
    count_only_matches = bool(arguments.get("count_only_matches", False)) or bool(
        arguments.get("total_only", False)
    )
    timeout_ms = arguments.get("timeout_ms")
    use_parallel = should_use_parallel(arguments, search_roots)

    started = time.time()
    if use_parallel and search_roots is not None:
        rc, out, err = await _run_parallel_search(
            search_roots,
            count_only_matches,
            timeout_ms,
            max_count,
            rg_args,
            fd_rg_utils,
        )
    else:
        rc, out, err = await _run_single_search(
            search_roots, count_only_matches, timeout_ms, rg_args, fd_rg_utils
        )

    elapsed_ms = int((time.time() - started) * 1000)
    return rc, out, err, elapsed_ms


def should_use_parallel(
    arguments: dict[str, Any], search_roots: list[str] | None
) -> bool:
    """Return whether the search should fan out across root chunks."""
    return (
        search_roots is not None
        and len(search_roots) > 1
        and arguments.get("enable_parallel", True)
    )


def _prepare_search_roots(
    path_resolver: Any,
    arguments: dict[str, Any],
    rg_args: dict[str, Any],
    roots: list[str] | None,
    files: list[str] | None,
) -> list[str] | None:
    """Convert explicit files into parent search roots and include globs."""
    if not files:
        return roots

    parent_dirs: set[str] = set()
    file_globs: list[str] = []
    for file_path in files:
        resolved = path_resolver.resolve(file_path)
        parent_dirs.add(str(Path(resolved).parent))
        escaped = Path(resolved).name.replace("[", "[[]").replace("]", "[]]")
        file_globs.append(escaped)

    if not arguments.get("include_globs"):
        arguments["include_globs"] = []
    arguments["include_globs"].extend(file_globs)
    rg_args["include_globs"] = arguments["include_globs"]
    return list(parent_dirs)


async def _run_parallel_search(
    search_roots: list[str],
    count_only_matches: bool,
    timeout_ms: int | None,
    max_count: int | None,
    rg_args: dict[str, Any],
    fd_rg_utils: Any,
) -> tuple[int, bytes, bytes]:
    """Execute rg against root chunks and merge results."""
    root_chunks = fd_rg_utils.split_roots_for_parallel_processing(
        search_roots, max_chunks=4
    )
    commands = [
        fd_rg_utils.build_rg_command(
            roots=chunk, count_only_matches=count_only_matches, **rg_args
        )
        for chunk in root_chunks
    ]
    results = await fd_rg_utils.run_parallel_rg_searches(
        commands, timeout_ms=timeout_ms, max_concurrent=4
    )
    return fd_rg_utils.merge_rg_results(results, count_only_matches)


async def _run_single_search(
    search_roots: list[str] | None,
    count_only_matches: bool,
    timeout_ms: int | None,
    rg_args: dict[str, Any],
    fd_rg_utils: Any,
) -> tuple[int, bytes, bytes]:
    """Execute rg once and return raw process output."""
    cmd = fd_rg_utils.build_rg_command(
        roots=search_roots,
        count_only_matches=count_only_matches,
        **rg_args,
    )
    return await fd_rg_utils.run_command_capture(cmd, timeout_ms=timeout_ms)


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
            if "agent_summary" in result:
                minimal["agent_summary"] = result["agent_summary"]
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
    # Conditional check
    if "agent_summary" in result:
        minimal["agent_summary"] = result["agent_summary"]
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
            "agent_summary": result.get("agent_summary"),
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
    return steps
