"""Tests for Error Handling MCP Tool."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.error_handling_tool import ErrorHandlingTool


@pytest.fixture
def tool(tmp_path: Path):
    return ErrorHandlingTool(project_root=str(tmp_path))


@pytest.fixture
def tmp_py_file(tmp_path: Path):
    def _create(code: str) -> Path:
        p = tmp_path / "test_module.py"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    return _create


class TestErrorHandlingToolDefinition:
    def test_tool_name(self, tool: ErrorHandlingTool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "error_handling"

    def test_tool_has_input_schema(self, tool: ErrorHandlingTool):
        defn = tool.get_tool_definition()
        assert "inputSchema" in defn
        props = defn["inputSchema"]["properties"]
        assert "file_path" in props
        assert "project_root" in props
        assert "format" in props
        assert "severity" in props
        assert "pattern_type" in props


@pytest.mark.asyncio
class TestErrorHandlingToolExecute:
    async def test_analyze_file_json(self, tool: ErrorHandlingTool, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except:
                pass
        """)
        result = await tool.execute({
            "file_path": str(path),
            "format": "json",
        })
        assert result["total_issues"] >= 1
        assert "by_severity" in result
        assert "issues" in result

    async def test_analyze_file_toon(self, tool: ErrorHandlingTool, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except:
                pass
        """)
        result = await tool.execute({
            "file_path": str(path),
            "format": "toon",
        })
        assert "content" in result
        assert result["total_issues"] >= 1

    async def test_no_file_or_root_returns_empty(self, tool: ErrorHandlingTool):
        result = await tool.execute({"format": "json"})
        assert result["total_issues"] == 0

    async def test_severity_filter(self, tool: ErrorHandlingTool, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except:
                pass
            except ValueError:
                pass
        """)
        result = await tool.execute({
            "file_path": str(path),
            "format": "json",
            "severity": "error",
        })
        # Only bare except has severity "error"
        for issue in result["issues"]:
            assert issue["severity"] == "error"

    async def test_pattern_filter(self, tool: ErrorHandlingTool, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except:
                pass
        """)
        result = await tool.execute({
            "file_path": str(path),
            "format": "json",
            "pattern_type": "bare_except",
        })
        for issue in result["issues"]:
            assert issue["pattern_type"] == "bare_except"

    async def test_project_scan(self, tool: ErrorHandlingTool, tmp_path: Path):
        py_file = tmp_path / "mod.py"
        py_file.write_text("try:\n    x = 1\nexcept:\n    pass\n")
        result = await tool.execute({
            "project_root": str(tmp_path),
            "format": "json",
        })
        assert result["total_issues"] >= 1
