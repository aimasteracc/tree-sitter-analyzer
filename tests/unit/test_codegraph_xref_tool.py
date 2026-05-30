"""Tests for codegraph_xref MCP tool — instant multi-dimension cross-reference."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_xref_tool import CodeGraphXRefTool


@pytest.fixture
def tool():
    return CodeGraphXRefTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphXRefTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_xref"

    def test_description_mentions_codegraph_parity(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "CodeGraph" in desc

    def test_annotations_readonly(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is True
        assert hints["destructiveHint"] is False

    def test_schema_mode_default_symbol(self, tool):
        mode_prop = tool.get_tool_schema()["properties"]["mode"]
        assert mode_prop["default"] == "symbol"
        assert set(mode_prop["enum"]) == {"symbol", "file"}

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )


class TestValidation:
    def test_symbol_mode_requires_symbol(self, tool):
        with pytest.raises(ValueError, match="symbol is required"):
            tool.validate_arguments({"mode": "symbol"})

    def test_file_mode_requires_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "file"})

    def test_invalid_mode_rejected(self, tool):
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "unknown", "symbol": "foo"})

    def test_valid_symbol_mode(self, tool):
        assert tool.validate_arguments({"mode": "symbol", "symbol": "foo"}) is True

    def test_valid_file_mode(self, tool):
        assert tool.validate_arguments({"mode": "file", "file_path": "app.py"}) is True


@pytest.mark.asyncio
class TestExecute:
    async def test_symbol_not_found_returns_not_found_verdict(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "symbol", "symbol": "no_such_symbol", "output_format": "json"}
        )
        assert result["verdict"] == "NOT_FOUND"

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "symbol", "symbol": "any_symbol"}
        )
        assert result["format"] == "toon"
        assert "toon_content" in result

    async def test_symbol_mode_field_in_response(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "symbol", "symbol": "anything", "output_format": "json"}
        )
        assert result.get("mode") == "symbol"

    async def test_file_mode_field_in_response(self, tool_with_root, tmp_path):
        (tmp_path / "app.py").write_text("def foo():\n    pass\n")
        result = await tool_with_root.execute(
            {"mode": "file", "file_path": "app.py", "output_format": "json"}
        )
        assert result.get("mode") == "file"
