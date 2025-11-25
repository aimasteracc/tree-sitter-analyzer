#!/usr/bin/env python3
"""Comprehensive tests for find_and_grep_cli module."""

from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.find_and_grep_cli import (
    _build_parser,
    _run,
    main,
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


class TestRunFunction:
    """Test the _run async function."""

    @pytest.mark.asyncio
    async def test_minimal_execution(self) -> None:
        """Test minimal execution with required arguments."""
        args = argparse.Namespace(
            roots=["root1"],
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            file_limit=None,
            sort=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            count_only_matches=False,
            summary_only=False,
            optimize_paths=False,
            group_by_file=False,
            total_only=False,
        )

        mock_result = {"matches": 5, "files": ["file1.py", "file2.py"]}

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ) as mock_set_output,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_data"
            ) as mock_output,
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value=mock_result)
            mock_tool_class.return_value = mock_tool

            result = await _run(args)

            assert result == 0
            mock_detect.assert_called_once()
            mock_set_output.assert_called_once_with(quiet=False, json_output=True)
            mock_tool_class.assert_called_once_with("/project/root")
            mock_tool.execute.assert_called_once()
            mock_output.assert_called_once_with(mock_result, "json")

    @pytest.mark.asyncio
    async def test_text_output_format(self) -> None:
        """Test text output format."""
        args = argparse.Namespace(
            roots=["root1"],
            query="test",
            output_format="text",
            quiet=True,
            project_root="/custom/root",
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            file_limit=None,
            sort=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            count_only_matches=False,
            summary_only=False,
            optimize_paths=False,
            group_by_file=False,
            total_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ) as mock_set_output,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_data"
            ) as mock_output,
        ):
            mock_detect.return_value = "/custom/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={"result": "text"})
            mock_tool_class.return_value = mock_tool

            result = await _run(args)

            assert result == 0
            mock_set_output.assert_called_once_with(quiet=True, json_output=False)
            mock_output.assert_called_once_with({"result": "text"}, "text")

    @pytest.mark.asyncio
    async def test_all_fd_options_in_payload(self) -> None:
        """Test all fd options are included in payload."""
        args = argparse.Namespace(
            roots=["root1", "root2"],
            query="search_term",
            output_format="json",
            quiet=False,
            project_root=None,
            pattern="*.py",
            glob=True,
            types=["python"],
            extensions=["py"],
            exclude=["__pycache__"],
            depth=3,
            follow_symlinks=True,
            hidden=True,
            no_ignore=True,
            size=["+1M"],
            changed_within="1week",
            changed_before="2023-01-01",
            full_path_match=True,
            file_limit=500,
            sort="mtime",
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            count_only_matches=False,
            summary_only=False,
            optimize_paths=False,
            group_by_file=False,
            total_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_data"),
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            # Check the payload passed to execute
            call_args = mock_tool.execute.call_args[0][0]
            assert call_args["roots"] == ["root1", "root2"]
            assert call_args["query"] == "search_term"
            assert call_args["pattern"] == "*.py"
            assert call_args["glob"] is True
            assert call_args["types"] == ["python"]
            assert call_args["extensions"] == ["py"]
            assert call_args["exclude"] == ["__pycache__"]
            assert call_args["depth"] == 3
            assert call_args["follow_symlinks"] is True
            assert call_args["hidden"] is True
            assert call_args["no_ignore"] is True
            assert call_args["size"] == ["+1M"]
            assert call_args["changed_within"] == "1week"
            assert call_args["changed_before"] == "2023-01-01"
            assert call_args["full_path_match"] is True
            assert call_args["file_limit"] == 500
            assert call_args["sort"] == "mtime"

    @pytest.mark.asyncio
    async def test_all_rg_options_in_payload(self) -> None:
        """Test all ripgrep options are included in payload."""
        args = argparse.Namespace(
            roots=["root1"],
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            file_limit=None,
            sort=None,
            case="insensitive",
            fixed_strings=True,
            word=True,
            multiline=True,
            include_globs=["*.py"],
            exclude_globs=["*.txt"],
            max_filesize="1M",
            context_before=2,
            context_after=3,
            encoding="utf-8",
            max_count=50,
            timeout_ms=1000,
            count_only_matches=True,
            summary_only=True,
            optimize_paths=True,
            group_by_file=True,
            total_only=True,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_data"),
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            # Check the payload passed to execute
            call_args = mock_tool.execute.call_args[0][0]
            assert call_args["case"] == "insensitive"
            assert call_args["fixed_strings"] is True
            assert call_args["word"] is True
            assert call_args["multiline"] is True
            assert call_args["include_globs"] == ["*.py"]
            assert call_args["exclude_globs"] == ["*.txt"]
            assert call_args["max_filesize"] == "1M"
            assert call_args["context_before"] == 2
            assert call_args["context_after"] == 3
            assert call_args["encoding"] == "utf-8"
            assert call_args["max_count"] == 50
            assert call_args["timeout_ms"] == 1000
            assert call_args["count_only_matches"] is True
            assert call_args["summary_only"] is True
            assert call_args["optimize_paths"] is True
            assert call_args["group_by_file"] is True
            assert call_args["total_only"] is True

    @pytest.mark.asyncio
    async def test_integer_result(self) -> None:
        """Test integer result (count) is handled correctly."""
        args = argparse.Namespace(
            roots=["root1"],
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            file_limit=None,
            sort=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            count_only_matches=False,
            summary_only=False,
            optimize_paths=False,
            group_by_file=False,
            total_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_data"
            ) as mock_output,
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value=42)  # Integer result
            mock_tool_class.return_value = mock_tool

            result = await _run(args)

            assert result == 0
            mock_output.assert_called_once_with(42, "json")

    @pytest.mark.asyncio
    async def test_error_handling(self) -> None:
        """Test error handling in _run."""
        args = argparse.Namespace(
            roots=["root1"],
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            file_limit=None,
            sort=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            count_only_matches=False,
            summary_only=False,
            optimize_paths=False,
            group_by_file=False,
            total_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_error"
            ) as mock_error,
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(side_effect=RuntimeError("Test error"))
            mock_tool_class.return_value = mock_tool

            result = await _run(args)

            assert result == 1
            mock_error.assert_called_once_with("Test error")

    @pytest.mark.asyncio
    async def test_custom_project_root(self) -> None:
        """Test custom project root is used."""
        args = argparse.Namespace(
            roots=["root1"],
            query="test",
            output_format="json",
            quiet=False,
            project_root="/custom/path",
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            file_limit=None,
            sort=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            count_only_matches=False,
            summary_only=False,
            optimize_paths=False,
            group_by_file=False,
            total_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_data"),
        ):
            mock_detect.return_value = "/custom/path"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            mock_detect.assert_called_once_with(None, "/custom/path")
            mock_tool_class.assert_called_once_with("/custom/path")


class TestMainFunction:
    """Test the main() entry point."""

    def test_main_success(self) -> None:
        """Test main function with successful execution."""
        test_args = ["--roots", "root1", "--query", "test"]

        with (
            patch("sys.argv", ["find_and_grep_cli.py"] + test_args),
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_data"),
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            main()

        assert exc_info.value.code == 0

    def test_main_error(self) -> None:
        """Test main function with error."""
        test_args = ["--roots", "root1", "--query", "test"]

        with (
            patch("sys.argv", ["find_and_grep_cli.py"] + test_args),
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_error"),
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(side_effect=RuntimeError("Test error"))
            mock_tool_class.return_value = mock_tool

            main()

        assert exc_info.value.code == 1

    def test_main_keyboard_interrupt(self) -> None:
        """Test main function handles keyboard interrupt."""
        test_args = ["--roots", "root1", "--query", "test"]

        with (
            patch("sys.argv", ["find_and_grep_cli.py"] + test_args),
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(side_effect=KeyboardInterrupt())
            mock_tool_class.return_value = mock_tool

            main()

        assert exc_info.value.code == 1

    def test_main_invalid_arguments(self) -> None:
        """Test main function with invalid arguments."""
        test_args = ["--invalid-arg"]

        with (
            patch("sys.argv", ["find_and_grep_cli.py"] + test_args),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code != 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_depth_zero(self) -> None:
        """Test depth=0 (current directory only)."""
        args = argparse.Namespace(
            roots=["root1"],
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=0,  # Zero depth
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            file_limit=None,
            sort=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            count_only_matches=False,
            summary_only=False,
            optimize_paths=False,
            group_by_file=False,
            total_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_data"),
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            call_args = mock_tool.execute.call_args[0][0]
            assert call_args["depth"] == 0

    @pytest.mark.asyncio
    async def test_context_zero(self) -> None:
        """Test context lines = 0."""
        args = argparse.Namespace(
            roots=["root1"],
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            file_limit=None,
            sort=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            max_filesize=None,
            context_before=0,  # Zero context
            context_after=0,  # Zero context
            encoding=None,
            max_count=None,
            timeout_ms=None,
            count_only_matches=False,
            summary_only=False,
            optimize_paths=False,
            group_by_file=False,
            total_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_data"),
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            call_args = mock_tool.execute.call_args[0][0]
            assert call_args["context_before"] == 0
            assert call_args["context_after"] == 0

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        """Test empty search result."""
        args = argparse.Namespace(
            roots=["root1"],
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            pattern=None,
            glob=False,
            types=None,
            extensions=None,
            exclude=None,
            depth=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            size=None,
            changed_within=None,
            changed_before=None,
            full_path_match=False,
            file_limit=None,
            sort=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            count_only_matches=False,
            summary_only=False,
            optimize_paths=False,
            group_by_file=False,
            total_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.FindAndGrepTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.set_output_mode"
            ),
            patch(
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli.output_data"
            ) as mock_output,
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={"matches": 0, "files": []})
            mock_tool_class.return_value = mock_tool

            result = await _run(args)

            assert result == 0
            mock_output.assert_called_once_with({"matches": 0, "files": []}, "json")

    def test_parser_help(self) -> None:
        """Test parser help output."""
        parser = _build_parser()

        # Should not raise
        help_str = parser.format_help()
        assert "roots" in help_str.lower()
        assert "query" in help_str.lower()
