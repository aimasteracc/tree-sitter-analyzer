"""Tests for codegraph_similarity MCP tool — AST-structural clone detection."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.code_similarity_tool import (
    CodeGraphSimilarityTool as CodeSimilarityTool,
)


@pytest.fixture
def tool():
    return CodeSimilarityTool()


@pytest.fixture
def tool_with_root(tmp_path):
    (tmp_path / "a.py").write_text(
        "def process(x):\n    return x * 2\n\ndef handle(x):\n    return x * 2\n"
    )
    return CodeSimilarityTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_similarity"

    def test_description_mentions_no_other(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "No other tool" in desc

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {"all", "structural", "textual"}
        assert mode["default"] == "all"

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )


@pytest.mark.asyncio
class TestExecute:
    async def test_runs_on_project(self, tool_with_root):
        result = await tool_with_root.execute({"output_format": "json"})
        assert result["success"] is True

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute({})
        assert result["format"] == "toon"
        assert "toon_content" in result
