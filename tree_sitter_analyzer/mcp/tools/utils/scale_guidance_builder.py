"""Guidance builder helpers for analyze_scale — Phase 3 REQ-CLEAN-004.

Extracted from analyze_scale_helpers.py.
"""

from __future__ import annotations

from typing import Any

from .scale_structural_extractor import (
    _COMPLEXITY_HOTSPOT_THRESHOLD,
    _LANG_QUERIES,
    _PRIORITY_QUERIES,
    _REQUIRED_OVERVIEW_FIELDS,
)


def generate_llm_guidance(
    file_metrics: dict[str, Any], structural_overview: dict[str, Any]
) -> dict[str, Any]:
    """Generate guidance for LLM on how to efficiently analyze this file.

    r37bd (dogfood): tool flagged this at 226 lines. Split into 6 phases
    + 3 module-level data tables. Behaviour preserved (size thresholds
    100/500/1500, complexity_hotspot recommendation, dependency/health
    workflow tail).
    """
    total_lines = file_metrics["total_lines"]
    language = file_metrics.get("language", "")

    _ensure_required_overview_fields(structural_overview)

    guidance = _empty_guidance()
    _classify_size(guidance, total_lines)
    _recommend_tools(guidance, total_lines, structural_overview)
    _assess_complexity(guidance, structural_overview)
    _identify_key_areas(guidance, structural_overview)
    guidance["suggested_queries"] = _LANG_QUERIES.get(language, [])
    guidance["workflow_steps"] = _build_workflow_steps(guidance, structural_overview)
    _attach_available_queries(guidance, language)
    return guidance


def _empty_guidance() -> dict[str, Any]:
    """The skeleton guidance dict — 7 named fields, all empty/zero."""
    return {
        "analysis_strategy": "",
        "recommended_tools": [],
        "key_areas": [],
        "complexity_assessment": "",
        "size_category": "",
        "suggested_queries": [],
        "workflow_steps": [],
    }


def _ensure_required_overview_fields(structural_overview: dict[str, Any]) -> None:
    """Fill in missing keys so downstream lookups never KeyError."""
    for field in _REQUIRED_OVERVIEW_FIELDS:
        if field not in structural_overview:
            structural_overview[field] = []


def _classify_size(guidance: dict[str, Any], total_lines: int) -> None:
    """Pick a size_category + matching analysis_strategy from total_lines."""
    if total_lines < 100:
        guidance["size_category"] = "small"
        guidance["analysis_strategy"] = (
            "This is a small file that can be analyzed in full detail."
        )
    elif total_lines < 500:
        guidance["size_category"] = "medium"
        guidance["analysis_strategy"] = (
            "This is a medium-sized file. Consider focusing on key classes and methods."
        )
    elif total_lines < 1500:
        guidance["size_category"] = "large"
        guidance["analysis_strategy"] = (
            "This is a large file. Use targeted analysis with extract_code_section."
        )
    else:
        guidance["size_category"] = "very_large"
        guidance["analysis_strategy"] = (
            "This is a very large file. Strongly recommend using structural "
            "analysis first, then targeted deep-dives."
        )


def _recommend_tools(
    guidance: dict[str, Any],
    total_lines: int,
    structural_overview: dict[str, Any],
) -> None:
    """Append tool recommendations based on size + presence of hotspots."""
    if total_lines > 200:
        guidance["recommended_tools"].append("extract_code_section")
        guidance["recommended_tools"].append("query_code")
    if len(structural_overview["complexity_hotspots"]) > 0:
        guidance["recommended_tools"].append("analyze_code_structure")


def _assess_complexity(
    guidance: dict[str, Any], structural_overview: dict[str, Any]
) -> None:
    """Set complexity_assessment based on hotspot count."""
    hotspots = structural_overview["complexity_hotspots"]
    if len(hotspots) > 0:
        guidance["complexity_assessment"] = f"Found {len(hotspots)} complexity hotspots"
    else:
        guidance["complexity_assessment"] = (
            "No significant complexity hotspots detected"
        )


def _identify_key_areas(
    guidance: dict[str, Any], structural_overview: dict[str, Any]
) -> None:
    """Note structural characteristics worth surfacing to the agent."""
    if len(structural_overview["classes"]) > 1:
        guidance["key_areas"].append(
            "Multiple classes - consider analyzing class relationships"
        )
    if len(structural_overview["methods"]) > 20:
        guidance["key_areas"].append(
            "Many methods - focus on public interfaces and high-complexity methods"
        )
    if len(structural_overview["imports"]) > 10:
        guidance["key_areas"].append("Many imports - consider dependency analysis")


def _build_workflow_steps(
    guidance: dict[str, Any], structural_overview: dict[str, Any]
) -> list[str]:
    """Compose the ordered workflow_steps list — size-dependent middle, fixed tail."""
    steps = ["check_code_scale (done)"]
    if guidance["size_category"] in ("large", "very_large"):
        steps.extend(_large_file_steps(structural_overview))
    else:
        steps.extend(_small_or_medium_steps(structural_overview))

    if len(structural_overview.get("imports", [])) > 5:
        steps.append("analyze_dependencies mode=blast_radius to assess change impact")
    steps.append("check_file_health to see if this file needs refactoring")
    return steps


def _large_file_steps(structural_overview: dict[str, Any]) -> list[str]:
    """Targeted-analysis steps for files ≥500 lines."""
    steps = [
        "analyze_code_structure with format=compact for overview",
        "query_code with specific query keys to find target elements",
    ]
    hotspots = structural_overview.get("complexity_hotspots", [])
    if hotspots:
        top = hotspots[0]
        name = top.get("name", "hotspot")
        start = top.get("start_line", "")
        end = top.get("end_line", "")
        steps.append(
            f"extract_code_section for '{name}' (L{start}-{end}) - complexity hotspot"
        )
    else:
        steps.append("extract_code_section for targeted line ranges")
    return steps


def _small_or_medium_steps(structural_overview: dict[str, Any]) -> list[str]:
    """Full-analysis steps for files <500 lines."""
    steps = [
        "analyze_code_structure for full structure table",
        "query_code for specific elements if needed",
    ]
    notable = structural_overview.get("methods", [])
    long_methods = [
        m for m in notable if m.get("complexity", 0) >= _COMPLEXITY_HOTSPOT_THRESHOLD
    ]
    if long_methods:
        top = long_methods[0]
        start = top.get("start_line", "")
        end = top.get("end_line", "")
        steps.append(
            f"extract_code_section for '{top.get('name', 'method')}' "
            f"(L{start}-{end}) - high complexity"
        )
    return steps


def _attach_available_queries(guidance: dict[str, Any], language: str) -> None:
    """Look up tree-sitter queries for ``language`` and cap to 15 entries."""
    from ....query_loader import get_query_loader

    loader = get_query_loader()
    all_queries = loader.list_queries_for_language(language)
    if not all_queries:
        return
    priority = [q for q in all_queries if q in _PRIORITY_QUERIES]
    rest = sorted(q for q in all_queries if q not in priority)[: 15 - len(priority)]
    guidance["available_queries"] = sorted(priority) + rest


# validate_scale_arguments: implementation
# Input validation for batch and single-file analysis modes
