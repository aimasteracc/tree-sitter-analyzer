#!/usr/bin/env python3
"""
Unit tests for Tool Discovery MCP Tools.
"""

import pytest

from tree_sitter_analyzer.mcp.registry import get_registry, reset_registry
from tree_sitter_analyzer.mcp.tool_registration import register_all_tools
from tree_sitter_analyzer.mcp.tools.tool_discovery_tools import (
    ToolDescribeTool,
    ToolDiscoveryTool,
)


@pytest.fixture(autouse=True)
def setup_registry() -> None:
    """Setup registry with tools before each test."""
    reset_registry()
    register_all_tools()


class TestToolDiscoveryTool:
    """Tests for ToolDiscoveryTool (tools/list)."""

    @pytest.mark.asyncio
    async def test_list_all_tools(self) -> None:
        """Test listing all tools without filtering."""
        tool = ToolDiscoveryTool()
        result = await tool.execute({})

        assert "tools" in result
        assert "count" in result
        assert result["count"] == 29  # All tools (28 + test_coverage)
        assert len(result["tools"]) == 29

    @pytest.mark.asyncio
    async def test_list_tools_by_toolset(self) -> None:
        """Test listing tools filtered by toolset."""
        tool = ToolDiscoveryTool()

        # List analysis tools
        result = await tool.execute({"toolset": "analysis"})

        assert "tools" in result
        assert len(result["tools"]) == 16  # 15 + test_coverage

        for t in result["tools"]:
            assert t["toolset"] == "analysis"

    @pytest.mark.asyncio
    async def test_list_diagnostic_tools(self) -> None:
        """Test listing diagnostic tools."""
        tool = ToolDiscoveryTool()

        # List diagnostic tools
        result = await tool.execute({"toolset": "diagnostic"})

        assert "tools" in result
        assert len(result["tools"]) == 2  # check_tools + ci_report

        for t in result["tools"]:
            assert t["toolset"] == "diagnostic"

    @pytest.mark.asyncio
    async def test_list_safety_tools(self) -> None:
        """Test listing safety tools."""
        tool = ToolDiscoveryTool()

        # List safety tools
        result = await tool.execute({"toolset": "safety"})

        assert "tools" in result
        assert len(result["tools"]) == 2  # modification_guard + security_scan

        for t in result["tools"]:
            assert t["toolset"] == "safety"

    @pytest.mark.asyncio
    async def test_list_available_only(self) -> None:
        """Test listing only available tools."""
        tool = ToolDiscoveryTool()
        result = await tool.execute({"available_only": True})

        # All tools should be available (no check_fn that returns False)
        assert len(result["tools"]) > 0
        for t in result["tools"]:
            assert t["available"] is True

    def test_validate_arguments_invalid_toolset(self) -> None:
        """Test validation with invalid toolset."""
        tool = ToolDiscoveryTool()

        with pytest.raises(ValueError, match="Invalid toolset"):
            tool.validate_arguments({"toolset": "invalid"})

    def test_validate_arguments_invalid_available_only(self) -> None:
        """Test validation with invalid available_only."""
        tool = ToolDiscoveryTool()

        with pytest.raises(ValueError, match="must be a boolean"):
            tool.validate_arguments({"available_only": "not_a_bool"})

    def test_validate_arguments_valid(self) -> None:
        """Test validation with valid arguments."""
        tool = ToolDiscoveryTool()

        # Valid arguments
        assert tool.validate_arguments({}) is True
        assert tool.validate_arguments({"toolset": "analysis"}) is True
        assert tool.validate_arguments({"available_only": True}) is True


class TestToolDescribeTool:
    """Tests for ToolDescribeTool (tools/describe)."""

    @pytest.mark.asyncio
    async def test_describe_existing_tool(self) -> None:
        """Test describing an existing tool."""
        tool = ToolDescribeTool()
        result = await tool.execute({"tool_name": "dependency_query"})

        assert result["name"] == "dependency_query"
        assert result["toolset"] == "analysis"
        assert result["category"] == "dependency-graph"
        assert "description" in result
        assert "emoji" in result
        assert "schema" in result
        assert "available" in result

    @pytest.mark.asyncio
    async def test_describe_nonexistent_tool(self) -> None:
        """Test describing a non-existent tool."""
        tool = ToolDescribeTool()
        result = await tool.execute({"tool_name": "nonexistent_tool"})

        assert "error" in result
        assert "available_tools" in result
        assert len(result["available_tools"]) > 0

    def test_validate_arguments_missing_tool_name(self) -> None:
        """Test validation with missing tool_name."""
        tool = ToolDescribeTool()

        with pytest.raises(ValueError, match="is required"):
            tool.validate_arguments({})

    def test_validate_arguments_empty_tool_name(self) -> None:
        """Test validation with empty tool_name."""
        tool = ToolDescribeTool()

        with pytest.raises(ValueError, match="non-empty string"):
            tool.validate_arguments({"tool_name": ""})

    def test_validate_arguments_invalid_type(self) -> None:
        """Test validation with invalid type."""
        tool = ToolDescribeTool()

        with pytest.raises(ValueError, match="must be a non-empty string"):
            tool.validate_arguments({"tool_name": 123})

    def test_validate_arguments_valid(self) -> None:
        """Test validation with valid arguments."""
        tool = ToolDescribeTool()

        assert tool.validate_arguments({"tool_name": "query_code"}) is True


class TestToolDiscoveryIntegration:
    """Integration tests for tool discovery."""

    @pytest.mark.asyncio
    async def test_discovery_workflow(self) -> None:
        """Test complete discovery workflow: list then describe."""
        list_tool = ToolDiscoveryTool()
        describe_tool = ToolDescribeTool()

        # List all tools
        list_result = await list_tool.execute({})
        assert list_result["count"] > 0

        # Describe first tool
        first_tool_name = list_result["tools"][0]["name"]
        describe_result = await describe_tool.execute({"tool_name": first_tool_name})

        assert describe_result["name"] == first_tool_name
        assert "schema" in describe_result

    @pytest.mark.asyncio
    async def test_toolsets_consistency(self) -> None:
        """Test that toolsets in list match registry."""
        list_tool = ToolDiscoveryTool()
        registry = get_registry()

        for toolset in ["analysis", "query", "navigation", "safety", "diagnostic", "index"]:
            list_result = await list_tool.execute({"toolset": toolset})
            registry_tools = registry.list_tools(toolset=toolset)

            assert len(list_result["tools"]) == len(registry_tools)
