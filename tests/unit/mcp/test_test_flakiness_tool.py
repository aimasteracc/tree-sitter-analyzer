"""Tests for Test Flakiness MCP Tool."""
from __future__ import annotations

import tempfile
import textwrap

import pytest

from tree_sitter_analyzer.mcp.tools.test_flakiness_tool import TestFlakinessTool


@pytest.fixture
def tool() -> TestFlakinessTool:
    return TestFlakinessTool()


def _write_tmp(content: str, suffix: str, prefix: str = "test_") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, prefix=prefix, delete=False, dir="/tmp")
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


@pytest.mark.asyncio
async def test_tool_definition(tool: TestFlakinessTool) -> None:
    defn = tool.get_tool_definition()
    assert defn["name"] == "test_flakiness"
    assert "file_path" in defn["inputSchema"]["properties"]


@pytest.mark.asyncio
async def test_validate_valid(tool: TestFlakinessTool) -> None:
    assert tool.validate_arguments({"file_path": "/tmp/test.py", "format": "json"}) is True


@pytest.mark.asyncio
async def test_validate_missing_path(tool: TestFlakinessTool) -> None:
    with pytest.raises(ValueError, match="file_path"):
        tool.validate_arguments({"format": "json"})


@pytest.mark.asyncio
async def test_validate_bad_format(tool: TestFlakinessTool) -> None:
    with pytest.raises(ValueError, match="format"):
        tool.validate_arguments({"file_path": "/tmp/test.py", "format": "xml"})


@pytest.mark.asyncio
async def test_execute_json(tool: TestFlakinessTool) -> None:
    path = _write_tmp("""
        import time
        def test_slow():
            time.sleep(2)
    """, ".py")
    result = await tool.execute({"file_path": path, "format": "json"})
    assert "total_factors" in result
    assert result["total_factors"] >= 1


@pytest.mark.asyncio
async def test_execute_toon(tool: TestFlakinessTool) -> None:
    path = _write_tmp("""
        import time
        def test_slow():
            time.sleep(2)
    """, ".py")
    result = await tool.execute({"file_path": path, "format": "toon"})
    assert "content" in result
    assert "total_factors" in result


@pytest.mark.asyncio
async def test_execute_no_path(tool: TestFlakinessTool) -> None:
    result = await tool.execute({"format": "json"})
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_non_test_file(tool: TestFlakinessTool) -> None:
    path = _write_tmp("""
        import time
        def production():
            time.sleep(1)
    """, ".py", prefix="prod_")
    result = await tool.execute({"file_path": path, "format": "json"})
    assert result["total_factors"] == 0


@pytest.mark.asyncio
async def test_execute_js_test(tool: TestFlakinessTool) -> None:
    path = _write_tmp("""
        test('random', () => {
            const val = Math.random();
            expect(val).toBeDefined();
        });
    """, ".test.js")
    result = await tool.execute({"file_path": path, "format": "json"})
    assert result["total_factors"] >= 1
