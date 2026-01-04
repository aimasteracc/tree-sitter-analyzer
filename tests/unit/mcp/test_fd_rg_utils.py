#!/usr/bin/env python3
"""
Tests for fd_rg_utils module.

This module tests the shared utilities for fd and ripgrep
command execution and result processing.
"""

import asyncio
from unittest.mock import AsyncMock, patch

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
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"output", b"")
            mock_subprocess.return_value = mock_proc

            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
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


class TestBuildRgCommand:
    """Tests for build_rg_command function."""

    def test_build_basic_command(self):
        """Test building basic ripgrep command."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "rg" in cmd
        assert "--json" in cmd
        assert "--no-heading" in cmd
        assert "--color" in cmd
        assert "never" in cmd
        assert "test" in cmd
        assert "/path" in cmd

    def test_build_with_case_smart(self):
        """Test building with smart case sensitivity."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-S" in cmd

    def test_build_with_case_insensitive(self):
        """Test building with insensitive case."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case="insensitive",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-i" in cmd

    def test_build_with_case_sensitive(self):
        """Test building with sensitive case."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case="sensitive",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-s" in cmd

    def test_build_with_fixed_strings(self):
        """Test building with fixed strings."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=True,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-F" in cmd

    def test_build_with_word(self):
        """Test building with word matching."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=True,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-w" in cmd

    def test_build_with_multiline(self):
        """Test building with multiline support."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=True,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "--multiline" in cmd

    def test_build_with_include_globs(self):
        """Test building with include globs."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=["*.py", "*.js"],
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-g" in cmd
        assert "*.py" in cmd
        assert "*.js" in cmd

    def test_build_with_exclude_globs(self):
        """Test building with exclude globs."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=["*.log", "__pycache__"],
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-g" in cmd
        assert "!*.log" in cmd or "*.log" in cmd

    def test_build_with_context_before(self):
        """Test building with context before."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=3,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-B" in cmd
        assert "3" in cmd

    def test_build_with_context_after(self):
        """Test building with context after."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=3,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-A" in cmd
        assert "3" in cmd

    def test_build_with_encoding(self):
        """Test building with encoding."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding="utf-8",
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "--encoding" in cmd
        assert "utf-8" in cmd

    def test_build_with_max_count(self):
        """Test building with max count."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=100,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-m" in cmd
        assert "100" in cmd

    def test_build_with_max_filesize(self):
        """Test building with max filesize."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize="10M",
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "--max-filesize" in cmd
        assert "10M" in cmd

    def test_build_with_follow_symlinks(self):
        """Test building with follow symlinks."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=True,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-L" in cmd

    def test_build_with_hidden(self):
        """Test building with hidden files."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=True,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-H" in cmd

    def test_build_with_no_ignore(self):
        """Test building with no ignore."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=True,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
        )
        assert "-u" in cmd

    def test_build_count_only_matches(self):
        """Test building with count only matches."""
        cmd = fd_rg_utils.build_rg_command(
            query="test",
            case=None,
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=["/path"],
            files_from=None,
            count_only_matches=True,
        )
        assert "--count-matches" in cmd
        assert "--json" not in cmd  # Count mode doesn't use JSON


class TestParseRgJsonLinesToMatches:
    """Tests for parse_rg_json_lines_to_matches function."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON output."""
        json_line = b'{"type":"match","data":{"path":{"text":"file.py"},"line_number":1,"lines":{"text":"test"},"submatches":[]}}'
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_line)
        assert len(result) == 1
        assert result[0]["file"] == "file.py"
        assert result[0]["line"] == 1
        assert result[0]["text"] == "test"

    def test_parse_multiple_lines(self):
        """Test parsing multiple JSON lines."""
        json_lines = b'{"type":"match","data":{"path":{"text":"file1.py"},"line_number":1,"lines":{"text":"test"},"submatches":[]}}\n{"type":"match","data":{"path":{"text":"file2.py"},"line_number":2,"lines":{"text":"test"},"submatches":[]}}'
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_lines)
        assert len(result) == 2
        assert result[0]["file"] == "file1.py"
        assert result[1]["file"] == "file2.py"

    def test_parse_non_match_event(self):
        """Test that non-match events are skipped."""
        json_line = b'{"type":"begin","data":{}}'
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_line)
        assert len(result) == 0

    def test_parse_invalid_json(self):
        """Test that invalid JSON is skipped."""
        json_line = b"invalid json"
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_line)
        assert len(result) == 0

    def test_parse_empty_lines(self):
        """Test that empty lines are skipped."""
        json_lines = b"\n\n"
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_lines)
        assert len(result) == 0

    def test_parse_with_submatches(self):
        """Test parsing with submatches."""
        json_line = b'{"type":"match","data":{"path":{"text":"file.py"},"submatches":[{"start":0,"end":5}]}}'
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_line)
        assert len(result) == 1
        assert "matches" in result[0]
        assert result[0]["matches"] == [[0, 5]]

    def test_parse_hard_cap(self):
        """Test that results are capped at hard limit."""
        # Create more than hard cap results
        json_lines = b"\n".join(
            [b'{"type":"match","data":{"path":{"text":"file.py"}}}']
            * (fd_rg_utils.MAX_RESULTS_HARD_CAP + 10)
        )

        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_lines)
        assert len(result) == fd_rg_utils.MAX_RESULTS_HARD_CAP


class TestGroupMatchesByFile:
    """Tests for group_matches_by_file function."""

    def test_group_empty_matches(self):
        """Test grouping empty matches."""
        result = fd_rg_utils.group_matches_by_file([])
        assert result["success"] is True
        assert result["count"] == 0
        assert result["files"] == []

    def test_group_single_file(self):
        """Test grouping matches from single file."""
        matches = [
            {"file": "file1.py", "line": 1, "text": "test1"},
            {"file": "file1.py", "line": 2, "text": "test2"},
        ]
        result = fd_rg_utils.group_matches_by_file(matches)
        assert result["count"] == 2
        assert len(result["files"]) == 1
        assert result["files"][0]["file"] == "file1.py"
        assert result["files"][0]["match_count"] == 2

    def test_group_multiple_files(self):
        """Test grouping matches from multiple files."""
        matches = [
            {"file": "file1.py", "line": 1, "text": "test1"},
            {"file": "file2.py", "line": 1, "text": "test2"},
            {"file": "file1.py", "line": 2, "text": "test3"},
        ]
        result = fd_rg_utils.group_matches_by_file(matches)
        assert result["count"] == 3
        assert len(result["files"]) == 2
        assert result["files"][0]["match_count"] == 2
        assert result["files"][1]["match_count"] == 1


class TestOptimizeMatchPaths:
    """Tests for optimize_match_paths function."""

    def test_optimize_empty_matches(self):
        """Test optimizing empty matches."""
        result = fd_rg_utils.optimize_match_paths([])
        assert result == []

    def test_optimize_single_match(self):
        """Test optimizing single match."""
        matches = [{"file": "/path/to/file.py", "line": 1}]
        result = fd_rg_utils.optimize_match_paths(matches)
        assert len(result) == 1
        # Path should be optimized
        assert result[0]["file"] == "/path/to/file.py"

    def test_optimize_with_common_prefix(self):
        """Test optimizing with common prefix."""
        matches = [
            {"file": "/common/path/file1.py", "line": 1},
            {"file": "/common/path/file2.py", "line": 1},
        ]
        result = fd_rg_utils.optimize_match_paths(matches)
        assert len(result) == 2
        # Common prefix should be removed, leaving relative paths
        assert "file1.py" in result[0]["file"] or result[0]["file"] == "file1.py"
        assert "file2.py" in result[1]["file"] or result[1]["file"] == "file2.py"

    def test_optimize_with_long_path(self):
        """Test optimizing with long path."""
        matches = [
            {
                "file": "/very/long/path/that/goes/deep/into/many/directories/to/file.py",
                "line": 1,
            }
        ]
        result = fd_rg_utils.optimize_match_paths(matches)
        assert len(result) == 1
        # Long path should be shortened
        assert "..." in result[0]["file"]


class TestSummarizeSearchResults:
    """Tests for summarize_search_results function."""

    def test_summarize_empty_results(self):
        """Test summarizing empty results."""
        result = fd_rg_utils.summarize_search_results([])
        assert result["total_matches"] == 0
        assert result["total_files"] == 0
        assert result["summary"] == "No matches found"
        assert result["top_files"] == []

    def test_summarize_single_file(self):
        """Test summarizing single file."""
        matches = [
            {"file": "file.py", "line": 1, "text": "test1"},
            {"file": "file.py", "line": 2, "text": "test2"},
        ]
        result = fd_rg_utils.summarize_search_results(matches, max_files=5)
        assert result["total_matches"] == 2
        assert result["total_files"] == 1
        assert result["top_files"][0]["file"] == "file.py"
        assert result["top_files"][0]["match_count"] == 2

    def test_summarize_multiple_files(self):
        """Test summarizing multiple files."""
        matches = [
            {"file": "file1.py", "line": 1, "text": "test"},
            {"file": "file2.py", "line": 1, "text": "test"},
        ]
        result = fd_rg_utils.summarize_search_results(matches, max_files=10)
        assert result["total_matches"] == 2
        assert result["total_files"] == 2
        assert len(result["top_files"]) == 2

    def test_summarize_with_max_files_limit(self):
        """Test summarizing with max files limit."""
        matches = [
            {"file": f"file{i}.py", "line": 1, "text": "test"} for i in range(15)
        ]
        result = fd_rg_utils.summarize_search_results(matches, max_files=5)
        assert result["total_files"] == 15
        assert len(result["top_files"]) == 5

    def test_summarize_truncates_long_lines(self):
        """Test that long lines are truncated."""
        matches = [
            {
                "file": "file.py",
                "line": 1,
                "text": "a" * 100,  # Very long line
            }
        ]
        result = fd_rg_utils.summarize_search_results(matches)
        assert "..." in result["top_files"][0]["sample_lines"][0]


class TestParseRgCountOutput:
    """Tests for parse_rg_count_output function."""

    def test_parse_valid_output(self):
        """Test parsing valid count output."""
        output = b"file1.py:10\nfile2.py:5\n"
        result = fd_rg_utils.parse_rg_count_output(output)
        assert result["file1.py"] == 10
        assert result["file2.py"] == 5
        assert result["__total__"] == 15

    def test_parse_empty_output(self):
        """Test parsing empty output."""
        result = fd_rg_utils.parse_rg_count_output(b"")
        assert result == {"__total__": 0}

    def test_parse_with_whitespace_lines(self):
        """Test that whitespace lines are skipped."""
        output = b"file1.py:10\n  \nfile2.py:5\n"
        result = fd_rg_utils.parse_rg_count_output(output)
        assert result["file1.py"] == 10
        assert result["file2.py"] == 5
        assert result["__total__"] == 15

    def test_parse_invalid_format(self):
        """Test that invalid format lines are skipped."""
        output = b"invalid line\nfile1.py:10\n"
        result = fd_rg_utils.parse_rg_count_output(output)
        assert "file1.py" in result
        assert result["__total__"] == 10


class TestExtractFileListFromCountData:
    """Tests for extract_file_list_from_count_data function."""

    def test_extract_file_list(self):
        """Test extracting file list from count data."""
        count_data = {
            "file1.py": 10,
            "file2.py": 5,
            "__total__": 15,
        }
        result = fd_rg_utils.extract_file_list_from_count_data(count_data)
        assert len(result) == 2
        assert "file1.py" in result
        assert "file2.py" in result
        assert "__total__" not in result


class TestCreateFileSummaryFromCountData:
    """Tests for create_file_summary_from_count_data function."""

    def test_create_summary(self):
        """Test creating file summary from count data."""
        count_data = {
            "file1.py": 10,
            "file2.py": 5,
            "__total__": 15,
        }
        result = fd_rg_utils.create_file_summary_from_count_data(count_data)
        assert result["success"] is True
        assert result["total_matches"] == 15
        assert result["file_count"] == 2
        assert len(result["files"]) == 2
        assert result["derived_from_count"] is True


class TestSplitRootsForParallelProcessing:
    """Tests for split_roots_for_parallel_processing function."""

    def test_split_empty_roots(self):
        """Test splitting empty roots."""
        result = fd_rg_utils.split_roots_for_parallel_processing([], max_chunks=4)
        assert result == []

    def test_split_single_root(self):
        """Test splitting single root."""
        result = fd_rg_utils.split_roots_for_parallel_processing(
            ["/path"], max_chunks=4
        )
        assert len(result) == 1
        assert result[0] == ["/path"]

    def test_split_multiple_roots(self):
        """Test splitting multiple roots."""
        roots = [f"/path{i}" for i in range(10)]
        result = fd_rg_utils.split_roots_for_parallel_processing(roots, max_chunks=4)
        assert len(result) == 4

    def test_split_with_remainder(self):
        """Test splitting with remainder."""
        roots = [f"/path{i}" for i in range(9)]  # 9 roots
        result = fd_rg_utils.split_roots_for_parallel_processing(roots, max_chunks=4)
        assert len(result) == 4
        # chunk_size = 9 // 4 = 2, remainder = 9 % 4 = 1
        # First chunk gets extra item due to remainder, so it has 3 roots
        # Remaining 3 chunks have 2 roots each
        # So chunks are: [3, 2, 2, 2]
        assert len(result[0]) == 3
        assert len(result[1]) == 2
        assert len(result[2]) == 2
        assert len(result[3]) == 2


class TestRunParallelRgSearches:
    """Tests for run_parallel_rg_searches function."""

    @pytest.mark.asyncio
    async def test_run_single_command(self):
        """Test running single command."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"output", b"")
            mock_subprocess.return_value = mock_proc

            commands = [["rg", "test"]]
            results = await fd_rg_utils.run_parallel_rg_searches(
                commands, max_concurrent=2
            )

            assert len(results) == 1
            assert results[0] == (0, b"output", b"")

    @pytest.mark.asyncio
    async def test_run_multiple_commands(self):
        """Test running multiple commands."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"output", b"")
            mock_subprocess.return_value = mock_proc

            commands = [["rg", "test1"], ["rg", "test2"]]
            results = await fd_rg_utils.run_parallel_rg_searches(
                commands, max_concurrent=2
            )

            assert len(results) == 2
            assert results[0] == (0, b"output", b"")
            assert results[1] == (0, b"output", b"")

    @pytest.mark.asyncio
    async def test_run_with_timeout(self):
        """Test running with timeout."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"output", b"")
            mock_subprocess.return_value = mock_proc

            commands = [["rg", "test"]]
            results = await fd_rg_utils.run_parallel_rg_searches(
                commands, timeout_ms=5000, max_concurrent=2
            )

            assert len(results) == 1


class TestMergeRgResults:
    """Tests for merge_rg_results function."""

    def test_merge_successful_results(self):
        """Test merging successful results."""
        results = [
            (0, b"output1", b""),
            (0, b"output2", b""),
        ]
        rc, out, err = fd_rg_utils.merge_rg_results(results, count_only_mode=False)
        assert rc == 0
        assert b"output1" in out
        assert b"output2" in out

    def test_merge_count_only_results(self):
        """Test merging count-only results."""
        results = [
            (0, b"file1.py:10\n", b""),
            (0, b"file2.py:5\n", b""),
        ]
        rc, out, err = fd_rg_utils.merge_rg_results(results, count_only_mode=True)
        assert rc == 0
        assert b"file1.py:10" in out
        assert b"file2.py:5" in out

    def test_merge_with_failure(self):
        """Test merging with a failure."""
        results = [
            (0, b"output1", b""),  # First result has output (rc=0)
            (1, b"", b"error"),  # Second result is error (rc=1)
        ]
        rc, out, err = fd_rg_utils.merge_rg_results(results, count_only_mode=False)
        # When first result has output (rc=0 with stdout), has_matches should be True
        # So return code should be 0, not 1
        assert rc == 0
        assert b"output1" in out


class TestNormalizeMaxFilesize:
    """Tests for normalize_max_filesize function."""

    def test_normalize_valid_size(self):
        """Test normalizing valid size."""
        result = fd_rg_utils.normalize_max_filesize("10M")
        assert result == "10M"

    def test_normalize_none(self):
        """Test normalizing None."""
        result = fd_rg_utils.normalize_max_filesize(None)
        assert result == "10M"  # Default value

    def test_normalize_above_hard_cap(self):
        """Test normalizing size above hard cap."""
        result = fd_rg_utils.normalize_max_filesize("500M")
        assert result == "200M"  # Capped at hard limit

    def test_normalize_invalid_format(self):
        """Test normalizing invalid format."""
        result = fd_rg_utils.normalize_max_filesize("invalid")
        assert result == "10M"  # Default value


class TestConstants:
    """Tests for module constants."""

    def test_max_results_hard_cap(self):
        """Test MAX_RESULTS_HARD_CAP constant."""
        assert fd_rg_utils.MAX_RESULTS_HARD_CAP == 10000

    def test_default_results_limit(self):
        """Test DEFAULT_RESULTS_LIMIT constant."""
        assert fd_rg_utils.DEFAULT_RESULTS_LIMIT == 2000

    def test_default_rg_max_filesize(self):
        """Test DEFAULT_RG_MAX_FILESIZE constant."""
        assert fd_rg_utils.DEFAULT_RG_MAX_FILESIZE == "10M"

    def test_rg_max_filesize_hard_cap_bytes(self):
        """Test RG_MAX_FILESIZE_HARD_CAP_BYTES constant."""
        assert fd_rg_utils.RG_MAX_FILESIZE_HARD_CAP_BYTES == 200 * 1024 * 1024

    def test_default_rg_timeout_ms(self):
        """Test DEFAULT_RG_TIMEOUT_MS constant."""
        assert fd_rg_utils.DEFAULT_RG_TIMEOUT_MS == 4000

    def test_rg_timeout_hard_cap_ms(self):
        """Test RG_TIMEOUT_HARD_CAP_MS constant."""
        assert fd_rg_utils.RG_TIMEOUT_HARD_CAP_MS == 30000
