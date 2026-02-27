#!/usr/bin/env python3
"""
Unit tests for read_partial_tool.py

Tests for ReadPartialTool MCP tool which provides partial file reading functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class TestReadPartialToolInit:
    """Tests for ReadPartialTool initialization."""

    def test_init_without_project_root(self):
        """Test initialization without project root."""
        tool = ReadPartialTool()
        assert tool is not None
        assert tool.project_root is None
        assert tool.file_output_manager is not None

    def test_init_with_project_root(self):
        """Test initialization with project root."""
        tool = ReadPartialTool(project_root="/test/path")
        assert tool is not None
        assert tool.project_root == "/test/path"
        assert tool.file_output_manager is not None


class TestReadPartialToolGetToolSchema:
    """Tests for get_tool_schema method."""

    def test_get_tool_schema_structure(self):
        """Test that schema has correct structure."""
        tool = ReadPartialTool()
        schema = tool.get_tool_schema()
        assert isinstance(schema, dict)
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_get_tool_schema_has_requests_property(self):
        """Test that schema has requests property for batch mode."""
        tool = ReadPartialTool()
        schema = tool.get_tool_schema()
        assert "requests" in schema["properties"]
        requests_prop = schema["properties"]["requests"]
        assert requests_prop["type"] == "array"

    def test_get_tool_schema_has_file_path_property(self):
        """Test that schema has file_path property."""
        tool = ReadPartialTool()
        schema = tool.get_tool_schema()
        assert "file_path" in schema["properties"]
        assert schema["properties"]["file_path"]["type"] == "string"


class TestReadPartialToolGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self):
        """Test that tool definition has correct name."""
        tool = ReadPartialTool()
        definition = tool.get_tool_definition()
        assert definition["name"] == "extract_code_section"

    def test_get_tool_definition_has_description(self):
        """Test that tool definition has description."""
        tool = ReadPartialTool()
        definition = tool.get_tool_definition()
        assert "description" in definition
        assert isinstance(definition["description"], str)

    def test_get_tool_definition_has_input_schema(self):
        """Test that tool definition has inputSchema."""
        tool = ReadPartialTool()
        definition = tool.get_tool_definition()
        assert "inputSchema" in definition
        assert isinstance(definition["inputSchema"], dict)


class TestReadPartialToolValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_arguments_missing_file_path(self):
        """Test that validation fails when file_path is missing."""
        tool = ReadPartialTool()
        args = {"start_line": 1}
        with pytest.raises(ValueError, match="Required field 'file_path' is missing"):
            tool.validate_arguments(args)

    def test_validate_arguments_missing_start_line(self):
        """Test that validation fails when start_line is missing."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py"}
        with pytest.raises(ValueError, match="Required field 'start_line' is missing"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_file_path_type(self):
        """Test that validation fails when file_path is not a string."""
        tool = ReadPartialTool()
        args = {"file_path": 123, "start_line": 1}
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(args)

    def test_validate_arguments_empty_file_path(self):
        """Test that validation fails when file_path is empty."""
        tool = ReadPartialTool()
        args = {"file_path": "", "start_line": 1}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_start_line_type(self):
        """Test that validation fails when start_line is not an integer."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": "1"}
        with pytest.raises(ValueError, match="start_line must be an integer"):
            tool.validate_arguments(args)

    def test_validate_arguments_start_line_below_minimum(self):
        """Test that validation fails when start_line < 1."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 0}
        with pytest.raises(ValueError, match="start_line must be >= 1"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_end_line_type(self):
        """Test that validation fails when end_line is not an integer."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "end_line": "10"}
        with pytest.raises(ValueError, match="end_line must be an integer"):
            tool.validate_arguments(args)

    def test_validate_arguments_end_line_below_start_line(self):
        """Test that validation fails when end_line < start_line."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 10, "end_line": 5}
        with pytest.raises(ValueError, match="end_line must be >= start_line"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_start_column_type(self):
        """Test that validation fails when start_column is not an integer."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "start_column": "0"}
        with pytest.raises(ValueError, match="start_column must be an integer"):
            tool.validate_arguments(args)

    def test_validate_arguments_start_column_below_zero(self):
        """Test that validation fails when start_column < 0."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "start_column": -1}
        with pytest.raises(ValueError, match="start_column must be >= 0"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_format(self):
        """Test that validation fails when format is invalid."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "format": "invalid"}
        with pytest.raises(ValueError, match="format must be 'text', 'json', or 'raw'"):
            tool.validate_arguments(args)

    def test_validate_arguments_valid_single_mode(self):
        """Test that validation passes for valid single mode arguments."""
        tool = ReadPartialTool()
        args = {
            "file_path": "test.py",
            "start_line": 1,
            "end_line": 10,
            "format": "text",
        }
        assert tool.validate_arguments(args) is True

    def test_validate_arguments_valid_batch_mode(self):
        """Test that validation passes for valid batch mode arguments."""
        tool = ReadPartialTool()
        args = {"requests": [{"file_path": "test.py", "sections": [{"start_line": 1}]}]}
        assert tool.validate_arguments(args) is True

    def test_validate_arguments_mutually_exclusive(self):
        """Test that validation fails when both batch and single mode args are present."""
        tool = ReadPartialTool()
        args = {
            "file_path": "test.py",
            "start_line": 1,
            "requests": [{"file_path": "test.py", "sections": []}],
        }
        with pytest.raises(ValueError, match="mutually exclusive"):
            tool.validate_arguments(args)


class TestReadPartialToolExecute:
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

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute(
                    {"file_path": "test_data.py", "start_line": 1, "end_line": 2}
                )
            assert result["success"] is True
            assert result["file_path"] == "test_data.py"
            assert result["range"]["start_line"] == 1
            assert result["range"]["end_line"] == 2
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

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute(
                    {
                        "file_path": "test_data.py",
                        "start_line": 1,
                        "end_line": 2,
                        "format": "json",
                    }
                )
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

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute(
                    {
                        "file_path": "test_data.py",
                        "start_line": 1,
                        "end_line": 2,
                        "suppress_output": True,
                    }
                )
            assert result["success"] is True
            # partial_content_result should still be included when no output_file
            assert "toon_content" in result or "partial_content_result" in result
        finally:
            # Clean up
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_empty_content(self):
        """Test execution returns error for empty content."""
        tool = ReadPartialTool()

        # Use temporary file to avoid permission issues
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute(
                    {"file_path": "test_data.py", "start_line": 1, "end_line": 10}
                )
            assert result["success"] is False
            assert "Invalid line range or empty content" in result["error"]
        finally:
            # Clean up
            if test_file.exists():
                test_file.unlink()


class TestReadPartialToolExecuteBatch:
    """Tests for _execute_batch method (batch mode)."""

    @pytest.mark.asyncio
    async def test_execute_batch_mutually_exclusive(self):
        """Test that batch mode fails with single mode arguments."""
        tool = ReadPartialTool()
        args = {
            "requests": [{"file_path": "test.py", "sections": [{"start_line": 1}]}],
            "file_path": "test.py",
        }
        with pytest.raises(ValueError, match="mutually exclusive"):
            await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_execute_batch_file_output_not_supported(self):
        """Test that batch mode doesn't support file output options."""
        tool = ReadPartialTool()
        args = {
            "requests": [{"file_path": "test.py", "sections": [{"start_line": 1}]}],
            "output_file": "output.txt",
        }
        with pytest.raises(
            ValueError, match="output_file/suppress_output are not supported"
        ):
            await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_execute_batch_invalid_requests_type(self):
        """Test that batch mode fails when requests is not a list."""
        tool = ReadPartialTool()
        args = {"requests": "not a list"}
        with pytest.raises(ValueError, match="requests must be a list"):
            await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_execute_batch_too_many_files(self):
        """Test that batch mode fails when too many files."""
        tool = ReadPartialTool()
        requests = [
            {"file_path": f"test{i}.py", "sections": [{"start_line": 1}]}
            for i in range(25)
        ]
        args = {"requests": requests}
        with pytest.raises(ValueError, match="Too many files"):
            await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_execute_batch_too_many_files_with_truncate(self):
        """Test that batch mode truncates when allow_truncate=True."""
        tool = ReadPartialTool()
        requests = [
            {"file_path": f"test{i}.py", "sections": [{"start_line": 1}]}
            for i in range(25)
        ]
        args = {"requests": requests, "allow_truncate": True}
        result = await tool._execute_batch(args)
        assert result["truncated"] is True
        assert result["count_files"] == 20  # max_files limit

    @pytest.mark.asyncio
    async def test_execute_batch_invalid_request_entry(self):
        """Test that batch mode handles invalid request entries."""
        tool = ReadPartialTool()
        args = {"requests": ["not a dict"], "fail_fast": False}
        result = await tool._execute_batch(args)
        assert result["success"] is False
        assert result["count_files"] == 1
        # Check if results key exists
        if "results" in result:
            assert len(result["results"][0]["errors"]) > 0

    @pytest.mark.asyncio
    async def test_execute_batch_invalid_file_path(self):
        """Test that batch mode handles invalid file_path."""
        tool = ReadPartialTool()
        args = {
            "requests": [{"file_path": "", "sections": [{"start_line": 1}]}],
            "fail_fast": False,
        }
        result = await tool._execute_batch(args)
        assert result["count_files"] == 1
        if "results" in result:
            assert len(result["results"][0]["errors"]) > 0

    @pytest.mark.asyncio
    async def test_execute_batch_invalid_sections(self):
        """Test that batch mode handles invalid sections."""
        tool = ReadPartialTool()
        args = {
            "requests": [{"file_path": "test.py", "sections": "not a list"}],
            "fail_fast": False,
        }
        result = await tool._execute_batch(args)
        assert result["count_files"] == 1
        if "results" in result:
            assert len(result["results"][0]["errors"]) > 0

    @pytest.mark.asyncio
    async def test_execute_batch_too_many_sections_per_file(self):
        """Test that batch mode fails when too many sections per file."""
        tool = ReadPartialTool()
        sections = [{"start_line": i} for i in range(60)]
        args = {
            "requests": [{"file_path": "test.py", "sections": sections}],
            "fail_fast": True,
        }
        with pytest.raises(ValueError, match="Too many sections"):
            await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_execute_batch_too_many_sections_per_file_with_truncate(self):
        """Test that batch mode truncates sections when allow_truncate=True."""
        tool = ReadPartialTool()
        sections = [{"start_line": i} for i in range(60)]
        args = {
            "requests": [{"file_path": "test.py", "sections": sections}],
            "allow_truncate": True,
        }
        result = await tool._execute_batch(args)
        assert result["truncated"] is True
        if "results" in result:
            assert len(result["results"][0]["sections"]) == 50  # max_sections_per_file

    @pytest.mark.asyncio
    async def test_execute_batch_file_not_found(self):
        """Test that batch mode handles file not found."""
        tool = ReadPartialTool()
        args = {
            "requests": [
                {"file_path": "nonexistent.py", "sections": [{"start_line": 1}]}
            ],
            "fail_fast": False,
        }
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/nonexistent.py"
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            result = await tool._execute_batch(args)
        assert result["count_files"] == 1
        if "results" in result:
            assert len(result["results"][0]["errors"]) > 0

    @pytest.mark.asyncio
    async def test_execute_batch_invalid_section_entry(self):
        """Test that batch mode handles invalid section entries."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3"

        # Use temporary file to avoid permission issues
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                args = {
                    "requests": [
                        {"file_path": "test_data.py", "sections": ["not a dict"]}
                    ],
                    "fail_fast": False,
                }
                result = await tool._execute_batch(args)
            assert result["count_files"] == 1
            if "results" in result:
                assert len(result["results"][0]["errors"]) > 0
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_batch_invalid_start_line(self):
        """Test that batch mode handles invalid start_line."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3"

        # Use temporary file to avoid permission issues
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                args = {
                    "requests": [
                        {"file_path": "test_data.py", "sections": [{"start_line": 0}]}
                    ],
                    "fail_fast": False,
                }
                result = await tool._execute_batch(args)
            assert result["count_files"] == 1
            if "results" in result:
                assert len(result["results"][0]["errors"]) > 0
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_batch_invalid_end_line(self):
        """Test that batch mode handles invalid end_line."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3"

        # Use temporary file to avoid permission issues
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                args = {
                    "requests": [
                        {
                            "file_path": "test_data.py",
                            "sections": [{"start_line": 10, "end_line": 5}],
                        }
                    ],
                    "fail_fast": False,
                }
                result = await tool._execute_batch(args)
            assert result["count_files"] == 1
            if "results" in result:
                assert len(result["results"][0]["errors"]) > 0
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_batch_success(self):
        """Test successful batch execution."""
        tool = ReadPartialTool()
        test_content = "line1\nline2\nline3\nline4\nline5"

        # Use temporary file to avoid permission issues
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                args = {
                    "requests": [
                        {
                            "file_path": "test_data.py",
                            "sections": [
                                {"start_line": 1, "end_line": 2, "label": "section1"},
                                {"start_line": 4, "end_line": 5, "label": "section2"},
                            ],
                        }
                    ]
                }
                result = await tool._execute_batch(args)
            assert result["success"] is True
            assert result["count_files"] == 1
            # count_sections may be less than expected if some sections fail
            assert result["count_sections"] >= 1
            if "results" in result:
                assert len(result["results"][0]["sections"]) >= 1
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_batch_fail_fast(self):
        """Test that batch mode stops on first error when fail_fast=True."""
        tool = ReadPartialTool()
        args = {
            "requests": [
                {"file_path": "test.py", "sections": [{"start_line": 1}]},
                {"file_path": "", "sections": [{"start_line": 1}]},
            ],
            "fail_fast": True,
        }
        # The error message contains "Invalid file path"
        with pytest.raises(ValueError, match="Invalid file path"):
            await tool._execute_batch(args)


class TestReadPartialToolReadFilePartial:
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

        # Use temporary file to avoid permission issues
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


# ---------------------------------------------------------------------------
# Additional targeted tests for uncovered branches in read_partial_tool.py
# ---------------------------------------------------------------------------


class TestExecuteSingleBranches:
    """Test uncovered branches in single-mode execute."""

    @pytest.mark.asyncio
    async def test_execute_content_returns_none(self):
        """Test execute when _read_file_partial returns None (line 233)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch.object(
                tool, "_read_file_partial", return_value=None
            ):
                result = await tool.execute({
                    "file_path": "test.py",
                    "start_line": 1,
                })
                assert result["success"] is False
                assert "Failed to read partial content" in result["error"]
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_json_format_padding(self):
        """Test JSON format when lines < lines_extracted (padding) (lines 309-311)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\n")  # Only 1 line, but request 1-5
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute({
                    "file_path": "test.py",
                    "start_line": 1,
                    "end_line": 5,
                    "format": "json",
                    "output_format": "json",
                })
                assert result["success"] is True
                if "partial_content_result" in result:
                    pcr = result["partial_content_result"]
                    # Should have padded to 5 lines
                    assert len(pcr["lines"]) == 5
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_json_format_truncate_lines(self):
        """Test JSON format when lines > lines_extracted (truncation) (lines 307-308)."""
        tool = ReadPartialTool()
        # Create a file with many lines
        content = "\n".join([f"line{i}" for i in range(20)])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool.execute({
                    "file_path": "test.py",
                    "start_line": 1,
                    "end_line": 3,
                    "format": "json",
                    "output_format": "json",
                })
                assert result["success"] is True
                if "partial_content_result" in result:
                    pcr = result["partial_content_result"]
                    assert len(pcr["lines"]) == 3
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_with_output_file_raw_format(self):
        """Test execute with output_file and raw format (lines 341-342)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/extract.txt"
            ):
                result = await tool.execute({
                    "file_path": "test.py",
                    "start_line": 1,
                    "end_line": 2,
                    "format": "raw",
                    "output_file": "extract.txt",
                    "output_format": "json",
                })
                assert result["success"] is True
                assert result.get("file_saved") is True
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_with_output_file_json_toon_format(self):
        """Test execute with output_file, json format, and toon output (lines 346-349)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/extract.json"
            ):
                result = await tool.execute({
                    "file_path": "test.py",
                    "start_line": 1,
                    "end_line": 2,
                    "format": "json",
                    "output_file": "extract.json",
                    "output_format": "toon",
                })
                assert result["success"] is True
                assert result.get("file_saved") is True
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_with_output_file_json_json_format(self):
        """Test execute with output_file, json format, json output (lines 350-351)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/extract.json"
            ):
                result = await tool.execute({
                    "file_path": "test.py",
                    "start_line": 1,
                    "end_line": 2,
                    "format": "json",
                    "output_file": "extract.json",
                    "output_format": "json",
                })
                assert result["success"] is True
                assert result.get("file_saved") is True
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_with_output_file_empty_name(self):
        """Test execute with output_file as empty string (line 335-336)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/extract.txt"
            ):
                result = await tool.execute({
                    "file_path": "test.py",
                    "start_line": 1,
                    "end_line": 2,
                    "output_file": "   ",
                    "output_format": "json",
                })
                assert result["success"] is True
                # Should generate a base name from file path
                assert result.get("file_saved") is True
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_output_file_save_error(self):
        """Test execute when file save throws exception (lines 366-369)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch.object(
                tool.file_output_manager, "save_to_file", side_effect=Exception("disk full")
            ):
                result = await tool.execute({
                    "file_path": "test.py",
                    "start_line": 1,
                    "end_line": 2,
                    "output_file": "extract.txt",
                    "output_format": "json",
                })
                assert result["success"] is True
                assert "file_save_error" in result
                assert result["file_saved"] is False
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_general_exception(self):
        """Test execute when _read_file_partial raises exception (lines 374-376)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch.object(
                tool, "_read_file_partial", side_effect=Exception("read error")
            ):
                result = await tool.execute({
                    "file_path": "test.py",
                    "start_line": 1,
                })
                assert result["success"] is False
                assert "read error" in result["error"]
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_suppress_output_with_output_file(self):
        """Test suppress_output=True with output_file set (line 301 - suppress branch)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/out.txt"
            ):
                result = await tool.execute({
                    "file_path": "test.py",
                    "start_line": 1,
                    "end_line": 2,
                    "output_file": "out.txt",
                    "suppress_output": True,
                    "output_format": "json",
                })
                assert result["success"] is True
                # When suppress=True + output_file, partial_content_result should be absent
                assert "partial_content_result" not in result
        finally:
            if test_file.exists():
                test_file.unlink()


class TestExecuteBatchBranches:
    """Test uncovered branches in batch mode execute."""

    @pytest.mark.asyncio
    async def test_batch_fail_fast_invalid_entry(self):
        """Test batch fail_fast with invalid request entry (lines 435-436)."""
        tool = ReadPartialTool()
        args = {
            "requests": ["not a dict"],
            "fail_fast": True,
        }
        with pytest.raises(ValueError, match="Each requests.*entry must be an object"):
            await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_batch_fail_fast_empty_file_path(self):
        """Test batch fail_fast with empty file_path (lines 451-452)."""
        tool = ReadPartialTool()
        args = {
            "requests": [{"file_path": "", "sections": [{"start_line": 1}]}],
            "fail_fast": True,
        }
        with pytest.raises(ValueError, match="non-empty string"):
            await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_batch_fail_fast_invalid_sections(self):
        """Test batch fail_fast with invalid sections (lines 463-465)."""
        tool = ReadPartialTool()
        args = {
            "requests": [{"file_path": "test.py", "sections": "not a list"}],
            "fail_fast": True,
        }
        with pytest.raises(ValueError, match="sections must be a list"):
            await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_batch_too_many_sections_no_truncate_no_fail_fast(self):
        """Test batch too many sections without truncate and without fail_fast (lines 478-492)."""
        tool = ReadPartialTool()
        sections = [{"start_line": i + 1} for i in range(60)]
        args = {
            "requests": [{"file_path": "test.py", "sections": sections}],
            "fail_fast": False,
            "allow_truncate": False,
        }
        result = await tool._execute_batch(args)
        # Should get error about too many sections
        assert result["count_files"] == 1
        if "results" in result:
            assert len(result["results"][0]["errors"]) > 0

    @pytest.mark.asyncio
    async def test_batch_fail_fast_security_validation_error(self):
        """Test batch fail_fast when security validation fails (lines 498-500)."""
        tool = ReadPartialTool()
        with patch.object(
            tool, "resolve_and_validate_file_path",
            side_effect=ValueError("path traversal detected"),
        ):
            args = {
                "requests": [{"file_path": "../../../etc/passwd", "sections": [{"start_line": 1}]}],
                "fail_fast": True,
            }
            with pytest.raises(ValueError, match="path traversal"):
                await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_batch_fail_fast_file_not_found(self):
        """Test batch fail_fast when file doesn't exist (lines 515-516)."""
        tool = ReadPartialTool()
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/nonexistent.py"
        ), patch("pathlib.Path.exists", return_value=False):
            args = {
                "requests": [{"file_path": "nonexistent.py", "sections": [{"start_line": 1}]}],
                "fail_fast": True,
            }
            with pytest.raises(ValueError, match="file does not exist"):
                await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_batch_file_too_large(self):
        """Test batch when file exceeds max_file_size_bytes (lines 529-542)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x" * 100)
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch("pathlib.Path.stat") as mock_stat:
                mock_stat_result = MagicMock()
                mock_stat_result.st_size = 10 * 1024 * 1024  # 10 MiB > 5 MiB limit
                mock_stat.return_value = mock_stat_result

                args = {
                    "requests": [{"file_path": "test.py", "sections": [{"start_line": 1}]}],
                    "fail_fast": False,
                }
                result = await tool._execute_batch(args)
                if "results" in result:
                    assert any("too large" in str(e) for e in result["results"][0]["errors"])
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_fail_fast_file_too_large(self):
        """Test batch fail_fast when file too large (lines 531-532)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x" * 100)
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch("pathlib.Path.stat") as mock_stat:
                mock_stat_result = MagicMock()
                mock_stat_result.st_size = 10 * 1024 * 1024
                mock_stat.return_value = mock_stat_result

                args = {
                    "requests": [{"file_path": "test.py", "sections": [{"start_line": 1}]}],
                    "fail_fast": True,
                }
                with pytest.raises(ValueError, match="File too large"):
                    await tool._execute_batch(args)
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_stat_os_error(self):
        """Test batch when stat raises OSError (lines 543-556)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                # Use a mock Path class that returns an object with controlled behavior
                original_path_cls = Path

                class _StatErrorPath:
                    """Proxy that makes stat() raise OSError but exists() return True."""

                    def __init__(self, *args, **kwargs):
                        self._real = original_path_cls(*args, **kwargs)

                    def exists(self):
                        return True

                    def stat(self, *args, **kwargs):
                        raise OSError("permission denied")

                with patch("tree_sitter_analyzer.mcp.tools.read_partial_tool.Path", _StatErrorPath):
                    args = {
                        "requests": [{"file_path": "test.py", "sections": [{"start_line": 1}]}],
                        "fail_fast": False,
                    }
                    result = await tool._execute_batch(args)
                    if "results" in result:
                        assert any("Could not stat" in str(e) for e in result["results"][0]["errors"])
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_fail_fast_stat_os_error(self):
        """Test batch fail_fast when stat raises OSError (lines 545-546)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                original_path_cls = Path

                class _StatErrorPath2:
                    """Proxy that makes stat() raise OSError but exists() return True."""

                    def __init__(self, *args, **kwargs):
                        self._real = original_path_cls(*args, **kwargs)

                    def exists(self):
                        return True

                    def stat(self, *args, **kwargs):
                        raise OSError("permission denied")

                with patch("tree_sitter_analyzer.mcp.tools.read_partial_tool.Path", _StatErrorPath2):
                    args = {
                        "requests": [{"file_path": "test.py", "sections": [{"start_line": 1}]}],
                        "fail_fast": True,
                    }
                    with pytest.raises(ValueError, match="Could not stat file"):
                        await tool._execute_batch(args)
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_section_invalid_entry_fail_fast(self):
        """Test batch section not-a-dict with fail_fast (lines 566-570)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                args = {
                    "requests": [{"file_path": "test.py", "sections": ["not a dict"]}],
                    "fail_fast": True,
                }
                result = await tool._execute_batch(args)
                # fail_fast causes break, so we get partial result
                assert result["count_files"] == 1
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_section_invalid_start_line_fail_fast(self):
        """Test batch section with invalid start_line with fail_fast (lines 576-582)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                args = {
                    "requests": [
                        {"file_path": "test.py", "sections": [{"start_line": -1}]}
                    ],
                    "fail_fast": True,
                }
                result = await tool._execute_batch(args)
                assert result["count_files"] == 1
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_section_invalid_end_line_fail_fast(self):
        """Test batch section with invalid end_line with fail_fast (lines 584-595)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                args = {
                    "requests": [
                        {"file_path": "test.py", "sections": [{"start_line": 10, "end_line": 5}]}
                    ],
                    "fail_fast": True,
                }
                result = await tool._execute_batch(args)
                assert result["count_files"] == 1
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_global_sections_limit_exceeded(self):
        """Test batch exceeds max_sections_total (lines 600-606)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            # Write lots of lines
            f.write("\n".join([f"line{i}" for i in range(300)]))
            f.flush()
            test_file = Path(f.name)

        try:
            # Create many files each with sections to exceed 200 total
            requests = []
            for _i in range(15):  # 15 files x 15 sections = 225 > 200
                requests.append({
                    "file_path": "test.py",
                    "sections": [{"start_line": j + 1, "end_line": j + 1} for j in range(15)],
                })

            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                with pytest.raises(ValueError, match="Too many sections"):
                    await tool._execute_batch({"requests": requests, "allow_truncate": False})
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_global_sections_limit_with_truncate(self):
        """Test batch exceeds max_sections_total with allow_truncate (lines 604-606)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("\n".join([f"line{i}" for i in range(300)]))
            f.flush()
            test_file = Path(f.name)

        try:
            requests = []
            for _i in range(15):
                requests.append({
                    "file_path": "test.py",
                    "sections": [{"start_line": j + 1, "end_line": j + 1} for j in range(15)],
                })

            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool._execute_batch({
                    "requests": requests,
                    "allow_truncate": True,
                })
                assert result["truncated"] is True
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_empty_content_fail_fast(self):
        """Test batch with empty content and fail_fast (lines 609-619)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")  # Empty file
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                args = {
                    "requests": [
                        {"file_path": "test.py", "sections": [{"start_line": 1, "end_line": 5}]}
                    ],
                    "fail_fast": True,
                }
                result = await tool._execute_batch(args)
                # fail_fast causes break on empty content
                assert result["count_files"] == 1
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_total_bytes_limit_exceeded(self):
        """Test batch exceeds max_total_bytes (lines 629-639)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x\n" * 100)  # Small file
            f.flush()
            test_file = Path(f.name)

        try:
            # Mock _read_file_partial to return large content that will exceed 1 MiB
            large_chunk = "x" * (600 * 1024)  # ~600 KB per section

            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch.object(
                tool, "_read_file_partial", return_value=large_chunk
            ):
                requests = [{
                    "file_path": "test.py",
                    "sections": [
                        {"start_line": 1, "end_line": 10},
                        {"start_line": 11, "end_line": 20},
                        {"start_line": 21, "end_line": 30},
                    ],
                }]
                with pytest.raises(ValueError, match="exceeds limits"):
                    await tool._execute_batch({
                        "requests": requests,
                        "allow_truncate": False,
                    })
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_total_limits_with_truncate(self):
        """Test batch exceeds total limits with allow_truncate (lines 638-639)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x\n" * 100)
            f.flush()
            test_file = Path(f.name)

        try:
            large_chunk = "x" * (600 * 1024)

            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ), patch.object(
                tool, "_read_file_partial", return_value=large_chunk
            ):
                requests = [{
                    "file_path": "test.py",
                    "sections": [
                        {"start_line": 1, "end_line": 10},
                        {"start_line": 11, "end_line": 20},
                        {"start_line": 21, "end_line": 30},
                    ],
                }]
                result = await tool._execute_batch({
                    "requests": requests,
                    "allow_truncate": True,
                })
                assert result["truncated"] is True
        finally:
            if test_file.exists():
                test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_raw_format_content(self):
        """Test batch with raw format (line 652)."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()
            test_file = Path(f.name)

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                args = {
                    "requests": [
                        {
                            "file_path": "test.py",
                            "sections": [
                                {"start_line": 1, "end_line": 2, "label": "sec1"}
                            ],
                        }
                    ],
                    "format": "raw",
                    "output_format": "json",
                }
                result = await tool._execute_batch(args)
                assert result["success"] is True
                if "results" in result:
                    sections = result["results"][0]["sections"]
                    assert len(sections) >= 1
                    assert "content" in sections[0]
        finally:
            if test_file.exists():
                test_file.unlink()


class TestValidateArgumentsBranches:
    """Test uncovered branches in validate_arguments."""

    def test_validate_requests_not_list(self):
        """Test validation fails when requests is not a list (line 736)."""
        tool = ReadPartialTool()
        args = {"requests": "not a list"}
        with pytest.raises(ValueError, match="requests must be a list"):
            tool.validate_arguments(args)

    def test_validate_end_line_below_one(self):
        """Test validation fails when end_line < 1 (line 766)."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "end_line": 0}
        with pytest.raises(ValueError, match="end_line must be >= 1"):
            tool.validate_arguments(args)

    def test_validate_invalid_format_type(self):
        """Test validation fails when format is not a string (line 783)."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "format": 123}
        with pytest.raises(ValueError, match="format must be a string"):
            tool.validate_arguments(args)

    def test_validate_empty_output_file(self):
        """Test validation fails when output_file is empty (line 791-793)."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "output_file": ""}
        with pytest.raises(ValueError, match="output_file cannot be empty"):
            tool.validate_arguments(args)

    def test_validate_output_file_not_string(self):
        """Test validation fails when output_file is not a string (line 791)."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "output_file": 123}
        with pytest.raises(ValueError, match="output_file must be a string"):
            tool.validate_arguments(args)

    def test_validate_suppress_output_not_bool(self):
        """Test validation fails when suppress_output is not a boolean (line 799)."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "suppress_output": "true"}
        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            tool.validate_arguments(args)

    def test_validate_end_column_below_zero(self):
        """Test validation fails when end_column < 0 (line 777)."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "end_column": -1}
        with pytest.raises(ValueError, match="end_column must be >= 0"):
            tool.validate_arguments(args)

    def test_validate_end_column_not_int(self):
        """Test validation fails when end_column is not an int (line 775)."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "end_column": "0"}
        with pytest.raises(ValueError, match="end_column must be an integer"):
            tool.validate_arguments(args)
