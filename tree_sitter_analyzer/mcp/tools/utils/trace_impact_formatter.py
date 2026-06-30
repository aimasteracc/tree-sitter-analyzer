"""Trace impact formatter helpers — Phase 3 REQ-CLEAN-005.

Extracted from trace_impact_tool.py.
"""

from __future__ import annotations

from typing import Any


# Lazy import to avoid circular dependency
def _get_impact_level(count: int) -> dict[str, str]:
    from .trace_impact_graph_walker import _get_impact_level as _impl

    return _impl(count)


def _build_not_found_response(symbol: str, language: str | None) -> dict[str, Any]:
    """M11: ripgrep returned zero matches → NOT_FOUND envelope.

    The typo-vs-real-zero-caller ambiguity is resolved as "verify
    spelling first" to match symbol_lineage's behaviour. ``impact_verdict``
    stays at the magnitude vocab (``NONE`` for zero callers) while
    top-level ``verdict`` flips to ``NOT_FOUND`` so cross-tool readers
    can branch on a single field.
    """
    impact = _get_impact_level(0)
    summary_line = f"trace_impact symbol={symbol} not_found"
    return {
        "success": True,
        "symbol": symbol,
        "language": language,
        "usages": [],
        "call_count": 0,
        "count": 0,
        "impact_level": impact["level"],
        "impact_verdict": impact["level"].upper(),
        "verdict": "NOT_FOUND",
        "found": False,
        "impact_badge": impact["badge"],
        "impact_guidance": impact["guidance"],
        "message": (
            f"No usages of '{symbol}' found in the project. "
            "Verify symbol name — no definitions or references "
            "exist anywhere in the source tree."
        ),
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": ("verify symbol name — no definitions or references found"),
            "verdict": "NOT_FOUND",
            "risk": "unknown",
        },
    }


def _truncate_for_display(
    source_matches: list[Any], max_results: int
) -> tuple[list[Any], bool]:
    """Display-cap source matches without affecting impact-level count."""
    if len(source_matches) > max_results:
        return source_matches[:max_results], True
    return source_matches, False


def _matches_to_usages(matches: list[Any]) -> list[dict[str, Any]]:
    """Convert rg matches to usage dicts with both ``file``/``file_path`` aliases."""
    usages: list[dict[str, Any]] = []
    for match in matches:
        line_no = match["line"]
        file_path_val = match["file"]
        usages.append(
            {
                "file": file_path_val,
                "file_path": file_path_val,
                "line": line_no,
                "line_number": line_no,
                "context": match["text"],
            }
        )
    return usages


def _verdict_and_next_step_for_impact(level: str, total_count: int) -> tuple[str, str]:
    """K5: map impact level (magnitude vocab) → (verdict, next_step) (safety vocab)."""
    if level == "high":
        return "UNSAFE", (
            f"batch_search to enumerate all {total_count} call sites before "
            "changing signature"
        )
    if level == "medium":
        return "CAUTION", (
            f"batch_search to enumerate all {total_count} call sites before "
            "changing signature"
        )
    if level == "low":
        return "CAUTION", "review the few callers, then proceed with the change"
    return "SAFE", "no callers — safe to refactor"


def _trace_impact_base_envelope(
    *,
    symbol: str,
    impact: dict[str, Any],
    source_total: int,
    true_total: int,
    usages: list[dict[str, Any]],
    summary_line: str,
    verdict: str,
    next_step: str,
) -> dict[str, Any]:
    """Build the always-present canonical fields of the trace_impact envelope.

    Caller layers conditional fields (``warning`` / ``language`` /
    ``source_file`` / ``truncated`` / ``non_source_match_count``) on top
    via ``_trace_impact_apply_conditional_fields``.
    """
    return {
        "success": True,
        "symbol": symbol,
        "call_count": source_total,
        "count": source_total,
        "source_call_count": source_total,
        "usage_count": len(usages),
        "raw_match_count": true_total,
        "impact_level": impact["level"],
        "impact_verdict": impact["level"].upper(),
        "verdict": verdict,
        "impact_badge": impact["badge"],
        "impact_guidance": impact["guidance"],
        # RFC-0018 R10: ``usages`` is the canonical array for trace_impact
        # (``usage_count`` counts it). The former ``"results": usages`` was an
        # exact duplicate of the SAME list object — it doubled the largest
        # field of the JSON response returned to the agent (trace emits a raw
        # JSON dict; it does not apply TOON) for zero added signal. Dropped;
        # consumers read ``usages``. (``results`` remains the cross-tool key
        # for *search* tools, which is unaffected — trace does not route
        # through search_envelope.)
        "usages": usages,
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": next_step,
            "verdict": verdict,
        },
    }


def _trace_impact_apply_conditional_fields(
    result: dict[str, Any],
    *,
    impact_level: str,
    source_total: int,
    true_total: int,
    language: str | None,
    file_path: str | None,
    truncated: bool,
    max_results: int,
) -> None:
    """Mutate ``result`` with optional fields based on signal flags.

    Adds in-place:
    - ``warning`` when impact_level == "high" (advises batch_search)
    - ``language`` + ``filtered_by_language`` when a language was inferred
    - ``source_file`` when ``file_path`` was provided
    - ``truncated`` + ``message`` when results overflowed ``max_results``
    - ``non_source_match_count`` when raw matches exceeded source matches
    """
    if impact_level == "high":
        result["warning"] = (
            f"🚨 HIGH IMPACT: This symbol has {source_total} callers. "
            f"Modifying its signature requires updating all call sites. "
            f"Use batch_search to locate all callers before proceeding."
        )
    if language:
        result["language"] = language
        result["filtered_by_language"] = True
    if file_path:
        result["source_file"] = file_path
    if truncated:
        result["truncated"] = True
        result["message"] = (
            f"Results truncated to {max_results} usages. "
            f"Consider narrowing the search scope or increasing max_results."
        )
    if true_total > source_total:
        result["non_source_match_count"] = true_total - source_total


def _build_trace_impact_result(
    *,
    symbol: str,
    language: str | None,
    file_path: str | None,
    usages: list[dict[str, Any]],
    source_total: int,
    true_total: int,
    truncated: bool,
    max_results: int,
) -> dict[str, Any]:
    """Compose the canonical trace_impact success envelope.

    r37bw: extracted from ``execute``. K5 verdict alias, H4 source-only
    counts, optional ``warning`` / ``language`` / ``source_file`` /
    ``truncated`` / ``non_source_match_count`` fields all preserved.

    r37f6 (dogfood): 64 → ~15 lines. Base envelope moved to
    ``_trace_impact_base_envelope``; conditional fields applied via
    ``_trace_impact_apply_conditional_fields``.
    """
    impact = _get_impact_level(source_total)
    summary_line = f"{symbol} callers={source_total} impact={impact['level']}"
    verdict, next_step = _verdict_and_next_step_for_impact(
        impact["level"], source_total
    )
    result = _trace_impact_base_envelope(
        symbol=symbol,
        impact=impact,
        source_total=source_total,
        true_total=true_total,
        usages=usages,
        summary_line=summary_line,
        verdict=verdict,
        next_step=next_step,
    )
    _trace_impact_apply_conditional_fields(
        result,
        impact_level=impact["level"],
        source_total=source_total,
        true_total=true_total,
        language=language,
        file_path=file_path,
        truncated=truncated,
        max_results=max_results,
    )
    return result


# r37f5 (dogfood): static MCP definition lifted out of ``TraceImpactTool``
# so introspection calls don't reconstruct the same 80-line dict every time.
_TRACE_IMPACT_DESCRIPTION: str = (
    "Find every caller and usage site of a symbol across the entire project. "
    "\n\n"
    "REQUIRED before modifying any public function, class, or variable. "
    "Without this, you are editing blindly — you do not know what breaks. "
    "This tool answers: 'if I change X, what else changes?' "
    "\n\n"
    "WHEN TO USE:\n"
    "- ALWAYS call this before renaming, removing, or changing the signature of any "
    "public method, class, or exported variable\n"
    "- Before refactoring code used across multiple files\n"
    "- To understand the blast radius of a deprecation\n"
    "- To verify that a symbol is truly unused before deletion\n"
    "\n"
    "WHEN NOT TO USE:\n"
    "- Private/internal methods (single-underscore prefix) within the same file — "
    "the impact is local and visible in context\n"
    "- Pure comment or docstring edits — no callers are affected\n"
    "- Adding a brand-new symbol that has no existing usages\n"
    "\n"
    "IMPORTANT: Provide file_path when available — this filters results to the same "
    "language, eliminating cross-language false positives. "
    "Set word_match=true (the default) to avoid substring noise."
)


_TRACE_IMPACT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": {
            "type": "string",
            "description": (
                "Symbol name to trace (method, class, function, or variable name). "
                "Example: 'processPayment', 'UserService', 'calculateTotal'"
            ),
        },
        "file_path": {
            "type": "string",
            "description": (
                "Optional: Source file where the symbol is defined. "
                "If provided, filters results to the same language. "
                "Example: 'src/services/PaymentService.java'"
            ),
        },
        "project_root": {
            "type": "string",
            "description": (
                "Optional: Project root directory to search. "
                "Defaults to the tool's configured project root. "
                "Can provide multiple roots as comma-separated paths."
            ),
        },
        "case_sensitive": {
            "type": "boolean",
            "description": (
                "Whether to perform case-sensitive search. "
                "Default: false (smart case - case-sensitive if symbol has uppercase)"
            ),
        },
        "word_match": {
            "type": "boolean",
            "description": (
                "Whether to match whole words only (not substrings). "
                "Default: true (recommended to avoid false positives)"
            ),
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return. Default: 1000",
        },
        "exclude_patterns": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Optional: Glob patterns to exclude from search. "
                "Example: ['**/test/**', '**/node_modules/**', '**/*.min.js']"
            ),
        },
    },
    "required": ["symbol"],
    # F5: refuse unknown keys; central enforcement is in
    # BaseMCPTool.__init_subclass__.
    "additionalProperties": False,
}
