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
from .search_envelope import normalize_envelope

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
    agent_summary = build_agent_summary(
        SearchAgentSummaryInput(
            arguments=arguments,
            mode="count_only",
            count=len(file_counts),
            total_matches=total_matches,
            file_count=len(file_counts),
            truncated=False,
            elapsed_ms=elapsed_ms,
        )
    )
    result: dict[str, Any] = {
        "success": True,
        "count_only": True,
        "count": int(total_matches),
        "results": [],
        "total_matches": total_matches,
        "file_counts": file_counts,
        "elapsed_ms": elapsed_ms,
        "truncated": False,
        "agent_summary": agent_summary,
    }
    normalize_envelope(result, total_count=int(total_matches))
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
    real_total: int | None = None,
    total_count_known: bool = True,
) -> dict[str, Any]:
    """Return matches organized by file."""
    displayed = len(matches)
    total_for_envelope = real_total if real_total is not None else displayed
    result = fd_rg_utils.group_matches_by_file(matches)
    result["truncated"] = truncated
    result["elapsed_ms"] = elapsed_ms
    result["agent_summary"] = build_agent_summary(
        SearchAgentSummaryInput(
            arguments=arguments,
            mode="group_by_file",
            count=int(result.get("count", displayed)),
            total_matches=total_for_envelope,
            file_count=len(result.get("files", [])),
            truncated=truncated,
            elapsed_ms=elapsed_ms,
        )
    )
    normalize_envelope(result, total_count=total_for_envelope)
    _attach_total_count_metadata(
        result,
        displayed_count=displayed,
        real_total=real_total,
        total_count_known=total_count_known,
        truncated=truncated,
    )

    suppressed = handle_output_and_cache(
        result, arguments, file_output_manager, cache, cache_key, output_format
    )
    if suppressed:
        return normalize_envelope(suppressed)

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
    real_total: int | None = None,
    total_count_known: bool = True,
) -> dict[str, Any]:
    """Return aggregated search statistics."""
    summary = fd_rg_utils.summarize_search_results(matches)
    displayed = len(matches)
    total_for_envelope = real_total if real_total is not None else displayed
    result: dict[str, Any] = {
        "success": True,
        "count": displayed,
        "results": [],
        "truncated": truncated,
        "elapsed_ms": elapsed_ms,
        "summary": summary,
        "agent_summary": build_agent_summary(
            SearchAgentSummaryInput(
                arguments=arguments,
                mode="summary",
                count=displayed,
                file_count=summary.get("total_files"),
                truncated=truncated,
                elapsed_ms=elapsed_ms,
            )
        ),
    }
    normalize_envelope(result, total_count=total_for_envelope)
    _attach_total_count_metadata(
        result,
        displayed_count=displayed,
        real_total=real_total,
        total_count_known=total_count_known,
        truncated=truncated,
    )

    suppressed = handle_output_and_cache(
        result, arguments, file_output_manager, cache, cache_key, output_format
    )
    if suppressed:
        return normalize_envelope(suppressed)

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
    real_total: int | None = None,
    total_count_known: bool = True,
) -> dict[str, Any]:
    """Return full match details with optional next steps."""
    displayed = len(matches)
    total_for_envelope = real_total if real_total is not None else displayed
    result: dict[str, Any] = {
        "success": True,
        "count": displayed,
        "truncated": truncated,
        "elapsed_ms": elapsed_ms,
        "agent_summary": build_agent_summary(
            SearchAgentSummaryInput(
                arguments=arguments,
                mode="normal",
                count=displayed,
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
    normalize_envelope(result, total_count=total_for_envelope)
    _attach_total_count_metadata(
        result,
        displayed_count=displayed,
        real_total=real_total,
        total_count_known=total_count_known,
        truncated=truncated,
    )

    suppressed = handle_output_and_cache(
        result, arguments, file_output_manager, cache, cache_key, output_format
    )
    if suppressed:
        return normalize_envelope(suppressed)

    return apply_toon(result, output_format)


def _attach_total_count_metadata(
    result: dict[str, Any],
    *,
    displayed_count: int,
    real_total: int | None,
    total_count_known: bool,
    truncated: bool,
) -> None:
    """Attach H2 fix metadata for total_count under truncation.

    Adds fields:
    - ``total_count_known``: True when ``total_count`` is the real total.
      False when ripgrep truncated and the recount pass was skipped or
      exceeded its time budget.
    - ``total_count_at_least``: a lower bound (``displayed_count``) when
      the real total is unknown — callers can ``>=`` against this safely.
    """
    if not truncated:
        # Non-truncated responses already have honest total_count via envelope.
        result["total_count_known"] = True
        return
    result["total_count_known"] = bool(total_count_known)
    if not total_count_known:
        # When the real total is unknown, the envelope already mirrors
        # displayed_count into total_count. Surface the lower-bound name
        # explicitly so callers don't accidentally trust it as exact.
        result["total_count_at_least"] = displayed_count
        # Also overwrite total_count to be max(displayed_count, real_total).
        # Since real_total is unknown we leave total_count == displayed_count
        # but the new flag makes the uncertainty explicit.
