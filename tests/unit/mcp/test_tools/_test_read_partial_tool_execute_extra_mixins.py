"""Private mixins for read_partial_tool tests.

These modules keep the collected pytest node IDs anchored in test_read_partial_tool.py.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_helpers import build_agent_summary
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class ReadPartialToolExecuteExtraMixin:
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
        assert result["agent_summary"]["output_saved"] is True
        assert result["agent_summary"]["suppress_output"] is True
        test_file.unlink()


class ReadPartialToolExecuteExtraContinuedMixin:
    """Additional read_partial execute and agent summary tests."""

    def test_agent_summary_for_small_exact_range(self):
        summary = build_agent_summary(
            file_path="example.py",
            start_line=10,
            end_line=14,
            start_column=None,
            end_column=None,
            content_length=120,
            lines_extracted=5,
            content_format="text",
        )

        assert summary["risk"] == "low"
        assert summary["suggested_tool"] == "query_code"
        assert summary["stop_condition"].startswith("The extracted range contains")

    def test_agent_summary_for_large_range(self):
        summary = build_agent_summary(
            file_path="example.py",
            start_line=1,
            end_line=250,
            start_column=None,
            end_column=None,
            content_length=25_000,
            lines_extracted=250,
            content_format="json",
        )

        assert summary["risk"] == "high"
        assert summary["suggested_tool"] == "extract_code_section"
        assert "Narrow" in summary["next_step"]

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

        path_patch = patch.object(
            tool,
            "resolve_and_validate_file_path",
            return_value=str(test_file),
        )
        read_patch = patch.object(
            tool,
            "_read_file_partial",
            side_effect=RuntimeError("unexpected"),
        )

        try:
            with path_patch, read_patch:
                result = await tool.execute({"file_path": "t.py", "start_line": 1})
            assert result["success"] is False
            assert "unexpected" in result["error"]
        finally:
            if test_file.exists():
                test_file.unlink()
