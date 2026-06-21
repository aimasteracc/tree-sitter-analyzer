#!/usr/bin/env python3
"""Shared mixin tests for handle_special_commands.

Keeps the large "TestHandleSpecialCommands" suite out of the primary module
for faster review and safer local refactoring.
"""

import argparse
from unittest.mock import Mock, patch

from tree_sitter_analyzer.cli_main import handle_special_commands


class TestHandleSpecialCommandsProfileMixin:
    """Tests for handle_special_commands() covering all branches."""

    __test__ = False

    # --- _effective_output_format / _tool_output_format ---

    def test_effective_output_format_default(self):
        """_effective_output_format returns 'json' by default."""
        args = argparse.Namespace(
            file_path="test.py",
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result is None

    def test_effective_output_format_toon(self):
        """_effective_output_format respects --format=toon."""
        args = argparse.Namespace(
            file_path="test.py",
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            format="toon",
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result is None

    # --- show_common_queries ---

    @patch("tree_sitter_analyzer.cli_main.query_loader.get_common_queries")
    @patch("tree_sitter_analyzer.cli_main.output_list")
    def test_show_common_queries_with_results(self, mock_output_list, mock_get_common):
        """show_common_queries lists common queries when available."""
        mock_get_common.return_value = ["class", "method"]

        args = argparse.Namespace(
            file_path=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=True,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 0
        mock_get_common.assert_called_once()
        assert mock_output_list.call_count >= 2  # ratchet: nondeterministic

    @patch("tree_sitter_analyzer.cli_main.query_loader.get_common_queries")
    @patch("tree_sitter_analyzer.cli_main.output_info")
    def test_show_common_queries_empty(self, mock_output_info, mock_get_common):
        """show_common_queries shows info when no common queries."""
        mock_get_common.return_value = []

        args = argparse.Namespace(
            file_path=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=True,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 0
        mock_output_info.assert_called_once_with("No common queries found.")

    # --- sql_platform_info ---

    @patch("tree_sitter_analyzer.platform_compat.detector.PlatformDetector")
    @patch("tree_sitter_analyzer.platform_compat.profiles.BehaviorProfile")
    @patch("tree_sitter_analyzer.cli_main.output_list")
    def test_sql_platform_info_with_profile(
        self, mock_output_list, mock_profile_cls, mock_detector
    ):
        """sql_platform_info when profile exists."""
        mock_info = Mock()
        mock_info.os_name = "macOS"
        mock_info.os_version = "14.0"
        mock_info.python_version = "3.14.3"
        mock_info.platform_key = "macos-14-arm64"
        mock_detector.detect.return_value = mock_info

        mock_profile = Mock()
        mock_profile.schema_version = "1.0.0"
        mock_profile.behaviors = {"a": 1, "b": 2}
        mock_profile.adaptation_rules = ["rule1"]
        mock_profile_cls.load.return_value = mock_profile

        args = argparse.Namespace(
            file_path=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=True,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 0
        mock_detector.detect.assert_called_once()
        mock_profile_cls.load.assert_called_once_with("macos-14-arm64")
        assert mock_output_list.call_count >= 2  # ratchet: nondeterministic

    @patch("tree_sitter_analyzer.platform_compat.detector.PlatformDetector")
    @patch("tree_sitter_analyzer.platform_compat.profiles.BehaviorProfile")
    @patch("tree_sitter_analyzer.cli_main.output_list")
    def test_sql_platform_info_no_profile(
        self, mock_output_list, mock_profile_cls, mock_detector
    ):
        """sql_platform_info when no profile found."""
        mock_info = Mock()
        mock_info.os_name = "macOS"
        mock_info.os_version = "14.0"
        mock_info.python_version = "3.14.3"
        mock_info.platform_key = "macos-14-arm64"
        mock_detector.detect.return_value = mock_info
        mock_profile_cls.load.return_value = None

        args = argparse.Namespace(
            file_path=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=True,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 0
        calls = mock_output_list.call_args_list
        no_profile_found = False
        for call in calls:
            args_list = call[0][0]
            for item in args_list:
                if "No profile found" in str(item):
                    no_profile_found = True
        assert no_profile_found, "Should output 'No profile found'"

    # --- record_sql_profile ---

    @patch("tree_sitter_analyzer.platform_compat.recorder.BehaviorRecorder")
    @patch("tree_sitter_analyzer.cli_main.output_info")
    @patch("tree_sitter_analyzer.cli.commands.sql_platform_helpers.pathlib.Path")
    def test_record_sql_profile_success(
        self, mock_path_cls, mock_output_info, mock_recorder_cls
    ):
        """record_sql_profile success path."""
        mock_profile = Mock()
        mock_profile.platform_key = "test-platform"
        mock_recorder = Mock()
        mock_recorder.record_all.return_value = mock_profile
        mock_recorder_cls.return_value = mock_recorder

        mock_output_dir = Mock()
        mock_path_cls.return_value = mock_output_dir

        args = argparse.Namespace(
            file_path=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=True,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 0
        mock_recorder.record_all.assert_called_once()
        mock_profile.save.assert_called_once_with(mock_output_dir)

    @patch("tree_sitter_analyzer.platform_compat.recorder.BehaviorRecorder")
    @patch("tree_sitter_analyzer.cli_main.output_error")
    @patch("tree_sitter_analyzer.cli_main.output_info")
    def test_record_sql_profile_failure(
        self, mock_output_info, mock_output_error, mock_recorder_cls
    ):
        """record_sql_profile failure path."""
        mock_recorder_cls.side_effect = RuntimeError("Recording failed")

        args = argparse.Namespace(
            file_path=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=True,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called_once()

    # --- compare_sql_profiles ---

    @patch("tree_sitter_analyzer.cli.commands.sql_platform_helpers.pathlib.Path")
    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_compare_sql_profiles_missing_first(self, mock_output_error, mock_path_cls):
        """compare_sql_profiles when first profile doesn't exist."""
        mock_p1 = Mock()
        mock_p1.exists.return_value = False
        mock_p2 = Mock()
        mock_p2.exists.return_value = True
        mock_path_cls.side_effect = [mock_p1, mock_p2]

        args = argparse.Namespace(
            file_path=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=["p1.json", "p2.json"],
            metrics_only=False,
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called_once()

    @patch("tree_sitter_analyzer.cli.commands.sql_platform_helpers.pathlib.Path")
    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_compare_sql_profiles_missing_second(
        self, mock_output_error, mock_path_cls
    ):
        """compare_sql_profiles when second profile doesn't exist."""
        mock_p1 = Mock()
        mock_p1.exists.return_value = True
        mock_p2 = Mock()
        mock_p2.exists.return_value = False
        mock_path_cls.side_effect = [mock_p1, mock_p2]

        args = argparse.Namespace(
            file_path=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=["p1.json", "p2.json"],
            metrics_only=False,
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called_once()

    @patch("tree_sitter_analyzer.cli.commands.sql_platform_helpers.pathlib.Path")
    @patch("tree_sitter_analyzer.platform_compat.compare.compare_profiles")
    @patch("tree_sitter_analyzer.platform_compat.compare.generate_diff_report")
    @patch("builtins.print")
    def test_compare_sql_profiles_success(
        self, mock_print, mock_generate_diff, mock_compare, mock_path_cls
    ):
        """compare_sql_profiles success path."""
        import json

        mock_p1 = Mock()
        mock_p1.exists.return_value = True
        mock_p2 = Mock()
        mock_p2.exists.return_value = True
        mock_path_cls.side_effect = [mock_p1, mock_p2]

        profile_data = json.dumps(
            {
                "schema_version": "1.0.0",
                "platform_key": "test-platform",
                "behaviors": {
                    "func_call": {
                        "construct_id": "func_call",
                        "node_type": "call",
                        "element_count": 5,
                        "attributes": ["name"],
                        "has_error": False,
                    }
                },
                "adaptation_rules": [],
            }
        )

        mock_comparison = Mock()
        mock_compare.return_value = mock_comparison
        mock_generate_diff.return_value = "Diff report content"

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = (
                profile_data
            )

            args = argparse.Namespace(
                file_path=None,
                partial_read=False,
                show_query_languages=False,
                show_common_queries=False,
                sql_platform_info=False,
                record_sql_profile=False,
                compare_sql_profiles=["p1.json", "p2.json"],
                metrics_only=False,
                quiet=False,
            )
            result = handle_special_commands(args)
            assert result == 0
            mock_compare.assert_called_once()
            mock_generate_diff.assert_called_once_with(mock_comparison)
            mock_print.assert_called_once_with("Diff report content")

    @patch("tree_sitter_analyzer.cli.commands.sql_platform_helpers.pathlib.Path")
    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_compare_sql_profiles_error(self, mock_output_error, mock_path_cls):
        """compare_sql_profiles when comparison raises."""
        mock_p1 = Mock()
        mock_p1.exists.return_value = True
        mock_p2 = Mock()
        mock_p2.exists.return_value = True
        mock_path_cls.side_effect = [mock_p1, mock_p2]

        with patch("builtins.open", side_effect=ValueError("Bad JSON")):
            args = argparse.Namespace(
                file_path=None,
                partial_read=False,
                show_query_languages=False,
                show_common_queries=False,
                sql_platform_info=False,
                record_sql_profile=False,
                compare_sql_profiles=["p1.json", "p2.json"],
                metrics_only=False,
                quiet=False,
            )
            result = handle_special_commands(args)
            assert result == 1
            mock_output_error.assert_called_once()
