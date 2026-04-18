#!/usr/bin/env python3
"""Tests for env_tracker MCP tool."""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.env_tracker_tool import EnvTrackerTool


@pytest.fixture
def tool() -> EnvTrackerTool:
    """Create an EnvTrackerTool instance."""
    return EnvTrackerTool()


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a sample project with env var usage."""
    # Python file
    py_code = '''
import os
api_key = os.getenv("API_KEY")
debug = os.getenv("DEBUG", "false")
db_host = os.environ["DB_HOST"]
'''
    (tmp_path / "config.py").write_text(py_code)

    # JavaScript file
    js_code = '''
const apiKey = process.env.API_KEY;
const dbHost = process.env["DB_HOST"];
'''
    (tmp_path / "config.js").write_text(js_code)

    # Go file
    go_code = '''package main
import "os"
func main() {
    apiKey := os.Getenv("API_KEY")
}'''
    (tmp_path / "main.go").write_text(go_code)

    return tmp_path


@pytest.mark.asyncio
async def test_tool_definition(tool: EnvTrackerTool) -> None:
    """Test tool definition has required fields."""
    definition = tool.get_tool_definition()
    assert definition["name"] == "env_tracker"
    assert "inputSchema" in definition
    assert "properties" in definition["inputSchema"]


@pytest.mark.asyncio
async def test_execute_single_file(tool: EnvTrackerTool, sample_project: Path) -> None:
    """Test executing on a single file."""
    result = await tool.execute({
        "file_path": str(sample_project / "config.py"),
        "format": "json",
    })
    assert "total_references" in result
    assert result["total_references"] >= 1


@pytest.mark.asyncio
async def test_execute_directory(tool: EnvTrackerTool, sample_project: Path) -> None:
    """Test executing on a directory."""
    result = await tool.execute({
        "project_root": str(sample_project),
        "format": "json",
    })
    assert "total_references" in result
    assert result["unique_vars"] >= 1


@pytest.mark.asyncio
async def test_execute_toon_format(tool: EnvTrackerTool, sample_project: Path) -> None:
    """Test TOON output format."""
    result = await tool.execute({
        "file_path": str(sample_project / "config.py"),
        "format": "toon",
    })
    assert result.get("format") == "toon"
    assert "result" in result


@pytest.mark.asyncio
async def test_execute_json_grouped(tool: EnvTrackerTool, sample_project: Path) -> None:
    """Test JSON output with grouping."""
    result = await tool.execute({
        "file_path": str(sample_project / "config.py"),
        "format": "json",
        "group_by_var": True,
    })
    assert "variables" in result
    assert "API_KEY" in result["variables"]


@pytest.mark.asyncio
async def test_execute_json_ungrouped(tool: EnvTrackerTool, sample_project: Path) -> None:
    """Test JSON output without grouping."""
    result = await tool.execute({
        "file_path": str(sample_project / "config.py"),
        "format": "json",
        "group_by_var": False,
    })
    assert "references" in result
    assert len(result["references"]) >= 1


@pytest.mark.asyncio
async def test_execute_no_args(tool: EnvTrackerTool) -> None:
    """Test error when no arguments provided."""
    result = await tool.execute({})
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_include_defaults(
    tool: EnvTrackerTool, sample_project: Path
) -> None:
    """Test filtering defaults."""
    result_with = await tool.execute({
        "file_path": str(sample_project / "config.py"),
        "format": "json",
        "include_defaults": True,
    })
    result_without = await tool.execute({
        "file_path": str(sample_project / "config.py"),
        "format": "json",
        "include_defaults": False,
    })
    assert result_with["total_references"] >= result_without["total_references"]


@pytest.mark.asyncio
async def test_execute_javascript(tool: EnvTrackerTool, sample_project: Path) -> None:
    """Test JavaScript env var detection."""
    result = await tool.execute({
        "file_path": str(sample_project / "config.js"),
        "format": "json",
    })
    assert result["total_references"] >= 1
    assert "API_KEY" in result.get("variables", {})


@pytest.mark.asyncio
async def test_execute_go(tool: EnvTrackerTool, sample_project: Path) -> None:
    """Test Go env var detection."""
    result = await tool.execute({
        "file_path": str(sample_project / "main.go"),
        "format": "json",
    })
    assert result["total_references"] >= 1
    assert "API_KEY" in result.get("variables", {})
