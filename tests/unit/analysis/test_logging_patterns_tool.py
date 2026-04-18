"""Tests for Logging Patterns MCP Tool."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.logging_patterns_tool import LoggingPatternsTool


@pytest.fixture
def tool() -> LoggingPatternsTool:
    return LoggingPatternsTool()


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


def _run(tool: LoggingPatternsTool, args: dict) -> dict:
    return asyncio.get_event_loop().run_until_complete(tool.execute(args))


class TestLoggingPatternsTool:
    def test_tool_definition(self, tool: LoggingPatternsTool) -> None:
        definition = tool.get_tool_definition()
        assert definition["name"] == "logging_patterns"
        assert "inputSchema" in definition
        assert "file_path" in definition["inputSchema"]["properties"]

    def test_execute_json_format(self, tool: LoggingPatternsTool) -> None:
        code = '''\
try:
    risky()
except Exception:
    pass
'''
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "json"})
        assert "catch_blocks" in result
        assert result["total_smells"] >= 1
        Path(path).unlink()

    def test_execute_toon_format(self, tool: LoggingPatternsTool) -> None:
        code = '''\
try:
    risky()
except Exception:
    pass
'''
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "toon"})
        text = result["content"][0]["text"]
        assert "LOGGING PATTERNS" in text
        assert "catch_blocks: " in text
        Path(path).unlink()

    def test_execute_nonexistent_file(self, tool: LoggingPatternsTool) -> None:
        result = _run(tool, {"file_path": "/nonexistent/file.py"})
        assert "total_smells" in result
        assert result["total_smells"] == 0

    def test_execute_no_smells(self, tool: LoggingPatternsTool) -> None:
        code = '''\
try:
    risky()
except Exception as e:
    logging.error("Failed: %s", e)
'''
        path = _write_tmp(code)
        result = _run(tool, {"file_path": path, "format": "json"})
        assert "total_smells" in result
        assert result["total_smells"] == 0
        Path(path).unlink()

    def test_execute_javascript(self, tool: LoggingPatternsTool) -> None:
        code = '''\
try {
    risky();
} catch (err) {
    // silent
}
'''
        path = _write_tmp(code, ".js")
        result = _run(tool, {"file_path": path, "format": "json"})
        assert "catch_blocks" in result
        Path(path).unlink()

    def test_tool_registered_in_analysis_toolset(self) -> None:
        from tree_sitter_analyzer.mcp.registry import TOOLSET_DEFINITIONS
        analysis_tools = TOOLSET_DEFINITIONS.get("analysis", {}).get("tools", [])
        assert "logging_patterns" in analysis_tools

    def test_validate_arguments_valid(self, tool: LoggingPatternsTool) -> None:
        assert tool.validate_arguments({"file_path": "test.py", "format": "json"})

    def test_validate_arguments_invalid_format(self, tool: LoggingPatternsTool) -> None:
        with pytest.raises(ValueError, match="format must be"):
            tool.validate_arguments({"file_path": "test.py", "format": "xml"})

    def test_validate_arguments_missing_path(self, tool: LoggingPatternsTool) -> None:
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"format": "json"})
