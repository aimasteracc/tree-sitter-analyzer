#!/usr/bin/env python3
"""Tests for _build_parser in search_content_cli module."""

from __future__ import annotations

import argparse

import pytest

from tree_sitter_analyzer.cli.commands.search_content_cli import _build_parser


class TestBuildParser:
    """Test argument parser construction."""

    def test_parser_creation(self) -> None:
        """Test parser is created successfully."""
        parser = _build_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        assert (
            "search" in parser.description.lower()
            or "ripgrep" in parser.description.lower()
        )

    def test_required_arguments(self) -> None:
        """Test required arguments are enforced."""
        parser = _build_parser()

        # Missing all required args should raise
        with pytest.raises(SystemExit):
            parser.parse_args([])

        # Missing --query should raise
        with pytest.raises(SystemExit):
            parser.parse_args(["--roots", "root1"])

        # Missing --roots or --files should raise
        with pytest.raises(SystemExit):
            parser.parse_args(["--query", "test"])

    def test_minimal_valid_arguments_with_roots(self) -> None:
        """Test minimal valid argument set with roots."""
        parser = _build_parser()
        args = parser.parse_args(["--roots", "root1", "--query", "test"])

        assert args.roots == ["root1"]
        assert args.query == "test"
        assert args.files is None
        assert args.output_format == "json"
        assert args.quiet is False

    def test_minimal_valid_arguments_with_files(self) -> None:
        """Test minimal valid argument set with files."""
        parser = _build_parser()
        args = parser.parse_args(["--files", "file1.py", "file2.py", "--query", "test"])

        assert args.files == ["file1.py", "file2.py"]
        assert args.query == "test"
        assert args.roots is None
        assert args.output_format == "json"
        assert args.quiet is False

    def test_roots_and_files_mutually_exclusive(self) -> None:
        """Test that --roots and --files cannot be used together."""
        parser = _build_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(
                ["--roots", "root1", "--files", "file1.py", "--query", "test"]
            )

    def test_multiple_roots(self) -> None:
        """Test multiple search roots."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "root1", "root2", "root3", "--query", "test"]
        )

        assert args.roots == ["root1", "root2", "root3"]

    def test_multiple_files(self) -> None:
        """Test multiple files."""
        parser = _build_parser()
        args = parser.parse_args(["--files", "a.py", "b.py", "c.py", "--query", "test"])

        assert args.files == ["a.py", "b.py", "c.py"]

    def test_output_format_options(self) -> None:
        """Test output format choices."""
        parser = _build_parser()

        # JSON format
        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--output-format", "json"]
        )
        assert args.output_format == "json"

        # Text format
        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--output-format", "text"]
        )
        assert args.output_format == "text"

        # Invalid format should raise
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["--roots", "root1", "--query", "test", "--output-format", "xml"]
            )

    def test_quiet_flag(self) -> None:
        """Test quiet flag."""
        parser = _build_parser()

        args = parser.parse_args(["--roots", "root1", "--query", "test", "--quiet"])
        assert args.quiet is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.quiet is False

    def test_case_options(self) -> None:
        """Test case sensitivity options."""
        parser = _build_parser()

        for case_val in ["smart", "insensitive", "sensitive"]:
            args = parser.parse_args(
                ["--roots", "root1", "--query", "test", "--case", case_val]
            )
            assert args.case == case_val

    def test_fixed_strings_flag(self) -> None:
        """Test fixed-strings flag."""
        parser = _build_parser()

        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--fixed-strings"]
        )
        assert args.fixed_strings is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.fixed_strings is False

    def test_word_flag(self) -> None:
        """Test word boundary flag."""
        parser = _build_parser()

        args = parser.parse_args(["--roots", "root1", "--query", "test", "--word"])
        assert args.word is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.word is False

    def test_multiline_flag(self) -> None:
        """Test multiline flag."""
        parser = _build_parser()

        args = parser.parse_args(["--roots", "root1", "--query", "test", "--multiline"])
        assert args.multiline is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.multiline is False

    def test_include_globs_option(self) -> None:
        """Test include-globs option."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--include-globs", "*.py", "*.js"]
        )
        assert args.include_globs == ["*.py", "*.js"]

    def test_exclude_globs_option(self) -> None:
        """Test exclude-globs option."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--exclude-globs", "*.txt", "*.md"]
        )
        assert args.exclude_globs == ["*.txt", "*.md"]

    def test_follow_symlinks_flag(self) -> None:
        """Test follow-symlinks flag."""
        parser = _build_parser()

        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--follow-symlinks"]
        )
        assert args.follow_symlinks is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.follow_symlinks is False

    def test_hidden_flag(self) -> None:
        """Test hidden flag."""
        parser = _build_parser()

        args = parser.parse_args(["--roots", "root1", "--query", "test", "--hidden"])
        assert args.hidden is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.hidden is False

    def test_no_ignore_flag(self) -> None:
        """Test no-ignore flag."""
        parser = _build_parser()

        args = parser.parse_args(["--roots", "root1", "--query", "test", "--no-ignore"])
        assert args.no_ignore is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.no_ignore is False

    def test_max_filesize_option(self) -> None:
        """Test max-filesize option."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--max-filesize", "10M"]
        )
        assert args.max_filesize == "10M"

    def test_context_options(self) -> None:
        """Test context before/after options."""
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--roots",
                "root1",
                "--query",
                "test",
                "--context-before",
                "3",
                "--context-after",
                "5",
            ]
        )
        assert args.context_before == 3
        assert args.context_after == 5

    def test_encoding_option(self) -> None:
        """Test encoding option."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--encoding", "utf-8"]
        )
        assert args.encoding == "utf-8"

    def test_max_count_option(self) -> None:
        """Test max-count option."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--max-count", "100"]
        )
        assert args.max_count == 100

    def test_timeout_ms_option(self) -> None:
        """Test timeout-ms option."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--timeout-ms", "5000"]
        )
        assert args.timeout_ms == 5000

    def test_count_only_matches_flag(self) -> None:
        """Test count-only-matches flag."""
        parser = _build_parser()

        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--count-only-matches"]
        )
        assert args.count_only_matches is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.count_only_matches is False

    def test_summary_only_flag(self) -> None:
        """Test summary-only flag."""
        parser = _build_parser()

        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--summary-only"]
        )
        assert args.summary_only is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.summary_only is False

    def test_optimize_paths_flag(self) -> None:
        """Test optimize-paths flag."""
        parser = _build_parser()

        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--optimize-paths"]
        )
        assert args.optimize_paths is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.optimize_paths is False

    def test_group_by_file_flag(self) -> None:
        """Test group-by-file flag."""
        parser = _build_parser()

        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--group-by-file"]
        )
        assert args.group_by_file is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.group_by_file is False

    def test_total_only_flag(self) -> None:
        """Test total-only flag."""
        parser = _build_parser()

        args = parser.parse_args(
            ["--roots", "root1", "--query", "test", "--total-only"]
        )
        assert args.total_only is True

        args = parser.parse_args(["--roots", "root1", "--query", "test"])
        assert args.total_only is False

    def test_project_root_option(self) -> None:
        """Test project root option."""
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--roots",
                "root1",
                "--query",
                "test",
                "--project-root",
                "/path/to/project",
            ]
        )
        assert args.project_root == "/path/to/project"

    def test_all_options_together_with_roots(self) -> None:
        """Test all options can be used together with roots."""
        parser = _build_parser()

        args = parser.parse_args(
            [
                "--roots",
                "root1",
                "root2",
                "--query",
                "search_term",
                "--output-format",
                "text",
                "--quiet",
                "--case",
                "insensitive",
                "--fixed-strings",
                "--word",
                "--multiline",
                "--include-globs",
                "*.py",
                "--exclude-globs",
                "*.txt",
                "--follow-symlinks",
                "--hidden",
                "--no-ignore",
                "--max-filesize",
                "1M",
                "--context-before",
                "2",
                "--context-after",
                "3",
                "--encoding",
                "utf-8",
                "--max-count",
                "50",
                "--timeout-ms",
                "1000",
                "--count-only-matches",
                "--summary-only",
                "--optimize-paths",
                "--group-by-file",
                "--total-only",
                "--project-root",
                "/project",
            ]
        )

        assert args.roots == ["root1", "root2"]
        assert args.query == "search_term"
        assert args.output_format == "text"
        assert args.quiet is True
        assert args.case == "insensitive"
        assert args.fixed_strings is True
        assert args.word is True
        assert args.multiline is True
        assert args.include_globs == ["*.py"]
        assert args.exclude_globs == ["*.txt"]
        assert args.follow_symlinks is True
        assert args.hidden is True
        assert args.no_ignore is True
        assert args.max_filesize == "1M"
        assert args.context_before == 2
        assert args.context_after == 3
        assert args.encoding == "utf-8"
        assert args.max_count == 50
        assert args.timeout_ms == 1000
        assert args.count_only_matches is True
        assert args.summary_only is True
        assert args.optimize_paths is True
        assert args.group_by_file is True
        assert args.total_only is True
        assert args.project_root == "/project"
