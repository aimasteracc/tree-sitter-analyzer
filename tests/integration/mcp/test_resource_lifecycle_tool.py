"""Integration tests for Resource Lifecycle MCP Tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.resource_lifecycle_tool import (
    ResourceLifecycleTool,
)


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


@pytest.fixture
def tool() -> ResourceLifecycleTool:
    return ResourceLifecycleTool()


class TestResourceLifecycleToolDefinition:
    def test_tool_name(self, tool: ResourceLifecycleTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "resource_lifecycle"

    def test_tool_has_description(self, tool: ResourceLifecycleTool) -> None:
        defn = tool.get_tool_definition()
        assert "resource" in defn["description"].lower()
        assert "cleanup" in defn["description"].lower()

    def test_tool_schema_requires_file_path(
        self, tool: ResourceLifecycleTool,
    ) -> None:
        defn = tool.get_tool_definition()
        assert "file_path" in defn["inputSchema"]["required"]


class TestResourceLifecycleToolExecution:
    @pytest.mark.asyncio
    async def test_execute_python_with_issue(
        self, tool: ResourceLifecycleTool,
    ) -> None:
        path = _write_tmp("f = open('data.txt')\nf.read()\n")
        try:
            result = await tool.execute({"file_path": path})
            assert result["result"]["issue_count"] > 0
            assert result["result"]["stats"]["risky_acquisitions"] > 0
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_clean_python(
        self, tool: ResourceLifecycleTool,
    ) -> None:
        path = _write_tmp("with open('data.txt') as f:\n    f.read()\n")
        try:
            result = await tool.execute({"file_path": path})
            assert result["result"]["issue_count"] == 0
            assert result["result"]["stats"]["safety_percentage"] == 100.0
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_java_with_issue(
        self, tool: ResourceLifecycleTool,
    ) -> None:
        code = 'FileInputStream fis = new FileInputStream("data.txt");\n'
        path = _write_tmp(code, suffix=".java")
        try:
            result = await tool.execute({"file_path": path})
            assert result["result"]["issue_count"] > 0
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_toon_format(
        self, tool: ResourceLifecycleTool,
    ) -> None:
        path = _write_tmp("f = open('data.txt')\n")
        try:
            result = await tool.execute({
                "file_path": path,
                "format": "toon",
            })
            assert "content" in result
            assert "summary" in result
        finally:
            Path(path).unlink()


class TestResourceLifecycleToolValidation:
    def test_validate_valid_arguments(self, tool: ResourceLifecycleTool) -> None:
        assert tool.validate_arguments({"file_path": "/tmp/test.py"})

    def test_validate_invalid_format(self, tool: ResourceLifecycleTool) -> None:
        with pytest.raises(ValueError, match="Invalid format"):
            tool.validate_arguments({
                "file_path": "/tmp/test.py",
                "format": "xml",
            })

    def test_validate_missing_file_path(self, tool: ResourceLifecycleTool) -> None:
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({})
