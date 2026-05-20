"""Mode-specific response builders for search_content."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .search_content_agent_summary import (
    SearchAgentSummaryInput,
    build_agent_summary,
    count_match_files,
)
from .search_content_helpers import (
    build_next_steps,
    handle_output_and_cache,
    save_enriched_output,
)

ToonFormatter = Callable[[dict[str, Any]], dict[str, Any]]
ToonApplier = Callable[[dict[str, Any], str], dict[str, Any]]


def create_count_only_cache_key(
    cache: Any,
    arguments: dict[str, Any],
) -> str | None:
    """Create a count_only_matches cache key from a total_only query."""
    if not cache:
        return None
    count_only_args = arguments.copy()
    count_only_args.pop("total_only", None)
    count_only_args["count_only_matches"] = True
    cache_params = {
        k: v for k, v in count_only_args.items() if k not in ["query", "roots", "files"]
    }
    return cache.create_cache_key(
        query=arguments["query"], roots=arguments.get("roots", []), **cache_params
    )


def respond_total_only(
    out: bytes,
    elapsed_ms: int,
    cache_key: str | None,
    arguments: dict[str, Any],
    cache: Any,
    fd_rg_utils: Any,
) -> int:
    """Return only the total match count."""
    file_counts = fd_rg_utils.parse_rg_count_output(out)
    total_matches = file_counts.get("__total__", 0)

    if cache and cache_key:
        cache.set(cache_key, total_matches)
        count_key = create_count_only_cache_key(cache, arguments)
        if count_key:
            file_counts_copy = {
                k: v for k, v in file_counts.items() if k != "__total__"
            }
            cache.set(
                count_key,
                {
                    "success": True,
                    "count_only": True,
                    "total_matches": total_matches,
                    "file_counts": file_counts_copy,
                    "elapsed_ms": elapsed_ms,
                    "derived_from_total_only": True,
                },
            )

    return int(total_matches)


def respond_count_only(
    out: bytes,
    elapsed_ms: int,
    output_format: str,
    cache_key: str | None,
    arguments: dict[str, Any],
    cache: Any,
    fd_rg_utils: Any,
    attach_toon: ToonFormatter,
) -> dict[str, Any]:
    """Return per-file match counts."""
    file_counts = fd_rg_utils.parse_rg_count_output(out)
    total_matches = file_counts.pop("__total__", 0)
    result: dict[str, Any] = {
        "success": True,
        "count_only": True,
        "total_matches": total_matches,
        "file_counts": file_counts,
        "elapsed_ms": elapsed_ms,
        "agent_summary": build_agent_summary(
            SearchAgentSummaryInput(
                arguments=arguments,
                mode="count_only",
                count=len(file_counts),
                total_matches=total_matches,
                file_count=len(file_counts),
                truncated=False,
                elapsed_ms=elapsed_ms,
            )
        ),
    }
    if cache and cache_key:
        cache.set(cache_key, result)
    if output_format == "toon":
        return attach_toon(result)
    return result


def respond_grouped(
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
) -> dict[str, Any]:
    """Return matches organized by file."""
    result = fd_rg_utils.group_matches_by_file(matches)
    result["truncated"] = truncated
    result["elapsed_ms"] = elapsed_ms
    result["agent_summary"] = build_agent_summary(
        SearchAgentSummaryInput(
            arguments=arguments,
            mode="group_by_file",
            count=int(result.get("count", len(matches))),
            total_matches=len(matches),
            file_count=len(result.get("files", [])),
            truncated=truncated,
            elapsed_ms=elapsed_ms,
        )
    )

    suppressed = handle_output_and_cache(
        result, arguments, file_output_manager, cache, cache_key, output_format
    )
    if suppressed:
        return suppressed

    if output_format == "toon":
        return attach_toon(result)
    return result


def respond_summary(
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
) -> dict[str, Any]:
    """Return aggregated search statistics."""
    summary = fd_rg_utils.summarize_search_results(matches)
    result: dict[str, Any] = {
        "success": True,
        "count": len(matches),
        "truncated": truncated,
        "elapsed_ms": elapsed_ms,
        "summary": summary,
        "agent_summary": build_agent_summary(
            SearchAgentSummaryInput(
                arguments=arguments,
                mode="summary",
                count=len(matches),
                file_count=summary.get("total_files"),
                truncated=truncated,
                elapsed_ms=elapsed_ms,
            )
        ),
    }

    suppressed = handle_output_and_cache(
        result, arguments, file_output_manager, cache, cache_key, output_format
    )
    if suppressed:
        return suppressed

    if output_format == "toon":
        return attach_toon(result)
    return result


def respond_full(
    matches: list[dict[str, Any]],
    truncated: bool,
    elapsed_ms: int,
    output_format: str,
    cache_key: str | None,
    arguments: dict[str, Any],
    cache: Any,
    file_output_manager: Any,
    fd_rg_utils: Any,
    apply_toon: ToonApplier,
) -> dict[str, Any]:
    """Return full match details with optional next steps."""
    result: dict[str, Any] = {
        "success": True,
        "count": len(matches),
        "truncated": truncated,
        "elapsed_ms": elapsed_ms,
        "agent_summary": build_agent_summary(
            SearchAgentSummaryInput(
                arguments=arguments,
                mode="normal",
                count=len(matches),
                file_count=count_match_files(matches),
                truncated=truncated,
                elapsed_ms=elapsed_ms,
            )
        ),
        "results": matches,
    }

    if matches and not arguments.get("suppress_output", False):
        steps = build_next_steps(matches)
        if steps:
            result["next_steps"] = steps

    save_enriched_output(
        result, matches, arguments, output_format, file_output_manager, fd_rg_utils
    )

    suppressed = handle_output_and_cache(
        result, arguments, file_output_manager, cache, cache_key, output_format
    )
    if suppressed:
        return suppressed

    return apply_toon(result, output_format)
