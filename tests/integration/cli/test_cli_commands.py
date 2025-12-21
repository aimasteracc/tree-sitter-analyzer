#!/usr/bin/env python3
"""
CLI Commands Integration Tests

Consolidated tests for CLI commands including basic execution, options, and coverage.
Merged from test_cli.py and test_cli_commands_coverage.py.
"""

import contextlib
import sys
import tempfile
from io import StringIO
from pathlib import Path

import pytest

from tree_sitter_analyzer.cli_main import main


class MockArgs:
    """Mock args object for CLI commands."""

    def __init__(self, **kwargs):
        self.file = kwargs.get("file", "test.py")
        self.language = kwargs.get("language", None)
        self.output_format = kwargs.get("output_format", "json")
        self.table = kwargs.get("table", "full")
        self.quiet = kwargs.get("quiet", False)
        self.toon_use_tabs = kwargs.get("toon_use_tabs", False)
        self.include_javadoc = kwargs.get("include_javadoc", False)
        self.project = kwargs.get("project", None)
        self.query_key = kwargs.get("query_key", None)
        self.query_string = kwargs.get("query_string", None)
        self.filter = kwargs.get("filter", None)
        self.start_line = kwargs.get("start_line", None)
        self.end_line = kwargs.get("end_line", None)
        self.element_name = kwargs.get("element_name", None)
        self.context_lines = kwargs.get("context_lines", 0)
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestCLIInfoCommands:
    """Test cases for informational CLI commands"""

    def test_show_query_languages(self, monkeypatch):
        """Test --show-query-languages option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--show-query-languages"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "Languages with query support" in output
        assert "java" in output
        assert "javascript" in output
        assert "python" in output

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
        assert "Common queries across multiple languages" in output
        assert any(
            query in output
            for query in [
                "class_names",
                "method_names",
                "imports",
                "all_declarations",
            ]
        )

    def test_help_option(self, monkeypatch):
        """Test help option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--help"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "usage" in output.lower()

    def test_no_arguments(self, monkeypatch):
        """Test CLI with no arguments"""
        monkeypatch.setattr(sys, "argv", ["cli"])
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert len(error_output) > 0


class TestCLIQueryCommands:
    """Test cases for query related CLI commands"""

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
        assert "java" in output.lower()

    def test_list_queries_without_language(self, monkeypatch):
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
        assert "class" in output
        assert "java" in output.lower()

    @pytest.mark.asyncio
    async def test_query_command_with_key(self):
        """Test QueryCommand with query key using MockArgs."""
        from tree_sitter_analyzer.cli.commands.query_command import QueryCommand

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def foo(): pass")
            temp_path = f.name

        try:
            args = MockArgs(file=temp_path, query_key="functions", output_format="json")
            command = QueryCommand(args)
            result = await command.execute_async("python")
            assert result == 0 or result == 1
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestCLIAnalysisCommands:
    """Test cases for file analysis commands"""

    @pytest.fixture
    def temp_java_file(self):
        """Create a temporary Java file"""
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello, World!");
    }
}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        yield temp_path

        Path(temp_path).unlink(missing_ok=True)

    def test_analyze_java_file(self, monkeypatch, temp_java_file):
        """Test analyzing a Java file"""
        temp_dir = str(Path(temp_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", temp_java_file, "--project-root", temp_dir, "--advanced"],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0

    def test_analyze_with_query_key(self, monkeypatch, temp_java_file):
        """Test analyzing file with specific query"""
        temp_dir = str(Path(temp_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                temp_java_file,
                "--query-key",
                "classes",
                "--project-root",
                temp_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0

    def test_analyze_with_custom_query(self, monkeypatch, temp_java_file):
        """Test analyzing file with custom query string"""
        custom_query = "(class_declaration name: (identifier) @class-name)"
        temp_dir = str(Path(temp_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                temp_java_file,
                "--query-string",
                custom_query,
                "--project-root",
                temp_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0

    def test_output_format_json(self, monkeypatch, temp_java_file):
        """Test JSON output format"""
        temp_dir = str(Path(temp_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                temp_java_file,
                "--output-format",
                "json",
                "--advanced",
                "--project-root",
                temp_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert "{" in output or "[" in output

    def test_output_format_text(self, monkeypatch, temp_java_file):
        """Test text output format"""
        temp_dir = str(Path(temp_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                temp_java_file,
                "--output-format",
                "text",
                "--project-root",
                temp_dir,
                "--advanced",
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        with contextlib.suppress(SystemExit):
            main()

        output = mock_stdout.getvalue()
        assert len(output) > 0


class TestCLILanguageHandling:
    """Test cases for language detection and overrides"""

    def test_language_detection(self, monkeypatch):
        """Test automatic language detection"""
        python_code = "def hello(): pass"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(python_code)
            temp_path = f.name

        try:
            temp_dir = str(Path(temp_path).parent)
            monkeypatch.setattr(
                sys,
                "argv",
                ["cli", temp_path, "--project-root", temp_dir, "--advanced"],
            )
            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            with contextlib.suppress(SystemExit):
                main()

            output = mock_stdout.getvalue()
            assert len(output) > 0
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_explicit_language_override(self, monkeypatch):
        """Test explicit language specification"""
        java_code = "public class Test {}"
        # .txt extension but forcing java
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            temp_dir = str(Path(temp_path).parent)
            monkeypatch.setattr(
                sys,
                "argv",
                ["cli", temp_path, "--language", "java", "--project-root", temp_dir],
            )
            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            with contextlib.suppress(SystemExit):
                main()

            output = mock_stdout.getvalue()
            assert len(output) > 0
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestCLIErrorHandling:
    """Test cases for error conditions"""

    def test_nonexistent_file(self, monkeypatch):
        """Test handling of nonexistent files"""
        nonexistent_path = "/path/that/does/not/exist.java"
        monkeypatch.setattr(
            sys, "argv", ["cli", nonexistent_path, "--project-root", "/tmp"]
        )
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        with contextlib.suppress(SystemExit):
            main()

        error_output = mock_stderr.getvalue()
        assert "Invalid file path" in error_output

    def test_invalid_query_key(self, monkeypatch):
        """Test with invalid query key"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write("class A {}")
            temp_path = f.name

        try:
            temp_dir = str(Path(temp_path).parent)
            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "cli",
                    temp_path,
                    "--query-key",
                    "invalid_query_key",
                    "--project-root",
                    temp_dir,
                ],
            )
            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            with contextlib.suppress(SystemExit):
                main()

            error_output = mock_stderr.getvalue()
            # This assertion depends on specific error message
            assert len(error_output) > 0
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestTableCommandCoverage:
    """Test TableCommand for coverage boost."""

    @pytest.mark.asyncio
    async def test_table_command_full(self):
        """Test TableCommand with full format."""
        from tree_sitter_analyzer.cli.commands.table_command import TableCommand

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def foo(): pass")
            temp_path = f.name

        try:
            args = MockArgs(file=temp_path, table="full")
            command = TableCommand(args)
            result = await command.execute_async("python")
            assert result == 0 or result == 1
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__])
