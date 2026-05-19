#!/usr/bin/env python3
"""Find and grep CLI tests — main function and edge cases."""

from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.find_and_grep_cli import (
    _build_parser,
    _run,
    main,
)


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
