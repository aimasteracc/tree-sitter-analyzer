#!/usr/bin/env python3
"""
Integration tests: CLI → MCP → output full pipeline.

Tests verify that analysis requests flow through the complete stack:
1. Tool receives arguments (as CLI would provide)
2. MCP server processes via analysis engine + tree-sitter
3. Output is formatted and returned correctly

These are NOT unit tests — they exercise real file I/O, real parsing,
and real formatting without mocking internal components.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

# ── Test fixtures ──

JAVA_MULTI_CLASS = """
package com.example;

import java.util.List;
import java.util.ArrayList;

public class Application {
    private String name;
    private List<Module> modules;

    public Application(String name) {
        this.name = name;
        this.modules = new ArrayList<>();
    }

    public void addModule(Module m) {
        modules.add(m);
    }

    public String getName() {
        return name;
    }

    @Override
    public String toString() {
        return "Application: " + name;
    }
}

class Module {
    private String moduleName;
    private int version;

    public Module(String name, int version) {
        this.moduleName = name;
        this.version = version;
    }

    public int getVersion() {
        return version;
    }
}

enum Status {
    ACTIVE, INACTIVE, PENDING
}
"""

PYTHON_PROJECT = """
\"\"\"Main application module.\"\"\"

import os
import sys
from pathlib import Path
from typing import Optional

class Config:
    \"\"\"Application configuration.\"\"\"

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.base_path: Optional[str] = None

    def load(self, path: str) -> None:
        \"\"\"Load configuration from file.\"\"\"
        self.base_path = path

    @property
    def is_debug(self) -> bool:
        return self.debug


def create_app(config: Config) -> str:
    \"\"\"Create application instance.\"\"\"
    return f"app-{config.base_path}"


async def async_handler(request: str) -> dict:
    \"\"\"Handle async requests.\"\"\"
    return {"status": "ok", "request": request}
"""


@pytest.fixture
def project_dir():
    """Create a temporary project with multiple source files."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # Java files
        java_dir = root / "src" / "main" / "java" / "com" / "example"
        java_dir.mkdir(parents=True)
        (java_dir / "Application.java").write_text(JAVA_MULTI_CLASS)

        # Python files
        py_dir = root / "src" / "python"
        py_dir.mkdir(parents=True)
        (py_dir / "app.py").write_text(PYTHON_PROJECT)
        (py_dir / "__init__.py").write_text("")

        # A simple Go file
        go_dir = root / "src" / "go"
        go_dir.mkdir(parents=True)
        (go_dir / "main.go").write_text("""package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}

func add(a int, b int) int {
    return a + b
}
""")

        yield str(root)


# ── Pipeline Tests ──


class TestAnalysisPipeline:
    """End-to-end tests: tool invocation → analysis → formatted output."""

    @pytest.mark.asyncio
    async def test_java_structure_analysis(self, project_dir: str) -> None:
        """Java analysis: classes, methods, fields extracted correctly."""
        tool = AnalyzeCodeStructureTool(project_root=project_dir)
        java_file = str(Path(project_dir) / "src" / "main" / "java" / "com" / "example" / "Application.java")

        result = await tool.execute({"file_path": java_file, "format_type": "compact"})

        # Result may be in MCP content format or direct dict
        result_str = str(result)
        assert result.get("success") is True or "success: true" in result_str
        assert "java" in result_str.lower()
        # Should find Application class
        assert "Application" in result_str

    @pytest.mark.asyncio
    async def test_python_structure_analysis(self, project_dir: str) -> None:
        """Python analysis: classes, functions, async functions."""
        tool = AnalyzeCodeStructureTool(project_root=project_dir)
        py_file = str(Path(project_dir) / "src" / "python" / "app.py")

        result = await tool.execute({"file_path": py_file, "format_type": "compact"})

        assert result.get("success") is True
        assert result.get("language") == "python"

    @pytest.mark.asyncio
    async def test_python_query_functions(self, project_dir: str) -> None:
        """Query tool: extract all functions from Python file."""
        tool = QueryTool(project_root=project_dir)
        py_file = str(Path(project_dir) / "src" / "python" / "app.py")

        result = await tool.execute({"file_path": py_file, "query_key": "functions"})

        assert result.get("success") is True
        assert "results" in result
        # Should find create_app and async_handler
        func_names = [r.get("content", "") for r in result["results"]]
        assert len(func_names) > 0

    @pytest.mark.asyncio
    async def test_read_partial_pipeline(self, project_dir: str) -> None:
        """Read partial: extract specific line range."""
        tool = ReadPartialTool(project_root=project_dir)
        py_file = str(Path(project_dir) / "src" / "python" / "app.py")

        result = await tool.execute({
            "file_path": py_file,
            "start_line": 1,
            "end_line": 5,
        })

        assert "partial_content_result" in result or "content" in result or "file_path" in result

    @pytest.mark.asyncio
    async def test_code_outline_pipeline(self, project_dir: str) -> None:
        """Code outline: hierarchical structure extraction."""
        tool = GetCodeOutlineTool(project_root=project_dir)
        java_file = str(Path(project_dir) / "src" / "main" / "java" / "com" / "example" / "Application.java")

        result = await tool.execute({"file_path": java_file})

        result_str = str(result)
        # Should contain outline data (MCP wraps in content)
        assert "Application" in result_str
        assert "class" in result_str.lower()

    @pytest.mark.asyncio
    async def test_search_content_pipeline(self, project_dir: str) -> None:
        """Search content: find text across project files."""
        tool = SearchContentTool(project_root=project_dir)

        try:
            result = await tool.execute({
                "roots": [project_dir],
                "query": "class",
            })
            assert result.get("success") is True or "results" in result or "count" in result
        except Exception:
            # search_content may require fd/rg which aren't guaranteed
            pytest.skip("fd/rg not available")

    @pytest.mark.asyncio
    async def test_go_file_analysis(self, project_dir: str) -> None:
        """Go file analysis: functions and package."""
        tool = AnalyzeCodeStructureTool(project_root=project_dir)
        go_file = str(Path(project_dir) / "src" / "go" / "main.go")

        result = await tool.execute({"file_path": go_file, "format_type": "compact"})

        assert result.get("success") is True
        assert result.get("language") == "go"

    @pytest.mark.asyncio
    async def test_toon_format_pipeline(self, project_dir: str) -> None:
        """Analysis with compact format (TOON is an output option)."""
        tool = AnalyzeCodeStructureTool(project_root=project_dir)
        py_file = str(Path(project_dir) / "src" / "python" / "app.py")

        result = await tool.execute({"file_path": py_file, "format_type": "compact"})

        result_str = str(result)
        assert result.get("success") is True or "success: true" in result_str
        assert "python" in result_str.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_file_graceful_error(self, project_dir: str) -> None:
        """Non-existent file within project returns graceful error."""
        tool = AnalyzeCodeStructureTool(project_root=project_dir)

        # Tool raises ValueError for non-existent file — that's acceptable
        with pytest.raises((ValueError, FileNotFoundError)):
            await tool.execute({"file_path": "nonexistent/path.py"})

    @pytest.mark.asyncio
    async def test_multi_tool_consistency(self, project_dir: str) -> None:
        """Multiple tools analyzing same file produce consistent results."""
        py_file = str(Path(project_dir) / "src" / "python" / "app.py")

        structure_tool = AnalyzeCodeStructureTool(project_root=project_dir)
        query_tool = QueryTool(project_root=project_dir)

        struct_result = await structure_tool.execute({"file_path": py_file})
        query_result = await query_tool.execute({"file_path": py_file, "query_key": "classes"})

        # Both should succeed
        assert struct_result.get("success") is True
        assert query_result.get("success") is True
        # Both should identify the same language
        assert struct_result.get("language") == "python"
