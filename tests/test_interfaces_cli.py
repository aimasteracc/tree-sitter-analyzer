#!/usr/bin/env python3
"""
Tests for interfaces CLI functionality

This module tests the CLI interface to improve coverage.
"""

import argparse
import os
import tempfile
from io import StringIO
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.interfaces.cli import (
    create_parser,
    format_analysis_output,
    format_extraction_output,
    format_query_output,
    format_validation_output,
    handle_analyze_command,
    handle_extract_command,
    handle_info_command,
    handle_languages_command,
    handle_queries_command,
    handle_query_command,
    handle_validate_command,
    main,
)


class TestCreateParser:
    """Test create_parser function"""

    def test_create_parser_basic(self) -> None:
        """Test basic parser creation"""
        parser = create_parser()

        assert isinstance(parser, argparse.ArgumentParser)
        assert parser.prog == "tree-sitter-analyzer"

    def test_parser_global_options(self) -> None:
        """Test global options parsing"""
        parser = create_parser()

        # Test version option
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])

    def test_parser_analyze_command(self) -> None:
        """Test analyze command parsing"""
        parser = create_parser()

        args = parser.parse_args(["analyze", "test.py"])
        assert args.command == "analyze"
        assert args.file_path == "test.py"

    def test_parser_analyze_with_options(self) -> None:
        """Test analyze command with options"""
        parser = create_parser()

        args = parser.parse_args(
            [
                "--verbose",
                "analyze",
                "test.py",
                "--language",
                "python",
                "--queries",
                "functions,classes",
                "--no-elements",
            ]
        )

        assert args.command == "analyze"
        assert args.file_path == "test.py"
        assert args.language == "python"
        assert args.queries == "functions,classes"
        assert args.no_elements is True
        assert args.verbose is True

    def test_parser_extract_command(self) -> None:
        """Test extract command parsing"""
        parser = create_parser()

        args = parser.parse_args(["extract", "test.py", "--types", "functions"])
        assert args.command == "extract"
        assert args.file_path == "test.py"
        assert args.types == "functions"

    def test_parser_query_command(self) -> None:
        """Test query command parsing"""
        parser = create_parser()

        args = parser.parse_args(["query", "test.py", "functions"])
        assert args.command == "query"
        assert args.file_path == "test.py"
        assert args.query_name == "functions"

    def test_parser_validate_command(self) -> None:
        """Test validate command parsing"""
        parser = create_parser()

        args = parser.parse_args(["validate", "test.py"])
        assert args.command == "validate"
        assert args.file_path == "test.py"

    def test_parser_languages_command(self) -> None:
        """Test languages command parsing"""
        parser = create_parser()

        args = parser.parse_args(["languages", "--extensions"])
        assert args.command == "languages"
        assert args.extensions is True

    def test_parser_info_command(self) -> None:
        """Test info command parsing"""
        parser = create_parser()

        args = parser.parse_args(["info"])
        assert args.command == "info"

    def test_parser_queries_command(self) -> None:
        """Test queries command parsing"""
        parser = create_parser()

        args = parser.parse_args(["queries", "python"])
        assert args.command == "queries"
        assert args.language == "python"


class TestHandleAnalyzeCommand:
    """Test handle_analyze_command function"""

    @pytest.fixture
    def mock_args(self) -> Mock:
        """Create mock arguments"""
        args = Mock()
        args.file_path = "test.py"
        args.language = None
        args.queries = None
        args.no_elements = False
        args.no_queries = False
        args.output = "text"
        return args

    def test_handle_analyze_command_file_not_found(self, mock_args: Mock) -> None:
        """Test analyze command with non-existent file"""
        mock_args.file_path = "nonexistent.py"

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = handle_analyze_command(mock_args)

        assert result == 1
        assert "does not exist" in mock_stderr.getvalue()

    def test_handle_analyze_command_success(self, mock_args: Mock) -> None:
        """Test successful analyze command"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello(): pass")
            temp_file = f.name

        try:
            mock_args.file_path = temp_file

            with patch(
                "tree_sitter_analyzer.interfaces.cli.api.analyze_file"
            ) as mock_analyze:
                mock_analyze.return_value = {
                    "success": True,
                    "language": "python",
                    "elements": [],
                }

                with patch(
                    "tree_sitter_analyzer.interfaces.cli.format_analysis_output"
                ) as mock_format:
                    result = handle_analyze_command(mock_args)

                assert result == 0
                mock_analyze.assert_called_once()
                mock_format.assert_called_once()

        finally:
            os.unlink(temp_file)

    def test_handle_analyze_command_json_output(self, mock_args: Mock) -> None:
        """Test analyze command with JSON output"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello(): pass")
            temp_file = f.name

        try:
            mock_args.file_path = temp_file
            mock_args.output = "json"

            with patch(
                "tree_sitter_analyzer.interfaces.cli.api.analyze_file"
            ) as mock_analyze:
                mock_analyze.return_value = {"success": True}

                with patch("builtins.print") as mock_print:
                    result = handle_analyze_command(mock_args)

                assert result == 0
                mock_print.assert_called()

        finally:
            os.unlink(temp_file)

    def test_handle_analyze_command_with_queries(self, mock_args: Mock) -> None:
        """Test analyze command with queries"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello(): pass")
            temp_file = f.name

        try:
            mock_args.file_path = temp_file
            mock_args.queries = "functions,classes"

            with patch(
                "tree_sitter_analyzer.interfaces.cli.api.analyze_file"
            ) as mock_analyze:
                mock_analyze.return_value = {"success": True}

                with patch(
                    "tree_sitter_analyzer.interfaces.cli.format_analysis_output"
                ):
                    result = handle_analyze_command(mock_args)

                assert result == 0
                # Check that queries were parsed correctly
                call_args = mock_analyze.call_args
                assert call_args[1]["queries"] == ["functions", "classes"]

        finally:
            os.unlink(temp_file)

    def test_handle_analyze_command_exception(self, mock_args: Mock) -> None:
        """Test analyze command with exception"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello(): pass")
            temp_file = f.name

        try:
            mock_args.file_path = temp_file

            with patch(
                "tree_sitter_analyzer.interfaces.cli.api.analyze_file"
            ) as mock_analyze:
                mock_analyze.side_effect = Exception("Test error")

                with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                    result = handle_analyze_command(mock_args)

                assert result == 1
                assert "Test error" in mock_stderr.getvalue()

        finally:
            os.unlink(temp_file)


class TestHandleExtractCommand:
    """Test handle_extract_command function"""

    @pytest.fixture
    def mock_args(self) -> Mock:
        """Create mock arguments"""
        args = Mock()
        args.file_path = "test.py"
        args.language = None
        args.types = None
        args.output = "text"
        return args

    def test_handle_extract_command_success(self, mock_args: Mock) -> None:
        """Test successful extract command"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello(): pass")
            temp_file = f.name

        try:
            mock_args.file_path = temp_file

            with patch(
                "tree_sitter_analyzer.interfaces.cli.api.extract_elements"
            ) as mock_extract:
                mock_extract.return_value = {"success": True, "elements": []}

                with patch(
                    "tree_sitter_analyzer.interfaces.cli.format_extraction_output"
                ) as mock_format:
                    result = handle_extract_command(mock_args)

                assert result == 0
                mock_extract.assert_called_once()
                mock_format.assert_called_once()

        finally:
            os.unlink(temp_file)

    def test_handle_extract_command_with_types(self, mock_args: Mock) -> None:
        """Test extract command with element types"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello(): pass")
            temp_file = f.name

        try:
            mock_args.file_path = temp_file
            mock_args.types = "functions,classes"

            with patch(
                "tree_sitter_analyzer.interfaces.cli.api.extract_elements"
            ) as mock_extract:
                mock_extract.return_value = {"success": True}

                with patch(
                    "tree_sitter_analyzer.interfaces.cli.format_extraction_output"
                ):
                    result = handle_extract_command(mock_args)

                assert result == 0
                # Check that types were parsed correctly
                call_args = mock_extract.call_args
                assert call_args[1]["element_types"] == ["functions", "classes"]

        finally:
            os.unlink(temp_file)


class TestHandleQueryCommand:
    """Test handle_query_command function"""

    @pytest.fixture
    def mock_args(self) -> Mock:
        """Create mock arguments"""
        args = Mock()
        args.file_path = "test.py"
        args.query_name = "functions"
        args.language = None
        args.output = "text"
        return args

    def test_handle_query_command_success(self, mock_args: Mock) -> None:
        """Test successful query command"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello(): pass")
            temp_file = f.name

        try:
            mock_args.file_path = temp_file

            with patch(
                "tree_sitter_analyzer.interfaces.cli.api.execute_query"
            ) as mock_query:
                mock_query.return_value = {"success": True, "results": []}

                with patch(
                    "tree_sitter_analyzer.interfaces.cli.format_query_output"
                ) as mock_format:
                    result = handle_query_command(mock_args)

                assert result == 0
                mock_query.assert_called_once()
                mock_format.assert_called_once()

        finally:
            os.unlink(temp_file)


class TestHandleValidateCommand:
    """Test handle_validate_command function"""

    @pytest.fixture
    def mock_args(self) -> Mock:
        """Create mock arguments"""
        args = Mock()
        args.file_path = "test.py"
        args.output = "text"
        return args

    def test_handle_validate_command_success(self, mock_args: Mock) -> None:
        """Test successful validate command"""
        with patch(
            "tree_sitter_analyzer.interfaces.cli.api.validate_file"
        ) as mock_validate:
            mock_validate.return_value = {"valid": True}

            with patch(
                "tree_sitter_analyzer.interfaces.cli.format_validation_output"
            ) as mock_format:
                result = handle_validate_command(mock_args)

            assert result == 0
            mock_validate.assert_called_once()
            mock_format.assert_called_once()


class TestHandleLanguagesCommand:
    """Test handle_languages_command function"""

    @pytest.fixture
    def mock_args(self) -> Mock:
        """Create mock arguments"""
        args = Mock()
        args.extensions = False
        args.output = "text"
        return args

    def test_handle_languages_command_success(self, mock_args: Mock) -> None:
        """Test successful languages command"""
        with patch(
            "tree_sitter_analyzer.interfaces.cli.api.get_supported_languages"
        ) as mock_get_langs:
            mock_get_langs.return_value = ["python", "java", "javascript"]

            with patch("builtins.print") as mock_print:
                result = handle_languages_command(mock_args)

            assert result == 0
            mock_get_langs.assert_called_once()
            mock_print.assert_called()

    def test_handle_languages_command_with_extensions(self, mock_args: Mock) -> None:
        """Test languages command with extensions"""
        mock_args.extensions = True

        with patch(
            "tree_sitter_analyzer.interfaces.cli.api.get_supported_languages"
        ) as mock_get_langs:
            with patch(
                "tree_sitter_analyzer.interfaces.cli.api.get_file_extensions"
            ) as mock_get_exts:
                mock_get_langs.return_value = ["python"]
                mock_get_exts.return_value = [".py"]

                with patch("builtins.print"):
                    result = handle_languages_command(mock_args)

                assert result == 0
                mock_get_exts.assert_called_with("python")

    def test_handle_languages_command_json_output(self, mock_args: Mock) -> None:
        """Test languages command with JSON output"""
        mock_args.output = "json"

        with patch(
            "tree_sitter_analyzer.interfaces.cli.api.get_supported_languages"
        ) as mock_get_langs:
            mock_get_langs.return_value = ["python", "java"]

            with patch("builtins.print") as mock_print:
                result = handle_languages_command(mock_args)

            assert result == 0
            # Check that JSON was printed
            mock_print.assert_called()
            printed_content = mock_print.call_args[0][0]
            assert isinstance(printed_content, str)


class TestHandleInfoCommand:
    """Test handle_info_command function"""

    @pytest.fixture
    def mock_args(self) -> Mock:
        """Create mock arguments"""
        args = Mock()
        args.output = "text"
        return args

    def test_handle_info_command_success(self, mock_args: Mock) -> None:
        """Test successful info command"""
        with patch(
            "tree_sitter_analyzer.interfaces.cli.api.get_framework_info"
        ) as mock_get_info:
            mock_get_info.return_value = {
                "name": "tree-sitter-analyzer",
                "version": "2.0.0",
                "total_languages": 3,
            }

            with patch("builtins.print") as mock_print:
                result = handle_info_command(mock_args)

            assert result == 0
            mock_get_info.assert_called_once()
            mock_print.assert_called()

    def test_handle_info_command_json_output(self, mock_args: Mock) -> None:
        """Test info command with JSON output"""
        mock_args.output = "json"

        with patch(
            "tree_sitter_analyzer.interfaces.cli.api.get_framework_info"
        ) as mock_get_info:
            mock_get_info.return_value = {"name": "test"}

            with patch("builtins.print") as mock_print:
                result = handle_info_command(mock_args)

            assert result == 0
            # Check that JSON was printed
            printed_content = mock_print.call_args[0][0]
            assert isinstance(printed_content, str)


class TestHandleQueriesCommand:
    """Test handle_queries_command function"""

    @pytest.fixture
    def mock_args(self) -> Mock:
        """Create mock arguments"""
        args = Mock()
        args.language = "python"
        args.output = "text"
        return args

    def test_handle_queries_command_success(self, mock_args: Mock) -> None:
        """Test successful queries command"""
        with patch(
            "tree_sitter_analyzer.interfaces.cli.api.is_language_supported"
        ) as mock_is_supported:
            with patch(
                "tree_sitter_analyzer.interfaces.cli.api.get_available_queries"
            ) as mock_get_queries:
                mock_is_supported.return_value = True
                mock_get_queries.return_value = ["functions", "classes"]

                with patch("builtins.print") as mock_print:
                    result = handle_queries_command(mock_args)

                assert result == 0
                mock_is_supported.assert_called_with("python")
                mock_get_queries.assert_called_with("python")
                mock_print.assert_called()

    def test_handle_queries_command_unsupported_language(self, mock_args: Mock) -> None:
        """Test queries command with unsupported language"""
        with patch(
            "tree_sitter_analyzer.interfaces.cli.api.is_language_supported"
        ) as mock_is_supported:
            mock_is_supported.return_value = False

            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                result = handle_queries_command(mock_args)

            assert result == 1
            assert "not supported" in mock_stderr.getvalue()


class TestFormatFunctions:
    """Test format output functions"""

    def test_format_analysis_output_success(self) -> None:
        """Test format_analysis_output with successful result"""
        result = {
            "success": True,
            "file_info": {"path": "test.py"},
            "language_info": {"language": "python", "auto_detected": True},
            "ast_info": {"source_lines": 10, "node_count": 25},
            "query_results": {"functions": [{"name": "test"}]},
            "elements": [{"type": "function", "name": "test"}],
        }

        with patch("builtins.print") as mock_print:
            format_analysis_output(result, "text")

        mock_print.assert_called()

    def test_format_analysis_output_failure(self) -> None:
        """Test format_analysis_output with failed result"""
        result = {"success": False, "error": "Test error"}

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            format_analysis_output(result, "text")

        assert "Test error" in mock_stderr.getvalue()

    def test_format_extraction_output_success(self) -> None:
        """Test format_extraction_output with successful result"""
        result = {
            "success": True,
            "file_path": "test.py",
            "language": "python",
            "elements": [{"name": "test", "type": "function", "start_line": 1}],
        }

        with patch("builtins.print") as mock_print:
            format_extraction_output(result, "text")

        mock_print.assert_called()

    def test_format_query_output_success(self) -> None:
        """Test format_query_output with successful result"""
        result = {
            "success": True,
            "file_path": "test.py",
            "language": "python",
            "query_name": "functions",
            "results": [{"start_line": 1, "content": "def test(): pass"}],
        }

        with patch("builtins.print") as mock_print:
            format_query_output(result, "text")

        mock_print.assert_called()

    def test_format_validation_output(self) -> None:
        """Test format_validation_output"""
        result = {
            "valid": True,
            "exists": True,
            "readable": True,
            "language": "python",
            "supported": True,
            "errors": [],
        }

        with patch("builtins.print") as mock_print:
            format_validation_output(result, "text")

        mock_print.assert_called()


class TestMainFunction:
    """Test main function"""

    def test_main_analyze_command(self) -> None:
        """Test main function with analyze command"""
        test_args = ["analyze", "test.py"]

        with patch("sys.argv", ["cli"] + test_args):
            with patch(
                "tree_sitter_analyzer.interfaces.cli.handle_analyze_command"
            ) as mock_handle:
                mock_handle.return_value = 0

                result = main()

                assert result == 0
                mock_handle.assert_called_once()

    def test_main_no_command(self) -> None:
        """Test main function with no command"""
        with patch("sys.argv", ["cli"]):
            with patch(
                "tree_sitter_analyzer.interfaces.cli.create_parser"
            ) as mock_create_parser:
                mock_parser = Mock()
                mock_parser.parse_args.return_value = Mock(command=None)
                mock_create_parser.return_value = mock_parser

                result = main()

                assert result == 1
                mock_parser.print_help.assert_called_once()

    def test_main_with_verbose(self) -> None:
        """Test main function with verbose flag"""
        test_args = ["--verbose", "info"]

        with patch("sys.argv", ["cli"] + test_args):
            with patch(
                "tree_sitter_analyzer.interfaces.cli.handle_info_command"
            ) as mock_handle:
                with patch("logging.getLogger") as mock_get_logger:
                    mock_logger = Mock()
                    mock_get_logger.return_value = mock_logger
                    mock_handle.return_value = 0

                    result = main()

                    assert result == 0
                    mock_logger.setLevel.assert_called()

    def test_main_with_quiet(self) -> None:
        """Test main function with quiet flag"""
        test_args = ["--quiet", "info"]

        with patch("sys.argv", ["cli"] + test_args):
            with patch(
                "tree_sitter_analyzer.interfaces.cli.handle_info_command"
            ) as mock_handle:
                with patch("logging.getLogger") as mock_get_logger:
                    mock_logger = Mock()
                    mock_get_logger.return_value = mock_logger
                    mock_handle.return_value = 0

                    result = main()

                    assert result == 0
                    mock_logger.setLevel.assert_called()


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_handle_command_with_api_exception(self) -> None:
        """Test command handlers with API exceptions"""
        mock_args = Mock()
        mock_args.file_path = "test.py"
        mock_args.output = "text"

        with patch(
            "tree_sitter_analyzer.interfaces.cli.api.validate_file"
        ) as mock_validate:
            mock_validate.side_effect = Exception("API error")

            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                result = handle_validate_command(mock_args)

            assert result == 1
            assert "API error" in mock_stderr.getvalue()

    def test_format_output_with_missing_data(self) -> None:
        """Test format functions with missing data"""
        result = {"success": True}  # Minimal data

        with patch("builtins.print") as mock_print:
            format_analysis_output(result, "text")

        mock_print.assert_called()

    def test_format_query_output_long_content(self) -> None:
        """Test format_query_output with long content"""
        result = {
            "success": True,
            "file_path": "test.py",
            "language": "python",
            "query_name": "functions",
            "results": [
                {
                    "start_line": 1,
                    "content": "def very_long_function_name_that_exceeds_fifty_characters(): pass",
                }
            ],
        }

        with patch("builtins.print") as mock_print:
            format_query_output(result, "text")

        mock_print.assert_called()
        # Check that content was truncated
        call_args = mock_print.call_args_list
        output_text = str(call_args)
        assert "..." in output_text
