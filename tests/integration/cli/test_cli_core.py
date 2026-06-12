#!/usr/bin/env python3
"""Core CLI tests — advanced options, summary, structure, table formatting."""

import contextlib
import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tree_sitter_analyzer.cli_main import main


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
        data = json.loads(output)
        assert data["success"] is True
        assert data["language"] == "java"
        assert data["line_count"] == 25
        assert data["class_count"] == 1
        assert data["method_count"] == 2
        assert data["field_count"] == 1
        assert data["import_count"] == 1
        assert (
            data["element_count"] == 6
        )  # 2 methods + class + field + import + package

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
        assert "--- Advanced Analysis Results ---" in output
        assert "Lines: 25" in output

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
        data = json.loads(output)
        assert data["success"] is True
        assert data["line_count"] == 25
        assert data["class_count"] == 1
        assert data["method_count"] == 2
        assert data["field_count"] == 1
        assert data["import_count"] == 1
        assert data["element_count"] == 6
        assert data["node_count"] == 76  # tree-sitter-java 0.23.5

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
        data = json.loads(output)
        assert data["success"] is True
        assert data["line_count"] == 25
        assert data["class_count"] == 1
        assert data["method_count"] == 2
        assert data["field_count"] == 1
        assert data["import_count"] == 1
        assert data["element_count"] == 6
        assert data["node_count"] == 76  # tree-sitter-java 0.23.5


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
        data = json.loads(output)
        assert data["success"] is True
        assert [c["name"] for c in data["summary"]["classes"]] == ["TestClass"]
        assert [m["name"] for m in data["summary"]["methods"]] == [
            "TestClass",
            "getField1",
        ]
        assert (
            "classes=1 methods=2 fields=0 imports=0 types=classes,methods"
            in data["summary_line"]
        )

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
        data = json.loads(output)
        assert data["success"] is True
        assert [c["name"] for c in data["summary"]["classes"]] == ["TestClass"]
        assert [m["name"] for m in data["summary"]["methods"]] == [
            "TestClass",
            "getField1",
        ]
        assert [f["name"] for f in data["summary"]["fields"]] == ["field1"]
        assert (
            "classes=1 methods=2 fields=1 imports=0 types=classes,methods,fields"
            in data["summary_line"]
        )

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
        data = json.loads(output)
        assert data["success"] is True
        assert [c["name"] for c in data["summary"]["classes"]] == ["TestClass"]
        assert [m["name"] for m in data["summary"]["methods"]] == [
            "TestClass",
            "getField1",
        ]
        assert (
            "classes=1 methods=2 fields=0 imports=0 types=classes,methods"
            in data["summary_line"]
        )

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
        data = json.loads(output)
        assert data["success"] is True
        assert data["statistics"] == {
            "class_count": 1,
            "method_count": 2,
            "field_count": 1,
            "import_count": 1,
            "total_lines": 25,
            "annotation_count": 0,
        }

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
        assert "--- Structure Analysis Results ---" in output
        assert "Package: com.example.test" in output
        assert "Classes: 1" in output
        assert "Methods: 2" in output
        assert "Fields: 1" in output
        assert "Imports: 1" in output
        assert "Total lines: 25" in output
        assert "- getField1" in output

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
