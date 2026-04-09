#!/usr/bin/env python3
"""
Tests for CheckToolsTool MCP Tool.

Verifies availability checking for fd and ripgrep, version parsing,
status values, and recommendation generation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.check_tools_tool import CheckToolsTool


@pytest.fixture
def tool() -> CheckToolsTool:
    """Create a fresh CheckToolsTool instance for each test."""
    return CheckToolsTool()


class TestCheckToolsToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool: CheckToolsTool) -> None:
        """Test that initialization creates a tool instance."""
        assert tool is not None

    def test_init_with_project_root(self) -> None:
        """Test initialization with a project root."""
        t = CheckToolsTool(project_root="/tmp/myproject")
        assert t.project_root == "/tmp/myproject"

    def test_init_without_project_root(self) -> None:
        """Test initialization without a project root defaults to None."""
        t = CheckToolsTool()
        assert t.project_root is None

    def test_set_project_path(self, tool: CheckToolsTool) -> None:
        """Test that set_project_path updates project_root."""
        tool.set_project_path("/new/path")
        assert tool.project_root == "/new/path"


class TestCheckToolsToolDefinition:
    """Tests for get_tool_definition()."""

    def test_tool_definition_has_required_keys(self, tool: CheckToolsTool) -> None:
        """Test that the tool definition has name, description, and inputSchema."""
        defn = tool.get_tool_definition()
        assert "name" in defn
        assert "description" in defn
        assert "inputSchema" in defn

    def test_tool_definition_name(self, tool: CheckToolsTool) -> None:
        """Test that the tool name is correct."""
        defn = tool.get_tool_definition()
        assert defn["name"] == "check_tools"

    def test_tool_definition_description_contains_when_to_use(
        self, tool: CheckToolsTool
    ) -> None:
        """Test that the description contains WHEN TO USE section."""
        defn = tool.get_tool_definition()
        assert "WHEN TO USE" in defn["description"]

    def test_tool_definition_description_contains_when_not_to_use(
        self, tool: CheckToolsTool
    ) -> None:
        """Test that the description contains WHEN NOT TO USE section."""
        defn = tool.get_tool_definition()
        assert "WHEN NOT TO USE" in defn["description"]

    def test_tool_definition_input_schema_empty_properties(
        self, tool: CheckToolsTool
    ) -> None:
        """Test that the input schema has no required properties (no arguments needed)."""
        defn = tool.get_tool_definition()
        schema = defn["inputSchema"]
        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert schema.get("additionalProperties") is False

    def test_tool_definition_no_required_fields(self, tool: CheckToolsTool) -> None:
        """Test that the schema has no required fields."""
        defn = tool.get_tool_definition()
        schema = defn["inputSchema"]
        assert "required" not in schema


class TestCheckToolsToolExecution:
    """Tests for execute() — core test class."""

    @pytest.mark.asyncio
    async def test_all_tools_available(self, tool: CheckToolsTool) -> None:
        """Test that when both fd and rg are present, status is all_tools_available."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"fd 9.0.0\n", b"")
        )
        mock_proc.returncode = 0

        mock_rg_proc = MagicMock()
        mock_rg_proc.communicate = AsyncMock(
            return_value=(b"ripgrep 14.1.0\n", b"")
        )
        mock_rg_proc.returncode = 0

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            if args[0] == "fd":
                return mock_proc
            return mock_rg_proc

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            result = await tool.execute({})

        assert result["status"] == "all_tools_available"
        assert result["fd"]["available"] is True
        assert result["rg"]["available"] is True
        assert result["recommendation"] is None

    @pytest.mark.asyncio
    async def test_fd_missing(self, tool: CheckToolsTool) -> None:
        """Test that when fd is missing, fd.available is False."""
        mock_rg_proc = MagicMock()
        mock_rg_proc.communicate = AsyncMock(
            return_value=(b"ripgrep 14.1.0\n", b"")
        )
        mock_rg_proc.returncode = 0

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            if args[0] == "fd":
                raise FileNotFoundError("fd not found")
            return mock_rg_proc

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            result = await tool.execute({})

        assert result["fd"]["available"] is False
        assert result["rg"]["available"] is True
        assert result["status"] == "missing_tools"
        assert "fd" in result["recommendation"]

    @pytest.mark.asyncio
    async def test_rg_missing(self, tool: CheckToolsTool) -> None:
        """Test that when rg is missing, rg.available is False."""
        mock_fd_proc = MagicMock()
        mock_fd_proc.communicate = AsyncMock(
            return_value=(b"fd 9.0.0\n", b"")
        )
        mock_fd_proc.returncode = 0

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            if args[0] == "rg":
                raise FileNotFoundError("rg not found")
            return mock_fd_proc

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            result = await tool.execute({})

        assert result["rg"]["available"] is False
        assert result["fd"]["available"] is True
        assert result["status"] == "missing_tools"
        assert "ripgrep" in result["recommendation"]

    @pytest.mark.asyncio
    async def test_both_missing(self, tool: CheckToolsTool) -> None:
        """Test that when both fd and rg are missing, status is missing_tools and recommendation is set."""

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            raise FileNotFoundError("command not found")

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            result = await tool.execute({})

        assert result["status"] == "missing_tools"
        assert result["fd"]["available"] is False
        assert result["rg"]["available"] is False
        assert result["recommendation"] is not None
        assert len(result["recommendation"]) > 0

    @pytest.mark.asyncio
    async def test_version_parsing(self, tool: CheckToolsTool) -> None:
        """Test that only the first line of stdout is used as the version string."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"fd 9.0.0\nsome extra line\n", b"")
        )
        mock_proc.returncode = 0

        mock_rg_proc = MagicMock()
        mock_rg_proc.communicate = AsyncMock(
            return_value=(b"ripgrep 14.1.0\nsome extra line\n", b"")
        )
        mock_rg_proc.returncode = 0

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            if args[0] == "fd":
                return mock_proc
            return mock_rg_proc

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            result = await tool.execute({})

        # Only first line should be captured
        assert result["fd"]["version"] == "fd 9.0.0"
        assert result["rg"]["version"] == "ripgrep 14.1.0"

    @pytest.mark.asyncio
    async def test_version_from_stderr_when_stdout_empty(
        self, tool: CheckToolsTool
    ) -> None:
        """Test that stderr is used when stdout is empty."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"fd 9.0.0\n")
        )
        mock_proc.returncode = 0

        mock_rg_proc = MagicMock()
        mock_rg_proc.communicate = AsyncMock(
            return_value=(b"ripgrep 14.1.0\n", b"")
        )
        mock_rg_proc.returncode = 0

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            if args[0] == "fd":
                return mock_proc
            return mock_rg_proc

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            result = await tool.execute({})

        assert result["fd"]["available"] is True
        assert result["fd"]["version"] == "fd 9.0.0"

    @pytest.mark.asyncio
    async def test_timeout_marks_tool_unavailable(self, tool: CheckToolsTool) -> None:
        """Test that a timeout when checking a tool marks it as unavailable."""
        mock_fd_proc = MagicMock()
        mock_fd_proc.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        mock_fd_proc.returncode = 0

        mock_rg_proc = MagicMock()
        mock_rg_proc.communicate = AsyncMock(
            return_value=(b"ripgrep 14.1.0\n", b"")
        )
        mock_rg_proc.returncode = 0

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            if args[0] == "fd":
                return mock_fd_proc
            return mock_rg_proc

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.wait_for",
                side_effect=asyncio.TimeoutError(),
            ):
                result = await tool.execute({})

        # Both will be affected by the wait_for mock
        assert result["fd"]["available"] is False
