"""Tests for Error Propagation MCP Tool."""
from __future__ import annotations

import tempfile
import textwrap

import pytest

from tree_sitter_analyzer.mcp.tools.error_propagation_tool import ErrorPropagationTool


@pytest.fixture
def tool() -> ErrorPropagationTool:
    return ErrorPropagationTool()


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


@pytest.mark.asyncio
async def test_tool_definition(tool: ErrorPropagationTool) -> None:
    defn = tool.get_tool_definition()
    assert defn["name"] == "error_propagation"
    assert "file_path" in defn["inputSchema"]["properties"]


@pytest.mark.asyncio
async def test_validate_valid(tool: ErrorPropagationTool) -> None:
    assert tool.validate_arguments({"file_path": "/tmp/test.py", "format": "json"}) is True


@pytest.mark.asyncio
async def test_validate_missing_path(tool: ErrorPropagationTool) -> None:
    with pytest.raises(ValueError, match="file_path"):
        tool.validate_arguments({"format": "json"})


@pytest.mark.asyncio
async def test_validate_bad_format(tool: ErrorPropagationTool) -> None:
    with pytest.raises(ValueError, match="format"):
        tool.validate_arguments({"file_path": "/tmp/test.py", "format": "xml"})


@pytest.mark.asyncio
async def test_execute_json(tool: ErrorPropagationTool) -> None:
    path = _write_tmp("""
        def foo():
            raise ValueError("bad")
    """, ".py")
    result = await tool.execute({"file_path": path, "format": "json"})
    assert "total_gaps" in result
    assert result["total_gaps"] >= 1


@pytest.mark.asyncio
async def test_execute_toon(tool: ErrorPropagationTool) -> None:
    path = _write_tmp("""
        def foo():
            raise ValueError("bad")
    """, ".py")
    result = await tool.execute({"file_path": path, "format": "toon"})
    assert "content" in result
    assert "total_gaps" in result


@pytest.mark.asyncio
async def test_execute_no_path(tool: ErrorPropagationTool) -> None:
    result = await tool.execute({"format": "json"})
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_js_file(tool: ErrorPropagationTool) -> None:
    path = _write_tmp("""
        function foo() {
            throw new Error("bad");
        }
    """, ".js")
    result = await tool.execute({"file_path": path, "format": "json"})
    assert result["total_gaps"] >= 1


@pytest.mark.asyncio
async def test_execute_java_file(tool: ErrorPropagationTool) -> None:
    path = _write_tmp("""
        public class Foo {
            void f() { throw new RuntimeException("x"); }
        }
    """, ".java")
    result = await tool.execute({"file_path": path, "format": "json"})
    assert result["total_gaps"] >= 1


@pytest.mark.asyncio
async def test_execute_clean_file(tool: ErrorPropagationTool) -> None:
    path = _write_tmp("""
        def safe():
            x = 1 + 2
            return x
    """, ".py")
    result = await tool.execute({"file_path": path, "format": "json"})
    assert result["total_gaps"] == 0
