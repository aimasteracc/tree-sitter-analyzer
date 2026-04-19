"""Tests for Circular Dependency MCP Tool."""
from __future__ import annotations

import tempfile
import textwrap

import pytest

from tree_sitter_analyzer.mcp.tools.circular_dependency_tool import CircularDependencyTool


@pytest.fixture
def tool() -> CircularDependencyTool:
    return CircularDependencyTool()


def _write_tmp(content: str, suffix: str, prefix: str = "test_") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, prefix=prefix, delete=False, dir="/tmp")
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


def _write_dir(files: dict[str, str]) -> str:
    d = tempfile.mkdtemp(dir="/tmp")
    for name, content in files.items():
        with open(f"{d}/{name}", "w") as f:
            f.write(textwrap.dedent(content))
    return d


@pytest.mark.asyncio
async def test_tool_definition(tool: CircularDependencyTool) -> None:
    defn = tool.get_tool_definition()
    assert defn["name"] == "circular_dependency"


@pytest.mark.asyncio
async def test_validate_valid(tool: CircularDependencyTool) -> None:
    assert tool.validate_arguments({"file_path": "/tmp/test.py"}) is True


@pytest.mark.asyncio
async def test_validate_bad_format(tool: CircularDependencyTool) -> None:
    with pytest.raises(ValueError, match="format"):
        tool.validate_arguments({"format": "xml"})


@pytest.mark.asyncio
async def test_execute_file_json(tool: CircularDependencyTool) -> None:
    path = _write_tmp("import os\nimport sys\n", ".py")
    result = await tool.execute({"file_path": path, "format": "json"})
    assert "edges" in result


@pytest.mark.asyncio
async def test_execute_project_json(tool: CircularDependencyTool) -> None:
    d = _write_dir({
        "a.py": "import b\n",
        "b.py": "import a\n",
    })
    result = await tool.execute({"project_path": d, "format": "json"})
    assert "total_cycles" in result
    assert result["total_cycles"] >= 1


@pytest.mark.asyncio
async def test_execute_project_toon(tool: CircularDependencyTool) -> None:
    d = _write_dir({
        "a.py": "import b\n",
        "b.py": "import a\n",
    })
    result = await tool.execute({"project_path": d, "format": "toon"})
    assert "content" in result
    assert result["total_cycles"] >= 1


@pytest.mark.asyncio
async def test_execute_no_args(tool: CircularDependencyTool) -> None:
    result = await tool.execute({"format": "json"})
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_js_project(tool: CircularDependencyTool) -> None:
    d = _write_dir({
        "a.js": "const b = require('./b');\n",
        "b.js": "const a = require('./a');\n",
    })
    result = await tool.execute({"project_path": d, "format": "json"})
    assert result["total_cycles"] >= 1
