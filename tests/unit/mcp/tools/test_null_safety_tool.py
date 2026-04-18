#!/usr/bin/env python3
"""Tests for Null Safety MCP Tool."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.null_safety_tool import NullSafetyTool


def _write_tmp_file(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


@pytest.fixture
def tool(tmp_path: Path) -> NullSafetyTool:
    return NullSafetyTool(str(tmp_path))


@pytest.mark.asyncio
async def test_tool_definition(tool: NullSafetyTool) -> None:
    defn = tool.get_tool_definition()
    assert defn["name"] == "null_safety"
    assert "inputSchema" in defn


@pytest.mark.asyncio
async def test_analyze_file_json(tool: NullSafetyTool, tmp_path: Path) -> None:
    p = _write_tmp_file(tmp_path, "a.py", """\
        def foo():
            result = None
            return result.strip()
    """)
    result = await tool.execute({
        "file_path": str(p),
        "format": "json",
    })
    assert result["total_issues"] >= 1
    assert result["language"] == "python"
    assert "issues" in result


@pytest.mark.asyncio
async def test_analyze_file_toon(tool: NullSafetyTool, tmp_path: Path) -> None:
    p = _write_tmp_file(tmp_path, "a.py", """\
        def foo():
            result = None
            return result.strip()
    """)
    result = await tool.execute({
        "file_path": str(p),
        "format": "toon",
    })
    assert "content" in result
    assert result["total_issues"] >= 1


@pytest.mark.asyncio
async def test_analyze_file_text(tool: NullSafetyTool, tmp_path: Path) -> None:
    p = _write_tmp_file(tmp_path, "a.py", """\
        def foo():
            result = None
            return result.strip()
    """)
    result = await tool.execute({
        "file_path": str(p),
        "format": "text",
    })
    assert "content" in result
    assert "Null Safety" in result["content"]


@pytest.mark.asyncio
async def test_no_file_error(tool: NullSafetyTool) -> None:
    result = await tool.execute({
        "file_path": "",
        "format": "json",
    })
    assert "error" in result


@pytest.mark.asyncio
async def test_nonexistent_file(tool: NullSafetyTool) -> None:
    result = await tool.execute({
        "file_path": "/nonexistent/file.py",
        "format": "json",
    })
    assert result["total_issues"] == 0


@pytest.mark.asyncio
async def test_severity_filter_high(
    tool: NullSafetyTool, tmp_path: Path
) -> None:
    p = _write_tmp_file(tmp_path, "a.py", """\
        data = {"a": 1}
        x = data["b"]
        result = None
        return result.strip()
    """)
    result = await tool.execute({
        "file_path": str(p),
        "format": "json",
        "severity": "high",
    })
    for issue in result["issues"]:
        assert issue["severity"] == "high"


@pytest.mark.asyncio
async def test_validate_good(tool: NullSafetyTool) -> None:
    assert tool.validate_arguments({
        "file_path": "test.py",
        "format": "json",
        "severity": "medium",
    })


@pytest.mark.asyncio
async def test_validate_bad_format(tool: NullSafetyTool) -> None:
    with pytest.raises(ValueError, match="format"):
        tool.validate_arguments({
            "file_path": "test.py",
            "format": "xml",
        })


@pytest.mark.asyncio
async def test_validate_bad_severity(tool: NullSafetyTool) -> None:
    with pytest.raises(ValueError, match="severity"):
        tool.validate_arguments({
            "file_path": "test.py",
            "format": "json",
            "severity": "critical",
        })


@pytest.mark.asyncio
async def test_validate_no_file(tool: NullSafetyTool) -> None:
    with pytest.raises(ValueError, match="file_path"):
        tool.validate_arguments({
            "file_path": "",
            "format": "json",
        })


@pytest.mark.asyncio
async def test_javascript_file(tool: NullSafetyTool, tmp_path: Path) -> None:
    p = _write_tmp_file(tmp_path, "a.js", """\
        function foo() {
            let result = null;
            return result.toString();
        }
    """)
    result = await tool.execute({
        "file_path": str(p),
        "format": "json",
    })
    assert result["language"] == "javascript"
    assert result["total_issues"] >= 1
