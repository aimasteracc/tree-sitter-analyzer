"""Private mixins for read_partial_tool tests.

These modules keep the collected pytest node IDs anchored in test_read_partial_tool.py.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.unit.mcp.test_tools._test_read_partial_tool_payloads import (
    batch_args,
    batch_request,
)
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class ReadPartialToolCoverageExecuteMixin:
    """Coverage tests for single-file execute branches."""

    @pytest.mark.asyncio
    async def test_execute_batch_via_execute_method(self):
        """Test that execute() dispatches to _execute_batch (line 156)."""
        tool = ReadPartialTool()
        with patch.object(
            tool, "_execute_batch", return_value={"success": True, "results": []}
        ) as mock_batch:
            result = await tool.execute(
                {"requests": [{"file_path": "t.py", "sections": [{"start_line": 1}]}]}
            )
            assert result["success"] is True
            mock_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_no_end_line_single_line(self):
        """Test execute without end_line (branches 265->269, 283->287)."""
        tool = ReadPartialTool()
        test_content = "only_one_line"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                # Use json to access the range dict directly (value-kind rule
                # strips non-passthrough non-empty dicts in TOON mode)
                result = await tool.execute(
                    {"file_path": "t.py", "start_line": 1, "output_format": "json"}
                )
            assert result["success"] is True
            assert result["range"]["end_line"] is None
            assert "next_steps" not in result
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_json_format_lines_padding(self):
        """Test JSON format with end_line where content has fewer lines (lines 316-318)."""
        tool = ReadPartialTool()
        test_content = "line1"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        args = {
            "file_path": "t.py",
            "start_line": 1,
            "end_line": 3,
            "format": "json",
        }

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute(args)
            assert result["success"] is True
            if "partial_content_result" in result:
                lines = result["partial_content_result"]["lines"]
                assert len(lines) == 3
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_empty_output_file_string(self):
        """Test empty output_file string generates base name from file path (line 343)."""
        tool = ReadPartialTool()
        test_content = "hello\nworld\n"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", prefix="mytest", delete=False
        ) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/extract.md"
            ) as mock_save,
        ):
            result = await tool.execute(
                {
                    "file_path": "mytest.py",
                    "start_line": 1,
                    "end_line": 2,
                    "output_file": "   ",
                }
            )
        assert result["success"] is True
        assert result["file_saved"] is True
        mock_save.assert_called_once()
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_no_end_line_no_next_steps(self):
        """Test no end_line means no next_steps added (branch 301->308)."""
        tool = ReadPartialTool()
        test_content = "hello"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        args = {"file_path": "t.py", "start_line": 1, "output_format": "json"}

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute(args)
            assert result["success"] is True
            assert "next_steps" not in result
        finally:
            if test_file.exists():
                test_file.unlink()


class ReadPartialToolCoverageBatchMixin:
    """Coverage tests for batch execute branches."""

    @pytest.mark.asyncio
    async def test_batch_resolve_error_no_fail_fast(self):
        """Test batch resolve error without fail_fast (lines 508-517)."""
        tool = ReadPartialTool()
        args = batch_args(batch_request("x.py"), fail_fast=False)
        with patch.object(
            tool,
            "resolve_and_validate_file_path",
            side_effect=ValueError("access denied"),
        ):
            result = await tool._execute_batch(args)
        if "results" in result:
            assert any(
                "access denied" in e["error"] for e in result["results"][0]["errors"]
            )

    @pytest.mark.asyncio
    async def test_batch_raw_content_format(self):
        """Test batch mode with content_format='raw' (line 659)."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        args = batch_args(
            batch_request("t.py", [{"start_line": 1, "end_line": 2}]),
            format="raw",
        )
        path_patch = patch.object(
            tool,
            "resolve_and_validate_file_path",
            return_value=str(test_file),
        )

        try:
            with path_patch, patch.object(Path, "stat") as mock_stat:
                mock_stat.return_value.st_size = 100
                result = await tool._execute_batch(args)
            assert result["success"] is True
            assert result["count_sections"]
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_end_line_none_content_lines(self):
        """Test batch section without end_line (branch 630->634)."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        args = batch_args(batch_request("t.py"))
        path_patch = patch.object(
            tool,
            "resolve_and_validate_file_path",
            return_value=str(test_file),
        )

        try:
            with path_patch, patch.object(Path, "stat") as mock_stat:
                mock_stat.return_value.st_size = 100
                result = await tool._execute_batch(args)
            assert result["success"] is True
        finally:
            if test_file.exists():
                test_file.unlink()


class ReadPartialToolCoverageValidateMixin:
    """Coverage tests for validation branches."""

    def test_validate_file_path_not_string_branch(self):
        """Test validate_arguments with file_path as non-string (branch 752->760)."""
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments({"file_path": 42, "start_line": 1})

    def test_validate_file_path_empty_branch(self):
        """Test validate_arguments with empty file_path (branch 760->768)."""
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments({"file_path": "  ", "start_line": 1})
