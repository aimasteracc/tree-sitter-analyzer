"""Regression tests for _shell_safe_path — issue #875.

shlex.quote() wraps paths in single quotes which fail in Windows CMD.
Double quotes work on Windows CMD, PowerShell, and Unix shells.
"""

from tree_sitter_analyzer.cli.agent_workflow import _shell_safe_path


class TestShellSafePathWindowsCompat:
    def test_none_returns_empty_string(self) -> None:
        assert _shell_safe_path(None) == ""

    def test_simple_path_no_quoting_needed(self) -> None:
        # Safe chars only — returned as-is (no quoting overhead)
        result = _shell_safe_path("src/main.py")
        assert result == "src/main.py"

    def test_path_with_spaces_uses_double_quotes(self) -> None:
        result = _shell_safe_path("src/my file.py")
        # Double-quoted — works on Windows CMD and Unix
        assert result == '"src/my file.py"'

    def test_path_with_spaces_not_single_quoted(self) -> None:
        # Single quotes fail in Windows CMD — must never appear
        result = _shell_safe_path("src/my file.py")
        assert not result.startswith("'"), (
            "must not use single quotes (fails Windows CMD)"
        )

    def test_windows_backslash_path_no_quoting_needed(self) -> None:
        # Pure backslash+alphanum — safe, no quoting needed
        result = _shell_safe_path("src\\main.py")
        assert result == "src\\main.py"

    def test_windows_path_with_spaces_double_quoted(self) -> None:
        result = _shell_safe_path("C:\\My Projects\\main.py")
        assert result == '"C:\\My Projects\\main.py"'
        assert not result.startswith("'")

    def test_empty_path_returns_empty(self) -> None:
        assert _shell_safe_path("") == ""
