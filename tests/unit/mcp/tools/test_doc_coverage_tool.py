#!/usr/bin/env python3
"""Tests for Documentation Coverage MCP Tool."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.doc_coverage_tool import DocCoverageTool


def _write_tmp_file(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


@pytest.fixture
def tool(tmp_path: Path) -> DocCoverageTool:
    return DocCoverageTool(str(tmp_path))


@pytest.mark.asyncio
async def test_tool_definition(tool: DocCoverageTool) -> None:
    defn = tool.get_tool_definition()
    assert defn["name"] == "doc_coverage"
    assert "inputSchema" in defn


@pytest.mark.asyncio
async def test_analyze_file_json(tool: DocCoverageTool, tmp_path: Path) -> None:
    p = _write_tmp_file(tmp_path, "a.py", '''\
        def foo():
            """Doc."""
            pass

        def bar():
            pass
    ''')
    result = await tool.execute({
        "file_path": str(p),
        "format": "json",
    })
    assert result["total_elements"] >= 2
    assert result["coverage_percent"] >= 0
    assert "missing_docs" in result


@pytest.mark.asyncio
async def test_analyze_file_toon(tool: DocCoverageTool, tmp_path: Path) -> None:
    p = _write_tmp_file(tmp_path, "a.py", '''\
        def foo():
            """Doc."""
            pass
    ''')
    result = await tool.execute({
        "file_path": str(p),
        "format": "toon",
    })
    assert "content" in result
    assert result["coverage_percent"] > 0


@pytest.mark.asyncio
async def test_validate_arguments_rejects_no_path() -> None:
    tool_no_root = DocCoverageTool()
    with pytest.raises(ValueError, match="Either file_path or project_root"):
        tool_no_root.validate_arguments({"format": "json"})


@pytest.mark.asyncio
async def test_directory_analysis(tool: DocCoverageTool, tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        'def foo():\n    """Doc."""\n    pass\n', encoding="utf-8"
    )
    (tmp_path / "b.py").write_text(
        "def bar():\n    pass\n", encoding="utf-8"
    )
    result = await tool.execute({
        "project_root": str(tmp_path),
        "format": "json",
    })
    assert result["total_elements"] >= 2


@pytest.mark.asyncio
async def test_element_type_filter(tool: DocCoverageTool, tmp_path: Path) -> None:
    p = _write_tmp_file(tmp_path, "a.py", '''\
        class Foo:
            """A class."""
            def bar(self):
                pass
    ''')
    result = await tool.execute({
        "file_path": str(p),
        "element_types": "class",
        "format": "json",
    })
    types = {e["type"] for e in result["elements"]}
    assert types == {"class"}


@pytest.mark.asyncio
async def test_min_coverage_threshold(tool: DocCoverageTool, tmp_path: Path) -> None:
    p = _write_tmp_file(tmp_path, "a.py", '''\
        def foo():
            """Doc."""
            pass

        def bar():
            pass
    ''')
    result = await tool.execute({
        "file_path": str(p),
        "min_coverage": 80.0,
        "format": "json",
    })
    assert result["meets_threshold"] is False


@pytest.mark.asyncio
async def test_js_file_analysis(tool: DocCoverageTool, tmp_path: Path) -> None:
    p = _write_tmp_file(tmp_path, "a.js", '''\
        /**
         * Add numbers.
         */
        function add(a, b) {
            return a + b;
        }
    ''')
    result = await tool.execute({
        "file_path": str(p),
        "format": "json",
    })
    assert result["total_elements"] >= 1
    assert result["documented_count"] >= 1


@pytest.mark.asyncio
async def test_nonexistent_file(tool: DocCoverageTool) -> None:
    result = await tool.execute({
        "file_path": "/nonexistent/file.py",
        "format": "json",
    })
    assert result["total_elements"] == 0
    assert result["coverage_percent"] == 100.0
