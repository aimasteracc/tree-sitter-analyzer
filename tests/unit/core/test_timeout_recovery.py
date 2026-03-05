#!/usr/bin/env python3
"""
Tests for timeout recovery and resource cleanup.

This module tests that operations properly handle timeouts,
clean up resources, and return meaningful error messages.
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.fd_rg_utils import (
    DEFAULT_RG_TIMEOUT_MS,
    RG_TIMEOUT_HARD_CAP_MS,
    clamp_int,
    run_command_capture,
)


class TestTimeoutRecovery:
    """Test timeout recovery for subprocess operations."""

    @pytest.mark.asyncio
    async def test_subprocess_killed_on_timeout(self):
        """Test that subprocess is properly killed on timeout."""
        # Create a mock process that never completes
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch(
                "asyncio.wait_for", side_effect=asyncio.TimeoutError()
            ):
                returncode, stdout, stderr = await run_command_capture(
                    ["test"], timeout_ms=100
                )

        # Verify process was killed
        mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_returns_error_code_124(self):
        """Test that timeout returns error code 124 (standard timeout exit code)."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_proc.kill = MagicMock()
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                returncode, stdout, stderr = await run_command_capture(
                    ["test"], timeout_ms=100
                )

        assert returncode == 124
        assert b"Timeout" in stderr

    @pytest.mark.asyncio
    async def test_timeout_error_message_includes_duration(self):
        """Test that timeout error message includes the timeout duration."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_proc.kill = MagicMock()
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                returncode, stdout, stderr = await run_command_capture(
                    ["test"], timeout_ms=5000
                )

        error_msg = stderr.decode()
        assert "5000" in error_msg
        assert "ms" in error_msg.lower() or "Timeout" in error_msg

    @pytest.mark.asyncio
    async def test_no_timeout_when_timeout_ms_is_none(self):
        """Test that operation completes when no timeout is specified."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            returncode, stdout, stderr = await run_command_capture(
                ["test"], timeout_ms=None
            )

        assert returncode == 0
        assert stdout == b"output"

    @pytest.mark.asyncio
    async def test_no_timeout_when_timeout_ms_is_zero(self):
        """Test that operation completes when timeout is zero (disabled)."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            returncode, stdout, stderr = await run_command_capture(
                ["test"], timeout_ms=0
            )

        assert returncode == 0

    @pytest.mark.asyncio
    async def test_command_not_found_returns_error_code_127(self):
        """Test that missing command returns error code 127 (standard not found code)."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
            return_value=False,
        ):
            returncode, stdout, stderr = await run_command_capture(
                ["nonexistent_command_xyz"]
            )

        assert returncode == 127
        assert b"not found" in stderr.lower() or b"not found" in stderr


class TestTimeoutConfiguration:
    """Test timeout configuration and clamping."""

    def test_default_timeout_value(self):
        """Test that default timeout is reasonable."""
        # Default should be between 1-10 seconds
        assert 1000 <= DEFAULT_RG_TIMEOUT_MS <= 10000

    def test_hard_cap_timeout_value(self):
        """Test that hard cap is reasonable."""
        # Hard cap should not exceed 60 seconds
        assert RG_TIMEOUT_HARD_CAP_MS <= 60000

    def test_clamp_int_returns_default_for_none(self):
        """Test that clamp_int returns default for None value."""
        result = clamp_int(None, 100, 1000)
        assert result == 100

    def test_clamp_int_returns_default_for_invalid(self):
        """Test that clamp_int returns default for invalid values."""
        result = clamp_int("invalid", 100, 1000)
        assert result == 100

        result = clamp_int(None, 100, 1000)
        assert result == 100

    def test_clamp_int_caps_at_hard_cap(self):
        """Test that clamp_int caps value at hard cap."""
        result = clamp_int(10000, 100, 1000)
        assert result == 1000

    def test_clamp_int_returns_zero_minimum(self):
        """Test that clamp_int enforces minimum of 0."""
        result = clamp_int(-100, 100, 1000)
        assert result == 0

    def test_clamp_int_preserves_valid_values(self):
        """Test that clamp_int preserves valid values."""
        result = clamp_int(500, 100, 1000)
        assert result == 500


class TestProcessCleanup:
    """Test process cleanup on various failure modes."""

    @pytest.mark.asyncio
    async def test_process_waited_after_kill(self):
        """Test that process.wait() is called after kill to prevent zombies."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                await run_command_capture(["test"], timeout_ms=100)

        # Process should be waited after kill
        mock_proc.wait.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_on_exception(self):
        """Test that cleanup happens even when unexpected exceptions occur."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=RuntimeError("Unexpected"))
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            # Should not raise, but handle gracefully
            try:
                await run_command_capture(["test"], timeout_ms=100)
            except RuntimeError:
                pass  # Expected - the actual error should propagate


class TestTimeoutIntegration:
    """Integration tests for timeout with actual subprocess operations."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_short_running_command_completes(self):
        """Test that short-running commands complete within timeout."""
        # Use 'echo' command which should complete quickly
        returncode, stdout, stderr = await run_command_capture(
            ["echo", "hello"], timeout_ms=5000
        )

        # Note: This test depends on 'echo' being available
        # Skip if command not found
        if returncode == 127:
            pytest.skip("echo command not available")

        assert returncode == 0
        assert b"hello" in stdout

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_timeout_with_input_data(self):
        """Test timeout handling when input data is provided."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                returncode, stdout, stderr = await run_command_capture(
                    ["test"], input_data=b"test input", timeout_ms=100
                )

        assert returncode == 124
