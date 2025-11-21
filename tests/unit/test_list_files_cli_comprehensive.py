#!/usr/bin/env python3
"""Comprehensive tests for list_files_cli module."""

from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.list_files_cli import (
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


class TestRunFunction:
    """Test the _run async function."""

    @pytest.mark.asyncio
    async def test_minimal_execution(self) -> None:
        """Test minimal execution with required arguments."""
        args = argparse.Namespace(
            roots=["root1"],
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
            limit=None,
            count_only=False,
        )

        mock_result = {"files": ["file1.py", "file2.py"], "success": True}

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"
            ) as mock_set_output,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.output_data"
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
            limit=None,
            count_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"
            ) as mock_set_output,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.output_data"
            ) as mock_output,
        ):

            mock_detect.return_value = "/custom/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={"files": []})
            mock_tool_class.return_value = mock_tool

            result = await _run(args)

            assert result == 0
            mock_set_output.assert_called_once_with(quiet=True, json_output=False)
            mock_output.assert_called_once_with({"files": []}, "text")

    @pytest.mark.asyncio
    async def test_all_options_in_payload(self) -> None:
        """Test all options are included in payload."""
        args = argparse.Namespace(
            roots=["root1", "root2"],
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
            limit=500,
            count_only=True,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_data"),
        ):

            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            # Check the payload passed to execute
            call_args = mock_tool.execute.call_args[0][0]
            assert call_args["roots"] == ["root1", "root2"]
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
            assert call_args["limit"] == 500
            assert call_args["count_only"] is True

    @pytest.mark.asyncio
    async def test_error_handling(self) -> None:
        """Test error handling in _run."""
        args = argparse.Namespace(
            roots=["root1"],
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
            limit=None,
            count_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.output_error"
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
            limit=None,
            count_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_data"),
        ):

            mock_detect.return_value = "/custom/path"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            mock_detect.assert_called_once_with(None, "/custom/path")
            mock_tool_class.assert_called_once_with("/custom/path")

    @pytest.mark.asyncio
    async def test_result_without_success_key(self) -> None:
        """Test result dict without success key returns 0."""
        args = argparse.Namespace(
            roots=["root1"],
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
            limit=None,
            count_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_data"),
        ):

            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(
                return_value={"files": ["file1.py"]}
            )  # No success key
            mock_tool_class.return_value = mock_tool

            result = await _run(args)

            assert result == 0


class TestMainFunction:
    """Test the main() entry point."""

    def test_main_success(self) -> None:
        """Test main function with successful execution."""
        test_args = ["root1"]

        with (
            patch("sys.argv", ["list_files_cli.py"] + test_args),
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_data"),
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
        test_args = ["root1"]

        with (
            patch("sys.argv", ["list_files_cli.py"] + test_args),
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_error"),
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
        test_args = ["root1"]

        with (
            patch("sys.argv", ["list_files_cli.py"] + test_args),
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
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
            patch("sys.argv", ["list_files_cli.py"] + test_args),
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
            limit=None,
            count_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_data"),
        ):

            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            call_args = mock_tool.execute.call_args[0][0]
            assert call_args["depth"] == 0

    @pytest.mark.asyncio
    async def test_limit_zero(self) -> None:
        """Test limit=0."""
        args = argparse.Namespace(
            roots=["root1"],
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
            limit=0,  # Zero limit
            count_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_data"),
        ):

            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            call_args = mock_tool.execute.call_args[0][0]
            assert call_args["limit"] == 0

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        """Test empty file list result."""
        args = argparse.Namespace(
            roots=["root1"],
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
            limit=None,
            count_only=False,
        )

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.output_data"
            ) as mock_output,
        ):

            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={"files": [], "count": 0})
            mock_tool_class.return_value = mock_tool

            result = await _run(args)

            assert result == 0
            mock_output.assert_called_once_with({"files": [], "count": 0}, "json")

    def test_parser_help(self) -> None:
        """Test parser help output."""
        parser = _build_parser()

        # Should not raise
        help_str = parser.format_help()
        assert "roots" in help_str.lower() or "root" in help_str.lower()
        assert "list" in help_str.lower() or "file" in help_str.lower()
