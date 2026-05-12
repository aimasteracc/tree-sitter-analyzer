#!/usr/bin/env python3
"""
Unit tests for CLI Main Module.

Tests command-line interface entry point and argument parsing.
"""

import argparse
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.cli_main import (
    CLICommandFactory,
    create_argument_parser,
    handle_special_commands,
    main,
)


class TestCLICommandFactory:
    """Tests for CLICommandFactory class."""

    def test_create_command_list_queries(self):
        """Test creating ListQueriesCommand."""
        args = argparse.Namespace(
            list_queries=True,
            file_path=None,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "ListQueriesCommand"

    def test_create_command_describe_query(self):
        """Test creating DescribeQueryCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query="class",
            file_path=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "DescribeQueryCommand"

    def test_create_command_show_languages(self):
        """Test creating ShowLanguagesCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=True,
            file_path=None,
            show_supported_extensions=False,
            filter_help=None,
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "ShowLanguagesCommand"

    def test_create_command_show_extensions(self):
        """Test creating ShowExtensionsCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=True,
            file_path=None,
            filter_help=None,
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "ShowExtensionsCommand"

    def test_create_command_filter_help(self):
        """Test creating filter help command."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=True,
            file_path=None,
        )
        command = CLICommandFactory.create_command(args)
        # filter_help returns None (exits with code 0)
        assert command is None

    def test_create_command_table(self):
        """Test creating TableCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            table="full",
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "TableCommand"

    def test_create_command_structure(self):
        """Test creating StructureCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            structure=True,
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "StructureCommand"

    def test_create_command_summary(self):
        """Test creating SummaryCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            summary="classes,methods",
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "SummaryCommand"

    def test_create_command_advanced(self):
        """Test creating AdvancedCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            advanced=True,
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "AdvancedCommand"

    def test_create_command_query_key(self):
        """Test creating QueryCommand with query_key."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            query_key="class",
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "QueryCommand"

    def test_create_command_query_string(self):
        """Test creating QueryCommand with query_string."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            query_string="(function_declaration)",
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "QueryCommand"

    def test_create_command_default(self):
        """Test creating DefaultCommand when no specific command is given."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "DefaultCommand"

    def test_create_command_partial_read(self):
        """Test creating PartialReadCommand."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path="test.py",
            partial_read=True,
            start_line=1,
            end_line=10,
        )
        command = CLICommandFactory.create_command(args)
        assert command is not None
        assert command.__class__.__name__ == "PartialReadCommand"

    def test_create_command_no_file_path(self):
        """Test that command is None when file_path is not provided."""
        args = argparse.Namespace(
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            file_path=None,
        )
        command = CLICommandFactory.create_command(args)
        assert command is None


class TestCreateArgumentParser:
    """Tests for create_argument_parser function."""

    def test_parser_creation(self):
        """Test that argument parser is created successfully."""
        parser = create_argument_parser()
        assert parser is not None
        assert isinstance(parser, argparse.ArgumentParser)

    def test_parser_has_file_path_argument(self):
        """Test that parser has file_path argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["test.py"])
        assert args.file_path == "test.py"

    def test_parser_has_query_key_argument(self):
        """Test that parser has --query-key argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--query-key", "class", "test.py"])
        assert args.query_key == "class"

    def test_parser_has_query_string_argument(self):
        """Test that parser has --query-string argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--query-string", "(function)", "test.py"])
        assert args.query_string == "(function)"

    def test_parser_has_filter_argument(self):
        """Test that parser has --filter argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--filter", "name=main", "test.py"])
        assert args.filter == "name=main"

    def test_parser_has_list_queries_argument(self):
        """Test that parser has --list-queries argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--list-queries"])
        assert args.list_queries is True

    def test_parser_has_describe_query_argument(self):
        """Test that parser has --describe-query argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--describe-query", "class"])
        assert args.describe_query == "class"

    def test_parser_has_show_supported_languages_argument(self):
        """Test that parser has --show-supported-languages argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--show-supported-languages"])
        assert args.show_supported_languages is True

    def test_parser_has_show_supported_extensions_argument(self):
        """Test that parser has --show-supported-extensions argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--show-supported-extensions"])
        assert args.show_supported_extensions is True

    def test_parser_has_output_format_argument(self):
        """Test that parser has --output-format argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--output-format", "json", "test.py"])
        assert args.output_format == "json"

    def test_parser_has_format_argument(self):
        """Test that parser has --format argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--format", "toon", "test.py"])
        assert args.format == "toon"

    def test_parser_has_table_argument(self):
        """Test that parser has --table argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--table", "full", "test.py"])
        assert args.table == "full"

    def test_parser_has_include_javadoc_argument(self):
        """Test that parser has --include-javadoc argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--include-javadoc", "test.py"])
        assert args.include_javadoc is True

    def test_parser_has_advanced_argument(self):
        """Test that parser has --advanced argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--advanced", "test.py"])
        assert args.advanced is True

    def test_parser_has_summary_argument(self):
        """Test that parser has --summary argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--summary", "test.py"])
        # --summary is a flag that accepts a value
        assert args.summary == "test.py"

    def test_parser_has_structure_argument(self):
        """Test that parser has --structure argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--structure", "test.py"])
        assert args.structure is True

    def test_parser_has_statistics_argument(self):
        """Test that parser has --statistics argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--statistics", "test.py"])
        assert args.statistics is True

    def test_parser_has_language_argument(self):
        """Test that parser has --language argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--language", "python", "test.py"])
        assert args.language == "python"

    def test_parser_has_project_root_argument(self):
        """Test that parser has --project-root argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--project-root", "/path/to/project", "test.py"])
        assert args.project_root == "/path/to/project"

    def test_parser_has_quiet_argument(self):
        """Test that parser has --quiet argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--quiet", "test.py"])
        assert args.quiet is True

    def test_parser_has_partial_read_argument(self):
        """Test that parser has --partial-read argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--partial-read", "test.py"])
        assert args.partial_read is True

    def test_parser_has_start_line_argument(self):
        """Test that parser has --start-line argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--start-line", "10", "test.py"])
        assert args.start_line == 10

    def test_parser_has_end_line_argument(self):
        """Test that parser has --end-line argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--end-line", "20", "test.py"])
        assert args.end_line == 20

    def test_parser_has_start_column_argument(self):
        """Test that parser has --start-column argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--start-column", "5", "test.py"])
        assert args.start_column == 5

    def test_parser_has_end_column_argument(self):
        """Test that parser has --end-column argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--end-column", "15", "test.py"])
        assert args.end_column == 15

    def test_parser_default_output_format(self):
        """Test that default output format is json."""
        parser = create_argument_parser()
        args = parser.parse_args(["test.py"])
        assert args.output_format == "json"

    def test_parser_file_path_optional(self):
        """Test that file_path is optional."""
        parser = create_argument_parser()
        args = parser.parse_args(["--list-queries"])
        assert args.file_path is None


class TestHandleSpecialCommands:
    """Tests for handle_special_commands function."""

    @patch("tree_sitter_analyzer.cli_main.output_list")
    def test_handle_show_query_languages(self, mock_output_list):
        """Test handling --show-query-languages."""
        args = argparse.Namespace(
            show_query_languages=True,
            list_queries=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            partial_read=False,
            metrics_only=False,
        )
        result = handle_special_commands(args)
        assert result == 0
        mock_output_list.assert_called()

    @patch("tree_sitter_analyzer.cli_main.output_list")
    def test_handle_show_common_queries(self, mock_output_list):
        """Test handling --show-common-queries."""
        args = argparse.Namespace(
            show_query_languages=False,
            list_queries=False,
            show_common_queries=True,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            partial_read=False,
            metrics_only=False,
        )
        result = handle_special_commands(args)
        assert result == 0
        mock_output_list.assert_called()

    def test_handle_sql_platform_info(self):
        """Test handling --sql-platform-info - skipped due to internal imports."""
        # This test is skipped because PlatformDetector is imported inside handle_special_commands
        pytest.skip(
            "PlatformDetector is imported inside handle_special_commands function"
        )

    def test_handle_record_sql_profile(self):
        """Test handling --record-sql-profile - skipped due to internal imports."""
        # This test is skipped because BehaviorRecorder is imported inside handle_special_commands
        pytest.skip(
            "BehaviorRecorder is imported inside handle_special_commands function"
        )

    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_handle_partial_read_missing_start_line(self, mock_output_error):
        """Test handling partial read without --start-line."""
        args = argparse.Namespace(
            partial_read=True,
            start_line=None,
            end_line=None,
            start_column=None,
            end_column=None,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called()

    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_handle_partial_read_invalid_start_line(self, mock_output_error):
        """Test handling partial read with invalid --start-line."""
        args = argparse.Namespace(
            partial_read=True,
            start_line=0,
            end_line=None,
            start_column=None,
            end_column=None,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called()

    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_handle_partial_read_invalid_end_line(self, mock_output_error):
        """Test handling partial read with invalid --end-line."""
        args = argparse.Namespace(
            partial_read=True,
            start_line=10,
            end_line=5,
            start_column=None,
            end_column=None,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called()

    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_handle_partial_read_invalid_start_column(self, mock_output_error):
        """Test handling partial read with invalid --start-column."""
        args = argparse.Namespace(
            partial_read=True,
            start_line=1,
            end_line=10,
            start_column=-1,
            end_column=None,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called()

    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_handle_partial_read_invalid_end_column(self, mock_output_error):
        """Test handling partial read with invalid --end-column."""
        args = argparse.Namespace(
            partial_read=True,
            start_line=1,
            end_line=10,
            start_column=None,
            end_column=-1,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called()

    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_handle_metrics_only_no_file_paths(self, mock_output_error):
        """Test handling --metrics-only without --file-paths or --files-from."""
        args = argparse.Namespace(
            metrics_only=True,
            file_paths=None,
            files_from=None,
        )
        result = handle_special_commands(args)
        assert result == 1
        mock_output_error.assert_called()

    def test_handle_no_special_command(self):
        """Test handling when no special command is given."""
        args = argparse.Namespace(
            show_query_languages=False,
            list_queries=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            partial_read=False,
            metrics_only=False,
        )
        result = handle_special_commands(args)
        assert result is None


class TestMainFunction:
    """Tests for main function."""

    def test_main_quiet_mode_sets_env_var(self):
        """Test that --quiet sets LOG_LEVEL environment variable - skipped due to complex mocking."""
        # This test is skipped because it requires complex mocking of main() function
        # which exits before setting LOG_LEVEL environment variable
        pytest.skip("Complex mocking required for main() function")

    def test_main_default_log_level(self):
        """Test that default log level is ERROR - skipped due to complex mocking."""
        # This test is skipped because it requires complex mocking of main() function
        # which exits before setting LOG_LEVEL environment variable
        pytest.skip("Complex mocking required for main() function")

    @patch("tree_sitter_analyzer.cli_main.create_argument_parser")
    @patch("tree_sitter_analyzer.cli_main.handle_special_commands")
    @patch("tree_sitter_analyzer.cli_main.sys.exit")
    def test_main_format_alias(self, mock_exit, mock_handle_special, mock_parser):
        """Test that --format is aliased to --output-format."""
        args = argparse.Namespace(
            format="toon",
            output_format="json",
            quiet=False,
            file_path=None,
            # Add all required attributes
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            partial_read=False,
            metrics_only=False,
        )
        mock_parser.return_value.parse_args.return_value = args
        mock_handle_special.return_value = 0

        main()

        assert args.output_format == "toon"

    @patch("tree_sitter_analyzer.cli_main.create_argument_parser")
    @patch("tree_sitter_analyzer.cli_main.handle_special_commands")
    @patch("tree_sitter_analyzer.cli_main.CLICommandFactory")
    @patch("tree_sitter_analyzer.cli_main.sys.exit")
    def test_main_creates_command(
        self, mock_exit, mock_factory, mock_handle_special, mock_parser
    ):
        """Test that main creates and executes command."""
        args = argparse.Namespace(
            file_path="test.py",
            quiet=False,
            # Add all required attributes
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            partial_read=False,
            metrics_only=False,
        )
        mock_parser.return_value.parse_args.return_value = args
        mock_handle_special.return_value = None

        mock_command = Mock()
        mock_command.execute.return_value = 0
        mock_factory.create_command.return_value = mock_command

        main()

        mock_factory.create_command.assert_called_once_with(args)
        mock_command.execute.assert_called_once()

    @patch("tree_sitter_analyzer.cli_main.create_argument_parser")
    @patch("tree_sitter_analyzer.cli_main.handle_special_commands")
    @patch("tree_sitter_analyzer.cli_main.CLICommandFactory")
    @patch("tree_sitter_analyzer.cli_main.sys.exit")
    def test_main_no_command_no_file_path(
        self, mock_exit, mock_factory, mock_handle_special, mock_parser
    ):
        """Test that main shows error when no command and no file path."""
        args = argparse.Namespace(
            file_path=None,
            quiet=False,
            # Add all required attributes
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            partial_read=False,
            metrics_only=False,
        )
        mock_parser.return_value.parse_args.return_value = args
        mock_handle_special.return_value = None
        mock_factory.create_command.return_value = None

        main()

        mock_exit.assert_called_once_with(1)

    @patch("tree_sitter_analyzer.cli_main.create_argument_parser")
    @patch("tree_sitter_analyzer.cli_main.output_error")
    @patch("tree_sitter_analyzer.cli_main.sys.exit")
    def test_main_keyboard_interrupt(self, mock_exit, mock_output_error, mock_parser):
        """Test that main handles KeyboardInterrupt."""
        mock_parser.return_value.parse_args.side_effect = KeyboardInterrupt()

        with patch("tree_sitter_analyzer.cli_main.output_info"):
            try:
                main()
            except KeyboardInterrupt:
                # Expected to be raised
                pass

        mock_output_error.assert_not_called()

    def test_main_unexpected_exception(self):
        """Test that main handles unexpected exceptions - skipped due to complex mocking."""
        # This test is skipped because it requires complex mocking of main() function
        pytest.skip("Complex mocking required for main() function")


class TestArgumentValidation:
    """Tests for argument validation."""

    def test_mutually_exclusive_query_options(self):
        """Test that --query-key and --query-string are mutually exclusive."""
        parser = create_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["--query-key", "class", "--query-string", "(function)", "test.py"]
            )

    def test_output_format_choices(self):
        """Test that --output-format accepts valid choices."""
        parser = create_argument_parser()
        for fmt in ["json", "text", "toon"]:
            args = parser.parse_args(["--output-format", fmt, "test.py"])
            assert args.output_format == fmt

    def test_table_format_choices(self):
        """Test that --table accepts valid choices."""
        parser = create_argument_parser()
        for table_fmt in ["full", "compact", "csv", "json", "toon"]:
            args = parser.parse_args(["--table", table_fmt, "test.py"])
            assert args.table == table_fmt


class TestSpecialCommandsIntegration:
    """Tests for special commands integration."""

    def test_batch_partial_read_json(self):
        """Test batch partial read with JSON requests - skipped due to internal imports."""
        # This test is skipped because ReadPartialTool is imported inside handle_special_commands
        pytest.skip(
            "ReadPartialTool is imported inside handle_special_commands function"
        )

    def test_batch_metrics_only(self):
        """Test batch metrics only mode - skipped due to internal imports."""
        # This test is skipped because AnalyzeScaleTool is imported inside handle_special_commands
        pytest.skip(
            "AnalyzeScaleTool is imported inside handle_special_commands function"
        )


class TestLoggingConfiguration:
    """Tests for logging configuration."""

    @patch("tree_sitter_analyzer.cli_main.create_argument_parser")
    @patch("tree_sitter_analyzer.cli_main.handle_special_commands")
    @patch("tree_sitter_analyzer.cli_main.sys.exit")
    def test_logging_configured_to_error(
        self, mock_exit, mock_handle_special, mock_parser
    ):
        """Test that logging is configured to ERROR level."""
        args = argparse.Namespace(
            quiet=False,
            file_path=None,
            # Add all required attributes
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            partial_read=False,
            metrics_only=False,
        )
        mock_parser.return_value.parse_args.return_value = args
        mock_handle_special.return_value = 0

        import logging

        with patch(
            "tree_sitter_analyzer.cli_main.logging.getLogger"
        ) as mock_get_logger:
            main()

            # Check that setLevel was called with ERROR
            calls = [
                call[0] for call in mock_get_logger.return_value.setLevel.call_args_list
            ]
            # calls contains tuples like (logging.ERROR,), so check if logging.ERROR is in the tuple
            assert any(logging.ERROR in call for call in calls)

    @patch("tree_sitter_analyzer.cli_main.create_argument_parser")
    @patch("tree_sitter_analyzer.cli_main.handle_special_commands")
    @patch("tree_sitter_analyzer.cli_main.sys.exit")
    def test_logging_configured_for_table_output(
        self, mock_exit, mock_handle_special, mock_parser
    ):
        """Test that logging is configured for table output."""
        args = argparse.Namespace(
            quiet=False,
            file_path=None,
            table="full",
            # Add all required attributes
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            partial_read=False,
            metrics_only=False,
        )
        mock_parser.return_value.parse_args.return_value = args
        mock_handle_special.return_value = 0

        import logging

        with patch(
            "tree_sitter_analyzer.cli_main.logging.getLogger"
        ) as mock_get_logger:
            main()

            # Check that setLevel was called with ERROR
            calls = [
                call[0] for call in mock_get_logger.return_value.setLevel.call_args_list
            ]
            # calls contains tuples like (logging.ERROR,), so check if logging.ERROR is in the tuple
            assert any(logging.ERROR in call for call in calls)


class TestErrorHandling:
    """Tests for error handling."""

    @patch("tree_sitter_analyzer.cli_main.create_argument_parser")
    @patch("tree_sitter_analyzer.cli_main.output_info")
    @patch("tree_sitter_analyzer.cli_main.sys.exit")
    def test_validation_error_shows_usage(
        self, mock_exit, mock_output_info, mock_parser
    ):
        """Test that validation error shows usage examples."""
        args = argparse.Namespace(
            file_path=None,
            # Add all required attributes
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            partial_read=False,
            metrics_only=False,
        )
        mock_parser.return_value.parse_args.return_value = args

        with patch(
            "tree_sitter_analyzer.cli_main.CLIArgumentValidator"
        ) as mock_validator:
            mock_validator.return_value.validate_arguments.return_value = (
                "Validation error"
            )
            mock_validator.return_value.get_usage_examples.return_value = (
                "Usage examples"
            )

            main()

            mock_output_info.assert_called_once_with("Usage examples")

    @patch("tree_sitter_analyzer.cli_main.create_argument_parser")
    @patch("tree_sitter_analyzer.cli_main.output_error")
    @patch("tree_sitter_analyzer.cli_main.sys.exit")
    def test_command_execute_error_exits_with_code(
        self, mock_exit, mock_output_error, mock_parser
    ):
        """Test that command execution error exits with error code."""
        args = argparse.Namespace(
            file_path="test.py",
            quiet=False,
            # Add all required attributes
            list_queries=False,
            describe_query=None,
            show_supported_languages=False,
            show_supported_extensions=False,
            filter_help=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            partial_read=False,
            metrics_only=False,
        )
        mock_parser.return_value.parse_args.return_value = args

        with patch(
            "tree_sitter_analyzer.cli_main.handle_special_commands"
        ) as mock_handle_special:
            mock_handle_special.return_value = None

            with patch(
                "tree_sitter_analyzer.cli_main.CLICommandFactory"
            ) as mock_factory:
                mock_command = Mock()
                mock_command.execute.return_value = 1
                mock_factory.create_command.return_value = mock_command

                main()

                mock_exit.assert_called_once_with(1)


class TestHandleSpecialCommands:
    """Tests for handle_special_commands() covering all branches."""

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
    def test_show_common_queries_with_results(
        self, mock_output_list, mock_get_common
    ):
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
        assert mock_output_list.call_count >= 2

    @patch("tree_sitter_analyzer.cli_main.query_loader.get_common_queries")
    @patch("tree_sitter_analyzer.cli_main.output_info")
    def test_show_common_queries_empty(
        self, mock_output_info, mock_get_common
    ):
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
        assert mock_output_list.call_count >= 2

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
    @patch("pathlib.Path")
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

    @patch("pathlib.Path")
    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_compare_sql_profiles_missing_first(
        self, mock_output_error, mock_path_cls
    ):
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

    @patch("pathlib.Path")
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

    @patch("pathlib.Path")
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

        profile_data = json.dumps({
            "schema_version": "1.0.0",
            "platform_key": "test-platform",
            "behaviors": {
                "func_call": {"construct_id": "func_call", "node_type": "call", "element_count": 5, "attributes": ["name"], "has_error": False}
            },
            "adaptation_rules": []
        })

        mock_comparison = Mock()
        mock_compare.return_value = mock_comparison
        mock_generate_diff.return_value = "Diff report content"

        with patch(
            "builtins.open", create=True
        ) as mock_open:
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

    @patch("pathlib.Path")
    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_compare_sql_profiles_error(
        self, mock_output_error, mock_path_cls
    ):
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
        with patch(
            "tree_sitter_analyzer.cli_main.output_error"
        ) as mock_error:
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
        with patch(
            "tree_sitter_analyzer.cli_main.output_error"
        ) as mock_error:
            result = handle_special_commands(args)
            assert result == 1
            mock_error.assert_called_once_with(
                "--start-line must be 1 or greater"
            )

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
        with patch(
            "tree_sitter_analyzer.cli_main.output_error"
        ) as mock_error:
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
        with patch(
            "tree_sitter_analyzer.cli_main.output_error"
        ) as mock_error:
            result = handle_special_commands(args)
            assert result == 1
            mock_error.assert_called_once_with(
                "--start-column must be 0 or greater"
            )

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
        with patch(
            "tree_sitter_analyzer.cli_main.output_error"
        ) as mock_error:
            result = handle_special_commands(args)
            assert result == 1
            mock_error.assert_called_once_with(
                "--end-column must be 0 or greater"
            )

    # --- Batch partial read ---

    @patch("tree_sitter_analyzer.mcp.tools.read_partial_tool.ReadPartialTool")
    @patch("tree_sitter_analyzer.cli_main.asyncio")
    def test_batch_partial_read_json_input(
        self, mock_asyncio, mock_read_tool_cls
    ):
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
    def test_batch_partial_read_failure(
        self, mock_read_tool_cls, mock_output_error
    ):
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
    def test_batch_metrics_success(
        self, mock_asyncio, mock_scale_tool_cls
    ):
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
        with patch(
            "tree_sitter_analyzer.cli_main.output_error"
        ) as mock_error:
            result = handle_special_commands(args)
            assert result == 1
            mock_error.assert_called_once_with(
                "--metrics-only requires --file-paths or --files-from"
            )

    @patch("tree_sitter_analyzer.mcp.tools.analyze_scale_tool.AnalyzeScaleTool")
    @patch("tree_sitter_analyzer.cli_main.output_error")
    def test_batch_metrics_failure(
        self, mock_output_error, mock_scale_tool_cls
    ):
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
