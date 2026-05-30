"""Tests for codegraph_metrics MCP tool — aggregated project intelligence."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool import CodeGraphMetricsTool


@pytest.fixture
def tool():
    return CodeGraphMetricsTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphMetricsTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_metrics"

    def test_description_mentions_codegraph_parity(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "CodeGraph" in desc

    def test_schema_has_sections_and_output_format(self, tool):
        schema = tool.get_tool_schema()
        assert "sections" in schema["properties"]
        assert "output_format" in schema["properties"]
        assert schema["properties"]["output_format"]["default"] == "toon"

    def test_schema_sections_enum(self, tool):
        items = tool.get_tool_schema()["properties"]["sections"]["items"]
        assert set(items["enum"]) == {
            "cache",
            "call_graph",
            "complexity",
            "routes",
            "health",
        }

    def test_annotations_readonly(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is True
        assert hints["destructiveHint"] is False


class TestValidation:
    def test_valid_no_sections(self, tool):
        assert tool.validate_arguments({}) is True

    def test_valid_subset_sections(self, tool):
        assert tool.validate_arguments({"sections": ["cache", "health"]}) is True

    def test_rejects_unknown_section(self, tool):
        with pytest.raises(ValueError, match="Invalid sections"):
            tool.validate_arguments({"sections": ["cache", "unknown"]})


@pytest.mark.asyncio
class TestExecuteNoCache:
    async def test_no_project_root_returns_info(self, tool):
        result = await tool.execute({"output_format": "json"})
        assert result["success"] is True
        assert result["cache_indexed"] is False

    async def test_cache_empty_section_hint(self, tool_with_root):
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool.ensure_indexed",
            return_value=None,
        ):
            result = await tool_with_root.execute(
                {"sections": ["cache"], "output_format": "json"}
            )
        assert result["success"] is True
        assert result["cache"]["status"] == "empty"

    async def test_toon_format_default(self, tool):
        result = await tool.execute({})
        assert result["format"] == "toon"
        assert "toon_content" in result

    async def test_sections_included_field(self, tool_with_root):
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool.ensure_indexed",
            return_value=None,
        ):
            result = await tool_with_root.execute(
                {"sections": ["cache", "health"], "output_format": "json"}
            )
        assert set(result["sections_included"]) == {"cache", "health"}


@pytest.mark.asyncio
class TestExecuteWithCache:
    async def test_cache_section_populated_when_indexed(self, tool_with_root):
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_files": 42,
            "total_symbols": 1000,
            "fts5_available": True,
            "fts_indexed_symbols": 950,
            "by_language": {"python": 40, "javascript": 2},
        }

        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool.ensure_indexed",
            return_value=mock_cache,
        ):
            result = await tool_with_root.execute(
                {"sections": ["cache"], "output_format": "json"}
            )

        assert result["cache"]["status"] == "indexed"
        assert result["cache"]["total_files"] == 42
        assert result["cache"]["total_symbols"] == 1000
        assert result["cache_indexed"] is True
