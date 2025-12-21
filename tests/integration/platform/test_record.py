"""Tests for platform_compat/record.py CLI tool."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestRecordCLI:
    """Test the record CLI tool functions."""

    def test_main_success(self, tmp_path):
        """Test successful profile recording."""
        with patch("sys.argv", ["record", "--output-dir", str(tmp_path)]):
            with patch(
                "tree_sitter_analyzer.platform_compat.record.BehaviorRecorder"
            ) as MockRecorder:
                mock_recorder = MagicMock()
                mock_profile = MagicMock()
                mock_profile.platform_key = "test-platform"
                mock_profile.behaviors = {"test": "behavior"}
                mock_recorder.record_all.return_value = mock_profile
                MockRecorder.return_value = mock_recorder

                from tree_sitter_analyzer.platform_compat.record import main

                # Should complete without error
                main()

                mock_recorder.record_all.assert_called_once()
                mock_profile.save.assert_called_once_with(tmp_path)

    def test_main_with_default_output_dir(self):
        """Test recording with default output directory."""
        with patch("sys.argv", ["record"]):
            with patch(
                "tree_sitter_analyzer.platform_compat.record.BehaviorRecorder"
            ) as MockRecorder:
                mock_recorder = MagicMock()
                mock_profile = MagicMock()
                mock_profile.platform_key = "test-platform"
                mock_profile.behaviors = {"test": "behavior"}
                mock_recorder.record_all.return_value = mock_profile
                MockRecorder.return_value = mock_recorder

                from tree_sitter_analyzer.platform_compat.record import main

                main()

                # Should save to default path
                mock_profile.save.assert_called_once()
                save_path = mock_profile.save.call_args[0][0]
                assert save_path == Path("tests/platform_profiles")

    def test_main_failure_exits(self, tmp_path):
        """Test that errors cause sys.exit(1)."""
        with patch("sys.argv", ["record", "--output-dir", str(tmp_path)]):
            with patch(
                "tree_sitter_analyzer.platform_compat.record.BehaviorRecorder"
            ) as MockRecorder:
                MockRecorder.return_value.record_all.side_effect = RuntimeError(
                    "Test error"
                )

                from tree_sitter_analyzer.platform_compat.record import main

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1

    def test_module_runnable_as_main(self):
        """Test that module can be run as __main__."""
        # Import should work without executing main
        import tree_sitter_analyzer.platform_compat.record

        assert hasattr(tree_sitter_analyzer.platform_compat.record, "main")
