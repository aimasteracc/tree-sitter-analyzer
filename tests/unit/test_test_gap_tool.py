#!/usr/bin/env python3

import pytest

from tree_sitter_analyzer.mcp.tools.test_gap_tool import CodeGraphTestGapTool


@pytest.fixture
def tool(tmp_path):
    t = CodeGraphTestGapTool()
    t.set_project_path(str(tmp_path))
    return t


@pytest.fixture
def project_with_code(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "service.py").write_text(
        "def process(data):\n    return data\n\n"
        "def validate(item):\n    return bool(item)\n"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_service.py").write_text(
        "def test_process():\n    assert process([]) == []\n"
    )
    return tmp_path


class TestCodeGraphTestGapTool:
    def test_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_test_gap"
        assert "inputSchema" in defn

    def test_schema_has_modes(self, tool):
        schema = tool.get_tool_schema()
        mode_enum = schema["properties"]["mode"]["enum"]
        assert "summary" in mode_enum
        assert "gaps" in mode_enum
        assert "file" in mode_enum

    def test_output_format_defaults_to_toon(self, tool):
        # Wave 1b (audit health-03): MCP default is TOON (CLAUDE.md §1).
        # test_gap was the lone tool defaulting to json.
        schema = tool.get_tool_schema()
        assert schema["properties"]["output_format"]["default"] == "toon"

    @pytest.mark.asyncio
    async def test_default_output_is_toon_formatted(self, tool, project_with_code):
        tool.set_project_path(str(project_with_code))
        result = await tool.execute({"mode": "summary"})
        assert result.get("format") == "toon"
        assert "toon_content" in result

    def test_validate_no_mode(self):
        t = CodeGraphTestGapTool()
        assert t.validate_arguments({})

    def test_validate_invalid_mode(self):
        t = CodeGraphTestGapTool()
        with pytest.raises(ValueError, match="Invalid mode"):
            t.validate_arguments({"mode": "invalid"})

    def test_validate_file_mode_no_path(self):
        t = CodeGraphTestGapTool()
        with pytest.raises(ValueError, match="file_path"):
            t.validate_arguments({"mode": "file"})

    @pytest.mark.asyncio
    async def test_execute_summary(self, tool, project_with_code):
        tool.set_project_path(str(project_with_code))
        result = await tool.execute({"mode": "summary"})
        assert result["success"] is True
        assert "coverage_pct" in result
        assert "total_production_symbols" in result

    @pytest.mark.asyncio
    async def test_execute_gaps(self, tool, project_with_code):
        tool.set_project_path(str(project_with_code))
        result = await tool.execute({"mode": "gaps"})
        assert result["success"] is True
        assert "gaps" in result
        assert isinstance(result["gaps"], list)

    @pytest.mark.asyncio
    async def test_execute_file_mode(self, tool, project_with_code):
        tool.set_project_path(str(project_with_code))
        result = await tool.execute(
            {
                "mode": "file",
                "file_path": "service.py",
            }
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_no_project_root(self):
        t = CodeGraphTestGapTool()
        result = await t.execute({"mode": "summary"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_empty_project(self, tool, tmp_path):
        tool.set_project_path(str(tmp_path))
        result = await tool.execute({"mode": "gaps"})
        assert result["success"] is True
        assert result["gap_count"] == 0
