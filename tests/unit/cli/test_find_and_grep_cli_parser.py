#!/usr/bin/env python3
"""Tests for find_and_grep_cli argument parser construction."""

from __future__ import annotations

import argparse

import pytest

from tree_sitter_analyzer.cli.commands.find_and_grep_cli import (
    _build_parser,
)


class TestBuildParser:
    """Test argument parser construction."""

    def test_parser_creation(self) -> None:
        """Test parser is created successfully."""
        parser = _build_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        assert (
            "find_and_grep" in parser.description.lower()
            or "search" in parser.description.lower()
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

        # Missing --roots should raise
        with pytest.raises(SystemExit):
            parser.parse_args(["--query", "test"])

    def test_minimal_valid_arguments(self) -> None:
        """Test minimal valid argument set."""
        parser = _build_parser()
        args = parser.parse_args(["--roots", "root1", "--query", "test"])

        assert args.roots == ["root1"]
        assert args.query == "test"
        assert args.output_format == "json"
        assert args.quiet is False

    def test_multiple_roots(self) -> None:
        """Test multiple search roots."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "root1", "root2", "root3", "--query", "test"]
        )

        assert args.roots == ["root1", "root2", "root3"]

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

    def test_fd_options(self) -> None:
        """Test fd-specific options."""
        parser = _build_parser()

        args = parser.parse_args(
            [
                "--roots",
                "root1",
                "--query",
                "test",
                "--pattern",
                "*.py",
                "--glob",
                "--types",
                "python",
                "javascript",
                "--extensions",
                "py",
                "js",
                "--exclude",
                "node_modules",
                "__pycache__",
                "--depth",
                "5",
                "--follow-symlinks",
                "--hidden",
                "--no-ignore",
                "--size",
                "+1M",
                "--changed-within",
                "1week",
                "--changed-before",
                "2023-01-01",
                "--full-path-match",
                "--file-limit",
                "1000",
                "--sort",
                "mtime",
            ]
        )

        assert args.pattern == "*.py"
        assert args.glob is True
        assert args.types == ["python", "javascript"]
        assert args.extensions == ["py", "js"]
        assert args.exclude == ["node_modules", "__pycache__"]
        assert args.depth == 5
        assert args.follow_symlinks is True
        assert args.hidden is True
        assert args.no_ignore is True
        assert args.size == ["+1M"]
        assert args.changed_within == "1week"
        assert args.changed_before == "2023-01-01"
        assert args.full_path_match is True
        assert args.file_limit == 1000
        assert args.sort == "mtime"

    def test_rg_options(self) -> None:
        """Test ripgrep-specific options."""
        parser = _build_parser()

        args = parser.parse_args(
            [
                "--roots",
                "root1",
                "--query",
                "test",
                "--case",
                "insensitive",
                "--fixed-strings",
                "--word",
                "--multiline",
                "--include-globs",
                "*.py",
                "*.js",
                "--exclude-globs",
                "*.txt",
                "--max-filesize",
                "1M",
                "--context-before",
                "3",
                "--context-after",
                "5",
                "--encoding",
                "utf-8",
                "--max-count",
                "100",
                "--timeout-ms",
                "5000",
                "--count-only-matches",
                "--summary-only",
                "--optimize-paths",
                "--group-by-file",
                "--total-only",
            ]
        )

        assert args.case == "insensitive"
        assert args.fixed_strings is True
        assert args.word is True
        assert args.multiline is True
        assert args.include_globs == ["*.py", "*.js"]
        assert args.exclude_globs == ["*.txt"]
        assert args.max_filesize == "1M"
        assert args.context_before == 3
        assert args.context_after == 5
        assert args.encoding == "utf-8"
        assert args.max_count == 100
        assert args.timeout_ms == 5000
        assert args.count_only_matches is True
        assert args.summary_only is True
        assert args.optimize_paths is True
        assert args.group_by_file is True
        assert args.total_only is True

    def test_case_options(self) -> None:
        """Test case sensitivity options."""
        parser = _build_parser()

        for case_val in ["smart", "insensitive", "sensitive"]:
            args = parser.parse_args(
                ["--roots", "root1", "--query", "test", "--case", case_val]
            )
            assert args.case == case_val

    def test_sort_options(self) -> None:
        """Test sort options."""
        parser = _build_parser()

        for sort_val in ["path", "mtime", "size"]:
            args = parser.parse_args(
                ["--roots", "root1", "--query", "test", "--sort", sort_val]
            )
            assert args.sort == sort_val

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
