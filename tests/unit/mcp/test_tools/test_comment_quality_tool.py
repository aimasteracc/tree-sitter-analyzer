"""Tests for Comment Quality MCP Tool."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.comment_quality_tool import CommentQualityTool


@pytest.fixture
def tool() -> CommentQualityTool:
    return CommentQualityTool()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    def _write(code: str) -> Path:
        p = tmp_path / "test_file.py"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p
    return _write  # type: ignore[return-value]


class TestToolDefinition:
    def test_tool_name(self, tool: CommentQualityTool) -> None:
        definition = tool.get_tool_definition()
        assert definition["name"] == "comment_quality"

    def test_has_input_schema(self, tool: CommentQualityTool) -> None:
        definition = tool.get_tool_definition()
        assert "inputSchema" in definition
        props = definition["inputSchema"]["properties"]
        assert "file_path" in props
        assert "project_root" in props
        assert "format" in props

    def test_has_issue_types_filter(self, tool: CommentQualityTool) -> None:
        definition = tool.get_tool_definition()
        props = definition["inputSchema"]["properties"]
        assert "issue_types" in props


class TestToolExecution:
    @pytest.mark.asyncio
    async def test_analyze_file_json(
        self, tool: CommentQualityTool, tmp_py: Path
    ) -> None:
        path = tmp_py('''
        def foo(x):
            """Do foo.

            :param y: not real
            """
            return x
        ''')
        result = await tool.execute({
            "file_path": str(path),
            "format": "json",
        })
        assert "issues" in result
        assert "quality_score" in result
        assert result["issue_count"] >= 1

    @pytest.mark.asyncio
    async def test_analyze_file_toon(
        self, tool: CommentQualityTool, tmp_py: Path
    ) -> None:
        path = tmp_py('''
        def bar():
            """Simple function."""
            pass
        ''')
        result = await tool.execute({
            "file_path": str(path),
            "format": "toon",
        })
        assert "content" in result
        assert "quality_score" in result

    @pytest.mark.asyncio
    async def test_filter_by_issue_type(
        self, tool: CommentQualityTool, tmp_py: Path
    ) -> None:
        path = tmp_py('''
        def baz(a, b):
            """Do baz.

            :param a: first
            """
            # TODO: fix later
            pass
        ''')
        result = await tool.execute({
            "file_path": str(path),
            "issue_types": "stale_todo",
            "format": "json",
        })
        assert result["issue_count"] >= 1
        for issue in result["issues"]:
            assert issue["type"] == "stale_todo"

    @pytest.mark.asyncio
    async def test_filter_by_severity(
        self, tool: CommentQualityTool, tmp_py: Path
    ) -> None:
        path = tmp_py('''
        def qux(x):
            # TODO: low severity
            pass
        ''')
        result = await tool.execute({
            "file_path": str(path),
            "min_severity": "high",
            "format": "json",
        })
        # TODOs are low severity, so filtering for high should exclude them
        for issue in result["issues"]:
            assert issue["severity"] == "high"

    @pytest.mark.asyncio
    async def test_missing_paths(self, tool: CommentQualityTool) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tool: CommentQualityTool) -> None:
        result = await tool.execute({
            "file_path": "/nonexistent.py",
            "format": "json",
        })
        assert result["total_elements"] == 0


class TestValidation:
    def test_valid_arguments(self, tool: CommentQualityTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"}) is True

    def test_invalid_format(self, tool: CommentQualityTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})

    def test_missing_paths(self, tool: CommentQualityTool) -> None:
        with pytest.raises(ValueError, match="file_path or project_root"):
            tool.validate_arguments({})
