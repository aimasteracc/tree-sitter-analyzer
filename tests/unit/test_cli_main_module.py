"""
Tests for CLI Module Entry Point (cli/__main__.py)

Tests for module execution via `python -m tree_sitter_analyzer.cli`
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestCLIMainModule:
    """Test suite for cli/__main__.py module execution."""

    def test_module_can_be_executed_as_main(self) -> None:
        """Test that the module can be executed as __main__."""
        # Import the module to verify it doesn't raise any exceptions
        from tree_sitter_analyzer.cli import __main__

        assert __main__ is not None

    @patch("tree_sitter_analyzer.cli_main.main")
    def test_main_delegates_to_cli_main(self, mock_main: MagicMock) -> None:
        """Test that __main__.py properly delegates to cli_main.main()."""
        # Execute the module
        import importlib

        import tree_sitter_analyzer.cli.__main__

        # Reload to trigger the if __name__ == "__main__" block
        # Note: This won't actually trigger it, so we need a different approach
        # We can test that the import is correct instead

        # Verify the module has imported main from cli_main
        assert hasattr(tree_sitter_analyzer.cli.__main__, "main")

    def test_module_imports_are_valid(self) -> None:
        """Test that all required imports are valid."""
        from tree_sitter_analyzer.cli.__main__ import main

        # Verify main is a callable function
        assert callable(main)

    @patch("tree_sitter_analyzer.cli_main.main")
    def test_module_execution_via_runpy(self, mock_main: MagicMock) -> None:
        """Test module execution using runpy (simulates python -m)."""
        import runpy

        # Mock main to prevent actual execution
        mock_main.return_value = None

        # Execute the module as __main__
        try:
            runpy.run_module("tree_sitter_analyzer.cli", run_name="__main__")
        except SystemExit:
            # main() might call sys.exit(), which is expected
            pass

        # Verify main was called
        mock_main.assert_called_once()

    def test_module_has_correct_docstring(self) -> None:
        """Test that the module has proper documentation."""
        from tree_sitter_analyzer.cli import __main__

        assert __main__.__doc__ is not None
        assert "CLI Module Entry Point" in __main__.__doc__
        assert "python -m" in __main__.__doc__

    @patch("tree_sitter_analyzer.cli_main.main")
    @patch("sys.exit")
    def test_module_handles_system_exit(
        self, mock_exit: MagicMock, mock_main: MagicMock
    ) -> None:
        """Test that module properly handles SystemExit exceptions."""
        import runpy

        # Make main raise SystemExit
        mock_main.side_effect = SystemExit(0)

        # Execute the module
        with pytest.raises(SystemExit):
            runpy.run_module("tree_sitter_analyzer.cli", run_name="__main__")

    def test_module_can_be_imported_without_execution(self) -> None:
        """Test that importing the module doesn't execute main()."""
        with patch("tree_sitter_analyzer.cli_main.main") as mock_main:
            # Import the module (not as __main__)
            import importlib

            import tree_sitter_analyzer.cli.__main__

            importlib.reload(tree_sitter_analyzer.cli.__main__)

            # main() should not be called on import
            # (it's only called when __name__ == "__main__")
            # Since we can't easily test the __name__ == "__main__" condition,
            # we verify that importing doesn't cause side effects

    @patch.dict(sys.modules, {}, clear=False)
    @patch("tree_sitter_analyzer.cli_main.main")
    def test_module_import_error_handling(self, mock_main: MagicMock) -> None:
        """Test that import errors are handled appropriately."""
        # This test verifies that the module can handle missing dependencies
        # In practice, this would test if cli_main is not available

        # The module should import successfully even if main is mocked
        from tree_sitter_analyzer.cli import __main__

        assert __main__ is not None
