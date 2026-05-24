"""Tests for project-local agent skill inventory helpers."""

from __future__ import annotations

import sys

import pytest

from tree_sitter_analyzer.cli.agent_skills import build_agent_skills_inventory
from tree_sitter_analyzer.cli.agent_skills_metadata import split_front_matter
from tree_sitter_analyzer.cli.agent_skills_validation import build_skill_validation


def test_split_front_matter_supports_folded_descriptions():
    """Folded YAML front matter should become useful trigger text."""
    metadata, body = split_front_matter(
        "---\n"
        "name: caveman\n"
        "description: >\n"
        "  Ultra-compressed communication mode.\n"
        "  Use when user says brief.\n"
        "disable-model-invocation: true\n"
        "---\n\n"
        "# Caveman\n"
    )

    assert metadata["name"] == "caveman"
    assert metadata["description"] == (
        "Ultra-compressed communication mode. Use when user says brief."
    )
    assert metadata["disable-model-invocation"] == "true"
    assert body.startswith("# Caveman")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows-specific incompatibility — tracked separately",
)
def test_agent_skills_inventory_exposes_decision_fields(tmp_path):
    """Inventory records should expose the fields an agent needs before loading."""
    skill_dir = tmp_path / ".agents" / "skills" / "triage"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "helper.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (skill_dir / "AGENT-BRIEF.md").write_text(
        "Acceptance criteria:\n- Issue has a label.\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: triage\n"
        "description: >\n"
        "  Triage issues through a state machine.\n"
        "  Use when user wants to create an issue.\n"
        "---\n\n"
        "# Triage\n\n"
        "Use the issue tracker and triage label vocabulary.\n",
        encoding="utf-8",
    )

    result = build_agent_skills_inventory(str(tmp_path))
    skill = result["skills"][0]

    assert result["skill_count"] == 1
    assert result["validation"]["status"] == "ready"
    assert result["agent_summary"]["validation_status"] == "ready"
    assert result["agent_summary"]["ready_for_use_count"] == 1
    assert result["agent_summary"]["readiness_ratio"] == 1.0
    assert result["agent_summary"]["actionable_skills"] == ["triage"]
    assert skill["name"] == "triage"
    assert skill["model_invocation_enabled"] is True
    assert skill["ready_for_use"] is True
    assert skill["actionability"] == "ready"
    assert skill["actionability_score"] >= 85
    assert skill["completion_guidance_present"] is True
    assert skill["scripts"] == [".agents/skills/triage/scripts/helper.sh"]
    assert skill["requires_context"] == ["issue_tracker", "triage_labels"]
    assert skill["side_effects"] == ["creates_issues"]
    assert skill["read_order"] == [
        ".agents/skills/triage/SKILL.md",
        ".agents/skills/triage/AGENT-BRIEF.md",
        ".agents/skills/triage/scripts/helper.sh",
    ]


def test_agent_skills_inventory_reports_missing_completion_without_brief_noise(
    tmp_path,
):
    """Missing AGENT-BRIEF is optional, while missing completion guidance is a gap."""
    skill_dir = tmp_path / ".agents" / "skills" / "zoom-out"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: zoom-out\n"
        "description: Tell the agent to zoom out. Use when more context helps.\n"
        "disable-model-invocation: true\n"
        "---\n\n"
        "# zoom-out\n\n"
        "Give a higher-level perspective.\n",
        encoding="utf-8",
    )

    result = build_agent_skills_inventory(str(tmp_path))
    skill = result["skills"][0]

    assert skill["model_invocation_enabled"] is False
    assert skill["ready_for_use"] is False
    assert skill["gaps"] == ["missing_completion_guidance"]
    assert result["gaps"]["missing_completion_guidance"] == ["zoom-out"]
    assert result["gaps"]["optional_agent_brief_missing"] == ["zoom-out"]
    assert result["agent_summary"]["ready_for_use_count"] == 0
    assert result["validation"]["status"] == "caution"
    assert result["validation"]["caution_gap_count"] == 1
    assert result["agent_summary"]["next_fix"] == (
        "Add completion or verification guidance to: zoom-out"
    )


def test_skill_validation_separates_blocking_caution_and_optional_gaps():
    """Validation summary should distinguish hard blockers from metadata polish."""
    validation = build_skill_validation(
        {
            "skills_root_missing": False,
            "missing_skill_md": ["broken"],
            "missing_completion_guidance": ["draft"],
            "missing_trigger_text": ["vague"],
            "optional_agent_brief_missing": ["draft", "vague"],
        }
    )

    assert validation == {
        "status": "blocked",
        "blocking_gaps": {
            "missing_skill_md": ["broken"],
            "missing_trigger_text": ["vague"],
        },
        "caution_gaps": {"missing_completion_guidance": ["draft"]},
        "optional_gaps": {"optional_agent_brief_missing": ["draft", "vague"]},
        "blocking_gap_count": 2,
        "caution_gap_count": 1,
        "optional_gap_count": 2,
        "next_fix": "Add SKILL.md to: broken",
    }
