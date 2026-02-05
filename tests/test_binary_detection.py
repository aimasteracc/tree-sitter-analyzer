"""
Test fd and ripgrep binary detection.

Following TDD: Write tests FIRST for binary detection.
This is T0.4: fd + ripgrep Detection
"""

from pathlib import Path
from unittest.mock import patch

import pytest


class TestBinaryDetection:
    """Test that fd and ripgrep binaries can be detected."""

    def test_binary_detector_module_exists(self):
        """Test that binary detector module exists."""
        from tree_sitter_analyzer_v2.utils import binaries

        assert binaries is not None

    def test_check_fd_binary_exists(self):
        """Test that we can check if fd binary exists."""
        from tree_sitter_analyzer_v2.utils.binaries import check_fd_available

        # Should return True or False, not raise
        result = check_fd_available()
        assert isinstance(result, bool)

    def test_check_ripgrep_binary_exists(self):
        """Test that we can check if ripgrep binary exists."""
        from tree_sitter_analyzer_v2.utils.binaries import check_ripgrep_available

        result = check_ripgrep_available()
        assert isinstance(result, bool)

    def test_get_fd_path(self):
        """Test getting fd binary path."""
        from tree_sitter_analyzer_v2.utils.binaries import get_fd_path

        # Should return path or None
        result = get_fd_path()
        if result is not None:
            assert isinstance(result, (str, Path))

    def test_get_ripgrep_path(self):
        """Test getting ripgrep binary path."""
        from tree_sitter_analyzer_v2.utils.binaries import get_ripgrep_path

        result = get_ripgrep_path()
        if result is not None:
            assert isinstance(result, (str, Path))


class TestBinaryValidation:
    """Test binary validation with actual binaries."""

    def test_fd_version_check(self):
        """Test that we can check fd version."""
        from tree_sitter_analyzer_v2.utils.binaries import (
            check_fd_available,
            get_fd_version,
        )

        if not check_fd_available():
            pytest.skip("fd not installed")

        version = get_fd_version()
        assert version is not None
        assert isinstance(version, str)
        # Version should look like "8.7.0" or similar
        assert len(version) > 0

    def test_ripgrep_version_check(self):
        """Test that we can check ripgrep version."""
        from tree_sitter_analyzer_v2.utils.binaries import (
            check_ripgrep_available,
            get_ripgrep_version,
        )

        if not check_ripgrep_available():
            pytest.skip("ripgrep not installed")

        version = get_ripgrep_version()
        assert version is not None
        assert isinstance(version, str)
        assert len(version) > 0


class TestBinaryMissing:
    """Test behavior when binaries are missing."""

    @patch("shutil.which")
    def test_fd_not_found_raises_clear_error(self, mock_which):
        """Test that missing fd raises clear error with installation instructions."""
        from tree_sitter_analyzer_v2.utils.binaries import (
            BinaryNotFoundError,
            require_fd,
        )

        # Mock fd not being found
        mock_which.return_value = None

        with pytest.raises(BinaryNotFoundError) as exc_info:
            require_fd()

        error_message = str(exc_info.value)
        assert "fd" in error_message.lower()
        # Should include installation instructions
        assert "install" in error_message.lower() or "brew" in error_message.lower()

    @patch("shutil.which")
    def test_ripgrep_not_found_raises_clear_error(self, mock_which):
        """Test that missing ripgrep raises clear error."""
        from tree_sitter_analyzer_v2.utils.binaries import (
            BinaryNotFoundError,
            require_ripgrep,
        )

        mock_which.return_value = None

        with pytest.raises(BinaryNotFoundError) as exc_info:
            require_ripgrep()

        error_message = str(exc_info.value)
        assert "ripgrep" in error_message.lower() or "rg" in error_message.lower()
        assert "install" in error_message.lower()


class TestBinaryInfo:
    """Test binary information functions."""

    def test_get_installation_instructions(self):
        """Test that we provide installation instructions."""
        from tree_sitter_analyzer_v2.utils.binaries import (
            get_fd_installation_instructions,
            get_ripgrep_installation_instructions,
        )

        fd_instructions = get_fd_installation_instructions()
        assert isinstance(fd_instructions, str)
        assert len(fd_instructions) > 0
        # Should mention common package managers
        assert any(
            pm in fd_instructions.lower() for pm in ["brew", "apt", "chocolatey", "scoop", "cargo"]
        )

        rg_instructions = get_ripgrep_installation_instructions()
        assert isinstance(rg_instructions, str)
        assert len(rg_instructions) > 0

    def test_check_all_binaries_status(self):
        """Test getting status of all required binaries."""
        from tree_sitter_analyzer_v2.utils.binaries import get_binaries_status

        status = get_binaries_status()

        assert isinstance(status, dict)
        assert "fd" in status
        assert "ripgrep" in status

        # Each binary status should have 'available' and 'path' keys
        for binary, info in status.items():
            assert "available" in info
            assert isinstance(info["available"], bool)
            if info["available"]:
                assert "path" in info
                assert "version" in info


class TestBinaryRequirements:
    """Test binary requirement checking."""

    def test_require_all_binaries(self):
        """Test requiring all binaries at once."""
        from tree_sitter_analyzer_v2.utils.binaries import require_all_binaries

        # This should either succeed or raise BinaryNotFoundError with details
        try:
            result = require_all_binaries()
            # If successful, should return status dict
            assert isinstance(result, dict)
            assert result["fd"]["available"]
            assert result["ripgrep"]["available"]
        except Exception as e:
            # If it raises, should be BinaryNotFoundError with helpful message
            assert "BinaryNotFoundError" in type(e).__name__
            assert "install" in str(e).lower()

    def test_graceful_fallback_mode(self):
        """Test that we can detect if binaries are available for graceful fallback."""
        from tree_sitter_analyzer_v2.utils.binaries import can_use_fast_search

        # Should return bool indicating if fast search (fd/rg) is available
        result = can_use_fast_search()
        assert isinstance(result, bool)
