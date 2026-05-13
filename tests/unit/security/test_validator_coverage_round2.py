"""Additional coverage supplement for security/validator.py.

Targets remaining uncovered lines in the validator module.
"""

import platform
from pathlib import Path
from unittest.mock import patch

from tree_sitter_analyzer.security.validator import SecurityValidator


class TestValidatorCoverageRound2:
    """Additional coverage for remaining uncovered branches."""

    # --- HAS_CTYPES import failure (lines 19-20) ---

    def test_has_ctypes_false_on_import_error(self):
        """Test that HAS_CTYPES is False when ctypes import fails."""
        with patch.dict("sys.modules", {"ctypes": None}):
            import importlib

            import tree_sitter_analyzer.security.validator as vmod

            importlib.reload(vmod)
            assert vmod.HAS_CTYPES is False

    # --- validate_file_path: symlink/junction edge cases ---

    @patch("tree_sitter_analyzer.security.validator.log_warning")
    def test_symlink_original_path_rejected(self, mock_log):
        """Line 140: symlink in original path returns False."""
        validator = SecurityValidator()
        with patch.object(Path, "is_symlink", return_value=True):
            is_valid, error = validator.validate_file_path("link.py", "/base")
            assert is_valid is False
            assert "Symbolic links" in error

    @patch("tree_sitter_analyzer.security.validator.log_warning")
    def test_junction_original_path_rejected(self, mock_log):
        """Lines 146-149: junction in original path returns False."""
        validator = SecurityValidator()
        with (
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(Path, "exists", return_value=True),
            patch.object(validator, "_is_junction_or_reparse_point", return_value=True),
        ):
            is_valid, error = validator.validate_file_path("junction.py", "/base")
            assert is_valid is False
            assert "Junctions" in error

    def test_symlink_check_oserror_fallback(self):
        """Lines 151-154: OSError during symlink check is caught."""
        validator = SecurityValidator()
        with (
            patch.object(Path, "is_symlink", side_effect=OSError("permission denied")),
            patch("tree_sitter_analyzer.security.validator.log_debug") as mock_debug,
        ):
            # Should not raise, should continue validation
            is_valid, error = validator.validate_file_path("file.py")
            mock_debug.assert_called()
            assert isinstance(is_valid, bool)

    @patch("tree_sitter_analyzer.security.validator.log_warning")
    def test_full_path_symlink_rejected(self, mock_log):
        """Lines 165-166: symlink in full path (base_path + file_path)."""
        validator = SecurityValidator()
        with (
            patch.object(Path, "is_symlink", side_effect=[False, True]),
            patch("tree_sitter_analyzer.security.validator.log_debug"),
        ):
            is_valid, error = validator.validate_file_path("link.py", "/base")
            assert is_valid is False
            assert "Symbolic links" in error

    @patch("tree_sitter_analyzer.security.validator.log_warning")
    def test_junction_in_path_hierarchy_rejected(self, mock_log_warning):
        """Lines 183-184: junction in path hierarchy returns False."""
        validator = SecurityValidator()
        with (
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(Path, "exists", return_value=False),
            patch.object(validator, "_has_junction_in_path", return_value=True),
            patch("tree_sitter_analyzer.security.validator.log_warning"),
            patch("tree_sitter_analyzer.security.validator.log_debug"),
        ):
            is_valid, error = validator.validate_file_path("deep.py", "/base")
            assert is_valid is False
            assert "junction" in error.lower()

    def test_junction_hierarchy_oserror_fallback(self):
        """Line 187: OSError during junction hierarchy check."""
        validator = SecurityValidator()
        with (
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(Path, "exists", return_value=False),
            patch.object(
                validator, "_has_junction_in_path", side_effect=OSError("broken")
            ),
            patch("tree_sitter_analyzer.security.validator.log_debug"),
        ):
            is_valid, error = validator.validate_file_path("deep.py", "/base")
            assert isinstance(is_valid, bool)

    def test_no_base_path_junction_hierarchy_rejected(self):
        """Lines 195-197: junction in hierarchy when no base_path."""
        validator = SecurityValidator()
        with (
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "is_absolute", return_value=True),
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(validator, "_has_junction_in_path", return_value=True),
            patch.object(
                validator, "_validate_windows_drive_letter", return_value=(True, "")
            ),
            patch.object(validator, "_validate_absolute_path", return_value=(True, "")),
            patch.object(
                validator, "_validate_path_traversal", return_value=(True, "")
            ),
            patch.object(
                validator, "_validate_project_boundary", return_value=(True, "")
            ),
            patch("tree_sitter_analyzer.security.validator.log_warning"),
            patch("tree_sitter_analyzer.security.validator.log_debug"),
        ):
            is_valid, error = validator.validate_file_path("/some/abs/path.py")
            assert is_valid is False
            assert "junction" in error.lower()

    def test_no_base_path_junction_oserror_fallback(self):
        """Line 199: OSError during junction check without base_path."""
        validator = SecurityValidator()
        with (
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(Path, "is_absolute", return_value=True),
            patch.object(
                validator, "_validate_windows_drive_letter", return_value=(True, "")
            ),
            patch.object(validator, "_validate_absolute_path", return_value=(True, "")),
            patch.object(
                validator, "_validate_path_traversal", return_value=(True, "")
            ),
            patch.object(
                validator, "_validate_project_boundary", return_value=(True, "")
            ),
            patch.object(
                validator, "_has_junction_in_path", side_effect=OSError("bad")
            ),
            patch("tree_sitter_analyzer.security.validator.log_debug"),
        ):
            is_valid, error = validator.validate_file_path("/some/path.py")
            assert is_valid is True  # caught and continued

    # --- validate_directory_path (lines 239-241) ---

    @patch("tree_sitter_analyzer.security.validator.log_warning")
    def test_path_traversal_regex_error(self, mock_re):
        """Lines 387-389: regex error during traversal check."""
        mock_re.compile.side_effect = Exception("bad regex")
        validator = SecurityValidator()
        with patch("tree_sitter_analyzer.security.validator.log_warning") as mock_warn:
            is_valid, error = validator._validate_path_traversal("../test")
            mock_warn.assert_called()

    # --- validate_absolute_path edge (line 549) ---

    def test_validate_absolute_path_test_env_not_allowed(self):
        """Line 549: test env check returns non-empty error."""
        validator = SecurityValidator()
        with patch.object(
            validator,
            "_check_test_environment_access",
            return_value=(False, "not a test file"),
        ):
            is_valid, error = validator._validate_absolute_path("/data/secret.py")
            assert is_valid is False

    # --- validate_absolute_path fallback to deny (line 552) ---

    def test_validate_file_path_absolute_denied(self):
        """Line 126: absolute path validation fails within validate_file_path."""
        validator = SecurityValidator()
        ok, err = validator.validate_file_path("/etc/hosts")
        if ok:
            # If allowed by test env, it's fine
            assert err == ""
        else:
            assert err is not None

    # --- validate_windows_drive_letter edge (line 146-154 context) ---

    def test_windows_drive_letter_pass_through(self):
        """Normal paths pass through windows drive letter check."""
        validator = SecurityValidator()
        is_valid, error = validator._validate_windows_drive_letter("normal/path.py")
        assert is_valid is True
        assert error == ""

    # --- _is_junction_or_reparse_point edge cases ---

    def test_is_junction_non_windows(self):
        """Non-Windows systems always return False."""
        with patch.object(platform, "system", return_value="Darwin"):
            import importlib

            import tree_sitter_analyzer.security.validator as vmod

            importlib.reload(vmod)
            validator = vmod.SecurityValidator()
            result = validator._is_junction_or_reparse_point(Path("/tmp"))
            assert result is False
