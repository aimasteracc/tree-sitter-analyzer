#!/usr/bin/env python3
"""Shared mixin tests for handle_special_commands.

Keeps the large "TestHandleSpecialCommands" suite out of the primary module
for faster review and safer local refactoring.
"""

import argparse
from unittest.mock import Mock, patch

from tree_sitter_analyzer.cli_main import handle_special_commands


class TestHandleSpecialCommandsBatchMixin:
    """Batch/partial-read tests for handle_special_commands."""

    __test__ = False

    # --- Partial read validation ---

    def test_partial_read_no_start_line(self):
        """partial_read without --start-line returns error."""
        args = argparse.Namespace(
            file_path="test.py",
            partial_read=True,
            start_line=None,
            end_line=None,
            start_column=None,
            end_column=None,
            partial_read_requests_json=None,
            partial_read_requests_file=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        with patch("tree_sitter_analyzer.cli_main.output_error") as mock_error:
            result = handle_special_commands(args)
            assert result == 1
            mock_error.assert_called_once_with("--start-line is required")

    def test_partial_read_start_line_zero(self):
        """partial_read with --start-line < 1 returns error."""
        args = argparse.Namespace(
            file_path="test.py",
            partial_read=True,
            start_line=0,
            end_line=None,
            start_column=None,
            end_column=None,
            partial_read_requests_json=None,
            partial_read_requests_file=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        with patch("tree_sitter_analyzer.cli_main.output_error") as mock_error:
            result = handle_special_commands(args)
            assert result == 1
            mock_error.assert_called_once_with("--start-line must be 1 or greater")

    def test_partial_read_end_line_lt_start(self):
        """partial_read with --end-line < --start-line returns error."""
        args = argparse.Namespace(
            file_path="test.py",
            partial_read=True,
            start_line=5,
            end_line=3,
            start_column=None,
            end_column=None,
            partial_read_requests_json=None,
            partial_read_requests_file=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        with patch("tree_sitter_analyzer.cli_main.output_error") as mock_error:
            result = handle_special_commands(args)
            assert result == 1
            mock_error.assert_called_once_with(
                "--end-line must be greater than or equal to --start-line"
            )

    def test_partial_read_negative_start_column(self):
        """partial_read with --start-column < 0 returns error."""
        args = argparse.Namespace(
            file_path="test.py",
            partial_read=True,
            start_line=1,
            end_line=None,
            start_column=-1,
            end_column=None,
            partial_read_requests_json=None,
            partial_read_requests_file=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        with patch("tree_sitter_analyzer.cli_main.output_error") as mock_error:
            result = handle_special_commands(args)
            assert result == 1
            mock_error.assert_called_once_with("--start-column must be 0 or greater")

    def test_partial_read_negative_end_column(self):
        """partial_read with --end-column < 0 returns error."""
        args = argparse.Namespace(
            file_path="test.py",
            partial_read=True,
            start_line=1,
            end_line=None,
            start_column=None,
            end_column=-5,
            partial_read_requests_json=None,
            partial_read_requests_file=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        with patch("tree_sitter_analyzer.cli_main.output_error") as mock_error:
            result = handle_special_commands(args)
            assert result == 1
            mock_error.assert_called_once_with("--end-column must be 0 or greater")

    # --- Batch partial read ---

    @patch("tree_sitter_analyzer.mcp.tools.read_partial_tool.ReadPartialTool")
    @patch("tree_sitter_analyzer.cli_main.asyncio")
    def test_batch_partial_read_json_input(self, mock_asyncio, mock_read_tool_cls):
        """batch partial read with JSON string input."""
        mock_tool = Mock()
        mock_tool.execute = Mock()
        mock_result = {"success": True, "toon_content": "result content"}
        mock_asyncio.run.return_value = mock_result
        mock_read_tool_cls.return_value = mock_tool

        args = argparse.Namespace(
            file_path=None,
            partial_read=True,
            partial_read_requests_json=(
                '{"requests": [{"path": "a.py", "start_line": 1}]}'
            ),
            partial_read_requests_file=None,
            start_line=None,
            end_line=None,
            start_column=None,
            end_column=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            allow_truncate=False,
            fail_fast=False,
            project_root="/tmp",
            format="toon",
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 0
        mock_read_tool_cls.assert_called_once_with(project_root="/tmp")
        mock_asyncio.run.assert_called_once()

    @patch("tree_sitter_analyzer.cli_main.output_error")
    @patch("tree_sitter_analyzer.mcp.tools.read_partial_tool.ReadPartialTool")
    def test_batch_partial_read_failure(self, mock_read_tool_cls, mock_output_error):
        """batch partial read handling exception."""
        mock_read_tool_cls.side_effect = RuntimeError("Tool error")

        args = argparse.Namespace(
            file_path=None,
            partial_read=True,
            partial_read_requests_json=(
                '{"requests": [{"path": "a.py", "start_line": 1}]}'
            ),
            partial_read_requests_file=None,
            start_line=None,
            end_line=None,
            start_column=None,
            end_column=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            allow_truncate=False,
            fail_fast=False,
            project_root="/tmp",
            format="json",
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called_once()

    # --- Batch metrics ---

    @patch("tree_sitter_analyzer.mcp.tools.analyze_scale_tool.AnalyzeScaleTool")
    @patch("tree_sitter_analyzer.cli_main.asyncio")
    def test_batch_metrics_success(self, mock_asyncio, mock_scale_tool_cls):
        """batch metrics success path."""
        mock_tool = Mock()
        mock_tool.execute = Mock()
        mock_result = {"success": True, "toon_content": "metrics results"}
        mock_asyncio.run.return_value = mock_result
        mock_scale_tool_cls.return_value = mock_tool

        args = argparse.Namespace(
            file_path=None,
            metrics_only=True,
            file_paths=["a.py", "b.py"],
            files_from=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            project_root="/tmp",
            format="toon",
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 0
        mock_scale_tool_cls.assert_called_once_with(project_root="/tmp")
        mock_asyncio.run.assert_called_once()

    def test_batch_metrics_no_paths(self):
        """batch metrics without file_paths or files_from."""
        args = argparse.Namespace(
            file_path=None,
            metrics_only=True,
            file_paths=None,
            files_from=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            quiet=False,
        )
        with patch("tree_sitter_analyzer.cli_main.output_error") as mock_error:
            result = handle_special_commands(args)
            assert result == 1
            mock_error.assert_called_once_with(
                "--metrics-only requires --file-paths or --files-from"
            )

    @patch("tree_sitter_analyzer.mcp.tools.analyze_scale_tool.AnalyzeScaleTool")
    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_batch_metrics_failure(self, mock_output_error, mock_scale_tool_cls):
        """batch metrics failure path."""
        mock_scale_tool_cls.side_effect = RuntimeError("Scale error")

        args = argparse.Namespace(
            file_path=None,
            metrics_only=True,
            file_paths=["a.py"],
            files_from=None,
            partial_read=False,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            project_root="/tmp",
            format="json",
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called_once()

    # --- show_query_languages ---

    @patch("tree_sitter_analyzer.cli_main.query_loader.list_supported_languages")
    @patch("tree_sitter_analyzer.cli_main.query_loader.list_queries_for_language")
    @patch("tree_sitter_analyzer.cli_main.output_list")
    def test_show_query_languages(
        self, mock_output_list, mock_list_queries, mock_list_langs
    ):
        """show_query_languages lists all supported languages."""
        mock_list_langs.return_value = ["python", "javascript"]
        mock_list_queries.return_value = ["class", "method", "function"]

        args = argparse.Namespace(
            file_path=None,
            partial_read=False,
            show_query_languages=True,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            metrics_only=False,
            quiet=False,
        )
        result = handle_special_commands(args)
        assert result == 0
        mock_list_langs.assert_called_once()
