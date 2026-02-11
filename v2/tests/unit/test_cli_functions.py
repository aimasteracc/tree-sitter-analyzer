"""
Unit tests for CLI interface.

Tests CLI functions directly (not via subprocess) to achieve coverage.
"""

import argparse
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def fixtures_dir():
    """Return path to analyze test fixtures."""
    return Path(__file__).parent.parent / "fixtures" / "analyze_fixtures"


@pytest.fixture
def search_fixtures_dir():
    """Return path to search test fixtures."""
    return Path(__file__).parent.parent / "fixtures" / "search_fixtures"


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_parser_has_subcommands(self):
        """Parser should have analyze, search-files, search-content subcommands."""
        from tree_sitter_analyzer_v2.cli.main import create_parser

        parser = create_parser()
        # Verify parser is created without errors
        assert isinstance(parser, argparse.ArgumentParser)

    def test_parse_analyze_command(self):
        """Parser should parse analyze command with file path."""
        from tree_sitter_analyzer_v2.cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["analyze", "test.py"])
        assert args.command == "analyze"
        assert args.file_path == "test.py"
        assert args.format == "markdown"  # Default
        assert args.summary is False  # Default

    def test_parse_analyze_with_toon_format(self):
        """Parser should parse format flag."""
        from tree_sitter_analyzer_v2.cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["analyze", "test.py", "--format", "toon"])
        assert args.format == "toon"

    def test_parse_analyze_with_summary(self):
        """Parser should parse summary flag."""
        from tree_sitter_analyzer_v2.cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["analyze", "test.py", "--summary"])
        assert args.summary is True

    def test_parse_search_files(self):
        """Parser should parse search-files command."""
        from tree_sitter_analyzer_v2.cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["search-files", "/some/dir", "*.py"])
        assert args.command == "search-files"
        assert args.root_dir == "/some/dir"
        assert args.pattern == "*.py"

    def test_parse_search_files_default_pattern(self):
        """Parser should use '*' as default pattern."""
        from tree_sitter_analyzer_v2.cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["search-files", "/some/dir"])
        assert args.pattern == "*"

    def test_parse_search_content(self):
        """Parser should parse search-content command."""
        from tree_sitter_analyzer_v2.cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["search-content", "/some/dir", "pattern"])
        assert args.command == "search-content"
        assert args.root_dir == "/some/dir"
        assert args.pattern == "pattern"

    def test_parse_search_content_ignore_case(self):
        """Parser should parse --ignore-case flag."""
        from tree_sitter_analyzer_v2.cli.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["search-content", "/some/dir", "pattern", "-i"])
        assert args.ignore_case is True


class TestMainFunction:
    """Tests for the main() entry point."""

    def test_no_command_shows_help(self):
        """No command should show help and return 0."""
        from tree_sitter_analyzer_v2.cli.main import main

        with patch("sys.stdout", new_callable=StringIO):
            result = main([])
        assert result == 0

    def test_unknown_command(self):
        """Unknown command should return error."""
        from tree_sitter_analyzer_v2.cli.main import main

        # argparse exits on unknown command, so we need to catch SystemExit
        with pytest.raises(SystemExit):
            main(["unknown-command"])


class TestCmdAnalyze:
    """Tests for analyze command handler."""

    def test_analyze_nonexistent_file(self):
        """Analyzing nonexistent file returns error code."""
        from tree_sitter_analyzer_v2.cli.main import cmd_analyze, create_parser

        parser = create_parser()
        args = parser.parse_args(["analyze", "nonexistent_file.py"])

        with patch("sys.stderr", new_callable=StringIO) as mock_err:
            result = cmd_analyze(args)

        assert result == 1
        assert "not found" in mock_err.getvalue().lower() or "error" in mock_err.getvalue().lower()

    def test_analyze_python_file_default(self, fixtures_dir):
        """Analyzing a Python file with default format."""
        from tree_sitter_analyzer_v2.cli.main import cmd_analyze, create_parser

        sample = fixtures_dir / "sample.py"
        parser = create_parser()
        args = parser.parse_args(["analyze", str(sample)])

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            result = cmd_analyze(args)

        assert result == 0
        output = mock_out.getvalue()
        assert len(output) > 0

    def test_analyze_python_file_toon(self, fixtures_dir):
        """Analyzing a Python file with TOON format."""
        from tree_sitter_analyzer_v2.cli.main import cmd_analyze, create_parser

        sample = fixtures_dir / "sample.py"
        parser = create_parser()
        args = parser.parse_args(["analyze", str(sample), "--format", "toon"])

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            result = cmd_analyze(args)

        assert result == 0
        output = mock_out.getvalue()
        assert len(output) > 0

    def test_analyze_python_file_summary(self, fixtures_dir):
        """Analyzing a Python file with --summary flag."""
        from tree_sitter_analyzer_v2.cli.main import cmd_analyze, create_parser

        sample = fixtures_dir / "sample.py"
        parser = create_parser()
        args = parser.parse_args(["analyze", str(sample), "--summary"])

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            result = cmd_analyze(args)

        assert result == 0
        output = mock_out.getvalue()
        assert len(output) > 0

    def test_analyze_java_file(self, fixtures_dir):
        """Analyzing a Java file."""
        from tree_sitter_analyzer_v2.cli.main import cmd_analyze, create_parser

        sample = fixtures_dir / "Sample.java"
        parser = create_parser()
        args = parser.parse_args(["analyze", str(sample)])

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            result = cmd_analyze(args)

        assert result == 0
        output = mock_out.getvalue()
        assert len(output) > 0

    def test_analyze_typescript_file(self, fixtures_dir):
        """Analyzing a TypeScript file."""
        from tree_sitter_analyzer_v2.cli.main import cmd_analyze, create_parser

        sample = fixtures_dir / "sample.ts"
        parser = create_parser()
        args = parser.parse_args(["analyze", str(sample)])

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            result = cmd_analyze(args)

        assert result == 0
        output = mock_out.getvalue()
        assert len(output) > 0

    def test_analyze_unsupported_language(self, tmp_path):
        """Analyzing unsupported language returns error."""
        from tree_sitter_analyzer_v2.cli.main import cmd_analyze, create_parser

        test_file = tmp_path / "test.xyz"
        test_file.write_text("unknown language content")
        parser = create_parser()
        args = parser.parse_args(["analyze", str(test_file)])

        with patch("sys.stderr", new_callable=StringIO) as mock_err:
            result = cmd_analyze(args)

        assert result == 1
        assert "error" in mock_err.getvalue().lower()


class TestCmdSearchFiles:
    """Tests for search-files command handler."""

    def test_search_files_in_directory(self, search_fixtures_dir):
        """Search files in a directory."""
        from tree_sitter_analyzer_v2.cli.main import cmd_search_files, create_parser

        parser = create_parser()
        args = parser.parse_args(["search-files", str(search_fixtures_dir), "*.py"])

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            result = cmd_search_files(args)

        assert result == 0
        output = mock_out.getvalue()
        assert "sample1.py" in output

    def test_search_files_nonexistent_dir(self):
        """Search in nonexistent directory returns error."""
        from tree_sitter_analyzer_v2.cli.main import cmd_search_files, create_parser

        parser = create_parser()
        args = parser.parse_args(["search-files", "/nonexistent/path", "*.py"])

        with patch("sys.stderr", new_callable=StringIO) as mock_err:
            result = cmd_search_files(args)

        assert result == 1
        assert "not found" in mock_err.getvalue().lower()


class TestCmdSearchContent:
    """Tests for search-content command handler."""

    def test_search_content_finds_matches(self, search_fixtures_dir):
        """Search content should find matches."""
        from tree_sitter_analyzer_v2.cli.main import cmd_search_content, create_parser

        parser = create_parser()
        args = parser.parse_args(["search-content", str(search_fixtures_dir), "class"])

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            result = cmd_search_content(args)

        assert result == 0
        output = mock_out.getvalue()
        # Should contain file:line:content format
        assert len(output) > 0

    def test_search_content_nonexistent_dir(self):
        """Search in nonexistent directory returns error."""
        from tree_sitter_analyzer_v2.cli.main import cmd_search_content, create_parser

        parser = create_parser()
        args = parser.parse_args(["search-content", "/nonexistent/path", "pattern"])

        with patch("sys.stderr", new_callable=StringIO) as mock_err:
            result = cmd_search_content(args)

        assert result == 1
        assert "not found" in mock_err.getvalue().lower()

    def test_search_content_case_insensitive(self, search_fixtures_dir):
        """Case-insensitive search."""
        from tree_sitter_analyzer_v2.cli.main import cmd_search_content, create_parser

        parser = create_parser()
        args = parser.parse_args([
            "search-content",
            str(search_fixtures_dir),
            "CLASS",
            "--ignore-case",
        ])

        with patch("sys.stdout", new_callable=StringIO):
            result = cmd_search_content(args)

        assert result == 0
