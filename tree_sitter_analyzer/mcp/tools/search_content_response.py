"""Response and argument helpers for search_content."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from .search_content_response_modes import (
    respond_count_only,
    respond_full,
    respond_grouped,
    respond_summary,
    respond_total_only,
)

logger = logging.getLogger(__name__)

# Time budget for the follow-up rg --count-matches pass that resolves the
# real pre-truncation total. If a single recount run takes longer than this,
# fall back to ``total_count_known=False`` and ``total_count_at_least``.
RECOUNT_BUDGET_MS = 500

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
    """Build shared ripgrep command keyword arguments.

    The new ``file_types`` / ``exclude_types`` / ``files_with_matches`` /
    ``only_matching`` / ``context`` / ``pcre2`` / ``max_depth`` / ``sort`` /
    ``invert_match`` / ``include_stats`` agent inputs are passed through
    here. ``build_rg_command`` defaults them to off when absent, so
    omitting them keeps backward compat.
    """
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
        # rg-native power flags (RG_FD_GAP_AUDIT.md Phase 1+2).
        "file_types": arguments.get("file_types"),
        "exclude_types": arguments.get("exclude_types"),
        "files_with_matches": bool(arguments.get("files_with_matches", False)),
        "only_matching": bool(arguments.get("only_matching", False)),
        "context": arguments.get("context"),
        "pcre2": bool(arguments.get("pcre2", False)),
        "max_depth": arguments.get("max_depth"),
        "sort": arguments.get("sort"),
        "invert_match": bool(arguments.get("invert_match", False)),
        "include_stats": bool(arguments.get("include_stats", False)),
    }


async def format_search_response(
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
    rg_args: dict[str, Any] | None = None,
    roots: list[str] | None = None,
    files: list[str] | None = None,
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
    if arguments.get("files_with_matches", False):
        # rg -l output is plain text (one file path per line), NOT JSON.
        # Bypass parse_rg_json_lines_to_matches which would return [].
        return _respond_files_with_matches(
            out, elapsed_ms, cache_key, arguments, cache, output_format, apply_toon
        )

    matches, truncated = _parse_limited_matches(arguments, out, fd_rg_utils)

    # H2 fix: ripgrep's --max-count truncates server-side per file, and the
    # tool's apply_limits truncates again globally. When truncated, the only
    # honest pre-truncation count is via a follow-up rg --count-matches run.
    real_total, total_count_known = await _resolve_real_total(
        truncated=truncated,
        displayed_count=len(matches),
        rg_args=rg_args,
        roots=roots,
        files=files,
        fd_rg_utils=fd_rg_utils,
    )

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
        real_total=real_total,
        total_count_known=total_count_known,
    )


async def _resolve_real_total(
    *,
    truncated: bool,
    displayed_count: int,
    rg_args: dict[str, Any] | None,
    roots: list[str] | None,
    files: list[str] | None,
    fd_rg_utils: Any,
) -> tuple[int, bool]:
    """Return (real_total, total_count_known) for a search response.

    When not truncated, real_total == displayed_count and known=True.

    When truncated, run a fresh rg --count-matches pass (no max_count) to
    learn the true count. If that pass exceeds RECOUNT_BUDGET_MS we drop
    back to displayed_count + total_count_known=False.
    """
    if not truncated:
        return displayed_count, True

    if rg_args is None:
        # No rg_args supplied (legacy callers): be honest about uncertainty.
        return displayed_count, False

    try:
        recount_args = dict(rg_args)
        # Drop the per-file cap that caused truncation in the first place.
        recount_args["max_count"] = None
        # Mirror search_content_tool._run_search file-vs-roots routing.
        if files:
            recount_roots = sorted({str(_parent_dir(f)) for f in files})
        else:
            recount_roots = roots or []

        cmd = fd_rg_utils.build_rg_command(
            roots=recount_roots,
            count_only_matches=True,
            **{k: v for k, v in recount_args.items() if k != "files_from"},
            files_from=None,
        )
        started = time.perf_counter()
        rc, out_bytes, _err = await fd_rg_utils.run_command_capture(
            cmd, timeout_ms=RECOUNT_BUDGET_MS
        )
        recount_ms = int((time.perf_counter() - started) * 1000)

        if rc not in (0, 1):
            logger.debug(
                "Recount pass failed (rc=%s, %sms); dropping to estimate.",
                rc,
                recount_ms,
            )
            return displayed_count, False

        if recount_ms > RECOUNT_BUDGET_MS:
            logger.debug(
                "Recount pass exceeded budget (%sms > %sms); using estimate.",
                recount_ms,
                RECOUNT_BUDGET_MS,
            )
            # Even if we have a value, treat it as estimate-only when slow.
            return displayed_count, False

        file_counts = fd_rg_utils.parse_rg_count_output(out_bytes)
        real_total = int(file_counts.get("__total__", 0))
        # If recount somehow undercounts (race/IO), trust displayed_count.
        if real_total < displayed_count:
            return displayed_count, False
        return real_total, True
    except Exception as exc:  # noqa: BLE001
        logger.debug("Recount pass raised %s; using estimate.", exc)
        return displayed_count, False


def _parent_dir(file_path: str) -> str:
    """Return the parent directory of a file path (mirrors _prepare_search_roots)."""
    from pathlib import Path

    return str(Path(file_path).parent)


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
    real_total: int | None = None,
    total_count_known: bool = True,
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
            real_total=real_total,
            total_count_known=total_count_known,
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
            real_total=real_total,
            total_count_known=total_count_known,
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
        real_total=real_total,
        total_count_known=total_count_known,
    )


def _respond_files_with_matches(
    out: bytes,
    elapsed_ms: int,
    cache_key: str | None,
    arguments: dict[str, Any],
    cache: Any,
    output_format: str,
    apply_toon: ToonApplier,
) -> dict[str, Any]:
    """Parse rg --files-with-matches plain-text output into a file list.

    rg -l emits one file path per line. Much smaller than the full match
    payload — for 'which files mention X' queries this is the right shape.
    """
    raw = out.decode("utf-8", errors="replace")
    files = sorted({line.strip() for line in raw.splitlines() if line.strip()})
    max_count = arguments.get("max_count")
    truncated = False
    if max_count is not None and len(files) > int(max_count):
        files = files[: int(max_count)]
        truncated = True

    result: dict[str, Any] = {
        "success": True,
        "verdict": "INFO" if files else "NOT_FOUND",
        "mode": "files_with_matches",
        "count": len(files),
        "files": files,
        "truncated": truncated,
        "elapsed_ms": elapsed_ms,
    }
    if cache is not None and cache_key:
        cache.set(cache_key, result)
    return apply_toon(result, output_format)


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
