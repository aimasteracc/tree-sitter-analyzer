"""Tests for GlobalStateTool MCP tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.global_state_tool import GlobalStateTool


@pytest.fixture
def tool() -> GlobalStateTool:
    return GlobalStateTool()


def _write_tmp(content: str, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="test_gs_tool_")
    with open(fd, "w") as f:
        f.write(content)
    return path


class TestGlobalStateToolDefinition:
    def test_tool_name(self, tool: GlobalStateTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "global_state"

    def test_tool_has_input_schema(self, tool: GlobalStateTool) -> None:
        defn = tool.get_tool_definition()
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_validate_arguments_valid(self, tool: GlobalStateTool) -> None:
        assert tool.validate_arguments({"file_path": "/tmp/test.py"})

    def test_validate_arguments_missing_path(self, tool: GlobalStateTool) -> None:
        with pytest.raises(ValueError, match="file_path must be provided"):
            tool.validate_arguments({})

    def test_validate_arguments_bad_format(self, tool: GlobalStateTool) -> None:
        with pytest.raises(ValueError, match="format must be"):
            tool.validate_arguments({"file_path": "/tmp/test.py", "format": "xml"})


@pytest.mark.asyncio
class TestGlobalStateToolExecute:
    async def test_execute_python_global_state(self, tool: GlobalStateTool) -> None:
        path = _write_tmp("counter = 0\n", ".py")
        try:
            result = await tool.execute({"file_path": path, "format": "json"})
            assert result["total_findings"] >= 1
            assert any(f["issue_type"] == "global_state" for f in result["findings"])
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_python_global_keyword(self, tool: GlobalStateTool) -> None:
        path = _write_tmp(
            "def f():\n    global x\n    x = 1\n",
            ".py",
        )
        try:
            result = await tool.execute({"file_path": path, "format": "json"})
            assert any(f["issue_type"] == "global_keyword" for f in result["findings"])
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_toon_format(self, tool: GlobalStateTool) -> None:
        path = _write_tmp("counter = 0\n", ".py")
        try:
            result = await tool.execute({"file_path": path, "format": "toon"})
            assert "content" in result
            assert "total_findings" in result
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_clean_file(self, tool: GlobalStateTool) -> None:
        path = _write_tmp("MAX_SIZE = 100\n", ".py")
        try:
            result = await tool.execute({"file_path": path, "format": "json"})
            assert result["total_findings"] == 0
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_missing_path(self, tool: GlobalStateTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    async def test_execute_js_let(self, tool: GlobalStateTool) -> None:
        path = _write_tmp("let counter = 0;\n", ".js")
        try:
            result = await tool.execute({"file_path": path, "format": "json"})
            assert result["total_findings"] >= 1
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_java_static_mutable(self, tool: GlobalStateTool) -> None:
        path = _write_tmp(
            "public class Config {\n    static int count = 0;\n}\n",
            ".java",
        )
        try:
            result = await tool.execute({"file_path": path, "format": "json"})
            assert any(
                f["issue_type"] == "static_mutable" for f in result["findings"]
            )
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_execute_go_package_var(self, tool: GlobalStateTool) -> None:
        path = _write_tmp(
            'package main\n\nvar count int\n',
            ".go",
        )
        try:
            result = await tool.execute({"file_path": path, "format": "json"})
            assert any(
                f["issue_type"] == "package_var" for f in result["findings"]
            )
        finally:
            Path(path).unlink(missing_ok=True)
