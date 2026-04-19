"""Tests for Middle Man MCP Tool."""
from __future__ import annotations

import os
import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.middle_man_tool import MiddleManTool


@pytest.fixture
def tool() -> MiddleManTool:
    return MiddleManTool()


@pytest.fixture
def middle_man_python_file() -> str:
    code = """\
class Manager:
    def __init__(self):
        self.worker = Worker()

    def process(self, data):
        return self.worker.process(data)

    def validate(self, data):
        return self.worker.validate(data)

    def transform(self, data):
        return self.worker.transform(data)
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        return f.name


@pytest.fixture
def clean_python_file() -> str:
    code = """\
class Service:
    def process(self, data):
        return data * 2
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        return f.name


class TestMiddleManToolDefinition:
    def test_get_tool_definition(self, tool: MiddleManTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "middle_man"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_validate_arguments_valid(self, tool: MiddleManTool) -> None:
        assert tool.validate_arguments({"file_path": "/tmp/test.py"})

    def test_validate_arguments_missing_path(self, tool: MiddleManTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_validate_arguments_invalid_format(self, tool: MiddleManTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "/tmp/test.py", "format": "xml"})


class TestMiddleManToolExecute:
    @pytest.mark.asyncio
    async def test_execute_finds_issues(
        self,
        tool: MiddleManTool,
        middle_man_python_file: str,
    ) -> None:
        try:
            result = await tool.execute(
                {"file_path": middle_man_python_file, "format": "json"}
            )
            assert result["issue_count"] > 0
            assert any(
                i["issue_type"] == "middle_man_class"
                for i in result["issues"]
            )
        finally:
            os.unlink(middle_man_python_file)

    @pytest.mark.asyncio
    async def test_execute_clean_file(
        self,
        tool: MiddleManTool,
        clean_python_file: str,
    ) -> None:
        try:
            result = await tool.execute({"file_path": clean_python_file})
            assert result["issue_count"] == 0
        finally:
            os.unlink(clean_python_file)

    @pytest.mark.asyncio
    async def test_execute_json_format(
        self,
        tool: MiddleManTool,
        middle_man_python_file: str,
    ) -> None:
        try:
            result = await tool.execute(
                {"file_path": middle_man_python_file, "format": "json"}
            )
            assert "file" in result
            assert "issues" in result
        finally:
            os.unlink(middle_man_python_file)

    @pytest.mark.asyncio
    async def test_execute_toon_format(
        self,
        tool: MiddleManTool,
        middle_man_python_file: str,
    ) -> None:
        try:
            result = await tool.execute(
                {"file_path": middle_man_python_file, "format": "toon"}
            )
            assert "content" in result
            assert "classes_analyzed" in result
        finally:
            os.unlink(middle_man_python_file)

    @pytest.mark.asyncio
    async def test_execute_missing_path(self, tool: MiddleManTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_custom_threshold(
        self,
        tool: MiddleManTool,
        middle_man_python_file: str,
    ) -> None:
        try:
            result = await tool.execute(
                {"file_path": middle_man_python_file, "delegation_threshold": 0.5}
            )
            assert isinstance(result["issue_count"], int)
        finally:
            os.unlink(middle_man_python_file)
