"""Integration tests for Concurrency Safety MCP Tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.concurrency_safety_tool import (
    ConcurrencySafetyTool,
)


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


@pytest.fixture
def tool() -> ConcurrencySafetyTool:
    return ConcurrencySafetyTool()


class TestConcurrencySafetyToolDefinition:
    def test_tool_name(self, tool: ConcurrencySafetyTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "concurrency_safety"

    def test_tool_has_description(self, tool: ConcurrencySafetyTool) -> None:
        defn = tool.get_tool_definition()
        assert "concurrency" in defn["description"].lower()
        assert "race" in defn["description"].lower()

    def test_tool_has_schema(self, tool: ConcurrencySafetyTool) -> None:
        defn = tool.get_tool_definition()
        props = defn["inputSchema"]["properties"]
        assert "file_path" in props
        assert "format" in props
        assert "severity" in props


class TestConcurrencySafetyToolExecution:
    @pytest.mark.asyncio
    async def test_execute_python_with_issue(
        self, tool: ConcurrencySafetyTool,
    ) -> None:
        code = """\
import threading

class Counter:
    def __init__(self):
        self.count = 0
    def increment(self):
        self.count += 1
    def run(self):
        t = threading.Thread(target=self.increment)
        t.start()
"""
        path = _write_tmp(code, ".py")
        try:
            result = await tool.execute(
                {"file_path": path, "format": "json"}
            )
            assert result["total_issues"] > 0
            assert result["high_severity"] > 0
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_clean_python(
        self, tool: ConcurrencySafetyTool,
    ) -> None:
        code = """\
x = 42
print(x)
"""
        path = _write_tmp(code, ".py")
        try:
            result = await tool.execute({"file_path": path})
            assert result["total_issues"] == 0
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_json_format(
        self, tool: ConcurrencySafetyTool,
    ) -> None:
        code = """\
import threading

data = []
t = threading.Thread(target=lambda: data.append(1))
t.start()
"""
        path = _write_tmp(code, ".py")
        try:
            result = await tool.execute(
                {"file_path": path, "format": "json"}
            )
            assert "issues" in result
            assert result["language"] == "python"
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_text_format(
        self, tool: ConcurrencySafetyTool,
    ) -> None:
        code = """\
import threading

class Counter:
    def __init__(self):
        self.count = 0
    def run(self):
        t = threading.Thread(target=lambda: None)
        t.start()
"""
        path = _write_tmp(code, ".py")
        try:
            result = await tool.execute(
                {"file_path": path, "format": "text"}
            )
            assert "content" in result
            assert isinstance(result["content"], str)
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_no_file_path(
        self, tool: ConcurrencySafetyTool,
    ) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_severity_filter(
        self, tool: ConcurrencySafetyTool,
    ) -> None:
        code = """\
import threading

class Counter:
    def __init__(self):
        self.count = 0
    def increment(self):
        self.count += 1
    def run(self):
        t = threading.Thread(target=self.increment)
        t.start()
"""
        path = _write_tmp(code, ".py")
        try:
            result_high = await tool.execute(
                {"file_path": path, "severity": "high", "format": "json"}
            )
            result_all = await tool.execute(
                {"file_path": path, "severity": "low", "format": "json"}
            )
            assert result_high["filtered_count"] <= result_all["filtered_count"]
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_validate_arguments_valid(
        self, tool: ConcurrencySafetyTool,
    ) -> None:
        assert tool.validate_arguments(
            {"file_path": "test.py", "format": "json", "severity": "high"}
        )

    @pytest.mark.asyncio
    async def test_validate_arguments_invalid_format(
        self, tool: ConcurrencySafetyTool,
    ) -> None:
        with pytest.raises(ValueError):
            tool.validate_arguments(
                {"file_path": "test.py", "format": "xml"}
            )

    @pytest.mark.asyncio
    async def test_validate_arguments_no_file(
        self, tool: ConcurrencySafetyTool,
    ) -> None:
        with pytest.raises(ValueError):
            tool.validate_arguments({"format": "json"})

    @pytest.mark.asyncio
    async def test_execute_go_goroutine(
        self, tool: ConcurrencySafetyTool,
    ) -> None:
        code = """\
package main

func main() {
    counter := 0
    go func() {
        counter = counter + 1
    }()
}
"""
        path = _write_tmp(code, ".go")
        try:
            result = await tool.execute(
                {"file_path": path, "format": "json"}
            )
            assert result["total_issues"] > 0
            assert result["language"] == "go"
        finally:
            Path(path).unlink()
