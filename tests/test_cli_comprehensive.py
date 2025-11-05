#!/usr/bin/env python3
"""
Comprehensive Tests for CLI module

This module provides comprehensive test coverage for the CLI functionality,
focusing on uncovered code paths to improve overall coverage.
Follows TDD principles and .roo-config.json requirements.
"""

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
    """Fixture providing a temporary Java file for testing"""
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

    # Cleanup
    if Path(temp_path).exists():
        Path(temp_path).unlink()


class TestCLIAdvancedOptions:
    """Test cases for advanced CLI options"""

    def test_advanced_option_json_output(self, monkeypatch, sample_java_file):
        """Test --advanced option with JSON output"""
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--advanced",
                "--output-format",
                "json",
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

    def test_advanced_option_text_output(self, monkeypatch, sample_java_file):
        """Test --advanced option with text output"""
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--advanced",
                "--output-format",
                "text",
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

        # Verify specific content - should show correct element counts
        assert "Classes: 1" in output
        assert (
            "Methods: 2" in output
        )  # Sample file has 2 methods (constructor + getField1)
        assert "Fields: 1" in output  # Sample file has 1 field
        assert "Imports: 1" in output  # Sample file has 1 import

    def test_advanced_option_text_output_strict(self, monkeypatch, sample_java_file):
        """Test --advanced option with strict content validation"""
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--advanced",
                "--output-format",
                "text",
                "--project-root",
                sample_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()

        # Parse the output to extract element counts
        lines = output.split("\n")
        element_counts = {}

        for line in lines:
            line = line.strip()
            if line.startswith('"Classes: '):
                element_counts["classes"] = int(line.split(": ")[1].rstrip('"'))
            elif line.startswith('"Methods: '):
                element_counts["methods"] = int(line.split(": ")[1].rstrip('"'))
            elif line.startswith('"Fields: '):
                element_counts["fields"] = int(line.split(": ")[1].rstrip('"'))
            elif line.startswith('"Imports: '):
                element_counts["imports"] = int(line.split(": ")[1].rstrip('"'))

        # Verify expected counts for the sample file
        assert (
            element_counts.get("classes", 0) == 1
        ), f"Expected 1 class, got {element_counts.get('classes', 0)}"
        assert (
            element_counts.get("methods", 0) == 2
        ), f"Expected 2 methods, got {element_counts.get('methods', 0)}"
        assert (
            element_counts.get("fields", 0) == 1
        ), f"Expected 1 field, got {element_counts.get('fields', 0)}"
        assert (
            element_counts.get("imports", 0) == 1
        ), f"Expected 1 import, got {element_counts.get('imports', 0)}"

    def test_advanced_option_analysis_failure(self, monkeypatch, sample_java_file):
        """Test --advanced option when analysis fails"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--advanced", "--project-root", sample_dir],
        )

        # Mock the UnifiedAnalysisEngine.analyze method to return failed result
        with patch(
            "tree_sitter_analyzer.core.analysis_engine.UnifiedAnalysisEngine.analyze"
        ) as mock_analyze:
            from tree_sitter_analyzer.models import AnalysisResult

            # Create a failed analysis result
            failed_result = AnalysisResult(
                file_path=sample_java_file,
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                language="java",
                success=False,
                error_message="Mocked analysis failure",
            )
            mock_analyze.return_value = failed_result

            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            with contextlib.suppress(SystemExit):
                main()

            error_output = mock_stderr.getvalue()
            assert "Analysis failed" in error_output

    def test_statistics_option(self, monkeypatch, sample_java_file):
        """Test --statistics option"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--advanced",
                "--statistics",
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

    def test_statistics_option_json(self, monkeypatch, sample_java_file):
        """Test --statistics option with JSON output"""
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--advanced",
                "--statistics",
                "--output-format",
                "json",
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


class TestCLISummaryOption:
    """Test cases for --summary option"""

    def test_summary_option_default(self, monkeypatch, sample_java_file):
        """Test --summary option with default types"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--summary", "--project-root", sample_dir],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0

    def test_summary_option_specific_types(self, monkeypatch, sample_java_file):
        """Test --summary option with specific types"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--summary=classes,methods,fields",
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

    def test_summary_option_json(self, monkeypatch, sample_java_file):
        """Test --summary option with JSON output"""
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--summary",
                "--output-format",
                "json",
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

    def test_summary_option_analysis_failure(self, monkeypatch, sample_java_file):
        """Test --summary option when analysis fails"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--summary", "--project-root", sample_dir],
        )

        # Mock the UnifiedAnalysisEngine.analyze method to return failed result
        with patch(
            "tree_sitter_analyzer.core.analysis_engine.UnifiedAnalysisEngine.analyze"
        ) as mock_analyze:
            from tree_sitter_analyzer.models import AnalysisResult

            # Create a failed analysis result
            failed_result = AnalysisResult(
                file_path=sample_java_file,
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                language="java",
                success=False,
                error_message="Mocked analysis failure",
            )
            mock_analyze.return_value = failed_result

            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            with contextlib.suppress(SystemExit):
                main()

            error_output = mock_stderr.getvalue()
            assert "Analysis failed" in error_output


class TestCLIStructureOption:
    """Test cases for --structure option"""

    def test_structure_option_json(self, monkeypatch, sample_java_file):
        """Test --structure option with JSON output"""
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--structure",
                "--output-format",
                "json",
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

    def test_structure_option_text(self, monkeypatch, sample_java_file):
        """Test --structure option with text output"""
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--structure",
                "--output-format",
                "text",
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

    def test_structure_option_analysis_failure(self, monkeypatch, sample_java_file):
        """Test --structure option when analysis fails"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--structure", "--project-root", sample_dir],
        )

        # Mock the UnifiedAnalysisEngine.analyze method to return failed result
        with patch(
            "tree_sitter_analyzer.core.analysis_engine.UnifiedAnalysisEngine.analyze"
        ) as mock_analyze:
            from tree_sitter_analyzer.models import AnalysisResult

            # Create a failed analysis result
            failed_result = AnalysisResult(
                file_path=sample_java_file,
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                language="java",
                success=False,
                error_message="Mocked analysis failure",
            )
            mock_analyze.return_value = failed_result

            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            with contextlib.suppress(SystemExit):
                main()

            error_output = mock_stderr.getvalue()
            assert "Analysis failed" in error_output


class TestCLITableOption:
    """Test cases for --table option"""

    def test_table_option_full(self, monkeypatch, sample_java_file):
        """Test --table option with full format"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--table", "full", "--project-root", sample_dir],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0

        # Verify table contains expected content
        assert "Total Methods" in output
        assert "Total Fields" in output
        assert "Public Methods" in output or "Methods" in output

    def test_table_option_full_strict(self, monkeypatch, sample_java_file):
        """Test --table option with strict content validation"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--table", "full", "--project-root", sample_dir],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()

        # Parse the output to extract method and field counts
        lines = output.split("\n")
        method_count = 0
        field_count = 0
        in_class_info = False

        for line in lines:
            line = line.strip()
            # Look for Total Methods and Total Fields in Class Info section
            if "## Class Info" in line:
                in_class_info = True
                continue
            elif line.startswith("## ") and in_class_info:
                # We've moved to another section
                in_class_info = False
                continue

            if in_class_info and "Total Methods" in line:
                parts = line.split("|")
                if len(parts) >= 3:
                    with contextlib.suppress(ValueError):
                        method_count = int(parts[2].strip())
            elif in_class_info and "Total Fields" in line:
                parts = line.split("|")
                if len(parts) >= 3:
                    with contextlib.suppress(ValueError):
                        field_count = int(parts[2].strip())

        # Verify expected counts for the sample file
        assert method_count == 2, f"Expected 2 methods in table, got {method_count}"
        assert field_count == 1, f"Expected 1 field in table, got {field_count}"

    def test_table_option_compact(self, monkeypatch, sample_java_file):
        """Test --table option with compact format"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--table",
                "compact",
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

    def test_table_option_csv(self, monkeypatch, sample_java_file):
        """Test --table option with CSV format"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--table", "csv", "--project-root", sample_dir],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0

    def test_table_option_analysis_failure(self, monkeypatch, sample_java_file):
        """Test --table option when analysis fails"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--table", "full", "--project-root", sample_dir],
        )

        # Mock the UnifiedAnalysisEngine.analyze method to return failed result
        with patch(
            "tree_sitter_analyzer.core.analysis_engine.UnifiedAnalysisEngine.analyze"
        ) as mock_analyze:
            from tree_sitter_analyzer.models import AnalysisResult

            # Create a failed analysis result
            failed_result = AnalysisResult(
                file_path=sample_java_file,
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                language="java",
                success=False,
                error_message="Mocked analysis failure",
            )
            mock_analyze.return_value = failed_result

            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            with contextlib.suppress(SystemExit):
                main()

            error_output = mock_stderr.getvalue()
            assert "Analysis failed" in error_output


class TestCLIPartialReadOption:
    """Test cases for --partial-read option"""

    def test_partial_read_basic(self, monkeypatch, sample_java_file):
        """Test --partial-read option with basic parameters"""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--partial-read",
                "--start-line",
                "1",
                "--end-line",
                "5",
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0

    def test_partial_read_missing_start_line(self, monkeypatch, sample_java_file):
        """Test --partial-read option without required --start-line"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--partial-read", "--project-root", sample_dir],
        )
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "--start-line is required" in error_output

    def test_partial_read_invalid_start_line(self, monkeypatch, sample_java_file):
        """Test --partial-read option with invalid start line"""
        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--partial-read", "--start-line", "0"],
        )
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "--start-line must be 1 or greater" in error_output

    def test_partial_read_invalid_end_line(self, monkeypatch, sample_java_file):
        """Test --partial-read option with invalid end line"""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--partial-read",
                "--start-line",
                "5",
                "--end-line",
                "3",
            ],
        )
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert (
            "--end-line must be greater than or equal to --start-line" in error_output
        )

    def test_partial_read_invalid_start_column(self, monkeypatch, sample_java_file):
        """Test --partial-read option with invalid start column"""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--partial-read",
                "--start-line",
                "1",
                "--start-column",
                "-1",
            ],
        )
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "--start-column must be 0 or greater" in error_output

    def test_partial_read_invalid_end_column(self, monkeypatch, sample_java_file):
        """Test --partial-read option with invalid end column"""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--partial-read",
                "--start-line",
                "1",
                "--end-column",
                "-1",
            ],
        )
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "--end-column must be 0 or greater" in error_output

    def test_partial_read_failure(self, monkeypatch, sample_java_file):
        """Test --partial-read option when reading fails"""
        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--partial-read", "--start-line", "1"],
        )

        with patch(
            "tree_sitter_analyzer.cli.commands.partial_read_command.read_file_partial",
            return_value=None,
        ):
            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            with contextlib.suppress(SystemExit):
                main()

            error_output = mock_stderr.getvalue()
            assert "Failed to read file partially" in error_output


class TestCLIQueryHandling:
    """Test cases for query handling"""

    def test_describe_query_not_found(self, monkeypatch, sample_java_file):
        """Test --describe-query with non-existent query"""
        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", "--describe-query", "nonexistent_query", "--language", "java"],
        )
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "not found" in error_output

    def test_describe_query_exception(self, monkeypatch, sample_java_file):
        """Test --describe-query with exception"""
        monkeypatch.setattr(
            sys, "argv", ["cli", "--describe-query", "class", "--language", "java"]
        )

        with patch(
            "tree_sitter_analyzer.cli.info_commands.query_loader.get_query_description",
            side_effect=ValueError("Test error"),
        ):
            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            with contextlib.suppress(SystemExit):
                main()

            error_output = mock_stderr.getvalue()
            assert "Test error" in error_output


class TestCLILanguageHandling:
    """Test cases for language handling"""

    def test_unsupported_language_fallback(self, monkeypatch, sample_java_file):
        """Test unsupported language with Java fallback"""
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--language",
                "unsupported_lang",
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
            assert "No results found matching the query" in output

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


# Additional test markers for categorization
pytestmark = [pytest.mark.unit]


class TestCLIAdditionalCoverage:
    """Additional test cases to improve CLI coverage"""

    def test_show_supported_languages(self, monkeypatch):
        """Test --show-supported-languages option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--show-supported-languages"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Supported languages" in output

    def test_show_supported_extensions(self, monkeypatch):
        """Test --show-supported-extensions option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--show-supported-extensions"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Supported file extensions" in output

    def test_show_common_queries(self, monkeypatch):
        """Test --show-common-queries option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--show-common-queries"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0

    def test_show_query_languages(self, monkeypatch):
        """Test --show-query-languages option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--show-query-languages"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Languages with query support" in output

    def test_list_queries_with_language(self, monkeypatch):
        """Test --list-queries with --language option"""
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
        """Test --list-queries with file path"""
        monkeypatch.setattr(sys, "argv", ["cli", "--list-queries", sample_java_file])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Available query keys" in output

    def test_list_queries_all_languages(self, monkeypatch):
        """Test --list-queries without language specification"""
        monkeypatch.setattr(sys, "argv", ["cli", "--list-queries"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Supported languages" in output

    def test_describe_query_with_language(self, monkeypatch):
        """Test --describe-query with --language option"""
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
        assert "Query key 'class'" in output

    def test_describe_query_missing_language_and_file(self, monkeypatch):
        """Test --describe-query without language or file"""
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

    def test_unknown_language_detection(self, monkeypatch):
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
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "Could not determine language for file" in error_output

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
        assert "Trying with Java analysis engine" in output

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
