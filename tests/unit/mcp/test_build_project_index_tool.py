#!/usr/bin/env python3
"""
Tests for BuildProjectIndexTool MCP Tool.

Verifies that the tool builds, persists, and reports on a project index.
Uses tmp_path fixture to avoid writing to the real project.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.build_project_index_tool import (
    BuildProjectIndexTool,
)
from tree_sitter_analyzer.mcp.utils.project_index import ProjectIndexManager


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text(
        '"""Source package."""\n'
    )
    (tmp_path / "src" / "app.py").write_text("def run():\n    pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_run(): pass\n")
    (tmp_path / "README.md").write_text("# Test project\n")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.poetry]\nname = 'testproject'\n"
    )
    return tmp_path


@pytest.fixture
def tool(project_dir: Path) -> BuildProjectIndexTool:
    """Create a BuildProjectIndexTool pointing at the temp project directory."""
    return BuildProjectIndexTool(project_root=str(project_dir))


class TestBuildProjectIndexToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool: BuildProjectIndexTool) -> None:
        """Test that initialization creates a tool instance."""
        assert tool is not None

    def test_init_with_project_root(self, project_dir: Path) -> None:
        """Test initialization with a project root sets project_root."""
        t = BuildProjectIndexTool(project_root=str(project_dir))
        assert t.project_root == str(project_dir)

    def test_set_project_path(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        """Test that set_project_path updates project_root."""
        new = str(project_dir / "subdir")
        tool.set_project_path(new)
        assert tool.project_root == new


class TestBuildProjectIndexToolDefinition:
    """Tests for get_tool_definition()."""

    def test_tool_definition_structure(self, tool: BuildProjectIndexTool) -> None:
        """Test that the tool definition has correct keys."""
        defn = tool.get_tool_definition()
        assert "name" in defn
        assert "description" in defn
        assert "inputSchema" in defn

    def test_tool_definition_name(self, tool: BuildProjectIndexTool) -> None:
        """Test that the tool name is build_project_index."""
        defn = tool.get_tool_definition()
        assert defn["name"] == "build_project_index"

    def test_description_contains_when_to_use(
        self, tool: BuildProjectIndexTool
    ) -> None:
        """Test that the description contains WHEN TO USE section."""
        defn = tool.get_tool_definition()
        assert "WHEN TO USE" in defn["description"]

    def test_description_contains_when_not_to_use(
        self, tool: BuildProjectIndexTool
    ) -> None:
        """Test that the description contains WHEN NOT TO USE section."""
        defn = tool.get_tool_definition()
        assert "WHEN NOT TO USE" in defn["description"]

    def test_add_notes_property_exists(self, tool: BuildProjectIndexTool) -> None:
        """Test that add_notes property is in the schema."""
        defn = tool.get_tool_definition()
        props = defn["inputSchema"]["properties"]
        assert "add_notes" in props

    def test_roots_property_exists(self, tool: BuildProjectIndexTool) -> None:
        """Test that roots property is in the schema."""
        defn = tool.get_tool_definition()
        props = defn["inputSchema"]["properties"]
        assert "roots" in props
        assert props["roots"]["type"] == "array"


class TestBuildProjectIndexToolExecution:
    """Tests for execute() — core test class."""

    @pytest.mark.asyncio
    async def test_returns_build_status(self, tool: BuildProjectIndexTool) -> None:
        """Test that the result contains status='built'."""
        result = await tool.execute({})
        assert result["status"] == "built"

    @pytest.mark.asyncio
    async def test_returns_build_duration(self, tool: BuildProjectIndexTool) -> None:
        """Test that the result contains a build_duration_ms field."""
        result = await tool.execute({})
        assert "build_duration_ms" in result
        assert isinstance(result["build_duration_ms"], int)
        assert result["build_duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_saves_index_to_disk(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        """Test that the tool saves the index to .tree-sitter-cache/project-index.json."""
        await tool.execute({})
        cache_file = project_dir / ".tree-sitter-cache" / "project-index.json"
        assert cache_file.exists()

    @pytest.mark.asyncio
    async def test_index_saved_to_path_reported(
        self, tool: BuildProjectIndexTool
    ) -> None:
        """Test that the result reports the index_saved_to path."""
        result = await tool.execute({})
        assert "index_saved_to" in result
        assert "project-index.json" in result["index_saved_to"]

    @pytest.mark.asyncio
    async def test_add_notes_stored(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        """Test that add_notes is stored in custom_notes field of the index."""
        await tool.execute({"add_notes": "This is a monorepo with 3 services."})

        # Verify via direct disk load
        manager = ProjectIndexManager(str(project_dir))
        index = manager.load()
        assert index is not None
        assert index.custom_notes == "This is a monorepo with 3 services."

    @pytest.mark.asyncio
    async def test_files_scanned_positive(self, tool: BuildProjectIndexTool) -> None:
        """Test that files_scanned is a positive integer."""
        result = await tool.execute({})
        assert "files_scanned" in result
        assert isinstance(result["files_scanned"], int)
        assert result["files_scanned"] > 0

    @pytest.mark.asyncio
    async def test_languages_found_dict(self, tool: BuildProjectIndexTool) -> None:
        """Test that languages_found is a dict with at least python."""
        result = await tool.execute({})
        assert "languages_found" in result
        lang = result["languages_found"]
        assert isinstance(lang, dict)
        assert "python" in lang

    @pytest.mark.asyncio
    async def test_next_step_field_present(self, tool: BuildProjectIndexTool) -> None:
        """Test that the result contains a next_step field."""
        result = await tool.execute({})
        assert "next_step" in result

    @pytest.mark.asyncio
    async def test_index_content_valid_json(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        """Test that the saved index file is valid JSON with expected keys."""
        await tool.execute({})
        cache_file = project_dir / ".tree-sitter-cache" / "project-index.json"
        with cache_file.open(encoding="utf-8") as fh:
            data = json.load(fh)
        assert "file_count" in data
        assert "language_distribution" in data
        assert "schema_version" in data

    @pytest.mark.asyncio
    async def test_existing_notes_preserved_when_add_notes_empty(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        """Test that existing custom_notes are preserved when add_notes is empty."""
        # First build with notes
        await tool.execute({"add_notes": "Keep this note."})
        # Second build without notes
        await tool.execute({})
        manager = ProjectIndexManager(str(project_dir))
        index = manager.load()
        assert index is not None
        assert index.custom_notes == "Keep this note."
