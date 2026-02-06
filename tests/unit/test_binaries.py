"""Tests for binary detection utilities."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tree_sitter_analyzer_v2.utils.binaries import (
    BinaryNotFoundError,
    get_fd_path,
    get_ripgrep_path,
    check_fd_available,
    check_ripgrep_available,
    get_fd_version,
    get_ripgrep_version,
    get_fd_installation_instructions,
    get_ripgrep_installation_instructions,
    require_fd,
    require_ripgrep,
    get_binaries_status,
    require_all_binaries,
    can_use_fast_search,
)


class TestGetFdPath:
    """Tests for get_fd_path function."""

    def test_fd_found(self) -> None:
        """Test when fd is available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/fd"
            result = get_fd_path()
            assert result == Path("/usr/bin/fd")

    def test_fd_not_found(self) -> None:
        """Test when fd is not available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.shutil.which") as mock_which:
            mock_which.return_value = None
            result = get_fd_path()
            assert result is None


class TestGetRipgrepPath:
    """Tests for get_ripgrep_path function."""

    def test_ripgrep_found(self) -> None:
        """Test when ripgrep is available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/rg"
            result = get_ripgrep_path()
            assert result == Path("/usr/bin/rg")

    def test_ripgrep_not_found(self) -> None:
        """Test when ripgrep is not available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.shutil.which") as mock_which:
            mock_which.return_value = None
            result = get_ripgrep_path()
            assert result is None


class TestCheckFdAvailable:
    """Tests for check_fd_available function."""

    def test_available(self) -> None:
        """Test when fd is available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_get:
            mock_get.return_value = Path("/usr/bin/fd")
            assert check_fd_available() is True

    def test_not_available(self) -> None:
        """Test when fd is not available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_get:
            mock_get.return_value = None
            assert check_fd_available() is False


class TestCheckRipgrepAvailable:
    """Tests for check_ripgrep_available function."""

    def test_available(self) -> None:
        """Test when ripgrep is available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_get:
            mock_get.return_value = Path("/usr/bin/rg")
            assert check_ripgrep_available() is True

    def test_not_available(self) -> None:
        """Test when ripgrep is not available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_get:
            mock_get.return_value = None
            assert check_ripgrep_available() is False


class TestGetFdVersion:
    """Tests for get_fd_version function."""

    def test_version_parsed(self) -> None:
        """Test version parsing."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_path:
            mock_path.return_value = Path("/usr/bin/fd")
            with patch("tree_sitter_analyzer_v2.utils.binaries.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="fd 8.7.0\n", returncode=0)
                result = get_fd_version()
                assert result == "8.7.0"

    def test_fd_not_found(self) -> None:
        """Test when fd is not available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_path:
            mock_path.return_value = None
            result = get_fd_version()
            assert result is None

    def test_version_exception(self) -> None:
        """Test exception handling."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_path:
            mock_path.return_value = Path("/usr/bin/fd")
            with patch("tree_sitter_analyzer_v2.utils.binaries.subprocess.run") as mock_run:
                mock_run.side_effect = Exception("Failed")
                result = get_fd_version()
                assert result is None

    def test_version_single_word_output(self) -> None:
        """Test when output is single word."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_path:
            mock_path.return_value = Path("/usr/bin/fd")
            with patch("tree_sitter_analyzer_v2.utils.binaries.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="8.7.0\n", returncode=0)
                result = get_fd_version()
                # Returns raw version_line when no space
                assert result == "8.7.0"


class TestGetRipgrepVersion:
    """Tests for get_ripgrep_version function."""

    def test_version_parsed(self) -> None:
        """Test version parsing."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_path:
            mock_path.return_value = Path("/usr/bin/rg")
            with patch("tree_sitter_analyzer_v2.utils.binaries.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="ripgrep 13.0.0\n", returncode=0)
                result = get_ripgrep_version()
                assert result == "13.0.0"

    def test_rg_not_found(self) -> None:
        """Test when ripgrep is not available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_path:
            mock_path.return_value = None
            result = get_ripgrep_version()
            assert result is None

    def test_version_exception(self) -> None:
        """Test exception handling."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_path:
            mock_path.return_value = Path("/usr/bin/rg")
            with patch("tree_sitter_analyzer_v2.utils.binaries.subprocess.run") as mock_run:
                mock_run.side_effect = Exception("Failed")
                result = get_ripgrep_version()
                assert result is None

    def test_version_single_word_output(self) -> None:
        """Test when output is single word."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_path:
            mock_path.return_value = Path("/usr/bin/rg")
            with patch("tree_sitter_analyzer_v2.utils.binaries.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="13.0.0\n", returncode=0)
                result = get_ripgrep_version()
                assert result == "13.0.0"


class TestGetFdInstallationInstructions:
    """Tests for get_fd_installation_instructions function."""

    def test_darwin(self) -> None:
        """Test macOS instructions."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.platform.system") as mock_system:
            mock_system.return_value = "Darwin"
            result = get_fd_installation_instructions()
            assert "brew install fd" in result

    def test_linux(self) -> None:
        """Test Linux instructions."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.platform.system") as mock_system:
            mock_system.return_value = "Linux"
            result = get_fd_installation_instructions()
            assert "apt install" in result

    def test_windows(self) -> None:
        """Test Windows instructions."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.platform.system") as mock_system:
            mock_system.return_value = "Windows"
            result = get_fd_installation_instructions()
            assert "scoop install fd" in result

    def test_unknown_os(self) -> None:
        """Test unknown OS instructions."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.platform.system") as mock_system:
            mock_system.return_value = "UnknownOS"
            result = get_fd_installation_instructions()
            assert "github.com" in result


class TestGetRipgrepInstallationInstructions:
    """Tests for get_ripgrep_installation_instructions function."""

    def test_darwin(self) -> None:
        """Test macOS instructions."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.platform.system") as mock_system:
            mock_system.return_value = "Darwin"
            result = get_ripgrep_installation_instructions()
            assert "brew install ripgrep" in result

    def test_linux(self) -> None:
        """Test Linux instructions."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.platform.system") as mock_system:
            mock_system.return_value = "Linux"
            result = get_ripgrep_installation_instructions()
            assert "apt install ripgrep" in result

    def test_windows(self) -> None:
        """Test Windows instructions."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.platform.system") as mock_system:
            mock_system.return_value = "Windows"
            result = get_ripgrep_installation_instructions()
            assert "scoop install ripgrep" in result

    def test_unknown_os(self) -> None:
        """Test unknown OS instructions."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.platform.system") as mock_system:
            mock_system.return_value = "FreeBSD"
            result = get_ripgrep_installation_instructions()
            assert "github.com" in result


class TestRequireFd:
    """Tests for require_fd function."""

    def test_success(self) -> None:
        """Test when fd is available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_path:
            mock_path.return_value = Path("/usr/bin/fd")
            result = require_fd()
            assert result == Path("/usr/bin/fd")

    def test_raises_error(self) -> None:
        """Test when fd is not available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_path:
            mock_path.return_value = None
            with pytest.raises(BinaryNotFoundError) as exc_info:
                require_fd()
            assert "fd binary not found" in str(exc_info.value)


class TestRequireRipgrep:
    """Tests for require_ripgrep function."""

    def test_success(self) -> None:
        """Test when ripgrep is available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_path:
            mock_path.return_value = Path("/usr/bin/rg")
            result = require_ripgrep()
            assert result == Path("/usr/bin/rg")

    def test_raises_error(self) -> None:
        """Test when ripgrep is not available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_path:
            mock_path.return_value = None
            with pytest.raises(BinaryNotFoundError) as exc_info:
                require_ripgrep()
            assert "ripgrep" in str(exc_info.value).lower()


class TestGetBinariesStatus:
    """Tests for get_binaries_status function."""

    def test_both_available(self) -> None:
        """Test when both binaries are available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_fd:
            with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_rg:
                with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_version") as mock_fd_ver:
                    with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_version") as mock_rg_ver:
                        mock_fd.return_value = Path("/usr/bin/fd")
                        mock_rg.return_value = Path("/usr/bin/rg")
                        mock_fd_ver.return_value = "8.7.0"
                        mock_rg_ver.return_value = "13.0.0"

                        result = get_binaries_status()
                        
                        assert result["fd"]["available"] is True
                        # Check path contains fd (platform-independent)
                        assert "fd" in result["fd"]["path"]
                        assert result["fd"]["version"] == "8.7.0"
                        assert result["ripgrep"]["available"] is True
                        # Check path contains rg (platform-independent)
                        assert "rg" in result["ripgrep"]["path"]
                        assert result["ripgrep"]["version"] == "13.0.0"

    def test_none_available(self) -> None:
        """Test when no binaries are available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_fd:
            with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_rg:
                mock_fd.return_value = None
                mock_rg.return_value = None

                result = get_binaries_status()
                
                assert result["fd"]["available"] is False
                assert "path" not in result["fd"]
                assert result["ripgrep"]["available"] is False
                assert "path" not in result["ripgrep"]

    def test_version_not_available(self) -> None:
        """Test when version is not available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_path") as mock_fd:
            with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_path") as mock_rg:
                with patch("tree_sitter_analyzer_v2.utils.binaries.get_fd_version") as mock_fd_ver:
                    with patch("tree_sitter_analyzer_v2.utils.binaries.get_ripgrep_version") as mock_rg_ver:
                        mock_fd.return_value = Path("/usr/bin/fd")
                        mock_rg.return_value = Path("/usr/bin/rg")
                        mock_fd_ver.return_value = None
                        mock_rg_ver.return_value = None

                        result = get_binaries_status()
                        
                        assert result["fd"]["available"] is True
                        assert "version" not in result["fd"]
                        assert result["ripgrep"]["available"] is True
                        assert "version" not in result["ripgrep"]


class TestRequireAllBinaries:
    """Tests for require_all_binaries function."""

    def test_success(self) -> None:
        """Test when all binaries are available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_binaries_status") as mock_status:
            mock_status.return_value = {
                "fd": {"available": True, "path": "/usr/bin/fd", "version": "8.7.0"},
                "ripgrep": {"available": True, "path": "/usr/bin/rg", "version": "13.0.0"},
            }
            result = require_all_binaries()
            assert result["fd"]["available"] is True
            assert result["ripgrep"]["available"] is True

    def test_fd_missing(self) -> None:
        """Test when fd is missing."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_binaries_status") as mock_status:
            mock_status.return_value = {
                "fd": {"available": False},
                "ripgrep": {"available": True, "path": "/usr/bin/rg"},
            }
            with pytest.raises(BinaryNotFoundError) as exc_info:
                require_all_binaries()
            assert "fd" in str(exc_info.value)

    def test_ripgrep_missing(self) -> None:
        """Test when ripgrep is missing."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_binaries_status") as mock_status:
            mock_status.return_value = {
                "fd": {"available": True, "path": "/usr/bin/fd"},
                "ripgrep": {"available": False},
            }
            with pytest.raises(BinaryNotFoundError) as exc_info:
                require_all_binaries()
            assert "ripgrep" in str(exc_info.value)

    def test_both_missing(self) -> None:
        """Test when both binaries are missing."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.get_binaries_status") as mock_status:
            mock_status.return_value = {
                "fd": {"available": False},
                "ripgrep": {"available": False},
            }
            with pytest.raises(BinaryNotFoundError) as exc_info:
                require_all_binaries()
            error_msg = str(exc_info.value)
            assert "fd" in error_msg
            assert "ripgrep" in error_msg


class TestCanUseFastSearch:
    """Tests for can_use_fast_search function."""

    def test_both_available(self) -> None:
        """Test when both binaries are available."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.check_fd_available") as mock_fd:
            with patch("tree_sitter_analyzer_v2.utils.binaries.check_ripgrep_available") as mock_rg:
                mock_fd.return_value = True
                mock_rg.return_value = True
                assert can_use_fast_search() is True

    def test_fd_missing(self) -> None:
        """Test when fd is missing."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.check_fd_available") as mock_fd:
            with patch("tree_sitter_analyzer_v2.utils.binaries.check_ripgrep_available") as mock_rg:
                mock_fd.return_value = False
                mock_rg.return_value = True
                assert can_use_fast_search() is False

    def test_ripgrep_missing(self) -> None:
        """Test when ripgrep is missing."""
        with patch("tree_sitter_analyzer_v2.utils.binaries.check_fd_available") as mock_fd:
            with patch("tree_sitter_analyzer_v2.utils.binaries.check_ripgrep_available") as mock_rg:
                mock_fd.return_value = True
                mock_rg.return_value = False
                assert can_use_fast_search() is False


class TestBinaryNotFoundError:
    """Tests for BinaryNotFoundError exception."""

    def test_exception_message(self) -> None:
        """Test exception message."""
        exc = BinaryNotFoundError("Binary not found")
        assert str(exc) == "Binary not found"
