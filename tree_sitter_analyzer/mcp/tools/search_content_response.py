"""Response and argument helpers for search_content."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .search_content_response_modes import (
    respond_count_only,
    respond_full,
    respond_grouped,
    respond_summary,
    respond_total_only,
)

ToonFormatter = Callable[[dict[str, Any]], dict[str, Any]]
ToonApplier = Callable[[dict[str, Any], str], dict[str, Any]]


def determine_requested_format(arguments: dict[str, Any]) -> str:
    """Return the requested search response mode."""
    if arguments.get("total_only", False):
        return "total_only"
    if arguments.get("count_only_matches", False):
        return "count_only"
    if arguments.get("summary_only", False):
        return "summary"
    if arguments.get("group_by_file", False):
        return "group_by_file"
    return "normal"


def resolve_max_count(arguments: dict[str, Any], fd_rg_utils: Any) -> int | None:
    """Clamp user-specified max_count to safe bounds."""
    max_count = arguments.get("max_count")
    if max_count is None:
        return None
    return fd_rg_utils.clamp_int(max_count, 1, fd_rg_utils.DEFAULT_RESULTS_LIMIT)


def build_rg_args(
    arguments: dict[str, Any],
    max_count: int | None,
    no_ignore: bool,
) -> dict[str, Any]:
    """Build shared ripgrep command keyword arguments."""
    return {
        "query": arguments["query"],
        "case": arguments.get("case", "smart"),
        "fixed_strings": bool(arguments.get("fixed_strings", False)),
        "word": bool(arguments.get("word", False)),
        "multiline": bool(arguments.get("multiline", False)),
        "include_globs": arguments.get("include_globs"),
        "exclude_globs": arguments.get("exclude_globs"),
        "follow_symlinks": bool(arguments.get("follow_symlinks", False)),
        "hidden": bool(arguments.get("hidden", False)),
        "no_ignore": no_ignore,
        "max_filesize": arguments.get("max_filesize"),
        "context_before": arguments.get("context_before"),
        "context_after": arguments.get("context_after"),
        "encoding": arguments.get("encoding"),
        "max_count": max_count,
        "timeout_ms": arguments.get("timeout_ms"),
        "files_from": None,
    }


def format_search_response(
    arguments: dict[str, Any],
    output_format: str,
    out: bytes,
    elapsed_ms: int,
    cache_key: str | None,
    *,
    cache: Any,
    file_output_manager: Any,
    fd_rg_utils: Any,
    attach_toon: ToonFormatter,
    apply_toon: ToonApplier,
) -> dict[str, Any] | int:
    """Dispatch successful rg output to the requested response mode."""
    if arguments.get("total_only", False):
        return respond_total_only(
            out, elapsed_ms, cache_key, arguments, cache, fd_rg_utils
        )
    if arguments.get("count_only_matches", False):
        return respond_count_only(
            out,
            elapsed_ms,
            output_format,
            cache_key,
            arguments,
            cache,
            fd_rg_utils,
            attach_toon,
        )

    matches, truncated = _parse_limited_matches(arguments, out, fd_rg_utils)
    return _format_match_response(
        matches,
        truncated,
        elapsed_ms,
        output_format,
        cache_key,
        arguments,
        cache,
        file_output_manager,
        fd_rg_utils,
        attach_toon,
        apply_toon,
    )


def _parse_limited_matches(
    arguments: dict[str, Any],
    out: bytes,
    fd_rg_utils: Any,
) -> tuple[list[dict[str, Any]], bool]:
    """Parse rg JSON output and apply match limits/path optimization."""
    matches = fd_rg_utils.parse_rg_json_lines_to_matches(out)
    matches, truncated = apply_limits(matches, arguments, fd_rg_utils)
    if arguments.get("optimize_paths", False) and matches:
        matches = fd_rg_utils.optimize_match_paths(matches)
    return matches, truncated


def _format_match_response(
    matches: list[dict[str, Any]],
    truncated: bool,
    elapsed_ms: int,
    output_format: str,
    cache_key: str | None,
    arguments: dict[str, Any],
    cache: Any,
    file_output_manager: Any,
    fd_rg_utils: Any,
    attach_toon: ToonFormatter,
    apply_toon: ToonApplier,
) -> dict[str, Any]:
    """Dispatch parsed matches to grouped, summary, or full response mode."""
    if arguments.get("group_by_file", False) and matches:
        return respond_grouped(
            matches,
            truncated,
            elapsed_ms,
            output_format,
            cache_key,
            arguments,
            cache,
            file_output_manager,
            fd_rg_utils,
            attach_toon,
        )
    if arguments.get("summary_only", False):
        return respond_summary(
            matches,
            truncated,
            elapsed_ms,
            output_format,
            cache_key,
            arguments,
            cache,
            file_output_manager,
            fd_rg_utils,
            attach_toon,
        )
    return respond_full(
        matches,
        truncated,
        elapsed_ms,
        output_format,
        cache_key,
        arguments,
        cache,
        file_output_manager,
        fd_rg_utils,
        apply_toon,
    )


def apply_limits(
    matches: list[dict[str, Any]],
    arguments: dict[str, Any],
    fd_rg_utils: Any,
) -> tuple[list[dict[str, Any]], bool]:
    """Truncate matches to user max_count or hard cap."""
    user_max = arguments.get("max_count")
    if user_max is not None and len(matches) > user_max:
        return matches[:user_max], True
    if len(matches) >= fd_rg_utils.MAX_RESULTS_HARD_CAP:
        return matches[: fd_rg_utils.MAX_RESULTS_HARD_CAP], True
    return matches, False
