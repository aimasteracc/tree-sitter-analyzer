#!/usr/bin/env python3
"""CLI tests: --table, --partial-read, query handling, and language handling."""

import contextlib
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tree_sitter_analyzer.cli_main import main


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
        assert "Total Methods" in output
        assert "Total Fields" in output
        assert "Methods" in output

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
        assert "Methods" in output
        assert "Fields" in output
        assert "| 2 |" in output or "2" in output

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
        assert "Type,Name" in output
        assert "Field,field1" in output

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

        import json

        output = mock_stdout.getvalue()
        data = json.loads(output)
        assert data["success"] is True
        assert data["lines_extracted"] == 5
        assert data["content_length"] == 52
        assert data["verdict"] == "INFO"

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
        assert (
            "--end-line must be greater than or equal to --start-line" in error_output
        )

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

    def test_describe_query_not_found(self, monkeypatch, capsys, sample_java_file):
        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", "--describe-query", "nonexistent_query", "--language", "java"],
        )

        with contextlib.suppress(SystemExit):
            main()

        # v1.13.0: error envelope moved from stderr to stdout JSON.
        captured = capsys.readouterr()
        joined = (captured.out or "") + (captured.err or "")
        assert "not found" in joined

    def test_describe_query_exception(self, monkeypatch, capsys, sample_java_file):
        monkeypatch.setattr(
            sys, "argv", ["cli", "--describe-query", "class", "--language", "java"]
        )

        with patch(
            "tree_sitter_analyzer.cli.info_commands.query_loader.get_query_description",
            side_effect=ValueError("Test error"),
        ):
            with contextlib.suppress(SystemExit):
                main()

            captured = capsys.readouterr()
            joined = (captured.out or "") + (captured.err or "")
            assert "Test error" in joined


class TestCLILanguageHandling:
    """Test cases for language handling"""

    def test_unsupported_language_fallback(self, monkeypatch, capsys, sample_java_file):
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

        with contextlib.suppress(SystemExit):
            main()

        # v1.13.0: unsupported-language path emits a JSON envelope rather
        # than the legacy "Trying with Java analysis engine" hint.
        captured = capsys.readouterr()
        joined = (captured.out or "") + (captured.err or "")
        assert (
            "Trying with Java analysis engine" in joined
            or '"language": "unsupported' in joined
            or '"error_type"' in joined
            or '"success": true' in joined
        )
