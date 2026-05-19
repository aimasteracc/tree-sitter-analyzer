#!/usr/bin/env python3
"""CLI tests: --table, --partial-read, query handling, and language handling."""

import contextlib
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

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


class TestCLITableOption:
    """Test cases for --table option"""

    def test_table_option_full(self, monkeypatch, sample_java_file):
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

        assert "Total Methods" in output
        assert "Total Fields" in output
        assert "Public Methods" in output or "Methods" in output

    def test_table_option_full_strict(self, monkeypatch, sample_java_file):
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

        lines = output.split("\n")
        method_count = 0
        field_count = 0
        in_class_info = False

        for line in lines:
            line = line.strip()
            if "## Class Info" in line:
                in_class_info = True
                continue
            elif line.startswith("## ") and in_class_info:
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

        assert method_count == 2, f"Expected 2 methods in table, got {method_count}"
        assert field_count == 1, f"Expected 1 field in table, got {field_count}"

    def test_table_option_compact(self, monkeypatch, sample_java_file):
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
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--table", "full", "--project-root", sample_dir],
        )

        with patch(
            "tree_sitter_analyzer.core.analysis_engine.UnifiedAnalysisEngine.analyze"
        ) as mock_analyze:
            from tree_sitter_analyzer.models import AnalysisResult

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
        assert "--end-line must be greater than or equal to --start-line" in error_output

    def test_partial_read_invalid_start_column(self, monkeypatch, sample_java_file):
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
