#!/usr/bin/env python3
"""Core CLI tests — advanced options, summary, structure, table formatting."""

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

        # Parse the output to extract element counts (text format without quotes)
        lines = output.split("\n")
        element_counts = {}

        for line in lines:
            line = line.strip()
            if line.startswith("Classes: "):
                element_counts["classes"] = int(line.split(": ")[1])
            elif line.startswith("Methods: "):
                element_counts["methods"] = int(line.split(": ")[1])
            elif line.startswith("Fields: "):
                element_counts["fields"] = int(line.split(": ")[1])
            elif line.startswith("Imports: "):
                element_counts["imports"] = int(line.split(": ")[1])

        # Verify expected counts for the sample file
        assert element_counts.get("classes", 0) == 1, (
            f"Expected 1 class, got {element_counts.get('classes', 0)}"
        )
        assert element_counts.get("methods", 0) == 2, (
            f"Expected 2 methods, got {element_counts.get('methods', 0)}"
        )
        assert element_counts.get("fields", 0) == 1, (
            f"Expected 1 field, got {element_counts.get('fields', 0)}"
        )
        assert element_counts.get("imports", 0) == 1, (
            f"Expected 1 import, got {element_counts.get('imports', 0)}"
        )

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


