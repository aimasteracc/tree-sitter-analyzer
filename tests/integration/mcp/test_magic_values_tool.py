"""Integration tests for magic values MCP tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.magic_values_tool import MagicValuesTool


@pytest.fixture
def tool() -> MagicValuesTool:
    return MagicValuesTool()


@pytest.fixture
def sample_py() -> Path:
    content = b'''x = 42
y = 100
url = "https://api.example.com"
color = "#ff0000"
path = "/usr/local/bin"
'''
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(content)
        return Path(f.name)


@pytest.fixture
def sample_js() -> Path:
    content = b'''const x = 42;
const url = "https://api.example.com/v2";
'''
    with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as f:
        f.write(content)
        return Path(f.name)


def test_tool_definition(tool: MagicValuesTool) -> None:
    defn = tool.get_tool_definition()
    assert defn["name"] == "magic_values"
    assert "inputSchema" in defn
    assert "file_path" in defn["inputSchema"]["properties"]


def test_execute_single_file(tool: MagicValuesTool, sample_py: Path) -> None:
    result = tool.execute({"file_path": str(sample_py), "format": "json"})
    assert len(result) == 1
    data = result[0]
    assert "total_values" in data
    assert data["total_values"] > 0


def test_execute_toon_format(tool: MagicValuesTool, sample_py: Path) -> None:
    result = tool.execute({"file_path": str(sample_py), "format": "toon"})
    assert len(result) == 1
    assert "content" in result[0]


def test_execute_with_categories(tool: MagicValuesTool, sample_py: Path) -> None:
    result = tool.execute({
        "file_path": str(sample_py),
        "categories": ["magic_number"],
        "format": "json",
    })
    data = result[0]
    for val_data in data["values"]:
        assert val_data["category"] == "magic_number"


def test_execute_min_occurrences(tool: MagicValuesTool, sample_py: Path) -> None:
    result = tool.execute({
        "file_path": str(sample_py),
        "min_occurrences": 10,
        "format": "json",
    })
    data = result[0]
    assert all(v["total_refs"] >= 10 for v in data["values"])


def test_execute_project_directory(tool: MagicValuesTool, sample_py: Path, sample_js: Path) -> None:
    parent = str(sample_py.parent)
    result = tool.execute({
        "project_root": parent,
        "format": "json",
    })
    data = result[0]
    assert data["total_values"] > 0


def test_execute_empty_file(tool: MagicValuesTool) -> None:
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(b"x = 0\ny = 1\n")
        p = Path(f.name)
    result = tool.execute({"file_path": str(p), "format": "json"})
    data = result[0]
    assert data["total_values"] == 0


def test_execute_js_file(tool: MagicValuesTool, sample_js: Path) -> None:
    result = tool.execute({"file_path": str(sample_js), "format": "json"})
    data = result[0]
    assert data["total_values"] > 0


def test_json_values_have_required_fields(tool: MagicValuesTool, sample_py: Path) -> None:
    result = tool.execute({"file_path": str(sample_py), "format": "json"})
    data = result[0]
    for val in data["values"]:
        assert "value" in val
        assert "category" in val
        assert "total_refs" in val
        assert "file_count" in val
