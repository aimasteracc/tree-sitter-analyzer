"""Tests for platform_compat.record module (CLI tool)."""

from unittest.mock import MagicMock, patch

import pytest


class TestRecordMain:
    """Tests for the record.main() CLI entry point."""

    @pytest.mark.unit
    @patch("tree_sitter_analyzer.platform_compat.record.BehaviorRecorder")
    @patch("tree_sitter_analyzer.platform_compat.record.argparse.ArgumentParser.parse_args")
    def test_main_success(self, mock_parse_args, mock_recorder_class, tmp_path):
        """Test main() successfully records and saves a profile."""
        from tree_sitter_analyzer.platform_compat.profiles import (
            BehaviorProfile,
        )
        from tree_sitter_analyzer.platform_compat.record import main

        mock_args = MagicMock()
        mock_args.output_dir = str(tmp_path)
        mock_parse_args.return_value = mock_args

        mock_profile = MagicMock(spec=BehaviorProfile)
        mock_profile.platform_key = "linux-3.12"
        mock_profile.behaviors = {"test": MagicMock()}
        mock_profile.save = MagicMock()

        mock_recorder = MagicMock()
        mock_recorder.record_all.return_value = mock_profile
        mock_recorder_class.return_value = mock_recorder

        main()

        mock_recorder.record_all.assert_called_once()
        mock_profile.save.assert_called_once()

    @pytest.mark.unit
    @patch("tree_sitter_analyzer.platform_compat.record.BehaviorRecorder")
    @patch("tree_sitter_analyzer.platform_compat.record.argparse.ArgumentParser.parse_args")
    def test_main_failure_exits(self, mock_parse_args, mock_recorder_class):
        """Test main() exits with code 1 on failure."""
        from tree_sitter_analyzer.platform_compat.record import main

        mock_args = MagicMock()
        mock_args.output_dir = "/tmp/test_profiles"
        mock_parse_args.return_value = mock_args

        mock_recorder_class.side_effect = RuntimeError("Failed to initialize")

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
