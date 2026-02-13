#!/usr/bin/env python3
"""Tests for assess_change_impact MCP tool."""
import pytest
from tree_sitter_analyzer.mcp.tools.assess_change_impact_tool import AssessChangeImpactTool


@pytest.fixture
def tool():
    return AssessChangeImpactTool(project_root="/tmp/test")


class TestAssessChangeImpactToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "assess_change_impact"

    def test_target_required(self, tool):
        assert "target" in tool.get_tool_definition()["inputSchema"]["required"]

    def test_change_type_enum(self, tool):
        schema = tool.get_tool_definition()["inputSchema"]
        assert "enum" in schema["properties"]["change_type"]


class TestAssessChangeImpactToolValidation:
    def test_valid_args(self, tool):
        assert tool.validate_arguments({"target": "foo"})

    def test_missing_target(self, tool):
        with pytest.raises(ValueError):
            tool.validate_arguments({})

    def test_invalid_change_type(self, tool):
        with pytest.raises(ValueError):
            tool.validate_arguments({"target": "foo", "change_type": "invalid"})


class TestAssessChangeImpactToolExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_dict(self, tool):
        result = await tool.execute({"target": "some_func"})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_has_data(self, tool):
        result = await tool.execute({"target": "some_func"})
        assert "data" in result or "error" in result
