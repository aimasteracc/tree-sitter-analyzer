"""Project agent skill inventory builders for the CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_sitter_analyzer.cli.agent_skills_metadata import (
    DESCRIPTION_KEY,
    DISABLE_MODEL_INVOCATION_KEY,
    NAME_KEY,
    metadata_bool,
    read_skill_metadata,
)
from tree_sitter_analyzer.cli.agent_skills_validation import build_skill_validation

SKILL_FILE = "SKILL.md"
AGENT_BRIEF_FILE = "AGENT-BRIEF.md"
OUT_OF_SCOPE_FILE = "OUT-OF-SCOPE.md"
SUPPORT_FILE_LIMIT = 8
READ_ORDER_SUPPORT_LIMIT = 4
ACCEPTANCE_MARKERS = (
    "acceptance criteria",
    "acceptance",
    "done when",
    "verification",
    "regression-test",
    "declaring done",
    "- [ ]",
)
CONTEXT_MARKERS = {
    "issue_tracker": ("issue tracker", "gh issue", "glab issue", ".scratch"),
    "triage_labels": ("triage label", "label vocabulary", "canonical role"),
    "domain_context": ("context.md", "context-map.md"),
    "adrs": ("docs/adr", "adrs"),
}
SIDE_EFFECT_MARKERS = {
    "edits_docs": ("update context.md", "docs/adr", "documentation", "write `docs"),
    "creates_issues": ("create an issue", "publish", "issue tracker"),
    "changes_communication_mode": ("communication mode", "active every response"),
    "creates_prototype": (
        "throwaway prototype",
        "runnable terminal app",
        "ui variations",
    ),
    "changes_tests": ("test-driven", "red-green-refactor", "regression-test"),
}
ACTIONABILITY_PREVIEW_LIMIT = 3


def _skills_verdict(
    validation: dict[str, Any],
    gaps: dict[str, Any],
    root_path: Path,
) -> str:
    """Canonical verdict for the agent-skills envelope.

    pain-01c: tsa-landing reads ``list_agent_skills.verdict`` as part of
    its decision surface. Map validation status to the canonical
    vocabulary, anti-bias toward higher severity.

      skills_root missing          → CAUTION  (no skills installed)
      blocking validation status   → CAUTION
      caution-level gaps           → REVIEW
      ready / no gaps              → INFO
    """
    if not root_path.exists():
        return "CAUTION"
    status = validation.get("status", "")
    if status in ("blocking", "missing"):
        return "CAUTION"
    if validation.get("blocking_gap_count", 0) > 0:
        return "CAUTION"
    if status in ("caution", "warning") or validation.get("caution_gap_count", 0) > 0:
        return "REVIEW"
    return "INFO"


def build_agent_skills_inventory(
    project_root: str,
    skills_root: str | None = None,
) -> dict[str, Any]:
    """Build an agent-friendly inventory of project-local skills."""
    project_path = Path(project_root).expanduser().resolve()
    root_path = _resolve_skills_root(project_path, skills_root)
    skills = _discover_skills(project_path, root_path)
    gaps = _build_gaps(skills, root_path)
    validation = build_skill_validation(gaps)

    agent_summary = _build_agent_summary(skills, gaps, validation)
    verdict = _skills_verdict(validation, gaps, root_path)
    agent_summary["verdict"] = verdict
    result = {
        "success": True,
        "verdict": verdict,
        "inventory": "project agent skills",
        "project_root": str(project_path),
        "skills_root": _display_path(root_path, project_path),
        "skills_root_exists": root_path.exists(),
        "skill_count": len(skills),
        "skills": skills,
        "gaps": gaps,
        "validation": validation,
        "agent_summary": agent_summary,
    }
    # N5 (round-29 dogfood): the success path used to ship
    # ``summary_line=None`` at the top level and omit
    # ``agent_summary.verdict`` entirely. The envelope contract snapshot
    # test catches that drift — populate both surfaces here so direct
    # CLI callers, MCP-routed callers, and snapshot-test consumers all
    # see the canonical shape.
    raw_agent_summary = result["agent_summary"]
    assert isinstance(raw_agent_summary, dict)  # nosec B101 — built above
    summary_line = _build_summary_line(result)
    result["summary_line"] = summary_line
    raw_agent_summary["summary_line"] = summary_line
    # Mirror verdict from the agent_summary surface (source of truth)
    # to the top-level envelope. The verdict was populated in
    # :func:`_build_agent_summary` based on ``validation.status``.
    verdict_value: Any = raw_agent_summary.get("verdict")
    if isinstance(verdict_value, str) and verdict_value:
        result["verdict"] = verdict_value
    result["toon_content"] = _build_toon_content(result)
    return result


def _build_summary_line(result: dict[str, Any]) -> str:
    """Build the canonical one-line headline for agent_skills output.

    N5 — pulls counts and validation_status off the assembled result so
    the line stays in lockstep with ``agent_summary``. Examples:

        agent_skills count=13 ready=11 status=ready
        agent_skills count=0 status=blocked
    """
    skill_count = result.get("skill_count", 0)
    agent_summary = result.get("agent_summary") or {}
    status = agent_summary.get("validation_status", "unknown")
    ready_for_use_count = agent_summary.get("ready_for_use_count", 0)
    if skill_count:
        return (
            f"agent_skills count={skill_count} "
            f"ready={ready_for_use_count} status={status}"
        )
    return f"agent_skills count={skill_count} status={status}"


def _resolve_skills_root(project_path: Path, skills_root: str | None) -> Path:
    """Resolve the skills root relative to the project when needed."""
    if not skills_root:
        return project_path / ".agents" / "skills"
    candidate = Path(skills_root).expanduser()
    return candidate if candidate.is_absolute() else project_path / candidate


def _discover_skills(project_path: Path, root_path: Path) -> list[dict[str, Any]]:
    """Discover skill directories in stable name order."""
    if not root_path.is_dir():
        return []
    skills = [
        _build_skill_record(project_path, skill_dir)
        for skill_dir in sorted(root_path.iterdir(), key=lambda path: path.name)
        if skill_dir.is_dir()
    ]
    return skills


def _build_skill_record(project_path: Path, skill_dir: Path) -> dict[str, Any]:
    """Build a compact inventory record for one skill directory."""
    skill_path = skill_dir / SKILL_FILE
    metadata, body = read_skill_metadata(skill_path)
    support_files = _list_support_files(skill_dir, project_path)
    scripts = _list_script_files(skill_dir, project_path)
    skill_text = body if skill_path.exists() else ""
    brief_path = skill_dir / AGENT_BRIEF_FILE
    out_of_scope_path = skill_dir / OUT_OF_SCOPE_FILE
    combined_text = _combined_skill_text(skill_text, brief_path)
    gaps = _skill_gaps(skill_path, metadata, combined_text)
    actionability = _skill_actionability(
        metadata=metadata,
        has_skill_md=skill_path.exists(),
        has_agent_brief=brief_path.exists(),
        gaps=gaps,
        support_file_count=len(support_files),
    )
    completion_present = _contains_completion_guidance(combined_text)

    return {
        "name": metadata.get(NAME_KEY) or skill_dir.name,
        "directory": _display_path(skill_dir, project_path),
        "skill_path": _display_path(skill_path, project_path),
        "title": _extract_title(skill_text, skill_dir.name),
        "description": _extract_description(metadata, skill_text),
        "has_skill_md": skill_path.exists(),
        "has_agent_brief": brief_path.exists(),
        "agent_brief_path": _display_optional_path(brief_path, project_path),
        "has_out_of_scope": out_of_scope_path.exists(),
        "out_of_scope_path": _display_optional_path(out_of_scope_path, project_path),
        "support_file_count": len(support_files),
        "support_files": support_files[:SUPPORT_FILE_LIMIT],
        "support_files_omitted_count": max(
            0,
            len(support_files) - SUPPORT_FILE_LIMIT,
        ),
        "scripts": scripts,
        "model_invocation_enabled": not metadata_bool(
            metadata,
            DISABLE_MODEL_INVOCATION_KEY,
        ),
        "completion_guidance_present": completion_present,
        "acceptance_criteria_present": completion_present,
        "requires_context": _detect_labels(combined_text, CONTEXT_MARKERS),
        "side_effects": _detect_labels(combined_text, SIDE_EFFECT_MARKERS),
        "agent_trigger": _build_agent_trigger(metadata, skill_dir.name),
        "read_order": _build_read_order(
            project_path,
            skill_path,
            brief_path,
            support_files,
        ),
        "actionability_score": actionability["score"],
        "actionability": actionability["status"],
        "ready_for_use": actionability["ready_for_use"],
        "gaps": gaps,
    }


def _skill_actionability(
    metadata: dict[str, str],
    has_skill_md: bool,
    has_agent_brief: bool,
    gaps: list[str],
    support_file_count: int,
) -> dict[str, Any]:
    """Compute a compact actionability score from metadata and guidance gaps."""
    score = 100
    if not has_skill_md:
        score -= 70
    if NAME_KEY not in metadata:
        score -= 12
    if DESCRIPTION_KEY not in metadata:
        score -= 18
    if "missing_trigger_text" in gaps:
        score -= 22
    if "missing_completion_guidance" in gaps:
        score -= 20
    if not has_agent_brief:
        score -= 8
    if support_file_count == 0:
        score -= 5

    score = max(0, score)
    ready_for_use = (
        has_skill_md
        and NAME_KEY in metadata
        and DESCRIPTION_KEY in metadata
        and "missing_trigger_text" not in gaps
        and "missing_completion_guidance" not in gaps
    )
    status = (
        "ready" if ready_for_use else "caution" if score >= 70 else "needs_improvement"
    )
    return {"score": score, "status": status, "ready_for_use": ready_for_use}


def _list_support_files(skill_dir: Path, project_path: Path) -> list[str]:
    """List non-SKILL support files for a skill directory."""
    support_files = []
    for path in sorted(skill_dir.rglob("*"), key=lambda item: str(item)):
        if not path.is_file() or path.name == SKILL_FILE:
            continue
        support_files.append(_display_path(path, project_path))
    return support_files


def _list_script_files(skill_dir: Path, project_path: Path) -> list[str]:
    """List bundled script files separately from docs-style support files."""
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        return []
    return [
        _display_path(path, project_path)
        for path in sorted(scripts_dir.rglob("*"), key=lambda item: str(item))
        if path.is_file()
    ]


def _skill_gaps(
    skill_path: Path,
    metadata: dict[str, str],
    combined_text: str,
) -> list[str]:
    """Return inventory gaps that make a skill harder for agents to apply."""
    gaps: list[str] = []
    if not skill_path.exists():
        gaps.append("missing_skill_md")
    if NAME_KEY not in metadata:
        gaps.append("missing_name")
    if DESCRIPTION_KEY not in metadata:
        gaps.append("missing_description")
    if not _has_trigger_text(metadata.get(DESCRIPTION_KEY, "")):
        gaps.append("missing_trigger_text")
    if not _contains_completion_guidance(combined_text):
        gaps.append("missing_completion_guidance")
    return gaps


def _combined_skill_text(skill_text: str, brief_path: Path) -> str:
    """Combine primary skill text and optional agent brief text."""
    combined = skill_text or ""
    if brief_path.exists():
        combined += "\n" + brief_path.read_text(encoding="utf-8", errors="replace")
    return combined


def _contains_completion_guidance(combined: str) -> bool:
    """Detect whether a skill exposes completion or verification criteria."""
    lowered = combined.lower()
    return any(marker in lowered for marker in ACCEPTANCE_MARKERS)


def _has_trigger_text(description: str) -> bool:
    """Return True when front matter gives a useful skill activation hint."""
    lowered = description.lower()
    return any(
        marker in lowered for marker in ("use when", "run before", "invoke when")
    )


def _detect_labels(text: str, marker_groups: dict[str, tuple[str, ...]]) -> list[str]:
    """Detect named labels from marker groups."""
    lowered = text.lower()
    return [
        label
        for label, markers in marker_groups.items()
        if any(marker in lowered for marker in markers)
    ]


def _extract_title(skill_text: str, fallback: str) -> str:
    """Extract the first Markdown H1 title."""
    for line in skill_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def _extract_description(metadata: dict[str, str], skill_text: str) -> str:
    """Return front-matter description or the first useful body paragraph."""
    description = metadata.get(DESCRIPTION_KEY)
    if description:
        return _truncate(description)

    for paragraph in _body_paragraphs(skill_text):
        if not paragraph.startswith("#"):
            return _truncate(paragraph)
    return ""


def _body_paragraphs(skill_text: str) -> list[str]:
    """Collect non-empty Markdown body paragraphs."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in skill_text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(stripped)
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def _truncate(text: str, limit: int = 220) -> str:
    """Keep CLI JSON compact without hiding useful trigger text."""
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "..."


def _build_agent_trigger(metadata: dict[str, str], fallback_name: str) -> str:
    """Build a short instruction for when an agent should load the skill."""
    description = metadata.get(DESCRIPTION_KEY)
    if not description:
        return f"Load this skill when the task explicitly names {fallback_name}."
    return _truncate(description, limit=180)


def _build_read_order(
    project_path: Path,
    skill_path: Path,
    brief_path: Path,
    support_files: list[str],
) -> list[str]:
    """Suggest a stable reading order for an agent using the skill."""
    paths = [_display_path(skill_path, project_path)]
    if brief_path.exists():
        paths.append(_display_path(brief_path, project_path))
    paths.extend(support_files[:READ_ORDER_SUPPORT_LIMIT])
    return _dedupe(paths)


def _dedupe(items: list[str]) -> list[str]:
    """De-duplicate while preserving the preferred reading order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def _build_gaps(skills: list[dict[str, Any]], root_path: Path) -> dict[str, Any]:
    """Aggregate skill inventory gaps for fast agent decisions."""
    missing_skill_md = [skill["name"] for skill in skills if not skill["has_skill_md"]]
    missing_completion = [
        skill["name"] for skill in skills if not skill["completion_guidance_present"]
    ]
    return {
        "skills_root_missing": not root_path.exists(),
        "missing_skill_md": missing_skill_md,
        "missing_completion_guidance": missing_completion,
        "missing_trigger_text": [
            skill["name"] for skill in skills if "missing_trigger_text" in skill["gaps"]
        ],
        "optional_agent_brief_missing": [
            skill["name"] for skill in skills if not skill["has_agent_brief"]
        ],
    }


def _build_agent_summary(
    skills: list[dict[str, Any]],
    gaps: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    """Build the compact decision surface agents read first.

    N5 (round-29 dogfood): also emit ``verdict`` per the envelope-contract
    vocabulary (see :data:`_N_VERDICT_VOCABULARY`):

    - ``validation.status == 'ready'`` → ``INFO`` (no metadata gaps)
    - ``validation.status == 'caution'`` → ``WARN`` (caller should look
      at the missing completion guidance before depending on a skill)
    - ``validation.status == 'blocked'`` → ``REVIEW`` (blocking gaps
      mean callers cannot trust the inventory until a fix lands)
    """
    missing_completion_count = len(gaps["missing_completion_guidance"])
    status = validation["status"]
    risk = "none" if status == "ready" else status
    if status == "ready":
        verdict = "INFO"
    elif status == "caution":
        verdict = "WARN"
    else:  # blocked or any future escalation tier
        verdict = "REVIEW"
    next_step = (
        "Create .agents/skills or run project setup skills first."
        if gaps["skills_root_missing"]
        else "Pick the matching skill, read its read_order, then run its verification guidance."
    )
    ready_for_use_count = len([skill for skill in skills if skill["ready_for_use"]])
    actionability_preview = _top_actionable_skills(skills)
    return {
        "risk": risk,
        "verdict": verdict,
        "skill_count": len(skills),
        "validation_status": status,
        "blocking_gap_count": validation["blocking_gap_count"],
        "caution_gap_count": validation["caution_gap_count"],
        "optional_gap_count": validation["optional_gap_count"],
        "missing_completion_count": missing_completion_count,
        "ready_for_use_count": ready_for_use_count,
        "actionable_skills": actionability_preview,
        "readiness_ratio": (
            round(ready_for_use_count / len(skills), 2) if skills else 0.0
        ),
        "next_step": next_step,
        "next_fix": validation["next_fix"],
        "inspection_command": "uv run tree-sitter-analyzer agent-skills --format json",
        "stop_condition": "A matching skill has clear trigger text and completion guidance.",
    }


def _top_actionable_skills(skills: list[dict[str, Any]]) -> list[str]:
    """Return highest-actionability skills by score."""
    ranked = sorted(skills, key=lambda item: item["actionability_score"], reverse=True)
    return [skill["name"] for skill in ranked[:ACTIONABILITY_PREVIEW_LIMIT]]


def _build_toon_content(result: dict[str, Any]) -> str:
    """Build a compact text representation for --format toon."""
    summary = result["agent_summary"]
    lines = [
        "inventory: project agent skills",
        f"skills_root: {result['skills_root']}",
        f"skill_count: {result['skill_count']}",
        f"risk: {summary['risk']}",
        f"validation_status: {summary['validation_status']}",
        f"blocking_gap_count: {summary['blocking_gap_count']}",
        f"caution_gap_count: {summary['caution_gap_count']}",
        f"missing_completion_count: {summary['missing_completion_count']}",
        f"ready_for_use_count: {summary['ready_for_use_count']}",
        f"readiness_ratio: {summary['readiness_ratio']}",
        "skills:",
    ]
    for skill in result["skills"]:
        gaps = ",".join(skill["gaps"]) if skill["gaps"] else "none"
        lines.append(
            "  - "
            + skill["name"]
            + f" | actionability={skill['actionability']} ({skill['actionability_score']})"
            + f" | ready={str(skill['ready_for_use']).lower()} | path={skill['skill_path']} gaps={gaps}"
        )
    lines.append("top_actionable_skills: " + ", ".join(summary["actionable_skills"]))
    lines.append(f"next_step: {summary['next_step']}")
    lines.append(f"next_fix: {summary['next_fix']}")
    return "\n".join(lines)


def _display_optional_path(path: Path, project_path: Path) -> str | None:
    """Display a path only when it exists."""
    return _display_path(path, project_path) if path.exists() else None


def _display_path(path: Path, project_path: Path) -> str:
    """Display project-relative paths when possible."""
    try:
        return str(path.resolve().relative_to(project_path))
    except ValueError:
        return str(path)
