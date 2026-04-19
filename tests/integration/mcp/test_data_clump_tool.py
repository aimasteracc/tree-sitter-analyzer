"""Tests for Data Clump MCP Tool."""
from __future__ import annotations

import os
import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.data_clump_tool import DataClumpTool


@pytest.fixture
def tool() -> DataClumpTool:
    return DataClumpTool()


@pytest.fixture
def clump_python_file() -> str:
    code = """\
def create_user(name, email, age, role):
    pass

def update_user(name, email, age, role):
    pass

def delete_user(name, email, age):
    pass
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        return f.name


@pytest.fixture
def clean_python_file() -> str:
    code = """\
def foo(a, b):
    pass

def bar(c, d):
    pass
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        return f.name


class TestDataClumpToolDefinition:
    def test_get_tool_definition(self, tool: DataClumpTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "data_clump"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_validate_arguments_valid(self, tool: DataClumpTool) -> None:
        assert tool.validate_arguments({"file_path": "/tmp/test.py"})

    def test_validate_arguments_missing_path(self, tool: DataClumpTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_validate_arguments_invalid_format(self, tool: DataClumpTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "/tmp/test.py", "format": "xml"})


class TestDataClumpToolExecute:
    @pytest.mark.asyncio
    async def test_execute_finds_issues(
        self,
        tool: DataClumpTool,
        clump_python_file: str,
    ) -> None:
        try:
            result = await tool.execute(
                {"file_path": clump_python_file, "format": "json"}
            )
            assert result["issue_count"] > 0
            assert any(
                i["issue_type"] == "data_clump"
                for i in result["issues"]
            )
        finally:
            os.unlink(clump_python_file)

    @pytest.mark.asyncio
    async def test_execute_clean_file(
        self,
        tool: DataClumpTool,
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
        tool: DataClumpTool,
        clump_python_file: str,
    ) -> None:
        try:
            result = await tool.execute(
                {"file_path": clump_python_file, "format": "json"}
            )
            assert "file" in result
            assert "issues" in result
            assert isinstance(result["issues"], list)
        finally:
            os.unlink(clump_python_file)

    @pytest.mark.asyncio
    async def test_execute_toon_format(
        self,
        tool: DataClumpTool,
        clump_python_file: str,
    ) -> None:
        try:
            result = await tool.execute(
                {"file_path": clump_python_file, "format": "toon"}
            )
            assert "content" in result
            assert "functions_analyzed" in result
        finally:
            os.unlink(clump_python_file)

    @pytest.mark.asyncio
    async def test_execute_missing_path(self, tool: DataClumpTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_custom_threshold(
        self,
        tool: DataClumpTool,
        clump_python_file: str,
    ) -> None:
        try:
            result = await tool.execute(
                {"file_path": clump_python_file, "min_params": 4}
            )
            assert isinstance(result["issue_count"], int)
        finally:
            os.unlink(clump_python_file)
