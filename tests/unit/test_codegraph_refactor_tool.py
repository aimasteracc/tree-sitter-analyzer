"""Tests for codegraph_refactor MCP tool — AST-aware symbol renaming."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_refactor_tool import CodeGraphRefactorTool


@pytest.fixture
def tool():
    return CodeGraphRefactorTool()


@pytest.fixture
def tool_with_root(tmp_path):
    t = CodeGraphRefactorTool(str(tmp_path))
    return t


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_refactor"

    def test_schema_required_fields(self, tool):
        required = tool.get_tool_schema()["required"]
        assert "symbol" in required
        assert "new_name" in required

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {"preview", "apply"}
        assert mode["default"] == "preview"

    def test_schema_output_format_default_toon(self, tool):
        fmt = tool.get_tool_schema()["properties"]["output_format"]
        assert fmt["default"] == "toon"

    def test_no_annotations_destructive_false(self, tool):
        defn = tool.get_tool_definition()
        # refactor tool explicitly does NOT have readOnlyHint in the dict
        # because it CAN write (apply mode); omitting the hint is fine per spec.
        # The important thing is it doesn't claim readOnlyHint=True.
        assert defn.get("annotations", {}).get("readOnlyHint") is not True


class TestValidation:
    def test_valid_rename(self, tool):
        assert (
            tool.validate_arguments({"symbol": "old_name", "new_name": "new_name"})
            is True
        )

    def test_requires_symbol(self, tool):
        with pytest.raises(ValueError, match="symbol is required"):
            tool.validate_arguments({"symbol": "", "new_name": "new_name"})

    def test_requires_new_name(self, tool):
        with pytest.raises(ValueError, match="new_name is required"):
            tool.validate_arguments({"symbol": "old_name", "new_name": ""})

    def test_same_name_rejected(self, tool):
        with pytest.raises(ValueError, match="must differ"):
            tool.validate_arguments({"symbol": "foo", "new_name": "foo"})

    def test_invalid_chars_in_symbol(self, tool):
        with pytest.raises(ValueError, match="valid identifier"):
            tool.validate_arguments({"symbol": "bad-name", "new_name": "good_name"})

    def test_invalid_chars_in_new_name(self, tool):
        with pytest.raises(ValueError, match="valid identifier"):
            tool.validate_arguments({"symbol": "old_name", "new_name": "bad-name"})

    def test_dotted_symbol_allowed(self, tool):
        assert (
            tool.validate_arguments(
                {"symbol": "Module.method", "new_name": "new_method"}
            )
            is True
        )


@pytest.mark.asyncio
class TestExecutePreview:
    async def test_preview_no_project_root_returns_error(self, tool):
        result = await tool.execute(
            {"symbol": "foo", "new_name": "bar", "output_format": "json"}
        )
        assert result["success"] is False

    async def test_preview_on_empty_project(self, tool_with_root):
        result = await tool_with_root.execute(
            {
                "symbol": "nonexistent_fn",
                "new_name": "renamed_fn",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert (
            result.get("dry_run") is True
            or result.get("preview") is True
            or "sites" in result
        )

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute(
            {"symbol": "nonexistent_fn", "new_name": "renamed_fn"}
        )
        assert result["format"] == "toon"
        assert "toon_content" in result
