"""Tests for Assertion Quality MCP Tool."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.assertion_quality_tool import AssertionQualityTool


@pytest.fixture
def tool() -> AssertionQualityTool:
    return AssertionQualityTool()


def _write_tmp(content: str, name: str = "test_sample.py") -> str:
    d = tempfile.mkdtemp()
    p = Path(d) / name
    p.write_text(content)
    return str(p)


def _run(tool: AssertionQualityTool, args: dict) -> dict:
    return asyncio.get_event_loop().run_until_complete(tool.execute(args))


class TestAssertionQualityTool:
    def test_tool_definition(self, tool: AssertionQualityTool) -> None:
        definition = tool.get_tool_definition()
        assert definition["name"] == "assertion_quality"
        assert "inputSchema" in definition
        assert "file_path" in definition["inputSchema"]["properties"]

    def test_execute_json_format(self, tool: AssertionQualityTool) -> None:
        code = '''\
def test_weak():
    result = get_value()
    assert result is not None
'''
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "json"})
        assert "result" in result
        data = result["result"]
        assert data["total_tests"] == 1
        assert data["total_issues"] >= 1
        Path(path).unlink()

    def test_execute_toon_format(self, tool: AssertionQualityTool) -> None:
        code = '''\
def test_ok():
    assert compute() == 42
'''
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "toon"})
        text = result["content"][0]["text"]
        assert "total_tests" in text.lower() or "quality_score" in text.lower()
        Path(path).unlink()

    def test_execute_text_format(self, tool: AssertionQualityTool) -> None:
        code = '''\
def test_ok():
    assert compute() == 42
'''
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "text"})
        text = result["content"][0]["text"]
        assert "Assertion Quality" in text
        assert "Score:" in text
        Path(path).unlink()

    def test_execute_nonexistent_file(self, tool: AssertionQualityTool) -> None:
        result = _run(tool, {"file_path": "/nonexistent/test_foo.py", "format": "json"})
        data = result["result"]
        assert data["total_tests"] == 0

    def test_execute_non_test_file(self, tool: AssertionQualityTool) -> None:
        path = _write_tmp("def hello():\n    pass\n", name="utils.py")
        result = _run(tool, {"file_path": path, "format": "json"})
        data = result["result"]
        assert data["total_tests"] == 0
        Path(path).unlink()

    def test_execute_javascript(self, tool: AssertionQualityTool) -> None:
        code = '''\
it('should work', () => {
    expect(result).toBeDefined();
});
'''
        path = _write_tmp(code, name="foo.test.js")
        result = _run(tool, {"file_path": path, "format": "json"})
        data = result["result"]
        assert data["total_tests"] == 1
        Path(path).unlink()

    def test_tool_registered_in_analysis_toolset(self) -> None:
        from tree_sitter_analyzer.mcp.registry import TOOLSET_DEFINITIONS

        analysis_tools = TOOLSET_DEFINITIONS.get("analysis", {}).get("tools", [])
        assert "assertion_quality" in analysis_tools

    def test_validate_arguments_valid(self, tool: AssertionQualityTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py", "format": "json"})

    def test_validate_arguments_invalid_format(self, tool: AssertionQualityTool) -> None:
        with pytest.raises(ValueError, match="Invalid output format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})

    def test_validate_arguments_missing_path(self, tool: AssertionQualityTool) -> None:
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"format": "json"})
