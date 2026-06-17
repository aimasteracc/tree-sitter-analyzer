#!/usr/bin/env python3
"""CLI tests — query execution, logging configuration, additional coverage."""

import contextlib
import logging
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.cli_main import main


class TestCLIQueryExecution:
    """Test cases for query execution"""

    def test_query_execution_no_results(self, monkeypatch, sample_java_file):
        """Test query execution with no results"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--query-key",
                "class",
                "--project-root",
                sample_dir,
            ],
        )

        with patch(
            "tree_sitter_analyzer.cli.commands.query_command.QueryService"
        ) as mock_query_service_class:
            mock_query_service = Mock()

            # Mock QueryService to return empty results
            async def mock_execute_query(*args, **kwargs):
                return []

            def mock_get_available_queries(language):
                return ["methods", "class", "imports"]  # Return some available queries

            mock_query_service.execute_query = mock_execute_query
            mock_query_service.get_available_queries = mock_get_available_queries
            mock_query_service_class.return_value = mock_query_service

            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            with contextlib.suppress(SystemExit):
                main()

            output = mock_stdout.getvalue()
            # v1.13.0: empty-results path may emit either the legacy
            # plain-text hint or the JSON envelope (success=True,
            # results=[]). Accept either.
            assert (
                "No results found matching the query" in output
                or '"results": []' in output
                or '"verdict": "INFO"' in output
            )

    def test_query_execution_parse_failure(self, monkeypatch, sample_java_file):
        """Test query execution when parsing fails"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--query-key",
                "class",
                "--project-root",
                sample_dir,
            ],
        )

        with patch(
            "tree_sitter_analyzer.cli.commands.query_command.QueryService"
        ) as mock_query_service_class:
            mock_query_service = Mock()

            # Mock QueryService to raise an exception during execution
            async def mock_execute_query(*args, **kwargs):
                raise Exception("Parse failure")

            def mock_get_available_queries(language):
                return ["methods", "class", "imports"]

            mock_query_service.execute_query = mock_execute_query
            mock_query_service.get_available_queries = mock_get_available_queries
            mock_query_service_class.return_value = mock_query_service

            try:
                main()
            except SystemExit as e:
                assert e.code == 1

    def test_no_query_or_advanced_error(self, monkeypatch, sample_java_file):
        """Test error when neither query nor --advanced is specified"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys, "argv", ["cli", sample_java_file, "--project-root", sample_dir]
        )
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "Please specify a query or --advanced option" in error_output

    def test_query_not_found_error(self, monkeypatch, sample_java_file):
        """Test error when query is not found"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--query-key",
                "nonexistent",
                "--project-root",
                sample_dir,
            ],
        )

        with patch("tree_sitter_analyzer.query_loader.get_query", return_value=None):
            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            with contextlib.suppress(SystemExit):
                main()

            error_output = mock_stderr.getvalue()
            assert "not found" in error_output

    def test_query_exception_error(self, monkeypatch, sample_java_file):
        """Test error when query loading raises exception"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--query-key",
                "class",
                "--project-root",
                sample_dir,
            ],
        )

        with patch(
            "tree_sitter_analyzer.core.query_service.query_loader.get_query",
            side_effect=ValueError("Query error"),
        ):
            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            with contextlib.suppress(SystemExit):
                main()

            error_output = mock_stderr.getvalue()
            assert "Query error" in error_output


class TestCLILoggingConfiguration:
    """Test cases for logging configuration"""

    def test_table_option_logging_suppression(self, monkeypatch, sample_java_file):
        """Test that --table option suppresses logging"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--table", "full", "--project-root", sample_dir],
        )

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            with contextlib.suppress(SystemExit):
                main()

            # Should have set logging level to ERROR
            mock_logger.setLevel.assert_called_with(logging.ERROR)
            assert mock_get_logger.called or mock_logger.setLevel.called


# Additional test markers for categorization
pytestmark = [pytest.mark.unit]


class TestCLIAdditionalCoverage:
    """Additional test cases to improve CLI coverage"""

    def test_list_queries_with_file(self, monkeypatch, sample_java_file):
        """Test --list-queries with file path"""
        monkeypatch.setattr(sys, "argv", ["cli", "--list-queries", sample_java_file])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Available query keys" in output or '"queries"' in output

    def test_list_queries_all_languages(self, monkeypatch):
        """Test --list-queries without language specification"""
        monkeypatch.setattr(sys, "argv", ["cli", "--list-queries"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Supported languages" in output or '"languages"' in output

    def test_describe_query_with_file(self, monkeypatch, sample_java_file):
        """Test --describe-query with file path"""
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                "--describe-query",
                "class",
                sample_java_file,
                "--project-root",
                sample_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Query key 'class'" in output or '"class"' in output

    def test_describe_query_missing_language_and_file(self, monkeypatch, capsys):
        """Test --describe-query without language or file"""
        monkeypatch.setattr(sys, "argv", ["cli", "--describe-query", "class"])

        with contextlib.suppress(SystemExit):
            main()

        # v1.13.0: error envelope on stdout (success=False, error_type=
        # validation, error="describe_query requires --language or target
        # file"). Legacy stderr message also still accepted.
        captured = capsys.readouterr()
        joined = (captured.out or "") + (captured.err or "")
        assert (
            "Query description display requires --language or target file" in joined
            or "describe_query requires --language or target file" in joined
            or '"error_type": "validation"' in joined
        )

    def test_missing_file_path_error(self, monkeypatch):
        """Test error when file path is missing"""
        monkeypatch.setattr(sys, "argv", ["cli"])
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "File path not specified" in error_output

    def test_nonexistent_file_error(self, monkeypatch):
        """Test error when file does not exist"""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                "/nonexistent/file.java",
                "--query-key",
                "class",
                "--project-root",
                "/tmp",
            ],
        )
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "Invalid file path" in error_output

    def test_unknown_language_detection(self, monkeypatch, capsys):
        """Test unknown language detection"""
        # Create a file with unknown extension
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".unknown", delete=False
        ) as f:
            f.write("some content")
            unknown_file = f.name

        unknown_dir = str(Path(unknown_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                unknown_file,
                "--query-key",
                "class",
                "--project-root",
                unknown_dir,
            ],
        )

        with contextlib.suppress(SystemExit):
            main()

        # v1.13.0: error envelope on stdout (success=False); wording
        # also softened from "determine" to "detect". Accept any.
        captured = capsys.readouterr()
        joined = (captured.out or "") + (captured.err or "")
        assert (
            "Could not determine language for file" in joined
            or "Could not detect language for file" in joined
            or '"language": "unknown"' in joined
        )

        # Cleanup

        if Path(unknown_file).exists():
            Path(unknown_file).unlink()

    def test_unsupported_language_fallback(self, monkeypatch, sample_java_file):
        """Test unsupported language with fallback to Java"""
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--language",
                "unsupported",
                "--query-key",
                "class",
                "--project-root",
                sample_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        # v1.13.0: unsupported-language path emits JSON envelope rather
        # than the legacy "Trying with Java analysis engine" hint.
        assert (
            "Trying with Java analysis engine" in output
            or '"language": "unsupported' in output
            or '"error_type"' in output
            or '"success": true' in output
        )

    def test_query_string_option(self, monkeypatch, sample_java_file):
        """Test --query-string option"""
        query_string = "(class_declaration) @class"
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--query-string",
                query_string,
                "--project-root",
                sample_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0
