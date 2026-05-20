#!/usr/bin/env python3
"""Tests for _run function in search_content_cli module."""

from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.search_content_cli import _run


class TestRunFunction:
    """Test the _run async function."""

    @pytest.mark.asyncio
    async def test_minimal_execution_with_roots(self) -> None:
        """Test minimal execution with roots."""
        args = argparse.Namespace(
            roots=["root1"],
            files=None,
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
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

        mock_result = {"matches": 5, "files": ["file1.py"]}

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
            ) as mock_set_output,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
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

            call_args = mock_tool.execute.call_args[0][0]
            assert call_args["query"] == "test"
            assert call_args["roots"] == ["root1"]
            assert "files" not in call_args

            mock_output.assert_called_once_with(mock_result, "json")

    @pytest.mark.asyncio
    async def test_minimal_execution_with_files(self) -> None:
        """Test minimal execution with files."""
        args = argparse.Namespace(
            roots=None,
            files=["file1.py", "file2.py"],
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
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
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.search_content_cli.output_data"),
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            call_args = mock_tool.execute.call_args[0][0]
            assert call_args["query"] == "test"
            assert call_args["files"] == ["file1.py", "file2.py"]
            assert "roots" not in call_args

    @pytest.mark.asyncio
    async def test_text_output_format(self) -> None:
        """Test text output format."""
        args = argparse.Namespace(
            roots=["root1"],
            files=None,
            query="test",
            output_format="text",
            quiet=True,
            project_root="/custom/root",
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
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
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
            ) as mock_set_output,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
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
    async def test_all_options_in_payload(self) -> None:
        """Test all options are included in payload."""
        args = argparse.Namespace(
            roots=["root1"],
            files=None,
            query="search_term",
            output_format="json",
            quiet=False,
            project_root=None,
            case="insensitive",
            fixed_strings=True,
            word=True,
            multiline=True,
            include_globs=["*.py"],
            exclude_globs=["*.txt"],
            follow_symlinks=True,
            hidden=True,
            no_ignore=True,
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
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.search_content_cli.output_data"),
        ):
            mock_detect.return_value = "/project/root"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            # Check the payload passed to execute
            call_args = mock_tool.execute.call_args[0][0]
            assert call_args["query"] == "search_term"
            assert call_args["case"] == "insensitive"
            assert call_args["fixed_strings"] is True
            assert call_args["word"] is True
            assert call_args["multiline"] is True
            assert call_args["include_globs"] == ["*.py"]
            assert call_args["exclude_globs"] == ["*.txt"]
            assert call_args["follow_symlinks"] is True
            assert call_args["hidden"] is True
            assert call_args["no_ignore"] is True
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
            files=None,
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
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
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
            ),
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.output_data"
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
            files=None,
            query="test",
            output_format="json",
            quiet=False,
            project_root=None,
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
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
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
            ),
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.output_error"
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
            files=None,
            query="test",
            output_format="json",
            quiet=False,
            project_root="/custom/path",
            case="smart",
            fixed_strings=False,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
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
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.search_content_cli.output_data"),
        ):
            mock_detect.return_value = "/custom/path"
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value={})
            mock_tool_class.return_value = mock_tool

            await _run(args)

            mock_detect.assert_called_once_with(None, "/custom/path")
            mock_tool_class.assert_called_once_with("/custom/path")
