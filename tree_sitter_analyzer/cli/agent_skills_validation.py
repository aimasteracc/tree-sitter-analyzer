"""Validation summary helpers for project-local agent skills."""

from __future__ import annotations

from typing import Any

BLOCKING_GAP_KEYS = ("skills_root_missing", "missing_skill_md", "missing_trigger_text")
CAUTION_GAP_KEYS = ("missing_completion_guidance",)
OPTIONAL_GAP_KEYS = ("optional_agent_brief_missing",)


def build_skill_validation(gaps: dict[str, Any]) -> dict[str, Any]:
    """Build an agent-friendly validation summary from inventory gaps."""
    blocking = _selected_gaps(gaps, BLOCKING_GAP_KEYS)
    caution = _selected_gaps(gaps, CAUTION_GAP_KEYS)
    optional = _selected_gaps(gaps, OPTIONAL_GAP_KEYS)
    blocking_count = _total_gap_count(blocking)
    caution_count = _total_gap_count(caution)
    optional_count = _total_gap_count(optional)
    status = _validation_status(blocking_count, caution_count)
    return {
        "status": status,
        "blocking_gaps": blocking,
        "caution_gaps": caution,
        "optional_gaps": optional,
        "blocking_gap_count": blocking_count,
        "caution_gap_count": caution_count,
        "optional_gap_count": optional_count,
        "next_fix": _next_fix(status, blocking, caution, optional),
    }


def _selected_gaps(
    gaps: dict[str, Any],
    keys: tuple[str, ...],
) -> dict[str, Any]:
    """Return non-empty gap entries for the requested keys."""
    selected: dict[str, Any] = {}
    for key in keys:
        value = gaps.get(key)
        if value:
            selected[key] = value
    return selected


def _total_gap_count(grouped_gaps: dict[str, Any]) -> int:
    """Count booleans and list-like gap values in a grouped gap map."""
    total = 0
    for value in grouped_gaps.values():
        if isinstance(value, bool):
            total += int(value)
        else:
            total += len(value)
    return total


def _validation_status(blocking_count: int, caution_count: int) -> str:
    """Return a coarse readiness status for agent skill use."""
    if blocking_count:
        return "blocked"
    if caution_count:
        return "caution"
    return "ready"


def _next_fix(
    status: str,
    blocking: dict[str, Any],
    caution: dict[str, Any],
    optional: dict[str, Any],
) -> str:
    """Suggest the next metadata cleanup action."""
    if status == "blocked":
        return _blocking_fix(blocking)
    if status == "caution":
        names = caution.get("missing_completion_guidance", [])
        return "Add completion or verification guidance to: " + ", ".join(names[:5])
    if optional:
        return "Optional: add AGENT-BRIEF.md for richer handoffs."
    return "No skill metadata fixes needed."


def _blocking_fix(blocking: dict[str, Any]) -> str:
    """Suggest a fix for blocking skill metadata gaps."""
    if blocking.get("skills_root_missing"):
        return "Create .agents/skills with at least one SKILL.md."
    if blocking.get("missing_skill_md"):
        return "Add SKILL.md to: " + ", ".join(blocking["missing_skill_md"][:5])
    if blocking.get("missing_trigger_text"):
        return "Add 'Use when...' trigger text to: " + ", ".join(
            blocking["missing_trigger_text"][:5]
        )
    return "Fix blocking skill metadata gaps."
