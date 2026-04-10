#!/usr/bin/env python3
"""
Tests for GetProjectSummaryTool MCP Tool.

Verifies toon/json format output, force_refresh behavior,
staleness detection, and fresh index loading.
Uses tmp_path fixture to avoid writing to the real project.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.get_project_summary_tool import (
    GetProjectSummaryTool,
)
from tree_sitter_analyzer.mcp.utils.project_index import ProjectIndexManager


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project structure for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text(
        '"""Core source package."""\n'
    )
    (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_foo.py").write_text("def test_foo(): pass\n")
    (tmp_path / "README.md").write_text(
        "# MyProject\n\nA great tool for doing things.\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.poetry]\nname = 'myproject'\nversion = '0.1.0'\n"
    )
    return tmp_path


@pytest.fixture
def tool(project_dir: Path) -> GetProjectSummaryTool:
    """Create a GetProjectSummaryTool pointing at the temp project directory."""
    return GetProjectSummaryTool(project_root=str(project_dir))


class TestGetProjectSummaryToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool: GetProjectSummaryTool) -> None:
        """Test that initialization creates a tool instance."""
        assert tool is not None

    def test_init_with_project_root(self, project_dir: Path) -> None:
        """Test initialization with a project root sets project_root."""
        t = GetProjectSummaryTool(project_root=str(project_dir))
        assert t.project_root == str(project_dir)

    def test_set_project_path(self, tool: GetProjectSummaryTool, project_dir: Path) -> None:
        """Test that set_project_path updates project_root."""
        new_path = str(project_dir / "subdir")
        tool.set_project_path(new_path)
        assert tool.project_root == new_path


class TestGetProjectSummaryToolDefinition:
    """Tests for get_tool_definition()."""

    def test_tool_definition_structure(self, tool: GetProjectSummaryTool) -> None:
        """Test that the tool definition has correct keys."""
        defn = tool.get_tool_definition()
        assert "name" in defn
        assert "description" in defn
        assert "inputSchema" in defn

    def test_tool_definition_name(self, tool: GetProjectSummaryTool) -> None:
        """Test that the tool name is get_project_summary."""
        defn = tool.get_tool_definition()
        assert defn["name"] == "get_project_summary"

    def test_description_contains_when_to_use(
        self, tool: GetProjectSummaryTool
    ) -> None:
        """Test that the description contains WHEN TO USE."""
        defn = tool.get_tool_definition()
        assert "WHEN TO USE" in defn["description"]

    def test_description_contains_when_not_to_use(
        self, tool: GetProjectSummaryTool
    ) -> None:
        """Test that the description contains WHEN NOT TO USE."""
        defn = tool.get_tool_definition()
        assert "WHEN NOT TO USE" in defn["description"]

    def test_format_property_enum(self, tool: GetProjectSummaryTool) -> None:
        """Test that the format property has toon and json options."""
        defn = tool.get_tool_definition()
        fmt_prop = defn["inputSchema"]["properties"]["format"]
        assert "toon" in fmt_prop["enum"]
        assert "json" in fmt_prop["enum"]


class TestGetProjectSummaryToolExecution:
    """Tests for execute() — core test class."""

    @pytest.mark.asyncio
    async def test_returns_toon_format_by_default(
        self, tool: GetProjectSummaryTool
    ) -> None:
        """Test that default call returns format='toon' and a summary string."""
        result = await tool.execute({})
        assert result["format"] == "toon"
        assert "summary" in result
        assert isinstance(result["summary"], str)

    @pytest.mark.asyncio
    async def test_toon_format_contains_project_name(
        self, tool: GetProjectSummaryTool, project_dir: Path
    ) -> None:
        """Test that the toon summary contains the project name."""
        result = await tool.execute({"format": "toon"})
        # The project name is derived from the directory name
        assert project_dir.name in result["summary"]

    @pytest.mark.asyncio
    async def test_toon_format_contains_purpose(
        self, tool: GetProjectSummaryTool
    ) -> None:
        """Test that the toon summary includes a purpose line when README is present."""
        result = await tool.execute({"format": "toon"})
        # The README contains "A great tool for doing things." — shown as "what:"
        assert "what:" in result["summary"] or "A great tool" in result["summary"]

    @pytest.mark.asyncio
    async def test_json_format_option(
        self, tool: GetProjectSummaryTool
    ) -> None:
        """Test that format='json' returns a structured dictionary."""
        result = await tool.execute({"format": "json"})
        assert "file_count" in result
        assert "language_distribution" in result
        assert "top_level_structure" in result
        assert "key_files" in result
        assert "entry_points" in result

    @pytest.mark.asyncio
    async def test_force_refresh_rebuilds_index(
        self, tool: GetProjectSummaryTool, project_dir: Path
    ) -> None:
        """Test that force_refresh=True triggers a rebuild and saves a fresh index."""
        # First call builds the index
        await tool.execute({})
        cache_file = project_dir / ".tree-sitter-cache" / "project-index.json"
        assert cache_file.exists()

        # Second call with force_refresh should recreate the file
        await tool.execute({"force_refresh": True})
        assert cache_file.exists()
        # The index was rebuilt — is_fresh should be True in result
        result = await tool.execute({"force_refresh": True, "format": "json"})
        assert result.get("is_fresh") is True

    @pytest.mark.asyncio
    async def test_stale_index_reports_age_correctly(
        self, tool: GetProjectSummaryTool, project_dir: Path
    ) -> None:
        """Test that a stale index (>24h) is loaded and its age reported correctly.

        The code loads the stale index without auto-rebuilding; age_hours reflects
        the real age. force_refresh=True is required to force a rebuild.
        """
        # Build and save index with an old updated_at timestamp
        manager = ProjectIndexManager(str(project_dir))
        index = manager.build()
        # Make the index look 25 hours old
        index.updated_at = time.time() - (25 * 3600)
        manager.save(index)

        # Execute without force_refresh — should load stale index and report its age
        result = await tool.execute({"format": "json"})
        # The loaded index is 25h old, so age_hours should be ~25
        assert result["index_age_hours"] >= 24.0

    @pytest.mark.asyncio
    async def test_force_refresh_on_stale_rebuilds(
        self, tool: GetProjectSummaryTool, project_dir: Path
    ) -> None:
        """Test that force_refresh=True on a stale index triggers a rebuild."""
        # Build and save index with an old updated_at timestamp
        manager = ProjectIndexManager(str(project_dir))
        index = manager.build()
        index.updated_at = time.time() - (25 * 3600)
        manager.save(index)

        # force_refresh should bypass the stale index and rebuild
        result = await tool.execute({"force_refresh": True, "format": "json"})
        # After force rebuild, age should be near-zero
        assert result["index_age_hours"] < 1.0
        assert result["is_fresh"] is True

    @pytest.mark.asyncio
    async def test_fresh_index_loaded_from_disk(
        self, tool: GetProjectSummaryTool, project_dir: Path
    ) -> None:
        """Test that a fresh on-disk index is loaded without rebuilding."""
        # Pre-build and save the index
        manager = ProjectIndexManager(str(project_dir))
        index = manager.build()
        manager.save(index)

        # Verify the cache file exists before calling execute
        cache_file = project_dir / ".tree-sitter-cache" / "project-index.json"
        assert cache_file.exists()

        # Call execute without force_refresh — should load from disk
        result = await tool.execute({"format": "json"})
        assert result["is_fresh"] is True
        # index_age_hours should be near zero since we just built it
        assert result["index_age_hours"] < 1.0

    @pytest.mark.asyncio
    async def test_custom_notes_included_in_toon_format(
        self, tool: GetProjectSummaryTool, project_dir: Path
    ) -> None:
        """Test that custom_notes appear in the toon output when include_notes=True."""
        # Build index with custom notes
        manager = ProjectIndexManager(str(project_dir))
        index = manager.build()
        index.custom_notes = "This is a monorepo."
        manager.save(index)

        result = await tool.execute({"include_notes": True})
        assert "This is a monorepo." in result["summary"]

    @pytest.mark.asyncio
    async def test_python_language_detected(
        self, tool: GetProjectSummaryTool
    ) -> None:
        """Test that Python files are counted in language_distribution."""
        result = await tool.execute({"format": "json"})
        lang_dist = result["language_distribution"]
        assert "python" in lang_dist
        assert lang_dist["python"] >= 2  # src/main.py, tests/test_foo.py, etc.
