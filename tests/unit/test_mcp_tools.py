"""
Test MCP Tool Interface implementation.

Following TDD: Write tests FIRST to define the contract.
This is T4.1: MCP Tool Interface

The tool interface provides:
- Base tool class
- Tool schema generation
- Argument validation
- Tool execution framework
"""

import pytest


class TestMCPToolBasics:
    """Test basic MCP tool functionality."""

    def test_base_tool_can_be_imported(self):
        """Test that BaseTool can be imported."""
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

        assert BaseTool is not None

    def test_tool_initialization(self):
        """Test creating a tool instance."""
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

        class TestTool(BaseTool):
            """Test tool implementation."""

            def get_name(self) -> str:
                return "test_tool"

            def get_description(self) -> str:
                return "A test tool"

            def get_schema(self) -> dict:
                return {"type": "object", "properties": {}}

            def execute(self, arguments: dict) -> dict:
                return {"result": "ok"}

        tool = TestTool()
        assert tool is not None


class TestToolSchema:
    """Test tool schema generation."""

    def test_tool_has_name(self):
        """Test that tool provides a name."""
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

        class TestTool(BaseTool):
            def get_name(self) -> str:
                return "test_tool"

            def get_description(self) -> str:
                return "A test tool"

            def get_schema(self) -> dict:
                return {"type": "object"}

            def execute(self, arguments: dict) -> dict:
                return {}

        tool = TestTool()
        assert tool.get_name() == "test_tool"

    def test_tool_has_description(self):
        """Test that tool provides a description."""
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

        class TestTool(BaseTool):
            def get_name(self) -> str:
                return "test"

            def get_description(self) -> str:
                return "Test description"

            def get_schema(self) -> dict:
                return {"type": "object"}

            def execute(self, arguments: dict) -> dict:
                return {}

        tool = TestTool()
        assert tool.get_description() == "Test description"

    def test_tool_has_schema(self):
        """Test that tool provides JSON schema."""
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

        class TestTool(BaseTool):
            def get_name(self) -> str:
                return "test"

            def get_description(self) -> str:
                return "Test"

            def get_schema(self) -> dict:
                return {
                    "type": "object",
                    "properties": {"arg1": {"type": "string"}},
                    "required": ["arg1"],
                }

            def execute(self, arguments: dict) -> dict:
                return {}

        tool = TestTool()
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "properties" in schema
        assert "arg1" in schema["properties"]


class TestToolExecution:
    """Test tool execution."""

    def test_tool_can_execute(self):
        """Test that tool can be executed."""
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

        class TestTool(BaseTool):
            def get_name(self) -> str:
                return "test"

            def get_description(self) -> str:
                return "Test"

            def get_schema(self) -> dict:
                return {"type": "object"}

            def execute(self, arguments: dict) -> dict:
                return {"result": "executed"}

        tool = TestTool()
        result = tool.execute({})

        assert result["result"] == "executed"

    def test_tool_receives_arguments(self):
        """Test that tool receives arguments."""
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

        class TestTool(BaseTool):
            def get_name(self) -> str:
                return "test"

            def get_description(self) -> str:
                return "Test"

            def get_schema(self) -> dict:
                return {"type": "object"}

            def execute(self, arguments: dict) -> dict:
                return {"arg1": arguments.get("arg1")}

        tool = TestTool()
        result = tool.execute({"arg1": "value1"})

        assert result["arg1"] == "value1"


class TestToolRegistry:
    """Test tool registry functionality."""

    def test_registry_can_be_imported(self):
        """Test that ToolRegistry can be imported."""
        from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry

        assert ToolRegistry is not None

    def test_registry_initialization(self):
        """Test creating a registry instance."""
        from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry

        registry = ToolRegistry()
        assert registry is not None

    def test_register_tool(self):
        """Test registering a tool."""
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
        from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry

        class TestTool(BaseTool):
            def get_name(self) -> str:
                return "test_tool"

            def get_description(self) -> str:
                return "Test"

            def get_schema(self) -> dict:
                return {"type": "object"}

            def execute(self, arguments: dict) -> dict:
                return {}

        registry = ToolRegistry()
        tool = TestTool()
        registry.register(tool)

        assert "test_tool" in registry.list_tools()

    def test_get_tool(self):
        """Test retrieving a tool."""
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
        from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry

        class TestTool(BaseTool):
            def get_name(self) -> str:
                return "test_tool"

            def get_description(self) -> str:
                return "Test"

            def get_schema(self) -> dict:
                return {"type": "object"}

            def execute(self, arguments: dict) -> dict:
                return {}

        registry = ToolRegistry()
        tool = TestTool()
        registry.register(tool)

        retrieved = registry.get("test_tool")
        assert retrieved.get_name() == "test_tool"

    def test_get_unknown_tool_raises_error(self):
        """Test that getting unknown tool raises error."""
        from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry

        registry = ToolRegistry()

        with pytest.raises(ValueError, match="Unknown tool"):
            registry.get("unknown_tool")

    def test_list_tools(self):
        """Test listing all tools."""
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
        from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry

        class Tool1(BaseTool):
            def get_name(self) -> str:
                return "tool1"

            def get_description(self) -> str:
                return "Tool 1"

            def get_schema(self) -> dict:
                return {"type": "object"}

            def execute(self, arguments: dict) -> dict:
                return {}

        class Tool2(BaseTool):
            def get_name(self) -> str:
                return "tool2"

            def get_description(self) -> str:
                return "Tool 2"

            def get_schema(self) -> dict:
                return {"type": "object"}

            def execute(self, arguments: dict) -> dict:
                return {}

        registry = ToolRegistry()
        registry.register(Tool1())
        registry.register(Tool2())

        tools = registry.list_tools()
        assert "tool1" in tools
        assert "tool2" in tools
