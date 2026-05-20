#!/usr/bin/env python3
"""CLI tests: --advanced, --summary, and --structure options."""

import contextlib
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tree_sitter_analyzer.cli_main import main


class TestCLIAdvancedOptions:
    """Test cases for advanced CLI options"""

    def test_advanced_option_json_output(self, monkeypatch, sample_java_file):
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

        assert "Classes: 1" in output
        assert "Methods: 2" in output
        assert "Fields: 1" in output
        assert "Imports: 1" in output

    def test_advanced_option_text_output_strict(self, monkeypatch, sample_java_file):
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

        assert element_counts.get("classes", 0) == 1
        assert element_counts.get("methods", 0) == 2
        assert element_counts.get("fields", 0) == 1
        assert element_counts.get("imports", 0) == 1

    def test_advanced_option_analysis_failure(self, monkeypatch, sample_java_file):
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--advanced", "--project-root", sample_dir],
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

    def test_statistics_option(self, monkeypatch, sample_java_file):
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
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--summary", "--project-root", sample_dir],
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


class TestCLIStructureOption:
    """Test cases for --structure option"""

    def test_structure_option_json(self, monkeypatch, sample_java_file):
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
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", sample_java_file, "--structure", "--project-root", sample_dir],
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
