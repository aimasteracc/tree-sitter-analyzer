"""Tests for the MCP SMART agent workflow tool."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.agent_workflow_tool import AgentWorkflowTool


@pytest.mark.asyncio
async def test_agent_workflow_tool_returns_full_json_pack(tmp_path):
    """MCP JSON output should mirror the CLI workflow pack shape."""
    target = tmp_path / "src" / "service.py"
    target.parent.mkdir()
    target.write_text("def run():\n    return 1\n", encoding="utf-8")

    result = await AgentWorkflowTool(str(tmp_path)).execute(
        {"target_path": "src/service.py", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["workflow"] == "SMART agent workflow pack"
    assert result["target_path"] == "src/service.py"
    assert result["current_phase"] == "analyze"
    assert result["phase_order"] == ["set", "map", "analyze", "retrieve", "trace"]
    assert result["current_step"]["step"] == "analyze"
    assert result["recommended_commands"] == result["current_step"]["cli_commands"]
    assert [step["step"] for step in result["steps"]] == [
        "set",
        "map",
        "analyze",
        "retrieve",
        "trace",
    ]
    assert result["agent_summary"]["next_step"] == (
        "uv run tree-sitter-analyzer safe-to-edit src/service.py --edit-type refactor --format json"
    )
    assert result["agent_summary"]["current_phase"] == "analyze"
    assert result["agent_summary"]["recommended_commands"] == [
        "uv run tree-sitter-analyzer smart-context src/service.py --format json",
        "uv run tree-sitter-analyzer file-health src/service.py --format json",
        "uv run tree-sitter-analyzer safe-to-edit src/service.py --edit-type refactor --format json",
        "uv run tree-sitter-analyzer refactor src/service.py --format json",
    ]
    assert result["agent_summary"]["queue_ledger_command"] == (
        "uv run tree-sitter-analyzer change-impact "
        "--change-impact-scope src/service.py --agent-summary-only --format json"
    )
    assert (
        result["steps"][-1]["cli_commands"][-1]
        == (result["agent_summary"]["queue_ledger_command"])
    )


@pytest.mark.asyncio
async def test_agent_workflow_tool_defaults_to_compact_toon(tmp_path):
    """TOON output keeps the MCP response compact but still actionable."""
    result = await AgentWorkflowTool(str(tmp_path)).execute({})

    assert result["format"] == "toon"
    assert result["workflow"] == "SMART agent workflow pack"
    assert "steps" not in result
    assert result["current_phase"] == "set"
    assert result["current_step"]["step"] == "set"
    assert result["recommended_commands"] == [
        "uv run tree-sitter-analyzer overview --format json"
    ]
    assert result["agent_summary"]["current_phase"] == "set"
    assert result["agent_summary"]["step_count"] == 5
    assert "current_phase: set" in result["toon_content"]
    assert "recommended_commands:" in result["toon_content"]
    assert "queue_boundary" in result["toon_content"]


@pytest.mark.asyncio
async def test_agent_workflow_toon_surfaces_queue_ledger_command(tmp_path):
    """Targeted TOON output should expose the scoped queue-ledger command."""
    target = tmp_path / "src" / "service.py"
    target.parent.mkdir()
    target.write_text("def run():\n    return 1\n", encoding="utf-8")

    result = await AgentWorkflowTool(str(tmp_path)).execute(
        {"target_path": "src/service.py", "output_format": "toon"}
    )

    assert result["agent_summary"]["queue_ledger_command"] == (
        "uv run tree-sitter-analyzer change-impact "
        "--change-impact-scope src/service.py --agent-summary-only --format json"
    )
    assert (
        "queue_ledger: uv run tree-sitter-analyzer change-impact"
        in result["toon_content"]
    )


@pytest.mark.asyncio
async def test_agent_workflow_tool_rejects_external_absolute_target(tmp_path):
    """MCP callers cannot generate workflow commands for outside paths."""
    tool = AgentWorkflowTool(str(tmp_path))

    with pytest.raises(ValueError, match="Invalid target_path"):
        await tool.execute({"target_path": "/tmp/outside.py"})
