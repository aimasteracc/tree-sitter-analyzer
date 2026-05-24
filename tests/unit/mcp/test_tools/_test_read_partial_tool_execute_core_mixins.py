"""Private mixins for read_partial_tool tests.

These modules keep the collected pytest node IDs anchored in test_read_partial_tool.py.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class ReadPartialToolExecuteMixin:
    """Tests for execute method (single mode)."""

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(self):
        """Test execution fails when file_path is missing."""
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="file_path is required"):
            await tool.execute({"start_line": 1})

    @pytest.mark.asyncio
    async def test_execute_missing_start_line(self):
        """Test execution fails when start_line is missing."""
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="start_line is required"):
            await tool.execute({"file_path": "test.py"})

    @pytest.mark.asyncio
    async def test_execute_invalid_path(self):
        """Test execution fails for invalid file path."""
        tool = ReadPartialTool()
        result = await tool.execute(
            {"file_path": "../../../etc/passwd", "start_line": 1}
        )
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self):
        """Test execution fails when file doesn't exist."""
        tool = ReadPartialTool()
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/fake/path.py"
        ):
            result = await tool.execute(
                {"file_path": "nonexistent.py", "start_line": 1}
            )
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_invalid_start_line(self):
        """Test execution fails when start_line < 1."""
        tool = ReadPartialTool()
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
        ):
            result = await tool.execute({"file_path": "test.py", "start_line": 0})
        assert result["success"] is False
        assert "start_line must be >= 1" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_invalid_end_line(self):
        """Test execution fails when end_line < start_line."""
        tool = ReadPartialTool()
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
        ):
            result = await tool.execute(
                {"file_path": "test.py", "start_line": 10, "end_line": 5}
            )
        assert result["success"] is False
        assert "end_line must be >= start_line" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_invalid_start_column(self):
        """Test execution fails when start_column < 0."""
        tool = ReadPartialTool()
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
        ):
            result = await tool.execute(
                {"file_path": "test.py", "start_line": 1, "start_column": -1}
            )
        assert result["success"] is False
        assert "start_column must be >= 0" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_invalid_end_column(self):
        """Test execution fails when end_column < 0."""
        tool = ReadPartialTool()
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
        ):
            result = await tool.execute(
                {"file_path": "test.py", "start_line": 1, "end_column": -1}
            )
        assert result["success"] is False
        assert "end_column must be >= 0" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_success_text_format(self):
        """Test successful execution with text format."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3"

        # Use temporary file to avoid permission issues
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        args = {
            "file_path": "test_data.py",
            "start_line": 1,
            "end_line": 2,
            "output_format": "json",
        }

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute(args)
            assert result["success"] is True
            assert result["file_path"] == "test_data.py"
            assert result["range"]["start_line"] == 1
            assert result["range"]["end_line"] == 2
            assert result["agent_summary"]["risk"] == "low"
            assert result["agent_summary"]["suggested_tool"] == "query_code"
            # TOON format converts partial_content_result to toon_content
            assert "toon_content" in result or "partial_content_result" in result
        finally:
            # Clean up
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_success_json_format(self):
        """Test successful execution with JSON format."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3"

        # Use temporary file to avoid permission issues
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        args = {
            "file_path": "test_data.py",
            "start_line": 1,
            "end_line": 2,
            "format": "json",
        }

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute(args)
            assert result["success"] is True
            # TOON format converts partial_content_result to toon_content
            assert "toon_content" in result or "partial_content_result" in result
            if "partial_content_result" in result:
                assert "lines" in result["partial_content_result"]
                assert "metadata" in result["partial_content_result"]
        finally:
            # Clean up
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_suppress_output(self):
        """Test execution with suppress_output=True."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3"

        # Use temporary file to avoid permission issues
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        args = {
            "file_path": "test_data.py",
            "start_line": 1,
            "end_line": 2,
            "suppress_output": True,
        }

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute(args)
            assert result["success"] is True
            # partial_content_result should still be included when no output_file
            assert "toon_content" in result or "partial_content_result" in result
        finally:
            # Clean up
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_empty_content(self):
        """Empty file with a non-trivial range used to fail with a
        generic ``success: False`` envelope. K8 (round-24) reshapes
        this to a structured ``out_of_range`` response so the agent
        can recover with a valid range instead of treating it as a
        hard error.
        """
        tool = ReadPartialTool()

        # Use temporary file to avoid permission issues
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")
            f.flush()
            test_file = Path(f.name)

        # Force JSON output so ``content``/``lines_extracted`` stay
        # at the top of the envelope (TOON would fold them into the
        # ``toon_content`` blob).
        args = {
            "file_path": "test_data.py",
            "start_line": 1,
            "end_line": 10,
            "output_format": "json",
        }

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute(args)
            # K8: empty file with a past-EOF range now returns a
            # structured success envelope with out_of_range=True.
            assert result["success"] is True
            assert result["content"] == ""
            assert result["content_length"] == 0
            assert result["lines_extracted"] == 0
            assert result.get("out_of_range") is True
            # Canonical verdict vocabulary (CLAUDE.md): out-of-range maps to
            # NOT_FOUND, not the historical "N/A" placeholder.
            assert result["agent_summary"]["verdict"] == "NOT_FOUND"
        finally:
            # Clean up
            if test_file.exists():
                test_file.unlink()


class ReadPartialToolReadFilePartialMixin:
    """Tests for _read_file_partial method."""

    @pytest.mark.asyncio
    async def test_read_file_partial_success(self):
        """Test successful partial file read."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3"

        # Use temporary file to avoid permission issues
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        try:
            content = tool._read_file_partial(str(test_file), 1, 2)
            assert content is not None
            assert "line1" in content or "line2" in content
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_read_file_partial_with_columns(self):
        """Test partial file read with column ranges."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        try:
            content = tool._read_file_partial(str(test_file), 1, 1, 0, 4)
            assert content is not None
        finally:
            if test_file.exists():
                test_file.unlink()
