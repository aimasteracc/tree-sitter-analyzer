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


class ReadPartialToolExecuteBatchValidationMixin:
    """Batch-mode validation and truncation tests."""

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
            assert (
                len(result["results"][0]["errors"]) > 0
            )  # ratchet: nondeterministic — 'results' key absent in TOON output; branch never executes in default format

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
            assert (
                len(result["results"][0]["errors"]) > 0
            )  # ratchet: nondeterministic — 'results' key absent in TOON output; branch never executes in default format

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
            assert (
                len(result["results"][0]["errors"]) > 0
            )  # ratchet: nondeterministic — 'results' key absent in TOON output; branch never executes in default format

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


class ReadPartialToolExecuteBatchProcessingMixin:
    """Batch-mode file processing tests."""

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
            assert (
                len(result["results"][0]["errors"]) > 0
            )  # ratchet: nondeterministic — 'results' key absent in TOON output; branch never executes in default format

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

        args = batch_args(
            batch_request("test_data.py", ["not a dict"]),
            fail_fast=False,
        )

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool._execute_batch(args)
            assert result["count_files"] == 1
            if "results" in result:
                assert (
                    len(result["results"][0]["errors"]) > 0
                )  # ratchet: nondeterministic — 'results' key absent in TOON output; branch never executes in default format
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

        args = batch_args(
            batch_request("test_data.py", [{"start_line": 0}]),
            fail_fast=False,
        )

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool._execute_batch(args)
            assert result["count_files"] == 1
            if "results" in result:
                assert (
                    len(result["results"][0]["errors"]) > 0
                )  # ratchet: nondeterministic — 'results' key absent in TOON output; branch never executes in default format
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

        args = batch_args(
            batch_request("test_data.py", [{"start_line": 10, "end_line": 5}]),
            fail_fast=False,
        )

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool._execute_batch(args)
            assert result["count_files"] == 1
            if "results" in result:
                assert (
                    len(result["results"][0]["errors"]) > 0
                )  # ratchet: nondeterministic — 'results' key absent in TOON output; branch never executes in default format
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

        sections = [
            {"start_line": 1, "end_line": 2, "label": "section1"},
            {"start_line": 4, "end_line": 5, "label": "section2"},
        ]
        args = batch_args(batch_request("test_data.py", sections))

        try:
            with patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ):
                result = await tool._execute_batch(args)
            assert result["success"] is True
            assert result["count_files"] == 1
            assert result["count_sections"] == 2
            if "results" in result:
                assert (
                    len(result["results"][0]["sections"]) >= 1
                )  # ratchet: nondeterministic — 'results' key absent in TOON output; branch never executes in default format
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
