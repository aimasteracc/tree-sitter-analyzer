#!/usr/bin/env python3
"""CLI tests: query execution, logging, and additional coverage."""

import contextlib
import logging
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.cli_main import main


@pytest.fixture
def sample_java_file():
    java_code = """
package com.example.test;

import java.util.List;

/**
 * Sample class for testing
 */
public class TestClass {
    private String field1;

    /**
     * Constructor
     */
    public TestClass(String field1) {
        this.field1 = field1;
    }

    /**
     * Public method
     */
    public String getField1() {
        return field1;
    }
}
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".java", delete=False, encoding="utf-8"
    ) as f:
        f.write(java_code)
        temp_path = f.name

    yield temp_path

    if Path(temp_path).exists():
        Path(temp_path).unlink()


class TestCLIQueryExecution:
    """Test cases for query execution"""

    def test_query_execution_no_results(self, monkeypatch, sample_java_file):
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

            async def mock_execute_query(*args, **kwargs):
                return []

            def mock_get_available_queries(language):
                return ["methods", "class", "imports"]

            mock_query_service.execute_query = mock_execute_query
            mock_query_service.get_available_queries = mock_get_available_queries
            mock_query_service_class.return_value = mock_query_service

            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            with contextlib.suppress(SystemExit):
                main()

            output = mock_stdout.getvalue()
            assert "No results found matching the query" in output

    def test_query_execution_parse_failure(self, monkeypatch, sample_java_file):
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

            mock_logger.setLevel.assert_called_with(logging.ERROR)


pytestmark = [pytest.mark.unit]


class TestCLIAdditionalCoverage:
    """Additional test cases to improve CLI coverage"""

    def test_show_supported_languages(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cli", "--show-supported-languages"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Supported languages" in output

    def test_show_supported_extensions(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cli", "--show-supported-extensions"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Supported file extensions" in output

    def test_show_common_queries(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cli", "--show-common-queries"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0

    def test_show_query_languages(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cli", "--show-query-languages"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Languages with query support" in output

    def test_list_queries_with_language(self, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", ["cli", "--list-queries", "--language", "java"]
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Available query keys" in output

    def test_list_queries_with_file(self, monkeypatch, sample_java_file):
        monkeypatch.setattr(sys, "argv", ["cli", "--list-queries", sample_java_file])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Available query keys" in output

    def test_list_queries_all_languages(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cli", "--list-queries"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Supported languages" in output

    def test_describe_query_with_language(self, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", ["cli", "--describe-query", "class", "--language", "java"]
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Query key 'class'" in output

    def test_describe_query_with_file(self, monkeypatch, sample_java_file):
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
        assert "Query key 'class'" in output

    def test_describe_query_missing_language_and_file(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cli", "--describe-query", "class"])
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert (
            "Query description display requires --language or target file specification"
            in error_output
        )

    def test_missing_file_path_error(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cli"])
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "File path not specified" in error_output

    def test_nonexistent_file_error(self, monkeypatch):
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

    def test_unknown_language_detection(self, monkeypatch):
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
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "Could not determine language for file" in error_output

        if Path(unknown_file).exists():
            Path(unknown_file).unlink()

    def test_unsupported_language_fallback(self, monkeypatch, sample_java_file):
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
        assert "Trying with Java analysis engine" in output

    def test_query_string_option(self, monkeypatch, sample_java_file):
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
