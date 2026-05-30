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
        mock_proc.communicate = AsyncMock(return_value=(b"fd 9.0.0\n", b""))
        mock_proc.returncode = 0

        mock_rg_proc = MagicMock()
        mock_rg_proc.communicate = AsyncMock(return_value=(b"ripgrep 14.1.0\n", b""))
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
        mock_rg_proc.communicate = AsyncMock(return_value=(b"ripgrep 14.1.0\n", b""))
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
        mock_fd_proc.communicate = AsyncMock(return_value=(b"fd 9.0.0\n", b""))
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
        mock_proc.communicate = AsyncMock(return_value=(b"", b"fd 9.0.0\n"))
        mock_proc.returncode = 0

        mock_rg_proc = MagicMock()
        mock_rg_proc.communicate = AsyncMock(return_value=(b"ripgrep 14.1.0\n", b""))
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
        mock_fd_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_fd_proc.returncode = 0

        mock_rg_proc = MagicMock()
        mock_rg_proc.communicate = AsyncMock(return_value=(b"ripgrep 14.1.0\n", b""))
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


class TestCheckToolsFailureModes:
    """Tests for the per-tool ``failure_mode`` classification (r37fD).

    Each failure path must surface a distinguishable enum value and an
    actionable ``recommended_fix`` instead of collapsing every error into
    the legacy ``{"available": False, "version": None}`` shape.
    """

    @pytest.mark.asyncio
    async def test_failure_mode_not_installed(self, tool: CheckToolsTool) -> None:
        """FileNotFoundError → failure_mode='not_installed' with install hint."""

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            # Simulate the missing binary for *both* fd and rg so we can
            # assert the per-tool classification independently.
            raise FileNotFoundError(f"{args[0]} not found")

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            result = await tool.execute({})

        for tool_name in ("fd", "rg"):
            entry = result[tool_name]
            assert entry["available"] is False
            assert entry["version"] is None
            assert entry["failure_mode"] == "not_installed"
            # Install hint must reference an actual package manager so the
            # agent can paste it into a shell.
            fix = entry["recommended_fix"]
            assert fix is not None
            assert "Install" in fix
            if tool_name == "fd":
                assert "brew install fd" in fix or "fd-find" in fix
            else:
                assert "ripgrep" in fix

        # next_step routes by failure_mode so the agent doesn't have to parse
        # the enum back into a command.
        next_step = result["agent_summary"]["next_step"]
        assert "not_installed" in next_step
        assert result["agent_summary"]["verdict"] == "ERROR"

    @pytest.mark.asyncio
    async def test_failure_mode_timeout(self, tool: CheckToolsTool) -> None:
        """TimeoutError on communicate() → failure_mode='timeout' with PATH hint."""

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = MagicMock()
        mock_proc.returncode = 0

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            return mock_proc

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.wait_for",
                side_effect=asyncio.TimeoutError(),
            ):
                result = await tool.execute({})

        for tool_name in ("fd", "rg"):
            entry = result[tool_name]
            assert entry["available"] is False
            assert entry["failure_mode"] == "timeout"
            fix = entry["recommended_fix"]
            assert fix is not None
            # Should hint at PATH diagnostics rather than reinstalling.
            assert "timed out" in fix
            assert "$PATH" in fix or "which" in fix

        assert result["agent_summary"]["verdict"] == "ERROR"
        assert "timeout" in result["agent_summary"]["next_step"]

    @pytest.mark.asyncio
    async def test_failure_mode_permission_denied(self, tool: CheckToolsTool) -> None:
        """PermissionError on spawn → failure_mode='permission_denied' with chmod hint."""

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            raise PermissionError(f"permission denied: {args[0]}")

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            result = await tool.execute({})

        for tool_name in ("fd", "rg"):
            entry = result[tool_name]
            assert entry["available"] is False
            assert entry["failure_mode"] == "permission_denied"
            fix = entry["recommended_fix"]
            assert fix is not None
            # Permission-denied fixes should propose chmod, not reinstallation.
            assert "chmod" in fix or "permission" in fix.lower()

        assert result["agent_summary"]["verdict"] == "ERROR"
        assert "permission_denied" in result["agent_summary"]["next_step"]

    @pytest.mark.asyncio
    async def test_failure_mode_wrong_version(self, tool: CheckToolsTool) -> None:
        """Old fd version (< MIN_FD_MAJOR=8) → failure_mode='wrong_version'."""

        mock_fd_proc = MagicMock()
        # fd 6.0.0 is below the minimum supported major (8).
        mock_fd_proc.communicate = AsyncMock(return_value=(b"fd 6.0.0\n", b""))
        mock_fd_proc.returncode = 0

        mock_rg_proc = MagicMock()
        # ripgrep 14.1.0 satisfies MIN_RG_MAJOR=13.
        mock_rg_proc.communicate = AsyncMock(return_value=(b"ripgrep 14.1.0\n", b""))
        mock_rg_proc.returncode = 0

        async def fake_subprocess(*args: object, **kwargs: object) -> MagicMock:
            if args[0] == "fd":
                return mock_fd_proc
            return mock_rg_proc

        with patch(
            "tree_sitter_analyzer.mcp.tools.check_tools_tool.asyncio.create_subprocess_exec",
            side_effect=fake_subprocess,
        ):
            result = await tool.execute({})

        fd_entry = result["fd"]
        assert fd_entry["available"] is False
        assert fd_entry["failure_mode"] == "wrong_version"
        # We still expose the captured version line so the agent can confirm
        # the diagnosis without re-running the probe.
        assert fd_entry["version"] == "fd 6.0.0"
        fix = fd_entry["recommended_fix"]
        assert fix is not None
        assert "Upgrade" in fix
        # Upgrade command must mention a package manager.
        assert "brew upgrade" in fix or "cargo install" in fix

        # rg is fine, so it must NOT carry a failure_mode.
        rg_entry = result["rg"]
        assert rg_entry["available"] is True
        assert rg_entry["failure_mode"] is None
        assert rg_entry["recommended_fix"] is None

        # Top-level status reflects the partial failure.
        assert result["status"] == "missing_tools"
        assert result["agent_summary"]["verdict"] == "ERROR"
        assert "wrong_version" in result["agent_summary"]["next_step"]
