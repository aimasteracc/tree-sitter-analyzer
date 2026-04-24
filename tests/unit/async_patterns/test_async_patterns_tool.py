"""
Tests for Async Pattern Analyzer MCP Tool.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.async_patterns_tool import AsyncPatternsTool


@pytest.fixture
def tool() -> AsyncPatternsTool:
    return AsyncPatternsTool()


def _write_tmp(content: str, suffix: str = ".py") -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w")
    tmp.write(content)
    tmp.close()
    return tmp.name


class TestAsyncPatternsToolDefinition:
    def test_tool_name(self, tool: AsyncPatternsTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "async_patterns"

    def test_tool_has_schema(self, tool: AsyncPatternsTool) -> None:
        defn = tool.get_tool_definition()
        assert "inputSchema" in defn
        props = defn["inputSchema"]["properties"]
        assert "file_path" in props
        assert "directory" in props
        assert "severity" in props
        assert "pattern_type" in props
        assert "format" in props

    def test_tool_description_mentions_languages(self, tool: AsyncPatternsTool) -> None:
        defn = tool.get_tool_definition()
        desc = defn["description"]
        assert "Python" in desc
        assert "JavaScript" in desc
        assert "Java" in desc
        assert "Go" in desc


class TestAsyncPatternsToolExecution:
    @pytest.mark.asyncio
    async def test_analyze_python_file(self, tool: AsyncPatternsTool) -> None:
        code = """
async def bad():
    return 42
"""
        path = _write_tmp(code)
        result = await tool.execute({"file_path": path, "format": "json"})
        assert "summary" in result
        assert result["summary"]["total_patterns"] >= 1

    @pytest.mark.asyncio
    async def test_analyze_with_toon_format(self, tool: AsyncPatternsTool) -> None:
        code = """
async def bad():
    return 42
"""
        path = _write_tmp(code)
        result = await tool.execute({"file_path": path, "format": "toon"})
        assert "result" in result
        assert result["format"] == "toon"

    @pytest.mark.asyncio
    async def test_severity_filter(self, tool: AsyncPatternsTool) -> None:
        code = """
import asyncio

async def fetch():
    asyncio.sleep(1)
    return 42
"""
        path = _write_tmp(code)
        result = await tool.execute({
            "file_path": path,
            "format": "json",
            "severity": "error",
        })
        # Only errors, no warnings
        for r in result.get("results", []):
            for p in r.get("patterns", []):
                assert p["severity"] == "error"

    @pytest.mark.asyncio
    async def test_pattern_type_filter(self, tool: AsyncPatternsTool) -> None:
        code = """
async def bad():
    return 42
"""
        path = _write_tmp(code)
        result = await tool.execute({
            "file_path": path,
            "format": "json",
            "pattern_type": "async_without_await",
        })
        for r in result.get("results", []):
            for p in r.get("patterns", []):
                assert p["type"] == "async_without_await"

    @pytest.mark.asyncio
    async def test_no_input_error(self, tool: AsyncPatternsTool) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_directory_analysis(self, tool: AsyncPatternsTool) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "test.py"
            py_file.write_text("async def bad():\n    return 1\n")

            result = await tool.execute({
                "directory": tmpdir,
                "format": "json",
            })
            assert "summary" in result
            assert result["summary"]["files_analyzed"] >= 1

    @pytest.mark.asyncio
    async def test_javascript_file_analysis(self, tool: AsyncPatternsTool) -> None:
        code = """
async function fetch() {
    return 42;
}
"""
        path = _write_tmp(code, ".js")
        result = await tool.execute({"file_path": path, "format": "json"})
        assert result["summary"]["total_patterns"] >= 1

    @pytest.mark.asyncio
    async def test_go_file_analysis(self, tool: AsyncPatternsTool) -> None:
        code = """package main

func main() {
    go func() {}()
}
"""
        path = _write_tmp(code, ".go")
        result = await tool.execute({
            "file_path": path,
            "format": "json",
            "severity": "info",
        })
        assert result["summary"]["total_patterns"] >= 1


class TestToolRegistration:
    def test_async_patterns_registered(self) -> None:
        from tree_sitter_analyzer.mcp.registry import get_registry
        from tree_sitter_analyzer.mcp.tool_registration import register_all_tools

        register_all_tools()
        registry = get_registry()
        tools = registry.list_tools()
        tool_names = [t.name for t in tools]
        assert "async_patterns" in tool_names
