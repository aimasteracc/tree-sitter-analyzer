#!/usr/bin/env python3
"""Tests for find_and_grep_cli _run async function."""

from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.find_and_grep_cli import (
    _run,
)


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
