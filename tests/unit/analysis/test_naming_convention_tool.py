"""Tests for Naming Convention MCP Tool."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.naming_convention_tool import (
    NamingConventionTool,
)
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


@pytest.fixture
def tool() -> NamingConventionTool:
    return NamingConventionTool()


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


def _run(tool: NamingConventionTool, args: dict) -> dict:
    return asyncio.get_event_loop().run_until_complete(tool.execute(args))


class TestNamingConventionTool:
    def test_tool_definition(self, tool: NamingConventionTool) -> None:
        definition = tool.get_tool_definition()
        assert definition["name"] == "naming_conventions"
        assert "inputSchema" in definition
        assert "file_path" in definition["inputSchema"]["properties"]

    def test_execute_json_format(self, tool: NamingConventionTool) -> None:
        code = "def BadFunc():\n    pass\n"
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "json"})
        assert "result" in result
        data = result["result"]
        assert data["language"] == "python"
        assert data["violation_count"] >= 1
        Path(path).unlink()

    def test_execute_toon_format(self, tool: NamingConventionTool) -> None:
        code = "def BadFunc():\n    pass\n"
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "toon"})
        text = result["content"][0]["text"]
        assert "Naming Convention" in text
        assert "BadFunc" in text
        Path(path).unlink()

    def test_execute_invalid_path_raises(
        self, tool: NamingConventionTool
    ) -> None:
        with pytest.raises(AnalysisError):
            _run(tool, {"file_path": "/nonexistent/file.py"})

    def test_execute_no_violations(self, tool: NamingConventionTool) -> None:
        code = "def good_func():\n    pass\n"
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "json"})
        assert result["result"]["violation_count"] == 0
        assert result["result"]["naming_score"] == 100.0
        Path(path).unlink()

    def test_validate_arguments_valid(self, tool: NamingConventionTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py"}) is True

    def test_validate_arguments_invalid_format(
        self, tool: NamingConventionTool
    ) -> None:
        with pytest.raises(ValueError, match="Invalid format"):
            tool.validate_arguments({"file_path": "t.py", "format": "xml"})

    def test_validate_arguments_missing_path(
        self, tool: NamingConventionTool
    ) -> None:
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"format": "json"})

    def test_summary_in_toon(self, tool: NamingConventionTool) -> None:
        code = "q = 42\n"
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "toon"})
        summary = result["summary"]
        assert "naming_score" in summary
        assert "violation_count" in summary
        Path(path).unlink()
