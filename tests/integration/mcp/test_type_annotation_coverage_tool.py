"""Integration tests for type annotation coverage MCP tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.type_annotation_coverage_tool import (
    TypeAnnotationCoverageTool,
)


@pytest.fixture
def tool() -> TypeAnnotationCoverageTool:
    return TypeAnnotationCoverageTool()


@pytest.fixture
def sample_py() -> Path:
    content = b'''def foo(x: int, y: str) -> bool:
    return True

def bar(a, b):
    return a + b

z: int = 42
'''
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(content)
        return Path(f.name)


def test_tool_definition(tool: TypeAnnotationCoverageTool) -> None:
    defn = tool.get_tool_definition()
    assert defn["name"] == "type_annotation_coverage"
    assert "inputSchema" in defn
    assert "file_path" in defn["inputSchema"]["properties"]


def test_execute_single_file_json(tool: TypeAnnotationCoverageTool, sample_py: Path) -> None:
    result = tool.execute({"file_path": str(sample_py), "format": "json"})
    assert len(result) == 1
    data = result[0]
    assert "coverage_pct" in data
    assert "total_elements" in data
    assert "stats" in data


def test_execute_single_file_toon(tool: TypeAnnotationCoverageTool, sample_py: Path) -> None:
    result = tool.execute({"file_path": str(sample_py), "format": "toon"})
    assert len(result) == 1
    assert "content" in result[0]


def test_execute_directory(tool: TypeAnnotationCoverageTool, sample_py: Path) -> None:
    parent = str(sample_py.parent)
    result = tool.execute({"project_root": parent, "format": "json"})
    assert len(result) >= 1
    for r in result:
        assert "coverage_pct" in r


def test_validate_arguments_valid(tool: TypeAnnotationCoverageTool) -> None:
    assert tool.validate_arguments({"format": "json"}) is True
    assert tool.validate_arguments({"format": "toon"}) is True


def test_validate_arguments_invalid(tool: TypeAnnotationCoverageTool) -> None:
    assert tool.validate_arguments({"format": "xml"}) is False
