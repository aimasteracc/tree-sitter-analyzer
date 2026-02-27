#!/usr/bin/env python3
"""Tests for list_files_cli module."""

from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.list_files_cli import _build_parser, _run, main


class TestBuildParser:
    """Test argument parser construction."""

    def test_parser_creation(self) -> None:
        parser = _build_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        assert "list" in parser.description.lower() or "fd" in parser.description.lower()

    def test_required_arguments(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_minimal_valid_arguments(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["root1"])
        assert args.roots == ["root1"]
        assert args.output_format == "json"
        assert args.quiet is False

    def test_multiple_roots(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["root1", "root2", "root3"])
        assert args.roots == ["root1", "root2", "root3"]

    def test_output_format_options(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["root1", "--output-format", "json"])
        assert args.output_format == "json"
        args = parser.parse_args(["root1", "--output-format", "text"])
        assert args.output_format == "text"
        with pytest.raises(SystemExit):
            parser.parse_args(["root1", "--output-format", "xml"])

    def test_quiet_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["root1", "--quiet"])
        assert args.quiet is True
        args = parser.parse_args(["root1"])
        assert args.quiet is False

    def test_all_options_together(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "root1", "root2", "--output-format", "text", "--quiet",
            "--pattern", "*.py", "--glob", "--types", "python",
            "--extensions", "py", "--exclude", "__pycache__",
            "--depth", "3", "--follow-symlinks", "--hidden", "--no-ignore",
            "--size", "+1K", "--changed-within", "1day",
            "--changed-before", "2023-12-31", "--full-path-match",
            "--limit", "50", "--count-only", "--project-root", "/project",
        ])
        assert args.roots == ["root1", "root2"]
        assert args.output_format == "text"
        assert args.quiet is True
        assert args.pattern == "*.py"
        assert args.glob is True
        assert args.depth == 3
        assert args.follow_symlinks is True
        assert args.hidden is True
        assert args.no_ignore is True
        assert args.limit == 50
        assert args.count_only is True
        assert args.project_root == "/project"


class TestRunFunction:
    """Test the _run async function."""

    @pytest.mark.asyncio
    async def test_minimal_execution(self) -> None:
        args = argparse.Namespace(
            roots=["root1"], output_format="json", quiet=False, project_root=None,
            pattern=None, glob=False, types=None, extensions=None, exclude=None,
            depth=None, follow_symlinks=False, hidden=False, no_ignore=False,
            size=None, changed_within=None, changed_before=None,
            full_path_match=False, limit=None, count_only=False,
        )
        mock_result = {"files": ["file1.py", "file2.py"], "success": True}
        with (
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root") as mock_detect,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool") as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode") as mock_set_output,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_data") as mock_output,
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
            mock_output.assert_called_once_with(mock_result, "json")

    @pytest.mark.asyncio
    async def test_text_output_format(self) -> None:
        args = argparse.Namespace(
            roots=["root1"], output_format="text", quiet=True, project_root="/custom/root",
            pattern=None, glob=False, types=None, extensions=None, exclude=None,
            depth=None, follow_symlinks=False, hidden=False, no_ignore=False,
            size=None, changed_within=None, changed_before=None,
            full_path_match=False, limit=None, count_only=False,
        )
        with (
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root") as mock_detect,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool") as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode") as mock_set_output,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_data") as mock_output,
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
    async def test_error_handling(self) -> None:
        args = argparse.Namespace(
            roots=["root1"], output_format="json", quiet=False, project_root=None,
            pattern=None, glob=False, types=None, extensions=None, exclude=None,
            depth=None, follow_symlinks=False, hidden=False, no_ignore=False,
            size=None, changed_within=None, changed_before=None,
            full_path_match=False, limit=None, count_only=False,
        )
        with (
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root") as mock_detect,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool") as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_error") as mock_error,
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
        args = argparse.Namespace(
            roots=["root1"], output_format="json", quiet=False, project_root="/custom/path",
            pattern=None, glob=False, types=None, extensions=None, exclude=None,
            depth=None, follow_symlinks=False, hidden=False, no_ignore=False,
            size=None, changed_within=None, changed_before=None,
            full_path_match=False, limit=None, count_only=False,
        )
        with (
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root") as mock_detect,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool") as mock_tool_class,
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


class TestMainFunction:
    """Test the main() entry point."""

    def test_main_success(self) -> None:
        with (
            patch("sys.argv", ["list_files_cli.py", "root1"]),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root") as mock_detect,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool") as mock_tool_class,
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
        with (
            patch("sys.argv", ["list_files_cli.py", "root1"]),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root") as mock_detect,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool") as mock_tool_class,
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
        with (
            patch("sys.argv", ["list_files_cli.py", "root1"]),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root") as mock_detect,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool") as mock_tool_class,
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
        with (
            patch("sys.argv", ["list_files_cli.py", "--invalid-arg"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code != 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_depth_zero(self) -> None:
        args = argparse.Namespace(
            roots=["root1"], output_format="json", quiet=False, project_root=None,
            pattern=None, glob=False, types=None, extensions=None, exclude=None,
            depth=0, follow_symlinks=False, hidden=False, no_ignore=False,
            size=None, changed_within=None, changed_before=None,
            full_path_match=False, limit=None, count_only=False,
        )
        with (
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root") as mock_detect,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool") as mock_tool_class,
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

    def test_parser_help(self) -> None:
        parser = _build_parser()
        help_str = parser.format_help()
        assert "roots" in help_str.lower() or "root" in help_str.lower()
