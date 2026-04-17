#!/usr/bin/env python3
"""
Unit tests for MCP Tool Registry.
"""

from typing import Any

import pytest

from tree_sitter_analyzer.mcp.registry import (
    TOOLSET_DEFINITIONS,
    ToolEntry,
    ToolRegistry,
    get_registry,
    reset_registry,
)


class TestToolEntry:
    """Tests for ToolEntry class."""

    def test_init(self) -> None:
        """Test ToolEntry initialization."""
        schema = {
            "name": "test_tool",
            "description": "Test tool",
        }

        def handler() -> dict[str, str]:
            return {"result": "ok"}

        entry = ToolEntry(
            name="test_tool",
            toolset="test",
            category="test-category",
            schema=schema,
            handler=handler,
            is_async=True,
            description="Test tool description",
            emoji="🧪",
        )

        assert entry.name == "test_tool"
        assert entry.toolset == "test"
        assert entry.category == "test-category"
        assert entry.schema == schema
        assert entry.handler == handler
        assert entry.is_async is True
        assert entry.description == "Test tool description"
        assert entry.emoji == "🧪"

    def test_is_available_no_check_fn(self) -> None:
        """Test is_available returns True when no check function."""
        entry = ToolEntry(
            name="test",
            toolset="test",
            category="test",
            schema={},
            handler=lambda: {},
        )
        assert entry.is_available() is True

    def test_is_available_with_check_fn(self) -> None:
        """Test is_available uses check function."""
        entry_true = ToolEntry(
            name="test",
            toolset="test",
            category="test",
            schema={},
            handler=lambda: {},
            check_fn=lambda: True,
        )
        assert entry_true.is_available() is True

        entry_false = ToolEntry(
            name="test",
            toolset="test",
            category="test",
            schema={},
            handler=lambda: {},
            check_fn=lambda: False,
        )
        assert entry_false.is_available() is False

    def test_is_available_check_fn_exception(self) -> None:
        """Test is_available handles exceptions gracefully."""

        def failing_check() -> bool:
            raise RuntimeError("Check failed")

        entry = ToolEntry(
            name="test",
            toolset="test",
            category="test",
            schema={},
            handler=lambda: {},
            check_fn=failing_check,
        )
        assert entry.is_available() is False

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        entry = ToolEntry(
            name="test_tool",
            toolset="test",
            category="test-category",
            schema={"description": "Test"},
            handler=lambda: {},
            description="Test description",
            emoji="🧪",
        )

        result = entry.to_dict()
        assert result == {
            "name": "test_tool",
            "toolset": "test",
            "category": "test-category",
            "description": "Test description",
            "emoji": "🧪",
            "available": True,
            "is_async": True,
        }


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        reset_registry()

    def test_singleton(self) -> None:
        """Test singleton pattern."""
        reg1 = ToolRegistry.get_instance()
        reg2 = ToolRegistry.get_instance()
        assert reg1 is reg2

    def test_register(self) -> None:
        """Test tool registration."""
        registry = ToolRegistry.get_instance()

        schema = {"name": "test_tool", "description": "Test"}

        def handler() -> dict[str, Any]:
            return {}

        registry.register(
            name="test_tool",
            toolset="test",
            category="test-category",
            schema=schema,
            handler=handler,
        )

        assert "test_tool" in registry._tools
        assert registry._tools["test_tool"].name == "test_tool"

    def test_register_duplicate_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test warning on duplicate registration."""
        registry = ToolRegistry.get_instance()

        schema1 = {"name": "test", "description": "First"}
        schema2 = {"name": "test", "description": "Second"}

        registry.register(
            name="test",
            toolset="first",
            category="test",
            schema=schema1,
            handler=lambda: {},
        )

        with caplog.at_level("WARNING"):
            registry.register(
                name="test",
                toolset="second",
                category="test",
                schema=schema2,
                handler=lambda: {},
            )

        assert "Tool name collision" in caplog.text
        assert registry._tools["test"].toolset == "second"

    def test_get_tool(self) -> None:
        """Test get_tool method."""
        registry = ToolRegistry.get_instance()

        registry.register(
            name="test_tool",
            toolset="test",
            category="test",
            schema={},
            handler=lambda: {},
        )

        tool = registry.get_tool("test_tool")
        assert tool is not None
        assert tool.name == "test_tool"

        assert registry.get_tool("nonexistent") is None

    def test_list_tools(self) -> None:
        """Test list_tools method."""
        registry = ToolRegistry.get_instance()

        registry.register(
            name="tool1",
            toolset="analysis",
            category="test",
            schema={},
            handler=lambda: {},
        )
        registry.register(
            name="tool2",
            toolset="query",
            category="test",
            schema={},
            handler=lambda: {},
        )
        registry.register(
            name="tool3",
            toolset="analysis",
            category="test",
            schema={},
            handler=lambda: {},
            check_fn=lambda: False,
        )

        # All tools
        all_tools = registry.list_tools()
        assert len(all_tools) == 3

        # Filter by toolset
        analysis_tools = registry.list_tools(toolset="analysis")
        assert len(analysis_tools) == 2
        assert all(t.toolset == "analysis" for t in analysis_tools)

        # Available only
        available = registry.list_tools(available_only=True)
        assert len(available) == 2

    def test_get_toolsets(self) -> None:
        """Test get_toolsets method."""
        registry = ToolRegistry.get_instance()

        registry.register(
            name="tool1",
            toolset="analysis",
            category="test",
            schema={"description": "Tool 1"},
            handler=lambda: {},
        )
        registry.register(
            name="tool2",
            toolset="query",
            category="test",
            schema={"description": "Tool 2"},
            handler=lambda: {},
        )

        toolsets = registry.get_toolsets()
        assert "analysis" in toolsets
        assert "query" in toolsets
        assert toolsets["analysis"]["count"] == 1
        assert toolsets["query"]["count"] == 1
        assert toolsets["analysis"]["tools"][0]["name"] == "tool1"

    def test_deregister(self) -> None:
        """Test deregister method."""
        registry = ToolRegistry.get_instance()

        registry.register(
            name="test_tool",
            toolset="test",
            category="test",
            schema={},
            handler=lambda: {},
        )

        assert "test_tool" in registry._tools

        registry.deregister("test_tool")

        assert "test_tool" not in registry._tools

    def test_deregister_unknown(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test deregister with unknown tool."""
        registry = ToolRegistry.get_instance()

        with caplog.at_level("WARNING"):
            registry.deregister("unknown")

        assert "Cannot deregister unknown tool" in caplog.text

    def test_clear(self) -> None:
        """Test clear method."""
        registry = ToolRegistry.get_instance()

        registry.register(
            name="tool1",
            toolset="test",
            category="test",
            schema={},
            handler=lambda: {},
        )
        registry.register(
            name="tool2",
            toolset="test",
            category="test",
            schema={},
            handler=lambda: {},
        )

        assert len(registry._tools) == 2

        registry.clear()

        assert len(registry._tools) == 0
        assert len(registry._toolsets) == 0


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        reset_registry()

    def test_get_registry(self) -> None:
        """Test get_registry returns singleton."""
        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2

    def test_reset_registry(self) -> None:
        """Test reset_registry."""
        reg1 = get_registry()
        reg1.register(
            name="test",
            toolset="test",
            category="test",
            schema={},
            handler=lambda: {},
        )

        reset_registry()

        reg2 = get_registry()
        assert reg1 is not reg2
        assert len(reg2._tools) == 0


class TestToolsetDefinitions:
    """Tests for TOOLSET_DEFINITIONS constant."""

    def test_definitions_exist(self) -> None:
        """Test that toolset definitions are defined."""
        assert isinstance(TOOLSET_DEFINITIONS, dict)
        assert len(TOOLSET_DEFINITIONS) > 0

    def test_expected_toolsets(self) -> None:
        """Test that expected toolsets exist."""
        expected_toolsets = ["analysis", "query", "navigation", "safety", "diagnostic", "index"]
        for toolset in expected_toolsets:
            assert toolset in TOOLSET_DEFINITIONS, f"Missing toolset: {toolset}"

    def test_toolset_structure(self) -> None:
        """Test that each toolset has required fields."""
        for _toolset, config in TOOLSET_DEFINITIONS.items():
            assert "description" in config
            assert "emoji" in config
            assert "tools" in config
            assert isinstance(config["tools"], list)

    def test_analysis_toolset(self) -> None:
        """Test analysis toolset contains expected tools."""
        analysis = TOOLSET_DEFINITIONS["analysis"]
        assert "dependency_query" in analysis["tools"]
        assert "trace_impact" in analysis["tools"]
