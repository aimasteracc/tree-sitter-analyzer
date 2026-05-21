"""Agent-facing summaries for search_content responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchAgentSummaryInput:
    """Inputs needed to summarize one search_content response."""

    arguments: dict[str, Any]
    mode: str
    count: int
    truncated: bool
    elapsed_ms: int
    file_count: int | None = None
    total_matches: int | None = None


def build_agent_summary(context: SearchAgentSummaryInput) -> dict[str, Any]:
    """Build a compact search summary for immediate agent decisions."""
    match_total = (
        context.total_matches if context.total_matches is not None else context.count
    )
    risk = _search_summary_risk(match_total, context.truncated)
    # T5 (round-37g): canonical envelope requires ``verdict``. search is
    # informational; map risk → verdict matching the project-wide vocab
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
        "truncated": context.truncated,
        "elapsed_ms": context.elapsed_ms,
        "next_step": _search_summary_next_step(
            risk, context.mode, match_total, context.file_count
        ),
        "suggested_tool": _search_summary_suggested_tool(
            risk, context.mode, context.file_count
        ),
        "stop_condition": _search_summary_stop_condition(risk, context.mode),
    }
    if context.file_count is not None:
        summary["file_count"] = context.file_count
    if context.arguments.get("output_file"):
        summary["output_saved"] = True
    if context.arguments.get("suppress_output"):
        summary["suppress_output"] = True
    summary["summary_line"] = _build_summary_line(context, match_total=match_total)
    return summary


def _build_summary_line(context: SearchAgentSummaryInput, *, match_total: int) -> str:
    """Build a one-line human/agent-readable digest."""
    query = _short_query(context.arguments.get("query", ""), limit=60)
    files_part = f" in {context.file_count} files" if context.file_count else ""
    truncated_part = " (truncated)" if context.truncated else ""
    return (
        f"search_content '{query}': {match_total} matches{files_part}{truncated_part}"
    )


def count_match_files(matches: list[dict[str, Any]]) -> int:
    """Return the number of unique files represented by search matches."""
    return len({m.get("file") for m in matches if m.get("file")})


def _short_query(query: Any, limit: int = 120) -> str:
    text = str(query)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _search_summary_risk(match_total: int, truncated: bool) -> str:
    if truncated or match_total >= 500:
        return "high"
    if match_total >= 50:
        return "medium"
    return "low"


def _search_summary_next_step(
    risk: str,
    mode: str,
    match_total: int,
    file_count: int | None,
) -> str:
    if match_total == 0:
        return "Broaden the query or check roots/globs before opening files."
    if risk == "high":
        return "Narrow the query with globs, max_count, or more specific text."
    if mode in {"summary", "count_only"}:
        return "Run search_content in normal or group_by_file mode for the top files."
    if file_count == 1:
        return (
            "Use extract_code_section around the returned lines in the matching file."
        )
    return "Inspect top matches, then use extract_code_section for exact context."


def _search_summary_suggested_tool(
    risk: str,
    mode: str,
    file_count: int | None,
) -> str:
    if risk == "high" or mode in {"summary", "count_only"}:
        return "search_content"
    if file_count == 1:
        return "extract_code_section"
    return "query_code"


def _search_summary_stop_condition(risk: str, mode: str) -> str:
    if risk == "high":
        return "A narrower search returns fewer than 500 matches without truncation."
    if mode in {"summary", "count_only"}:
        return "The next search returns concrete line matches for the target files."
    return (
        "The returned matches identify the file and line range needed for the change."
    )
