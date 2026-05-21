"""Agent-facing summaries for find_and_grep responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FindAndGrepSummaryInput:
    """Inputs needed to summarize one find_and_grep response."""

    arguments: dict[str, Any]
    mode: str
    count: int
    truncated: bool
    fd_elapsed_ms: int
    rg_elapsed_ms: int
    searched_file_count: int
    file_count: int | None = None
    total_matches: int | None = None


def build_agent_summary(context: FindAndGrepSummaryInput) -> dict[str, Any]:
    """Build a compact fd+rg summary for immediate agent decisions."""
    match_total = (
        context.total_matches if context.total_matches is not None else context.count
    )
    risk = _find_and_grep_summary_risk(
        match_total, context.searched_file_count, context.truncated
    )
    # T5 (round-37g): canonical envelope requires ``verdict``. find_and_grep
    # is informational; map risk → verdict matching project-wide vocab
    # (low→INFO, medium→CAUTION, high→REVIEW).
    if risk == "high":
        verdict = "REVIEW"
    elif risk == "medium":
        verdict = "CAUTION"
    else:
        verdict = "INFO"
    summary: dict[str, Any] = {
        "risk": risk,
        "verdict": verdict,
        "mode": context.mode,
        "query": _short_query(context.arguments.get("query", "")),
        "count": context.count,
        "total_matches": match_total,
        "searched_file_count": context.searched_file_count,
        "truncated": context.truncated,
        "fd_elapsed_ms": context.fd_elapsed_ms,
        "rg_elapsed_ms": context.rg_elapsed_ms,
        "next_step": _find_and_grep_summary_next_step(
            risk, context.mode, match_total, context.file_count
        ),
        "suggested_tool": _find_and_grep_summary_suggested_tool(
            risk, context.mode, context.file_count
        ),
        "stop_condition": _find_and_grep_summary_stop_condition(risk, context.mode),
    }
    if context.file_count is not None:
        summary["file_count"] = context.file_count
    if context.arguments.get("pattern"):
        summary["pattern"] = _short_query(context.arguments.get("pattern", ""))
    if context.arguments.get("output_file"):
        summary["output_saved"] = True
    if context.arguments.get("suppress_output"):
        summary["suppress_output"] = True
    summary["summary_line"] = _build_summary_line(context, match_total=match_total)
    return summary


def _build_summary_line(context: FindAndGrepSummaryInput, *, match_total: int) -> str:
    """Build a one-line human/agent-readable digest."""
    query = _short_query(context.arguments.get("query", ""), limit=60)
    pattern = context.arguments.get("pattern")
    pattern_part = f" in '{_short_query(pattern, limit=40)}'" if pattern else ""
    files_part = (
        f", {context.searched_file_count} files searched"
        if context.searched_file_count
        else ""
    )
    truncated_part = " (truncated)" if context.truncated else ""
    return (
        f"find_and_grep '{query}'{pattern_part}: {match_total} matches"
        f"{files_part}{truncated_part}"
    )


def build_agent_summary_from_meta(
    arguments: dict[str, Any],
    *,
    mode: str,
    count: int,
    meta: dict[str, Any],
    file_count: int | None = None,
    total_matches: int | None = None,
) -> dict[str, Any]:
    """Build an agent summary from the shared find_and_grep meta block."""
    return build_agent_summary(
        FindAndGrepSummaryInput(
            arguments=arguments,
            mode=mode,
            count=count,
            total_matches=total_matches,
            truncated=bool(meta.get("truncated", False)),
            fd_elapsed_ms=int(meta.get("fd_elapsed_ms", 0) or 0),
            rg_elapsed_ms=int(meta.get("rg_elapsed_ms", 0) or 0),
            searched_file_count=int(meta.get("searched_file_count", 0) or 0),
            file_count=file_count,
        )
    )


def count_match_files(matches: list[dict[str, Any]]) -> int:
    """Return the number of unique files represented by matches."""
    file_paths: set[str] = set()
    for match in matches:
        path_value = match.get("file") or match.get("path")
        if isinstance(path_value, dict):
            path_value = path_value.get("text")
        if path_value:
            file_paths.add(str(path_value))
    return len(file_paths)


def _short_query(query: Any, limit: int = 120) -> str:
    text = str(query)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _find_and_grep_summary_risk(
    match_total: int, searched_file_count: int, truncated: bool
) -> str:
    if truncated or match_total >= 500 or searched_file_count >= 2000:
        return "high"
    if match_total >= 50 or searched_file_count >= 500:
        return "medium"
    return "low"


def _find_and_grep_summary_next_step(
    risk: str,
    mode: str,
    match_total: int,
    file_count: int | None,
) -> str:
    if match_total == 0:
        return "Broaden the query or check roots, pattern, and globs."
    if risk == "high":
        return "Narrow fd filters or the rg query before opening matches."
    if mode in {"summary", "count_only"}:
        return "Run find_and_grep in normal or group_by_file mode for top files."
    if file_count == 1:
        return "Use extract_code_section around returned lines in the matching file."
    return "Inspect grouped matches, then open exact file ranges."


def _find_and_grep_summary_suggested_tool(
    risk: str,
    mode: str,
    file_count: int | None,
) -> str:
    if risk == "high" or mode in {"summary", "count_only"}:
        return "find_and_grep"
    if file_count == 1:
        return "extract_code_section"
    return "query_code"


def _find_and_grep_summary_stop_condition(risk: str, mode: str) -> str:
    if risk == "high":
        return "A narrower fd+rg search returns fewer than 500 matches."
    if mode in {"summary", "count_only"}:
        return "The next search returns concrete line matches for target files."
    return "The returned matches identify the files and line ranges to inspect."
