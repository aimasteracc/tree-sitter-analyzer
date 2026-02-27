"""Tests for platform_compat.detector module."""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.platform_compat.detector import (
    PlatformDetector,
    PlatformInfo,
)


class TestPlatformInfo:
    """Tests for the PlatformInfo dataclass."""

    @pytest.mark.unit
    def test_create_platform_info(self):
        """Test creating a PlatformInfo."""
        info = PlatformInfo(
            os_name="linux",
            os_version="5.15.0",
            python_version="3.12",
            platform_key="linux-3.12",
        )
        assert info.os_name == "linux"
        assert info.os_version == "5.15.0"
        assert info.python_version == "3.12"
        assert info.platform_key == "linux-3.12"


class TestPlatformDetector:
    """Tests for the PlatformDetector class."""

    @pytest.mark.unit
    def test_detect_returns_platform_info(self):
        """Test that detect() returns a PlatformInfo object."""
        result = PlatformDetector.detect()
        assert isinstance(result, PlatformInfo)
        assert result.os_name is not None
        assert result.python_version is not None
        assert result.platform_key is not None

    @pytest.mark.unit
    @patch("tree_sitter_analyzer.platform_compat.detector.platform")
    @patch("tree_sitter_analyzer.platform_compat.detector.sys")
    def test_detect_linux(self, mock_sys, mock_platform):
        """Test detect() on Linux platform."""
        mock_platform.system.return_value = "Linux"
        mock_platform.release.return_value = "5.15.0-generic"
        mock_sys.version_info.major = 3
        mock_sys.version_info.minor = 12

        result = PlatformDetector.detect()
        assert result.os_name == "linux"
        assert result.python_version == "3.12"
        assert result.platform_key == "linux-3.12"

    @pytest.mark.unit
    @patch("tree_sitter_analyzer.platform_compat.detector.platform")
    @patch("tree_sitter_analyzer.platform_compat.detector.sys")
    def test_detect_darwin_normalized_to_macos(self, mock_sys, mock_platform):
        """Test that Darwin is normalized to macos."""
        mock_platform.system.return_value = "Darwin"
        mock_platform.release.return_value = "22.1.0"
        mock_sys.version_info.major = 3
        mock_sys.version_info.minor = 11

        result = PlatformDetector.detect()
        assert result.os_name == "macos"
        assert result.platform_key == "macos-3.11"

    @pytest.mark.unit
    @patch("tree_sitter_analyzer.platform_compat.detector.platform")
    @patch("tree_sitter_analyzer.platform_compat.detector.sys")
    def test_detect_windows(self, mock_sys, mock_platform):
        """Test detect() on Windows platform."""
        mock_platform.system.return_value = "Windows"
        mock_platform.release.return_value = "10"
        mock_sys.version_info.major = 3
        mock_sys.version_info.minor = 13

        result = PlatformDetector.detect()
        assert result.os_name == "windows"
        assert result.python_version == "3.13"
        assert result.platform_key == "windows-3.13"

    @pytest.mark.unit
    def test_get_profile_path_with_platform_info(self, tmp_path):
        """Test get_profile_path with explicit platform info."""
        info = PlatformInfo(
            os_name="linux",
            os_version="5.15.0",
            python_version="3.12",
            platform_key="linux-3.12",
        )
        result = PlatformDetector.get_profile_path(tmp_path, info)
        expected = tmp_path / "linux" / "3.12" / "profile.json"
        assert result == expected

    @pytest.mark.unit
    def test_get_profile_path_without_platform_info(self, tmp_path):
        """Test get_profile_path auto-detects platform when info is None."""
        result = PlatformDetector.get_profile_path(tmp_path)
        # Should have 3 parts: base / os_name / python_version / profile.json
        assert result.name == "profile.json"
        assert result.parent.parent.parent == tmp_path

    @pytest.mark.unit
    def test_get_profile_path_macos(self, tmp_path):
        """Test get_profile_path produces correct path for macOS."""
        info = PlatformInfo(
            os_name="macos",
            os_version="22.1.0",
            python_version="3.11",
            platform_key="macos-3.11",
        )
        result = PlatformDetector.get_profile_path(tmp_path, info)
        expected = tmp_path / "macos" / "3.11" / "profile.json"
        assert result == expected

    @pytest.mark.unit
    def test_detect_platform_key_format(self):
        """Test that platform_key has the expected format."""
        result = PlatformDetector.detect()
        parts = result.platform_key.split("-")
        assert len(parts) == 2
        assert parts[0] == result.os_name
        assert parts[1] == result.python_version
