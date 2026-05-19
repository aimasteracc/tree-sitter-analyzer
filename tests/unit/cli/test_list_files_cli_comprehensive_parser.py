#!/usr/bin/env python3
"""Comprehensive tests for list_files_cli argument parser."""

from __future__ import annotations

import argparse

import pytest

from tree_sitter_analyzer.cli.commands.list_files_cli import _build_parser


class TestBuildParser:
    """Test argument parser construction."""

    def test_parser_creation(self) -> None:
        """Test parser is created successfully."""
        parser = _build_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        assert (
            "list" in parser.description.lower() or "fd" in parser.description.lower()
        )

    def test_required_arguments(self) -> None:
        """Test required arguments are enforced."""
        parser = _build_parser()

        # Missing roots should raise
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_minimal_valid_arguments(self) -> None:
        """Test minimal valid argument set."""
        parser = _build_parser()
        args = parser.parse_args(["root1"])

        assert args.roots == ["root1"]
        assert args.output_format == "json"
        assert args.quiet is False

    def test_multiple_roots(self) -> None:
        """Test multiple search roots."""
        parser = _build_parser()
        args = parser.parse_args(["root1", "root2", "root3"])

        assert args.roots == ["root1", "root2", "root3"]

    def test_output_format_options(self) -> None:
        """Test output format choices."""
        parser = _build_parser()

        # JSON format
        args = parser.parse_args(["root1", "--output-format", "json"])
        assert args.output_format == "json"

        # Text format
        args = parser.parse_args(["root1", "--output-format", "text"])
        assert args.output_format == "text"

        # Invalid format should raise
        with pytest.raises(SystemExit):
            parser.parse_args(["root1", "--output-format", "xml"])

    def test_quiet_flag(self) -> None:
        """Test quiet flag."""
        parser = _build_parser()

        args = parser.parse_args(["root1", "--quiet"])
        assert args.quiet is True

        args = parser.parse_args(["root1"])
        assert args.quiet is False

    def test_pattern_option(self) -> None:
        """Test pattern option."""
        parser = _build_parser()
        args = parser.parse_args(["root1", "--pattern", "*.py"])
        assert args.pattern == "*.py"

    def test_glob_flag(self) -> None:
        """Test glob flag."""
        parser = _build_parser()

        args = parser.parse_args(["root1", "--glob"])
        assert args.glob is True

        args = parser.parse_args(["root1"])
        assert args.glob is False

    def test_types_option(self) -> None:
        """Test types option."""
        parser = _build_parser()
        args = parser.parse_args(["root1", "--types", "python", "javascript"])
        assert args.types == ["python", "javascript"]

    def test_extensions_option(self) -> None:
        """Test extensions option."""
        parser = _build_parser()
        args = parser.parse_args(["root1", "--extensions", "py", "js", "ts"])
        assert args.extensions == ["py", "js", "ts"]

    def test_exclude_option(self) -> None:
        """Test exclude option."""
        parser = _build_parser()
        args = parser.parse_args(
            ["root1", "--exclude", "node_modules", "__pycache__", ".git"]
        )
        assert args.exclude == ["node_modules", "__pycache__", ".git"]

    def test_depth_option(self) -> None:
        """Test depth option."""
        parser = _build_parser()
        args = parser.parse_args(["root1", "--depth", "5"])
        assert args.depth == 5

    def test_follow_symlinks_flag(self) -> None:
        """Test follow-symlinks flag."""
        parser = _build_parser()

        args = parser.parse_args(["root1", "--follow-symlinks"])
        assert args.follow_symlinks is True

        args = parser.parse_args(["root1"])
        assert args.follow_symlinks is False

    def test_hidden_flag(self) -> None:
        """Test hidden flag."""
        parser = _build_parser()

        args = parser.parse_args(["root1", "--hidden"])
        assert args.hidden is True

        args = parser.parse_args(["root1"])
        assert args.hidden is False

    def test_no_ignore_flag(self) -> None:
        """Test no-ignore flag."""
        parser = _build_parser()

        args = parser.parse_args(["root1", "--no-ignore"])
        assert args.no_ignore is True

        args = parser.parse_args(["root1"])
        assert args.no_ignore is False

    def test_size_option(self) -> None:
        """Test size option."""
        parser = _build_parser()
        args = parser.parse_args(["root1", "--size", "+1M"])
        assert args.size == ["+1M"]

    def test_changed_within_option(self) -> None:
        """Test changed-within option."""
        parser = _build_parser()
        args = parser.parse_args(["root1", "--changed-within", "1week"])
        assert args.changed_within == "1week"

    def test_changed_before_option(self) -> None:
        """Test changed-before option."""
        parser = _build_parser()
        args = parser.parse_args(["root1", "--changed-before", "2023-01-01"])
        assert args.changed_before == "2023-01-01"

    def test_full_path_match_flag(self) -> None:
        """Test full-path-match flag."""
        parser = _build_parser()

        args = parser.parse_args(["root1", "--full-path-match"])
        assert args.full_path_match is True

        args = parser.parse_args(["root1"])
        assert args.full_path_match is False

    def test_limit_option(self) -> None:
        """Test limit option."""
        parser = _build_parser()
        args = parser.parse_args(["root1", "--limit", "100"])
        assert args.limit == 100

    def test_count_only_flag(self) -> None:
        """Test count-only flag."""
        parser = _build_parser()

        args = parser.parse_args(["root1", "--count-only"])
        assert args.count_only is True

        args = parser.parse_args(["root1"])
        assert args.count_only is False

    def test_project_root_option(self) -> None:
        """Test project root option."""
        parser = _build_parser()
        args = parser.parse_args(["root1", "--project-root", "/path/to/project"])
        assert args.project_root == "/path/to/project"

    def test_all_options_together(self) -> None:
        """Test all options can be used together."""
        parser = _build_parser()

        args = parser.parse_args(
            [
                "root1",
                "root2",
                "--output-format",
                "text",
                "--quiet",
                "--pattern",
                "*.py",
                "--glob",
                "--types",
                "python",
                "--extensions",
                "py",
                "--exclude",
                "__pycache__",
                "--depth",
                "3",
                "--follow-symlinks",
                "--hidden",
                "--no-ignore",
                "--size",
                "+1K",
                "--changed-within",
                "1day",
                "--changed-before",
                "2023-12-31",
                "--full-path-match",
                "--limit",
                "50",
                "--count-only",
                "--project-root",
                "/project",
            ]
        )

        assert args.roots == ["root1", "root2"]
        assert args.output_format == "text"
        assert args.quiet is True
        assert args.pattern == "*.py"
        assert args.glob is True
        assert args.types == ["python"]
        assert args.extensions == ["py"]
        assert args.exclude == ["__pycache__"]
        assert args.depth == 3
        assert args.follow_symlinks is True
        assert args.hidden is True
        assert args.no_ignore is True
        assert args.size == ["+1K"]
        assert args.changed_within == "1day"
        assert args.changed_before == "2023-12-31"
        assert args.full_path_match is True
        assert args.limit == 50
        assert args.count_only is True
        assert args.project_root == "/project"


class TestParserEdgeCases:
    """Parser-related edge cases."""

    def test_parser_help(self) -> None:
        """Test parser help output."""
        parser = _build_parser()

        help_str = parser.format_help()
        assert "roots" in help_str.lower() or "root" in help_str.lower()
        assert "list" in help_str.lower() or "file" in help_str.lower()
