"""Tests for codegraph_query MCP tool — chain DSL entry point."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    CodeGraphQueryTool,
    parse_chain,
)


@pytest.fixture
def tool():
    return CodeGraphQueryTool()


@pytest.fixture
def tool_with_root(tmp_path):
    (tmp_path / "app.py").write_text(
        "def handle_request(req):\n    return process(req)\n\ndef process(req):\n    pass\n"
    )
    return CodeGraphQueryTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_query"

    def test_description_mentions_confidence(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "confidence" in desc

    def test_description_mentions_bm25(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "BM25" in desc

    def test_annotations_readonly(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is True
        assert hints["destructiveHint"] is False

    def test_schema_requires_query(self, tool):
        assert "query" in tool.get_tool_schema()["required"]

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )


class TestValidation:
    def test_requires_query(self, tool):
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments({})

    def test_empty_query_rejected(self, tool):
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments({"query": "  "})

    def test_valid_query(self, tool):
        assert tool.validate_arguments({"query": "search('foo')"}) is True


class TestParseChain:
    def test_plain_string_expands(self):
        steps = parse_chain("MyService")
        assert steps[0].name == "explore"

    def test_dotted_chain_parsed(self):
        steps = parse_chain("search('foo').callers(depth=2)")
        names = [s.name for s in steps]
        assert "search" in names
        assert "callers" in names


@pytest.mark.asyncio
class TestExecute:
    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute({"query": "search('handle_request')"})
        assert result["format"] == "toon"
        assert "toon_content" in result

    async def test_json_format(self, tool_with_root):
        result = await tool_with_root.execute(
            {"query": "search('handle_request')", "output_format": "json"}
        )
        assert "toon_content" not in result
        assert result["success"] is True

    async def test_plain_query_returns_results(self, tool_with_root):
        result = await tool_with_root.execute(
            {"query": "handle_request", "output_format": "json"}
        )
        assert result["success"] is True

    async def test_invalid_chain_step_returns_error(self, tool_with_root):
        result = await tool_with_root.execute(
            {"query": "search('foo').delete()", "output_format": "json"}
        )
        assert result["success"] is False
