#!/usr/bin/env python3
"""Tests for search_content_cli.py."""

import argparse
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.search_content_cli import (
    _build_parser,
    _run,
    main,
)


class TestBuildParser:
    """Tests for _build_parser function."""

    def test_build_parser_creates_parser(self):
        """Test that _build_parser creates an ArgumentParser."""
        parser = _build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_build_parser_has_roots_argument(self):
        """Test that parser has --roots argument."""
        parser = _build_parser()
        args = parser.parse_args(["--roots", "src", "--query", "test"])
        assert args.roots == ["src"]
        assert args.files is None

    def test_build_parser_has_files_argument(self):
        """Test that parser has --files argument."""
        parser = _build_parser()
        args = parser.parse_args(["--files", "file1.py", "--query", "test"])
        assert args.files == ["file1.py"]
        assert args.roots is None

    def test_build_parser_roots_and_files_mutually_exclusive(self):
        """Test that --roots and --files are mutually exclusive."""
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["--roots", "src", "--files", "file.py", "--query", "test"]
            )

    def test_build_parser_query_required(self):
        """Test that --query is required."""
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--roots", "src"])

    def test_build_parser_output_format_default(self):
        """Test that output_format defaults to 'json'."""
        parser = _build_parser()
        args = parser.parse_args(["--roots", "src", "--query", "test"])
        assert args.output_format == "json"

    def test_build_parser_output_format_choices(self):
        """Test that output_format accepts 'json', 'text', 'toon'."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "src", "--query", "test", "--output-format", "toon"]
        )
        assert args.output_format == "toon"

    def test_build_parser_quiet_flag(self):
        """Test that --quiet flag works."""
        parser = _build_parser()
        args = parser.parse_args(["--roots", "src", "--query", "test", "--quiet"])
        assert args.quiet is True

    def test_build_parser_case_default(self):
        """Test that case defaults to 'smart'."""
        parser = _build_parser()
        args = parser.parse_args(["--roots", "src", "--query", "test"])
        assert args.case == "smart"

    def test_build_parser_case_choices(self):
        """Test that case accepts 'smart', 'insensitive', 'sensitive'."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "src", "--query", "test", "--case", "sensitive"]
        )
        assert args.case == "sensitive"

    def test_build_parser_boolean_flags(self):
        """Test that boolean flags work correctly."""
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--roots",
                "src",
                "--query",
                "test",
                "--fixed-strings",
                "--word",
                "--multiline",
                "--follow-symlinks",
                "--hidden",
                "--no-ignore",
                "--count-only-matches",
                "--summary-only",
                "--optimize-paths",
                "--group-by-file",
                "--total-only",
            ]
        )
        assert args.fixed_strings is True
        assert args.word is True
        assert args.multiline is True
        assert args.follow_symlinks is True
        assert args.hidden is True
        assert args.no_ignore is True
        assert args.count_only_matches is True
        assert args.summary_only is True
        assert args.optimize_paths is True
        assert args.group_by_file is True
        assert args.total_only is True

    def test_build_parser_list_arguments(self):
        """Test that list arguments work correctly."""
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--roots",
                "src",
                "tests",
                "--query",
                "test",
                "--include-globs",
                "*.py",
                "*.js",
                "--exclude-globs",
                "*.pyc",
                "__pycache__",
            ]
        )
        assert args.roots == ["src", "tests"]
        assert args.include_globs == ["*.py", "*.js"]
        assert args.exclude_globs == ["*.pyc", "__pycache__"]

    def test_build_parser_integer_arguments(self):
        """Test that integer arguments work correctly."""
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--roots",
                "src",
                "--query",
                "test",
                "--context-before",
                "2",
                "--context-after",
                "3",
                "--max-count",
                "100",
                "--timeout-ms",
                "5000",
            ]
        )
        assert args.context_before == 2
        assert args.context_after == 3
        assert args.max_count == 100
        assert args.timeout_ms == 5000

    def test_build_parser_string_arguments(self):
        """Test that string arguments work correctly."""
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--roots",
                "src",
                "--query",
                "test",
                "--max-filesize",
                "10M",
                "--encoding",
                "utf-8",
            ]
        )
        assert args.max_filesize == "10M"
        assert args.encoding == "utf-8"

    def test_build_parser_project_root(self):
        """Test that --project-root argument works."""
        parser = _build_parser()
        args = parser.parse_args(
            ["--roots", "src", "--query", "test", "--project-root", "/path/to/project"]
        )
        assert args.project_root == "/path/to/project"


class TestRun:
    """Tests for _run function."""

    @pytest.mark.asyncio
    async def test_run_with_roots_success(self):
        """Test _run with --roots argument succeeds."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "json"
        mock_args.roots = ["src"]
        mock_args.files = None
        mock_args.query = "test"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = {"matches": []}
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ):
                        result = await _run(mock_args)

                        assert result == 0
                        mock_tool_class.assert_called_once_with("/project")
                        mock_tool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_files_success(self):
        """Test _run with --files argument succeeds."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "json"
        mock_args.roots = None
        mock_args.files = ["file1.py", "file2.py"]
        mock_args.query = "test"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = {"matches": []}
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ):
                        result = await _run(mock_args)

                        assert result == 0

    @pytest.mark.asyncio
    async def test_run_with_all_options(self):
        """Test _run with all options set."""
        mock_args = MagicMock()
        mock_args.quiet = True
        mock_args.output_format = "toon"
        mock_args.roots = ["src", "tests"]
        mock_args.files = None
        mock_args.query = "test"
        mock_args.case = "sensitive"
        mock_args.fixed_strings = True
        mock_args.word = True
        mock_args.multiline = True
        mock_args.include_globs = ["*.py"]
        mock_args.exclude_globs = ["*.pyc"]
        mock_args.follow_symlinks = True
        mock_args.hidden = True
        mock_args.no_ignore = True
        mock_args.max_filesize = "10M"
        mock_args.context_before = 2
        mock_args.context_after = 3
        mock_args.encoding = "utf-8"
        mock_args.max_count = 100
        mock_args.timeout_ms = 5000
        mock_args.count_only_matches = True
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = "/custom/root"

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/custom/root",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = {"matches": []}
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ):
                        result = await _run(mock_args)

                        assert result == 0
                        # Verify payload contains all options
                        call_args = mock_tool.execute.call_args[0][0]
                        assert call_args["query"] == "test"
                        assert call_args["roots"] == ["src", "tests"]
                        assert call_args["case"] == "sensitive"
                        assert call_args["fixed_strings"] is True
                        assert call_args["word"] is True
                        assert call_args["multiline"] is True
                        assert call_args["include_globs"] == ["*.py"]
                        assert call_args["exclude_globs"] == ["*.pyc"]
                        assert call_args["follow_symlinks"] is True
                        assert call_args["hidden"] is True
                        assert call_args["no_ignore"] is True
                        assert call_args["max_filesize"] == "10M"
                        assert call_args["context_before"] == 2
                        assert call_args["context_after"] == 3
                        assert call_args["encoding"] == "utf-8"
                        assert call_args["max_count"] == 100
                        assert call_args["timeout_ms"] == 5000
                        assert call_args["count_only_matches"] is True
                        assert call_args["output_format"] == "toon"

    @pytest.mark.asyncio
    async def test_run_with_summary_only(self):
        """Test _run with --summary-only option."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "json"
        mock_args.roots = ["src"]
        mock_args.files = None
        mock_args.query = "test"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = True
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = {"matches": []}
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ):
                        result = await _run(mock_args)

                        assert result == 0
                        call_args = mock_tool.execute.call_args[0][0]
                        assert call_args["summary_only"] is True

    @pytest.mark.asyncio
    async def test_run_with_group_by_file(self):
        """Test _run with --group-by-file option."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "json"
        mock_args.roots = ["src"]
        mock_args.files = None
        mock_args.query = "test"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = True
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = {"matches": []}
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ):
                        result = await _run(mock_args)

                        assert result == 0
                        call_args = mock_tool.execute.call_args[0][0]
                        assert call_args["group_by_file"] is True

    @pytest.mark.asyncio
    async def test_run_with_total_only(self):
        """Test _run with --total-only option."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "json"
        mock_args.roots = ["src"]
        mock_args.files = None
        mock_args.query = "test"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = True
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = 42
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ):
                        result = await _run(mock_args)

                        assert result == 0
                        call_args = mock_tool.execute.call_args[0][0]
                        assert call_args["total_only"] is True

    @pytest.mark.asyncio
    async def test_run_with_optimize_paths(self):
        """Test _run with --optimize-paths option."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "json"
        mock_args.roots = ["src"]
        mock_args.files = None
        mock_args.query = "test"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = True
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = {"matches": []}
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ):
                        result = await _run(mock_args)

                        assert result == 0
                        call_args = mock_tool.execute.call_args[0][0]
                        assert call_args["optimize_paths"] is True

    @pytest.mark.asyncio
    async def test_run_exception_handling(self):
        """Test _run handles exceptions correctly."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "json"
        mock_args.roots = ["src"]
        mock_args.files = None
        mock_args.query = "test"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.side_effect = Exception("Search failed")
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_error"
                    ):
                        result = await _run(mock_args)

                        assert result == 1

    @pytest.mark.asyncio
    async def test_run_with_text_output_format(self):
        """Test _run with text output format."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "text"
        mock_args.roots = ["src"]
        mock_args.files = None
        mock_args.query = "test"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = {"matches": []}
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ):
                        result = await _run(mock_args)

                        assert result == 0
                        call_args = mock_tool.execute.call_args[0][0]
                        assert call_args["output_format"] == "text"

    @pytest.mark.asyncio
    async def test_run_with_toon_output_format(self):
        """Test _run with toon output format."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "toon"
        mock_args.roots = ["src"]
        mock_args.files = None
        mock_args.query = "test"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = {"matches": []}
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ):
                        result = await _run(mock_args)

                        assert result == 0
                        call_args = mock_tool.execute.call_args[0][0]
                        assert call_args["output_format"] == "toon"


class TestMain:
    """Tests for main function."""

    def test_main_success(self):
        """Test main function with successful execution."""
        test_args = ["--roots", "src", "--query", "test"]

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli._build_parser"
        ) as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.roots = ["src"]
            mock_args.files = None
            mock_args.query = "test"
            mock_args.quiet = False
            mock_args.output_format = "json"
            mock_args.case = "smart"
            mock_args.fixed_strings = False
            mock_args.word = False
            mock_args.multiline = False
            mock_args.include_globs = None
            mock_args.exclude_globs = None
            mock_args.follow_symlinks = False
            mock_args.hidden = False
            mock_args.no_ignore = False
            mock_args.max_filesize = None
            mock_args.context_before = None
            mock_args.context_after = None
            mock_args.encoding = None
            mock_args.max_count = None
            mock_args.timeout_ms = None
            mock_args.count_only_matches = False
            mock_args.summary_only = False
            mock_args.optimize_paths = False
            mock_args.group_by_file = False
            mock_args.total_only = False
            mock_args.project_root = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                    return_value="/project",
                ):
                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                    ) as mock_tool_class:
                        mock_tool = AsyncMock()
                        mock_tool.execute.return_value = {"matches": []}
                        mock_tool_class.return_value = mock_tool

                        with patch(
                            "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                        ):
                            with patch("sys.exit") as mock_exit:
                                main()
                                mock_exit.assert_called_once_with(0)

    def test_main_keyboard_interrupt(self):
        """Test main function handles KeyboardInterrupt."""
        test_args = ["--roots", "src", "--query", "test"]

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli._build_parser"
        ) as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.roots = ["src"]
            mock_args.files = None
            mock_args.query = "test"
            mock_args.quiet = False
            mock_args.output_format = "json"
            mock_args.case = "smart"
            mock_args.fixed_strings = False
            mock_args.word = False
            mock_args.multiline = False
            mock_args.include_globs = None
            mock_args.exclude_globs = None
            mock_args.follow_symlinks = False
            mock_args.hidden = False
            mock_args.no_ignore = False
            mock_args.max_filesize = None
            mock_args.context_before = None
            mock_args.context_after = None
            mock_args.encoding = None
            mock_args.max_count = None
            mock_args.timeout_ms = None
            mock_args.count_only_matches = False
            mock_args.summary_only = False
            mock_args.optimize_paths = False
            mock_args.group_by_file = False
            mock_args.total_only = False
            mock_args.project_root = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                    return_value="/project",
                ):
                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                    ) as mock_tool_class:
                        mock_tool = AsyncMock()
                        mock_tool.execute.side_effect = KeyboardInterrupt()
                        mock_tool_class.return_value = mock_tool

                        with patch("sys.exit") as mock_exit:
                            main()
                            mock_exit.assert_called_once_with(1)


class TestIntegration:
    """Integration tests for search_content_cli."""

    @pytest.mark.asyncio
    async def test_full_workflow_roots_search(self):
        """Test full workflow with roots search."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "json"
        mock_args.roots = ["src", "tests"]
        mock_args.files = None
        mock_args.query = "TODO"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = ["*.py"]
        mock_args.exclude_globs = ["*.pyc"]
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = 2
        mock_args.context_after = 2
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = {
                        "matches": [
                            {
                                "path": "src/file1.py",
                                "line": 10,
                                "column": 5,
                                "content": "# TODO: implement feature",
                            }
                        ]
                    }
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ) as mock_output:
                        result = await _run(mock_args)

                        assert result == 0
                        mock_tool_class.assert_called_once_with("/project")
                        mock_tool.execute.assert_called_once()
                        mock_output.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_workflow_files_search(self):
        """Test full workflow with files search."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "json"
        mock_args.roots = None
        mock_args.files = ["file1.py", "file2.py"]
        mock_args.query = "import"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.return_value = {
                        "matches": [
                            {
                                "path": "file1.py",
                                "line": 1,
                                "column": 0,
                                "content": "import os",
                            }
                        ]
                    }
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
                    ):
                        result = await _run(mock_args)

                        assert result == 0

    @pytest.mark.asyncio
    async def test_full_workflow_with_error(self):
        """Test full workflow with error."""
        mock_args = MagicMock()
        mock_args.quiet = False
        mock_args.output_format = "json"
        mock_args.roots = ["src"]
        mock_args.files = None
        mock_args.query = "test"
        mock_args.case = "smart"
        mock_args.fixed_strings = False
        mock_args.word = False
        mock_args.multiline = False
        mock_args.include_globs = None
        mock_args.exclude_globs = None
        mock_args.follow_symlinks = False
        mock_args.hidden = False
        mock_args.no_ignore = False
        mock_args.max_filesize = None
        mock_args.context_before = None
        mock_args.context_after = None
        mock_args.encoding = None
        mock_args.max_count = None
        mock_args.timeout_ms = None
        mock_args.count_only_matches = False
        mock_args.summary_only = False
        mock_args.optimize_paths = False
        mock_args.group_by_file = False
        mock_args.total_only = False
        mock_args.project_root = None

        with patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project",
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
                ) as mock_tool_class:
                    mock_tool = AsyncMock()
                    mock_tool.execute.side_effect = ValueError("Invalid query")
                    mock_tool_class.return_value = mock_tool

                    with patch(
                        "tree_sitter_analyzer.cli.commands.search_content_cli.output_error"
                    ) as mock_error:
                        result = await _run(mock_args)

                        assert result == 1
                        mock_error.assert_called_once()
