#!/usr/bin/env python3
"""
Tests for fd_rg_utils module.

This module tests the shared utilities for fd and ripgrep
command execution and result processing.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools import fd_rg_utils


class TestCheckExternalCommand:
    """Tests for check_external_command function."""

    def test_check_existing_command(self):
        """Test checking for an existing command."""
        with patch("shutil.which", return_value="/usr/bin/test"):
            result = fd_rg_utils.check_external_command("test")
            assert result is True

    def test_check_nonexistent_command(self):
        """Test checking for a nonexistent command."""
        with patch("shutil.which", return_value=None):
            result = fd_rg_utils.check_external_command("nonexistent")
            assert result is False

    def test_check_command_caching(self):
        """Test that command existence is cached."""
        # Clear cache before test
        fd_rg_utils._COMMAND_EXISTS_CACHE.clear()

        with patch("shutil.which", return_value="/usr/bin/test") as mock_which:
            # First call should cache result
            fd_rg_utils.check_external_command("test")
            assert mock_which.call_count == 1

            # Second call should use cache
            fd_rg_utils.check_external_command("test")
            assert mock_which.call_count == 1


class TestGetMissingCommands:
    """Tests for get_missing_commands function."""

    def test_all_commands_present(self):
        """Test when all commands are present."""
        with patch.object(fd_rg_utils, "check_external_command", return_value=True):
            missing = fd_rg_utils.get_missing_commands()
            assert missing == []

    def test_fd_missing(self):
        """Test when fd is missing."""
        with patch.object(
            fd_rg_utils, "check_external_command", side_effect=lambda x: x != "fd"
        ):
            missing = fd_rg_utils.get_missing_commands()
            assert "fd" in missing
            assert "rg" not in missing

    def test_rg_missing(self):
        """Test when rg is missing."""
        with patch.object(
            fd_rg_utils, "check_external_command", side_effect=lambda x: x != "rg"
        ):
            missing = fd_rg_utils.get_missing_commands()
            assert "rg" in missing
            assert "fd" not in missing

    def test_both_missing(self):
        """Test when both commands are missing."""
        with patch.object(fd_rg_utils, "check_external_command", return_value=False):
            missing = fd_rg_utils.get_missing_commands()
            assert "fd" in missing
            assert "rg" in missing


class TestClampInt:
    """Tests for clamp_int function."""

    def test_clamp_with_value(self):
        """Test clamping with a valid value."""
        result = fd_rg_utils.clamp_int(50, 0, 100)
        assert result == 50

    def test_clamp_below_min(self):
        """Test clamping when value is below minimum."""
        result = fd_rg_utils.clamp_int(-10, 0, 100)
        assert result == 0

    def test_clamp_above_max(self):
        """Test clamping when value is above maximum."""
        result = fd_rg_utils.clamp_int(150, 0, 100)
        assert result == 100

    def test_clamp_none_value(self):
        """Test clamping with None value."""
        result = fd_rg_utils.clamp_int(None, 0, 100)
        assert result == 0

    def test_clamp_invalid_string(self):
        """Test clamping with invalid string value."""
        result = fd_rg_utils.clamp_int("invalid", 0, 100)
        assert result == 0


class TestParseSizeToBytes:
    """Tests for parse_size_to_bytes function."""

    def test_parse_kb(self):
        """Test parsing kilobytes."""
        result = fd_rg_utils.parse_size_to_bytes("10K")
        assert result == 10 * 1024

    def test_parse_mb(self):
        """Test parsing megabytes."""
        result = fd_rg_utils.parse_size_to_bytes("100M")
        assert result == 100 * 1024 * 1024

    def test_parse_gb(self):
        """Test parsing gigabytes."""
        result = fd_rg_utils.parse_size_to_bytes("1G")
        assert result == 1024 * 1024 * 1024

    def test_parse_bytes(self):
        """Test parsing bytes."""
        result = fd_rg_utils.parse_size_to_bytes("1024")
        assert result == 1024

    def test_parse_lowercase(self):
        """Test parsing lowercase units."""
        result = fd_rg_utils.parse_size_to_bytes("10k")
        assert result == 10 * 1024

    def test_parse_none(self):
        """Test parsing None."""
        result = fd_rg_utils.parse_size_to_bytes(None)
        assert result is None

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        result = fd_rg_utils.parse_size_to_bytes("")
        assert result is None

    def test_parse_invalid_format(self):
        """Test parsing invalid format."""
        result = fd_rg_utils.parse_size_to_bytes("invalid")
        assert result is None


class TestRunCommandCapture:
    """Tests for run_command_capture function."""

    @pytest.mark.asyncio
    async def test_run_command_success(self):
        """Test successful command execution."""
        with (
            patch("asyncio.create_subprocess_exec") as mock_subprocess,
            patch.object(fd_rg_utils, "check_external_command", return_value=True),
        ):
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"output", b"error")
            mock_subprocess.return_value = mock_proc

            rc, out, err = await fd_rg_utils.run_command_capture(["echo", "test"])

            assert rc == 0
            assert out == b"output"
            assert err == b"error"

    @pytest.mark.asyncio
    async def test_run_command_failure(self):
        """Test command execution with non-zero return code."""
        with (
            patch("asyncio.create_subprocess_exec") as mock_subprocess,
            patch.object(fd_rg_utils, "check_external_command", return_value=True),
        ):
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate.return_value = (b"", b"error")
            mock_subprocess.return_value = mock_proc

            rc, out, err = await fd_rg_utils.run_command_capture(["false"])

            assert rc == 1

    @pytest.mark.asyncio
    async def test_run_command_timeout(self):
        """Test command execution with timeout."""
        with (
            patch("asyncio.create_subprocess_exec") as mock_subprocess,
            patch.object(fd_rg_utils, "check_external_command", return_value=True),
        ):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
            mock_proc.wait = AsyncMock(return_value=0)
            mock_subprocess.return_value = mock_proc

            async def fake_wait_for(awaitable, timeout=None):
                awaitable.close()
                raise asyncio.TimeoutError

            with patch("asyncio.wait_for", new=fake_wait_for):
                rc, out, err = await fd_rg_utils.run_command_capture(
                    ["sleep", "10"], timeout_ms=100
                )

            assert rc == 124
            assert b"Timeout" in err

    @pytest.mark.asyncio
    async def test_run_command_not_found(self):
        """Test command execution when command not found."""
        with (
            patch("asyncio.create_subprocess_exec") as mock_subprocess,
            patch.object(fd_rg_utils, "check_external_command", return_value=True),
        ):
            mock_subprocess.side_effect = FileNotFoundError("Command not found")

            rc, out, err = await fd_rg_utils.run_command_capture(["nonexistent"])

            assert rc == 127
            assert b"not found" in err

    @pytest.mark.asyncio
    async def test_run_command_with_input(self):
        """Test command execution with input data."""
        with (
            patch("asyncio.create_subprocess_exec") as mock_subprocess,
            patch.object(fd_rg_utils, "check_external_command", return_value=True),
        ):
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"result", b"")
            mock_subprocess.return_value = mock_proc

            rc, out, err = await fd_rg_utils.run_command_capture(
                ["cat"], input_data=b"test input"
            )

            assert rc == 0
            assert out == b"result"


class TestBuildFdCommand:
    """Tests for build_fd_command function."""

    def test_build_basic_command(self):
        """Test building basic fd command."""
        cmd = fd_rg_utils.build_fd_command(
            pattern="*.py",
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "fd" in cmd
        assert "--color" in cmd
        assert "never" in cmd
        assert "*.py" in cmd
        assert "/path" in cmd

    def test_build_with_glob(self):
        """Test building fd command with glob."""
        cmd = fd_rg_utils.build_fd_command(
            pattern="*.py",
            glob=True,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "--glob" in cmd

    def test_build_with_full_path_match(self):
        """Test building fd command with full path match."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=True,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "-p" in cmd

    def test_build_with_absolute(self):
        """Test building fd command with absolute paths."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=True,
            limit=None,
            roots=["/path"],
        )
        assert "-a" in cmd

    def test_build_with_follow_symlinks(self):
        """Test building fd command with follow symlinks."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=True,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "-L" in cmd

    def test_build_with_hidden(self):
        """Test building fd command with hidden files."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=True,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "-H" in cmd

    def test_build_with_no_ignore(self):
        """Test building fd command with no ignore."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=True,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "-I" in cmd

    def test_build_with_depth(self):
        """Test building fd command with depth."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=2,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "-d" in cmd
        assert "2" in cmd

    def test_build_with_types(self):
        """Test building fd command with types."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=["f", "d"],
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "-t" in cmd
        assert "f" in cmd
        assert "d" in cmd

    def test_build_with_extensions(self):
        """Test building fd command with extensions."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=["py", "js"],
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "-e" in cmd
        assert "py" in cmd
        assert "js" in cmd

    def test_build_with_exclude(self):
        """Test building fd command with exclude patterns."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=["*.tmp", "__pycache__"],
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "-E" in cmd
        assert "*.tmp" in cmd
        assert "__pycache__" in cmd

    def test_build_with_size(self):
        """Test building fd command with size filters."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=["+10M", "-1K"],
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "-S" in cmd
        assert "+10M" in cmd
        assert "-1K" in cmd

    def test_build_with_limit(self):
        """Test building fd command with limit."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=100,
            roots=["/path"],
        )
        assert "--max-results" in cmd
        assert "100" in cmd

    def test_build_without_pattern(self):
        """Test building fd command without pattern."""
        cmd = fd_rg_utils.build_fd_command(
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            absolute=False,
            limit=None,
            roots=["/path"],
        )
        assert "." in cmd  # Default pattern for all files
