"""Tests for Call Graph MCP Tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.call_graph_tool import CallGraphTool


@pytest.fixture
def tool() -> CallGraphTool:
    return CallGraphTool()


@pytest.fixture
def sample_py() -> Path:
    content = b'''
def foo():
    bar()

def bar():
    baz()

def baz():
    pass

def unused():
    pass

foo()
'''
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(content)
        return Path(f.name)


def test_tool_definition(tool: CallGraphTool) -> None:
    defn = tool.get_tool_definition()
    assert defn["name"] == "call_graph"
    assert "island" in defn["description"].lower()
    assert "file_path" in defn["inputSchema"]["properties"]


def test_validate_arguments_valid(tool: CallGraphTool) -> None:
    assert tool.validate_arguments({"format": "toon"})
    assert tool.validate_arguments({"format": "json"})
    assert tool.validate_arguments({"god_threshold": 10})


def test_validate_arguments_invalid(tool: CallGraphTool) -> None:
    assert not tool.validate_arguments({"format": "xml"})
    assert not tool.validate_arguments({"god_threshold": -1})
    assert not tool.validate_arguments({"god_threshold": "abc"})


def test_execute_single_file_toon(tool: CallGraphTool, sample_py: Path) -> None:
    result = tool.execute({"file_path": str(sample_py), "format": "toon"})
    assert len(result) == 1
    assert "content" in result[0]


def test_execute_single_file_json(tool: CallGraphTool, sample_py: Path) -> None:
    result = tool.execute({"file_path": str(sample_py), "format": "json"})
    assert len(result) == 1
    data = result[0]
    assert data["total_functions"] >= 4
    assert data["total_edges"] >= 2
    assert data["total_islands"] >= 1


def test_execute_json_has_files(tool: CallGraphTool, sample_py: Path) -> None:
    result = tool.execute({"file_path": str(sample_py), "format": "json"})
    data = result[0]
    assert len(data["files"]) == 1
    file_data = data["files"][0]
    assert "functions" in file_data
    assert "call_edges" in file_data
    assert "island_functions" in file_data


def test_execute_directory(tool: CallGraphTool, tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b'''
def hello():
    world()

def world():
    pass
''')
    result = tool.execute({"project_root": str(tmp_path), "format": "json"})
    data = result[0]
    assert data["total_functions"] >= 2


def test_execute_nonexistent_file(tool: CallGraphTool) -> None:
    result = tool.execute({"file_path": "/nonexistent/file.py", "format": "json"})
    data = result[0]
    assert data["total_functions"] == 0


def test_execute_empty_directory(tool: CallGraphTool, tmp_path: Path) -> None:
    result = tool.execute({"project_root": str(tmp_path), "format": "json"})
    data = result[0]
    assert data["total_functions"] == 0
