"""Tests for CodeGraph Status tool — index health at-a-glance."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
    CodeGraphStatusTool,
)


@pytest.fixture
def tool():
    return CodeGraphStatusTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphStatusTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_status"

    def test_description_starts_with_index_health(self, tool):
        defn = tool.get_tool_definition()
        assert defn["description"].startswith("INDEX HEALTH")

    def test_annotations_all_four_hints(self, tool):
        defn = tool.get_tool_definition()
        annotations = defn["annotations"]
        assert annotations["readOnlyHint"] is True
        assert annotations["destructiveHint"] is False
        assert annotations["idempotentHint"] is True
        assert annotations["openWorldHint"] is False

    def test_schema_strict_no_additional_properties(self, tool):
        schema = tool.get_tool_schema()
        assert schema["additionalProperties"] is False

    def test_schema_output_format_default_is_toon(self, tool):
        schema = tool.get_tool_schema()
        assert schema["properties"]["output_format"]["default"] == "toon"

    def test_schema_include_lag_default_true(self, tool):
        schema = tool.get_tool_schema()
        assert schema["properties"]["include_lag"]["default"] is True


class TestValidateArguments:
    def test_empty_args_accepted(self, tool):
        assert tool.validate_arguments({}) is True

    def test_include_lag_must_be_bool(self, tool):
        with pytest.raises(ValueError, match="include_lag"):
            tool.validate_arguments({"include_lag": "yes"})


class TestExecuteNoProjectRoot:
    @pytest.mark.asyncio
    async def test_no_project_root_returns_not_found(self, tool):
        result = await tool.execute({"output_format": "json"})
        assert result["verdict"] == "NOT_FOUND"
        assert result["indexed"] is False
        assert result["total_files"] == 0
        assert result["total_symbols"] == 0
        assert result["project_root"] is None
        assert "hint" in result, "NOT_FOUND response must carry a 'hint' field"
        assert "project_root" in result["hint"]


class TestExecuteNoCache:
    @pytest.mark.asyncio
    async def test_project_set_but_no_cache_returns_warn(self, tool_with_root):
        result = await tool_with_root.execute({"output_format": "json"})
        assert result["verdict"] == "WARN"
        assert result["indexed"] is False
        assert result["total_files"] == 0
        assert result["cache_path"] is None
        assert result["agent_summary"]["summary_line"] == (
            "codegraph_status: index missing or empty"
        )
        assert "hint" in result, "WARN response must carry a 'hint' field"
        assert "warm" in result["hint"].lower() or "index" in result["hint"].lower()


class TestExecuteOutputFormat:
    @pytest.mark.asyncio
    async def test_toon_format_default(self, tool):
        result = await tool.execute({})
        assert result["format"] == "toon"
        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_json_format_no_toon_blob(self, tool):
        result = await tool.execute({"output_format": "json"})
        assert "toon_content" not in result
        assert result["verdict"] == "NOT_FOUND"
