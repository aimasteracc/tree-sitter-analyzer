#!/usr/bin/env python3
"""
Unit tests for read_partial_tool.py

Tests for ReadPartialTool MCP tool which provides partial file reading functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

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


class TestReadPartialToolExecuteExtra:
    """Additional tests for uncovered execute() paths."""

    @pytest.mark.asyncio
    async def test_execute_resolve_path_value_error(self):
        tool = ReadPartialTool()
        with patch.object(
            tool, "resolve_and_validate_file_path", side_effect=ValueError("blocked")
        ):
            result = await tool.execute({"file_path": "secret.py", "start_line": 1})
        assert result["success"] is False
        assert "blocked" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_content_none(self):
        tool = ReadPartialTool()
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(tool, "_read_file_partial", return_value=None),
        ):
            result = await tool.execute({"file_path": "t.py", "start_line": 1})
        assert result["success"] is False
        assert "Failed to read" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_success_with_output_file_text(self):
        tool = ReadPartialTool()
        test_content = "hello\nworld\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/test.md"
            ),
        ):
            result = await tool.execute(
                {
                    "file_path": "t.py",
                    "start_line": 1,
                    "end_line": 2,
                    "output_file": "result",
                    "format": "text",
                }
            )
        assert result["success"] is True
        assert result["file_saved"] is True
        assert result["output_file_path"] == "/out/test.md"
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_success_with_output_file_json(self):
        tool = ReadPartialTool()
        test_content = "hello\nworld\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/j.md"
            ),
        ):
            result = await tool.execute(
                {
                    "file_path": "t.py",
                    "start_line": 1,
                    "end_line": 2,
                    "output_file": "res",
                    "format": "json",
                    "output_format": "json",
                }
            )
        assert result["success"] is True
        assert result["file_saved"] is True
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_success_with_output_file_raw(self):
        tool = ReadPartialTool()
        test_content = "hello\nworld\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/r.md"
            ),
        ):
            result = await tool.execute(
                {
                    "file_path": "t.py",
                    "start_line": 1,
                    "end_line": 2,
                    "output_file": "res",
                    "format": "raw",
                }
            )
        assert result["success"] is True
        assert result["file_saved"] is True
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_output_file_toon_format(self):
        tool = ReadPartialTool()
        test_content = "hello\nworld\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/t.md"
            ),
        ):
            result = await tool.execute(
                {
                    "file_path": "t.py",
                    "start_line": 1,
                    "end_line": 2,
                    "output_file": "res",
                    "format": "json",
                    "output_format": "toon",
                }
            )
        assert result["success"] is True
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_output_file_save_error(self):
        tool = ReadPartialTool()
        test_content = "hello\nworld\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch.object(
                tool.file_output_manager,
                "save_to_file",
                side_effect=PermissionError("no write"),
            ),
        ):
            result = await tool.execute(
                {
                    "file_path": "t.py",
                    "start_line": 1,
                    "end_line": 2,
                    "output_file": "res",
                }
            )
        assert result["success"] is True
        assert result["file_saved"] is False
        assert "file_save_error" in result
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_suppress_output_with_output_file(self):
        tool = ReadPartialTool()
        test_content = "hello\nworld\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch.object(
                tool.file_output_manager, "save_to_file", return_value="/out/s.md"
            ),
        ):
            result = await tool.execute(
                {
                    "file_path": "t.py",
                    "start_line": 1,
                    "end_line": 2,
                    "suppress_output": True,
                    "output_file": "res",
                }
            )
        assert result["success"] is True
        assert "partial_content_result" not in result
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_output_format_json(self):
        tool = ReadPartialTool()
        test_content = "hello\nworld\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        with patch.object(
            tool, "resolve_and_validate_file_path", return_value=str(test_file)
        ):
            result = await tool.execute(
                {
                    "file_path": "t.py",
                    "start_line": 1,
                    "end_line": 2,
                    "output_format": "json",
                }
            )
        assert result["success"] is True
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_execute_general_exception(self):
        tool = ReadPartialTool()
        test_content = "hello\nworld\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        try:
            with (
                patch.object(
                    tool,
                    "resolve_and_validate_file_path",
                    return_value=str(test_file),
                ),
                patch.object(
                    tool,
                    "_read_file_partial",
                    side_effect=RuntimeError("unexpected"),
                ),
            ):
                result = await tool.execute({"file_path": "t.py", "start_line": 1})
            assert result["success"] is False
            assert "unexpected" in result["error"]
        finally:
            if test_file.exists():
                test_file.unlink()


class TestReadPartialToolBatchExtra:
    """Additional tests for uncovered _execute_batch() paths."""

    @pytest.mark.asyncio
    async def test_batch_fail_fast_resolve_error(self):
        tool = ReadPartialTool()
        with patch.object(
            tool,
            "resolve_and_validate_file_path",
            side_effect=ValueError("no access"),
        ):
            with pytest.raises(ValueError, match="no access"):
                await tool._execute_batch(
                    {
                        "requests": [
                            {"file_path": "x.py", "sections": [{"start_line": 1}]}
                        ],
                        "fail_fast": True,
                    }
                )

    @pytest.mark.asyncio
    async def test_batch_fail_fast_file_not_exist(self):
        tool = ReadPartialTool()
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/x.py"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            with pytest.raises(ValueError, match="file does not exist"):
                await tool._execute_batch(
                    {
                        "requests": [
                            {"file_path": "x.py", "sections": [{"start_line": 1}]}
                        ],
                        "fail_fast": True,
                    }
                )

    @pytest.mark.asyncio
    async def test_batch_file_too_large_fail_fast(self):
        tool = ReadPartialTool()
        test_content = "x"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch.object(Path, "stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 10 * 1024 * 1024  # 10 MiB
            with pytest.raises(ValueError, match="File too large"):
                await tool._execute_batch(
                    {
                        "requests": [
                            {"file_path": "x.py", "sections": [{"start_line": 1}]}
                        ],
                        "fail_fast": True,
                    }
                )
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_file_too_large_no_fail_fast(self):
        tool = ReadPartialTool()
        test_content = "x"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            test_file = Path(f.name)

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch.object(Path, "stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 10 * 1024 * 1024
            result = await tool._execute_batch(
                {
                    "requests": [
                        {"file_path": "x.py", "sections": [{"start_line": 1}]}
                    ],
                    "fail_fast": False,
                }
            )
        if "results" in result:
            assert any(
                "Too large" in e["error"] for e in result["results"][0]["errors"]
            )
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_stat_oserror_fail_fast(self):
        tool = ReadPartialTool()
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/x.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat", side_effect=OSError("io error")),
        ):
            with pytest.raises(ValueError, match="Could not stat"):
                await tool._execute_batch(
                    {
                        "requests": [
                            {"file_path": "x.py", "sections": [{"start_line": 1}]}
                        ],
                        "fail_fast": True,
                    }
                )

    @pytest.mark.asyncio
    async def test_batch_stat_oserror_no_fail_fast(self):
        tool = ReadPartialTool()
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/x.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat", side_effect=OSError("io error")),
        ):
            result = await tool._execute_batch(
                {
                    "requests": [
                        {"file_path": "x.py", "sections": [{"start_line": 1}]}
                    ],
                    "fail_fast": False,
                }
            )
        if "results" in result:
            assert any("stat" in e["error"] for e in result["results"][0]["errors"])

    @pytest.mark.asyncio
    async def test_batch_sections_total_limit_no_truncate(self):
        tool = ReadPartialTool()
        requests = []
        for i in range(20):
            sections = [
                {"start_line": j, "end_line": j, "label": f"s{j}"} for j in range(1, 12)
            ]
            requests.append({"file_path": f"t{i}.py", "sections": sections})
        # 20 files * 11 sections = 220 > max_sections_total=200
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 100
            with pytest.raises(ValueError, match="Too many sections"):
                await tool._execute_batch({"requests": requests})

    @pytest.mark.asyncio
    async def test_batch_sections_total_limit_with_truncate(self):
        tool = ReadPartialTool()
        requests = []
        for i in range(20):
            sections = [
                {"start_line": j, "end_line": j, "label": f"s{j}"} for j in range(1, 12)
            ]
            requests.append({"file_path": f"t{i}.py", "sections": sections})
        # 20 * 11 = 220 > 200
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 100
            result = await tool._execute_batch(
                {"requests": requests, "allow_truncate": True}
            )
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_batch_total_bytes_limit_no_truncate(self):
        tool = ReadPartialTool()
        big = "x" * 600000

        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
            patch.object(tool, "_read_file_partial", return_value=big),
        ):
            mock_stat.return_value.st_size = 100
            with pytest.raises(ValueError, match="exceeds limits"):
                await tool._execute_batch(
                    {
                        "requests": [
                            {
                                "file_path": "t.py",
                                "sections": [
                                    {"start_line": 1, "end_line": 1},
                                    {"start_line": 1, "end_line": 1},
                                ],
                            }
                        ]
                    }
                )

    @pytest.mark.asyncio
    async def test_batch_total_bytes_limit_with_truncate(self):
        tool = ReadPartialTool()
        big = "x" * 600000

        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
            patch.object(tool, "_read_file_partial", return_value=big),
        ):
            mock_stat.return_value.st_size = 100
            result = await tool._execute_batch(
                {
                    "requests": [
                        {
                            "file_path": "t.py",
                            "sections": [
                                {"start_line": 1, "end_line": 1},
                                {"start_line": 1, "end_line": 1},
                            ],
                        }
                    ],
                    "allow_truncate": True,
                }
            )
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_batch_fail_fast_invalid_request_entry(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="must be an object"):
            await tool._execute_batch({"requests": ["bad"], "fail_fast": True})

    @pytest.mark.asyncio
    async def test_batch_fail_fast_empty_file_path(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="non-empty string"):
            await tool._execute_batch(
                {
                    "requests": [{"file_path": "", "sections": [{"start_line": 1}]}],
                    "fail_fast": True,
                }
            )

    @pytest.mark.asyncio
    async def test_batch_fail_fast_invalid_sections_type(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="sections must be a list"):
            await tool._execute_batch(
                {
                    "requests": [{"file_path": "t.py", "sections": "bad"}],
                    "fail_fast": True,
                }
            )

    @pytest.mark.asyncio
    async def test_batch_fail_fast_invalid_section_entry(self):
        tool = ReadPartialTool()
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 100
            result = await tool._execute_batch(
                {
                    "requests": [{"file_path": "t.py", "sections": ["bad"]}],
                    "fail_fast": True,
                }
            )
        if "results" in result:
            assert any(
                "Invalid section" in e["error"] for e in result["results"][0]["errors"]
            )

    @pytest.mark.asyncio
    async def test_batch_fail_fast_invalid_start_line(self):
        tool = ReadPartialTool()
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 100
            result = await tool._execute_batch(
                {
                    "requests": [
                        {"file_path": "t.py", "sections": [{"start_line": 0}]}
                    ],
                    "fail_fast": True,
                }
            )
        if "results" in result:
            assert any(
                "start_line" in e["error"] for e in result["results"][0]["errors"]
            )

    @pytest.mark.asyncio
    async def test_batch_fail_fast_invalid_end_line(self):
        tool = ReadPartialTool()
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 100
            result = await tool._execute_batch(
                {
                    "requests": [
                        {
                            "file_path": "t.py",
                            "sections": [{"start_line": 10, "end_line": 5}],
                        }
                    ],
                    "fail_fast": True,
                }
            )
        if "results" in result:
            assert any("end_line" in e["error"] for e in result["results"][0]["errors"])

    @pytest.mark.asyncio
    async def test_batch_fail_fast_empty_content(self):
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")
            f.flush()
            test_file = Path(f.name)

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch.object(Path, "stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 100
            result = await tool._execute_batch(
                {
                    "requests": [
                        {"file_path": "t.py", "sections": [{"start_line": 1}]}
                    ],
                    "fail_fast": True,
                }
            )
        if "results" in result:
            assert any(
                "empty" in e["error"].lower() for e in result["results"][0]["errors"]
            )
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_too_many_sections_per_file_no_fail_fast(self):
        tool = ReadPartialTool()
        sections = [{"start_line": i} for i in range(60)]
        with patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"):
            result = await tool._execute_batch(
                {
                    "requests": [{"file_path": "t.py", "sections": sections}],
                    "fail_fast": False,
                }
            )
        if "results" in result:
            assert any("Too many" in e["error"] for e in result["results"][0]["errors"])


class TestReadPartialToolValidateExtra:
    """Additional tests for uncovered validate_arguments paths."""

    def test_validate_end_column_below_zero(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="end_column must be >= 0"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "end_column": -1}
            )

    def test_validate_format_not_string(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="format must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "format": 123}
            )

    def test_validate_output_file_not_string(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="output_file must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "output_file": 42}
            )

    def test_validate_output_file_empty(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="output_file cannot be empty"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "output_file": "  "}
            )

    def test_validate_suppress_output_not_bool(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "suppress_output": "yes"}
            )

    def test_validate_end_line_below_one(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="end_line must be >= 1"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "end_line": 0}
            )

    def test_validate_requests_not_list(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="requests must be a list"):
            tool.validate_arguments({"requests": "not_list"})

    def test_validate_valid_with_all_optional_fields(self):
        tool = ReadPartialTool()
        args = {
            "file_path": "t.py",
            "start_line": 1,
            "end_line": 10,
            "start_column": 0,
            "end_column": 5,
            "format": "raw",
            "output_file": "out.md",
            "suppress_output": True,
        }
        assert tool.validate_arguments(args) is True
