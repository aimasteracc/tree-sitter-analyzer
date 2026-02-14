#!/usr/bin/env python3
"""Tests for trace_symbol MCP tool."""

import pytest

from tree_sitter_analyzer.mcp.tools.trace_symbol_tool import TraceSymbolTool


@pytest.fixture
def tool():
    return TraceSymbolTool(project_root="/tmp/test")


class TestTraceSymbolToolDefinition:
    def test_tool_name(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "trace_symbol"

    def test_tool_has_description(self, tool):
        defn = tool.get_tool_definition()
        assert "description" in defn
        assert len(defn["description"]) > 0

    def test_tool_has_input_schema(self, tool):
        defn = tool.get_tool_definition()
        assert "inputSchema" in defn
        schema = defn["inputSchema"]
        assert "symbol" in schema["properties"]

    def test_symbol_required(self, tool):
        defn = tool.get_tool_definition()
        assert "symbol" in defn["inputSchema"]["required"]

    def test_trace_type_enum(self, tool):
        defn = tool.get_tool_definition()
        trace_type = defn["inputSchema"]["properties"]["trace_type"]
        assert "enum" in trace_type
        assert "full" in trace_type["enum"]
        assert "definition" in trace_type["enum"]


class TestTraceSymbolToolValidation:
    def test_valid_args(self, tool):
        assert tool.validate_arguments({"symbol": "foo"})

    def test_missing_symbol(self, tool):
        with pytest.raises(ValueError):
            tool.validate_arguments({})

    def test_invalid_trace_type(self, tool):
        with pytest.raises(ValueError):
            tool.validate_arguments({"symbol": "foo", "trace_type": "invalid"})

    def test_valid_all_args(self, tool):
        assert tool.validate_arguments(
            {
                "symbol": "foo",
                "file_path": "a.py",
                "trace_type": "full",
                "depth": 3,
                "output_format": "json",
            }
        )


class TestTraceSymbolToolExecute:
    @pytest.mark.asyncio
    async def test_execute_definition_only(self, tool):
        result = await tool.execute(
            {"symbol": "nonexistent", "trace_type": "definition"}
        )
        assert "definitions" in result or "error" in str(result)

    @pytest.mark.asyncio
    async def test_execute_returns_dict(self, tool):
        result = await tool.execute({"symbol": "test_func", "trace_type": "definition"})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_full_trace(self, tool):
        result = await tool.execute({"symbol": "test_func", "trace_type": "full"})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_with_output_format(self, tool):
        result = await tool.execute({"symbol": "test_func", "output_format": "json"})
        assert isinstance(result, dict)
