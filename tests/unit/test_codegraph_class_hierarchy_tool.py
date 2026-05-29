"""Tests for codegraph_class_hierarchy MCP tool — type inheritance analysis."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool


@pytest.fixture
def tool():
    return ClassHierarchyTool()


@pytest.fixture
def tool_with_root(tmp_path):
    (tmp_path / "models.py").write_text(
        "class Animal:\n    pass\n\nclass Dog(Animal):\n    pass\n\nclass Poodle(Dog):\n    pass\n"
    )
    return ClassHierarchyTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_class_hierarchy"

    def test_description_mentions_no_other(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "No other tool" in desc

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {
            "subclasses",
            "superclasses",
            "tree",
            "impact",
            "all",
            "summary",
        }

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )

    def test_annotations_readonly(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is True
        assert hints["destructiveHint"] is False


class TestValidation:
    def test_all_mode_no_class_required(self, tool):
        assert tool.validate_arguments({"mode": "all"}) is True

    def test_summary_mode_no_class_required(self, tool):
        assert tool.validate_arguments({"mode": "summary"}) is True

    def test_subclasses_requires_class_name(self, tool):
        with pytest.raises(ValueError, match="class_name is required"):
            tool.validate_arguments({"mode": "subclasses"})

    def test_superclasses_requires_class_name(self, tool):
        with pytest.raises(ValueError, match="class_name is required"):
            tool.validate_arguments({"mode": "superclasses"})

    def test_valid_subclasses_with_class_name(self, tool):
        assert (
            tool.validate_arguments({"mode": "subclasses", "class_name": "Animal"})
            is True
        )


@pytest.mark.asyncio
class TestExecute:
    async def test_no_project_root_raises_or_returns_error(self, tool):
        try:
            result = await tool.execute({"mode": "all", "output_format": "json"})
            assert result["success"] is False
        except ValueError:
            pass  # tool raises ValueError when project root is not set

    async def test_all_mode_on_project(self, tool_with_root):
        result = await tool_with_root.execute({"mode": "all", "output_format": "json"})
        assert result["success"] is True

    async def test_summary_mode_on_project(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "summary", "output_format": "json"}
        )
        assert result["success"] is True

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute({"mode": "summary"})
        assert result["format"] == "toon"
        assert "toon_content" in result
