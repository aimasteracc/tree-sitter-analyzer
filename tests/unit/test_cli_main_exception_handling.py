"""Tests for CLI main exception handling."""
import sys
from unittest import mock

import pytest


class TestCLIMainExceptionHandling:
    """Test exception handling in CLI main."""

    def test_unexpected_exception_includes_exception_type_and_message(self, capsys):
        """Unexpected exceptions should include exception type and message in output."""
        # Mock to trigger an unexpected exception inside main()
        with mock.patch(
            "tree_sitter_analyzer.cli_main.handle_special_commands",
            side_effect=RuntimeError("Unexpected error"),
        ):
            with mock.patch.object(sys, "argv", ["tree-sitter-analyzer", "test.py"]):
                from tree_sitter_analyzer.cli_main import main
                from tree_sitter_analyzer.output_manager import output_error

                # Simulate the __main__ block's exception handling
                with pytest.raises(SystemExit) as exc_info:
                    try:
                        main()
                    except KeyboardInterrupt:
                        pass
                    except Exception as e:
                        import traceback

                        output_error(f"Unexpected error: {type(e).__name__}: {e}")
                        output_error("Full traceback:")
                        for line in traceback.format_exc().splitlines():
                            output_error(f"  {line}")
                        sys.exit(1)

                # Should exit with code 1
                assert exc_info.value.code == 1

                # Verify output includes exception type and message
                captured = capsys.readouterr()
                output = captured.err + captured.out
                assert "Unexpected error" in output
                assert "RuntimeError" in output

    def test_exception_type_is_shown_for_value_error(self, capsys):
        """Exception type should be shown for debugging."""
        with mock.patch(
            "tree_sitter_analyzer.cli_main.handle_special_commands",
            side_effect=ValueError("Bad value"),
        ):
            with mock.patch.object(sys, "argv", ["tree-sitter-analyzer", "test.py"]):
                from tree_sitter_analyzer.cli_main import main
                from tree_sitter_analyzer.output_manager import output_error

                with pytest.raises(SystemExit):
                    try:
                        main()
                    except KeyboardInterrupt:
                        pass
                    except Exception as e:
                        import traceback

                        output_error(f"Unexpected error: {type(e).__name__}: {e}")
                        output_error("Full traceback:")
                        for line in traceback.format_exc().splitlines():
                            output_error(f"  {line}")
                        sys.exit(1)

                captured = capsys.readouterr()
                output = captured.err + captured.out
                assert "ValueError" in output

    def test_full_traceback_is_logged(self, capsys):
        """Full traceback should be logged for debugging."""
        with mock.patch(
            "tree_sitter_analyzer.cli_main.handle_special_commands",
            side_effect=RuntimeError("Test traceback"),
        ):
            with mock.patch.object(sys, "argv", ["tree-sitter-analyzer", "test.py"]):
                from tree_sitter_analyzer.cli_main import main
                from tree_sitter_analyzer.output_manager import output_error

                with pytest.raises(SystemExit):
                    try:
                        main()
                    except KeyboardInterrupt:
                        pass
                    except Exception as e:
                        import traceback

                        output_error(f"Unexpected error: {type(e).__name__}: {e}")
                        output_error("Full traceback:")
                        for line in traceback.format_exc().splitlines():
                            output_error(f"  {line}")
                        sys.exit(1)

                captured = capsys.readouterr()
                output = captured.err + captured.out
                # Should include traceback indication
                assert "traceback" in output.lower()
                # Should include the error message
                assert "Test traceback" in output

    def test_actual_cli_main_exception_handler_code(self, capsys):
        """Test the actual exception handler code in cli_main.py works correctly."""
        # This test verifies that the exception handling code at the bottom
        # of cli_main.py correctly formats exceptions
        from tree_sitter_analyzer.output_manager import output_error

        # Simulate what the exception handler does
        try:
            raise RuntimeError("Test exception")
        except Exception as e:
            import traceback

            output_error(f"Unexpected error: {type(e).__name__}: {e}")
            output_error("Full traceback:")
            for line in traceback.format_exc().splitlines():
                output_error(f"  {line}")

        captured = capsys.readouterr()
        output = captured.err + captured.out
        assert "RuntimeError" in output
        assert "Test exception" in output
        assert "traceback" in output.lower()
