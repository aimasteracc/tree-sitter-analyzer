#!/usr/bin/env python3
"""Comprehensive tests for list_files_cli _run and main execution paths."""

from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.list_files_cli import _run, main


def _make_args(**overrides: object) -> argparse.Namespace:
    """Build a default args namespace with optional overrides."""
    defaults = {
        "roots": ["root1"],
        "output_format": "json",
        "quiet": False,
        "project_root": None,
        "pattern": None,
        "glob": False,
        "types": None,
        "extensions": None,
        "exclude": None,
        "depth": None,
        "follow_symlinks": False,
        "hidden": False,
        "no_ignore": False,
        "size": None,
        "changed_within": None,
        "changed_before": None,
        "full_path_match": False,
        "limit": None,
        "count_only": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestRunFunction:
    """Test the _run async function."""

    @pytest.mark.asyncio
    async def test_minimal_execution(self) -> None:
        """Test minimal execution with required arguments."""
        args = _make_args()

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
        args = _make_args(output_format="text", quiet=True, project_root="/custom/root")

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
        args = _make_args(
            roots=["root1", "root2"],
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
        args = _make_args()

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
        args = _make_args(project_root="/custom/path")

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
        args = _make_args()

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
            mock_tool.execute = AsyncMock(return_value={"files": ["file1.py"]})
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
        args = _make_args(depth=0)

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
        args = _make_args(limit=0)

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
        args = _make_args()

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
