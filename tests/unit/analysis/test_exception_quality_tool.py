"""Tests for Exception Handling Quality MCP Tool."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.exception_quality_tool import ExceptionQualityTool


@pytest.fixture
def tool() -> ExceptionQualityTool:
    return ExceptionQualityTool()


def _write_tmp(content: str, name: str = "sample.py") -> str:
    d = tempfile.mkdtemp()
    p = Path(d) / name
    p.write_text(content)
    return str(p)


def _run(tool: ExceptionQualityTool, args: dict) -> dict:
    return asyncio.get_event_loop().run_until_complete(tool.execute(args))


class TestExceptionQualityTool:
    def test_tool_definition(self, tool: ExceptionQualityTool) -> None:
        definition = tool.get_tool_definition()
        assert definition["name"] == "exception_quality"
        assert "inputSchema" in definition

    def test_execute_json_format(self, tool: ExceptionQualityTool) -> None:
        code = "try:\n    risky()\nexcept:\n    pass\n"
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "json"})
        data = result["result"]
        assert data["total_try_blocks"] == 1
        assert data["total_issues"] >= 1
        Path(path).unlink()

    def test_execute_toon_format(self, tool: ExceptionQualityTool) -> None:
        code = "try:\n    risky()\nexcept ValueError:\n    pass\n"
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "toon"})
        text = result["content"][0]["text"]
        assert "total_try_blocks" in text.lower() or "quality_score" in text.lower()
        Path(path).unlink()

    def test_execute_text_format(self, tool: ExceptionQualityTool) -> None:
        code = "try:\n    risky()\nexcept ValueError:\n    pass\n"
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "text"})
        text = result["content"][0]["text"]
        assert "Exception Quality" in text
        assert "Score:" in text
        Path(path).unlink()

    def test_execute_nonexistent_file(self, tool: ExceptionQualityTool) -> None:
        result = _run(tool, {"file_path": "/nonexistent/file.py", "format": "json"})
        data = result["result"]
        assert data["total_try_blocks"] == 0

    def test_execute_javascript(self, tool: ExceptionQualityTool) -> None:
        code = "try { risky(); } catch (e) { }\n"
        path = _write_tmp(code, name="sample.js")
        result = _run(tool, {"file_path": path, "format": "json"})
        data = result["result"]
        assert data["total_try_blocks"] == 1
        Path(path).unlink()

    def test_tool_registered_in_analysis_toolset(self) -> None:
        from tree_sitter_analyzer.mcp.registry import TOOLSET_DEFINITIONS

        analysis_tools = TOOLSET_DEFINITIONS.get("analysis", {}).get("tools", [])
        assert "exception_quality" in analysis_tools

    def test_validate_arguments_valid(self, tool: ExceptionQualityTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py", "format": "json"})

    def test_validate_arguments_invalid_format(self, tool: ExceptionQualityTool) -> None:
        with pytest.raises(ValueError, match="Invalid output format"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})

    def test_validate_arguments_missing_path(self, tool: ExceptionQualityTool) -> None:
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"format": "json"})
