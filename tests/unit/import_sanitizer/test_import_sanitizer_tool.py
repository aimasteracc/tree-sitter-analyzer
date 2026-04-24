"""Tests for import sanitizer MCP tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.import_sanitizer_tool import ImportSanitizerTool


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def tool(tmp_project: Path) -> ImportSanitizerTool:
    return ImportSanitizerTool(project_root=str(tmp_project))


class TestImportSanitizerToolDefinition:
    def test_tool_name(self, tool: ImportSanitizerTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "import_sanitizer"

    def test_tool_has_schema(self, tool: ImportSanitizerTool) -> None:
        defn = tool.get_tool_definition()
        assert "inputSchema" in defn
        props = defn["inputSchema"]["properties"]
        assert "file_path" in props
        assert "project_root" in props
        assert "format" in props

    def test_tool_description_mentions_languages(self, tool: ImportSanitizerTool) -> None:
        defn = tool.get_tool_definition()
        desc = defn["description"]
        assert "Python" in desc
        assert "JavaScript" in desc
        assert "Java" in desc
        assert "Go" in desc


class TestImportSanitizerToolExecution:
    @pytest.mark.asyncio
    async def test_analyze_file_unused(
        self, tool: ImportSanitizerTool, tmp_project: Path,
    ) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import os\nimport sys\nprint('hello')\n")
        result = await tool.execute({
            "file_path": str(py_file),
            "format": "json",
        })
        assert "total_imports" in result
        assert result["total_imports"] >= 2
        assert "total_unused" in result

    @pytest.mark.asyncio
    async def test_analyze_project(
        self, tool: ImportSanitizerTool, tmp_project: Path,
    ) -> None:
        (tmp_project / "a.py").write_text("import os\nos.getcwd()\n")
        (tmp_project / "b.py").write_text("import sys\n")
        result = await tool.execute({
            "project_root": str(tmp_project),
            "format": "json",
        })
        assert result["files_analyzed"] >= 2
        assert "total_imports" in result

    @pytest.mark.asyncio
    async def test_toon_format(
        self, tool: ImportSanitizerTool, tmp_project: Path,
    ) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import os\nprint('hello')\n")
        result = await tool.execute({
            "file_path": str(py_file),
            "format": "toon",
        })
        assert result["format"] == "toon"
        assert "content" in result

    @pytest.mark.asyncio
    async def test_clean_file_toon(
        self, tool: ImportSanitizerTool, tmp_project: Path,
    ) -> None:
        py_file = tmp_project / "clean.py"
        py_file.write_text("import os\nos.getcwd()\n")
        result = await tool.execute({
            "file_path": str(py_file),
            "format": "toon",
        })
        assert result["format"] == "toon"

    @pytest.mark.asyncio
    async def test_no_path_error(self) -> None:
        bare_tool = ImportSanitizerTool(project_root=None)
        result = await bare_tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_check_flags(
        self, tool: ImportSanitizerTool, tmp_project: Path,
    ) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import os\nimport requests\n")
        result = await tool.execute({
            "file_path": str(py_file),
            "check_unused": True,
            "check_circular": False,
            "check_sort": True,
            "format": "json",
        })
        assert "total_unused" in result
        assert "circular_imports" not in result

    @pytest.mark.asyncio
    async def test_js_file_analysis(
        self, tool: ImportSanitizerTool, tmp_project: Path,
    ) -> None:
        js_file = tmp_project / "test.js"
        js_file.write_text('import { useState } from "react";\nconsole.log("hi");\n')
        result = await tool.execute({
            "file_path": str(js_file),
            "format": "json",
        })
        assert result["total_imports"] >= 1

    @pytest.mark.asyncio
    async def test_java_file_analysis(
        self, tool: ImportSanitizerTool, tmp_project: Path,
    ) -> None:
        java_file = tmp_project / "Test.java"
        java_file.write_text("import java.util.List;\npublic class Test {}\n")
        result = await tool.execute({
            "file_path": str(java_file),
            "format": "json",
        })
        assert result["total_imports"] >= 1
