"""Tests for the MCP agent skills inventory tool."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool


@pytest.mark.asyncio
async def test_agent_skills_tool_lists_project_skills(tmp_path):
    """MCP output should mirror the CLI inventory shape."""
    skill_dir = tmp_path / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo\n"
        "description: Use when testing MCP skill inventory.\n"
        "---\n\n"
        "# Demo\n\n"
        "## Acceptance Criteria\n\n"
        "- MCP sees this skill.\n",
        encoding="utf-8",
    )

    result = await AgentSkillsTool(str(tmp_path)).execute({"output_format": "json"})

    assert result["success"] is True
    assert result["inventory"] == "project agent skills"
    assert result["skill_count"] == 1
    assert result["skills"][0]["name"] == "demo"
    assert result["validation"]["status"] == "ready"
    assert result["agent_summary"]["inspection_command"] == (
        "uv run tree-sitter-analyzer agent-skills --format json"
    )


@pytest.mark.asyncio
async def test_agent_skills_tool_supports_custom_relative_root(tmp_path):
    """Custom skills_root should be validated and passed to the shared builder."""
    skill_dir = tmp_path / "docs" / "skills" / "local"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: local\n"
        "description: Use when testing custom roots.\n"
        "---\n\n"
        "# Local\n",
        encoding="utf-8",
    )

    result = await AgentSkillsTool(str(tmp_path)).execute(
        {"skills_root": "docs/skills", "output_format": "toon"}
    )

    assert result["format"] == "toon"
    assert result["skills_root"] == "docs/skills"
    assert "skills" not in result
    assert result["validation"]["status"] == "caution"
    assert "toon_content" in result
    assert "validation_status: caution" in result["toon_content"]
    assert "local" in result["toon_content"]


@pytest.mark.asyncio
async def test_agent_skills_tool_rejects_external_absolute_root(tmp_path):
    """MCP callers cannot inspect skills outside the configured project root."""
    tool = AgentSkillsTool(str(tmp_path))

    with pytest.raises(ValueError, match="Invalid skills_root"):
        await tool.execute({"skills_root": "/tmp/outside-skills"})
