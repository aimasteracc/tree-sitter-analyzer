#!/usr/bin/env python3
"""
Unit tests for MCP Tool Registration.
"""

import pytest

from tree_sitter_analyzer.mcp.registry import get_registry, reset_registry
from tree_sitter_analyzer.mcp.tool_registration import (
    get_tool_info,
    register_all_tools,
)


@pytest.fixture(autouse=True)
def reset_registry_before_each_test() -> None:
    """Reset registry before each test."""
    reset_registry()


class TestRegisterAllTools:
    """Tests for register_all_tools function."""

    def test_registers_all_tools(self) -> None:
        """Test that all expected tools are registered."""
        register_all_tools()

        registry = get_registry()

        # Expected tools by toolset (sample of critical tools)
        expected_tools = {
            "analysis": [
                "dependency_query",
                "trace_impact",
                "analyze_scale",
                "analyze_code_structure",
                "code_diff",
                "code_clone_detection",
                "health_score",
                "error_recovery",
                "semantic_impact",
                "understand_codebase",

                "dead_code_analysis",
                "test_coverage",
                "refactoring_suggestions",
                "design_patterns",
                "api_discovery",
                "cognitive_complexity",
                "nesting_complexity",
                "solid_principles",
                "global_state",
                "reflection_usage",
            ],
            "query": ["query_code", "extract_code_section", "get_code_outline", "semantic_search"],
            "navigation": ["list_files", "find_and_grep", "search_content", "batch_search"],
            "safety": ["modification_guard", "security_scan"],
            "diagnostic": ["check_tools", "ci_report", "change_impact", "pr_summary"],
            "index": ["build_project_index", "get_project_summary"],
        }

        for toolset, tools in expected_tools.items():
            toolset_tools = registry.list_tools(toolset=toolset)
            tool_names = [t.name for t in toolset_tools]
            for tool in tools:
                assert tool in tool_names, f"Tool '{tool}' not found in toolset '{toolset}'"

    def test_tool_count(self) -> None:
        """Test that the expected number of tools are registered."""
        register_all_tools()

        registry = get_registry()
        all_tools = registry.list_tools()

        # Dynamic tool count — just verify a reasonable minimum
        assert len(all_tools) >= 80

    def test_tool_metadata(self) -> None:
        """Test that registered tools have proper metadata."""
        register_all_tools()

        registry = get_registry()

        # Check a few tools for metadata
        dep_tool = registry.get_tool("dependency_query")
        assert dep_tool is not None
        assert dep_tool.toolset == "analysis"
        assert dep_tool.category == "dependency-graph"
        assert dep_tool.emoji == "🕸️"

        query_tool = registry.get_tool("query_code")
        assert query_tool is not None
        assert query_tool.toolset == "query"
        assert query_tool.emoji == "🔎"

    def test_all_tools_have_handler(self) -> None:
        """Test that all registered tools have a handler."""
        register_all_tools()

        registry = get_registry()
        all_tools = registry.list_tools()

        for tool in all_tools:
            assert tool.handler is not None, f"Tool '{tool.name}' has no handler"


class TestGetToolInfo:
    """Tests for get_tool_info function."""

    def test_returns_toolsets(self) -> None:
        """Test that get_tool_info returns toolset definitions."""
        info = get_tool_info()

        assert "toolsets" in info
        assert "registered_tools" in info

        toolsets = info["toolsets"]
        assert "analysis" in toolsets
        assert "query" in toolsets
        assert "navigation" in toolsets

    def test_toolsets_have_metadata(self) -> None:
        """Test that each toolset has required metadata."""
        info = get_tool_info()
        toolsets = info["toolsets"]

        for _toolset, config in toolsets.items():
            assert "description" in config
            assert "emoji" in config
            assert "tools" in config

    def test_registered_tools_structure(self) -> None:
        """Test that registered_tools has correct structure."""
        register_all_tools()
        info = get_tool_info()

        registered = info["registered_tools"]
        assert isinstance(registered, dict)

        for _toolset, data in registered.items():
            assert "tools" in data
            assert "count" in data
            assert isinstance(data["tools"], list)
            assert isinstance(data["count"], int)


class TestToolRegistrationIntegration:
    """Integration tests for tool registration."""

    def test_double_registration(self) -> None:
        """Test that double registration works correctly."""
        register_all_tools()
        registry = get_registry()
        count_before = len(registry.list_tools())

        # Register again
        register_all_tools()
        count_after = len(registry.list_tools())

        # Should still have the same number of tools (overwrites duplicates)
        assert count_after == count_before

    def test_toolsets_match_definitions(self) -> None:
        """Test that registered toolsets match TOOLSET_DEFINITIONS."""
        register_all_tools()
        info = get_tool_info()

        defined_toolsets = set(info["toolsets"].keys())
        registered_toolsets = set(info["registered_tools"].keys())

        # All registered toolsets should be in definitions
        assert registered_toolsets.issubset(defined_toolsets)

    def test_all_analysis_tools_registered(self) -> None:
        """Test that all analysis tools are registered."""
        register_all_tools()
        registry = get_registry()

        analysis_tools = registry.list_tools(toolset="analysis")
        tool_names = [t.name for t in analysis_tools]

        assert "dependency_query" in tool_names
        assert "trace_impact" in tool_names
        assert "analyze_scale" in tool_names
        assert "analyze_code_structure" in tool_names
        assert "code_diff" in tool_names

    def test_all_query_tools_registered(self) -> None:
        """Test that all query tools are registered."""
        register_all_tools()
        registry = get_registry()

        query_tools = registry.list_tools(toolset="query")
        tool_names = [t.name for t in query_tools]

        assert "query_code" in tool_names
        assert "extract_code_section" in tool_names
        assert "get_code_outline" in tool_names
        assert "semantic_search" in tool_names
