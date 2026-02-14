#!/usr/bin/env python3
"""Tests for check_architecture_health MCP tool."""

import pytest

from tree_sitter_analyzer.mcp.tools.check_architecture_health_tool import (
    CheckArchitectureHealthTool,
)


@pytest.fixture
def tool():
    return CheckArchitectureHealthTool(project_root="/tmp/test")


class TestCheckArchitectureHealthToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "check_architecture_health"

    def test_path_required(self, tool):
        assert "path" in tool.get_tool_definition()["inputSchema"]["required"]

    def test_has_checks_param(self, tool):
        schema = tool.get_tool_definition()["inputSchema"]
        assert "checks" in schema["properties"]


class TestCheckArchitectureHealthToolValidation:
    def test_valid_args(self, tool):
        assert tool.validate_arguments({"path": "src/"})

    def test_missing_path(self, tool):
        with pytest.raises(ValueError):
            tool.validate_arguments({})


class TestCheckArchitectureHealthToolExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_dict(self, tool):
        result = await tool.execute({"path": "src/"})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_has_score(self, tool):
        result = await tool.execute({"path": "src/"})
        assert "data" in result
        assert "score" in result["data"]
