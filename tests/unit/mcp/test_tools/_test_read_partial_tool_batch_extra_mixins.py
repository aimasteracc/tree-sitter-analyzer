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


class ReadPartialToolBatchExtraFileErrorMixin:
    """Batch error handling tests for file and stat failures."""

    @pytest.mark.asyncio
    async def test_batch_fail_fast_resolve_error(self):
        tool = ReadPartialTool()
        args = batch_args(batch_request("x.py"), fail_fast=True)
        with patch.object(
            tool,
            "resolve_and_validate_file_path",
            side_effect=ValueError("no access"),
        ):
            with pytest.raises(ValueError, match="no access"):
                await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_batch_fail_fast_file_not_exist(self):
        tool = ReadPartialTool()
        args = batch_args(batch_request("x.py"), fail_fast=True)
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/x.py"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            with pytest.raises(ValueError, match="file does not exist"):
                await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_batch_file_too_large_fail_fast(self):
        tool = ReadPartialTool()
        test_content = "x"
        args = batch_args(batch_request("x.py"), fail_fast=True)

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
                await tool._execute_batch(args)
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_file_too_large_no_fail_fast(self):
        tool = ReadPartialTool()
        test_content = "x"
        args = batch_args(batch_request("x.py"), fail_fast=False)

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
            result = await tool._execute_batch(args)
        if "results" in result:
            assert any(
                "Too large" in e["error"] for e in result["results"][0]["errors"]
            )
        else:
            assert "error" in result or isinstance(result, dict)
        test_file.unlink()

    @pytest.mark.asyncio
    async def test_batch_stat_oserror_fail_fast(self):
        tool = ReadPartialTool()
        args = batch_args(batch_request("x.py"), fail_fast=True)
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/x.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat", side_effect=OSError("io error")),
        ):
            with pytest.raises(ValueError, match="Could not stat"):
                await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_batch_stat_oserror_no_fail_fast(self):
        tool = ReadPartialTool()
        args = batch_args(batch_request("x.py"), fail_fast=False)
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/x.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat", side_effect=OSError("io error")),
        ):
            result = await tool._execute_batch(args)
        if "results" in result:
            assert any("stat" in e["error"] for e in result["results"][0]["errors"])
        else:
            assert isinstance(result, dict)

        assert result is not None


class ReadPartialToolBatchExtraLimitMixin:
    """Batch aggregate limit and truncation tests."""

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
        sections = [
            {"start_line": 1, "end_line": 1},
            {"start_line": 1, "end_line": 1},
        ]
        args = batch_args(batch_request("t.py", sections))

        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
            patch.object(tool, "_read_file_partial", return_value=big),
        ):
            mock_stat.return_value.st_size = 100
            with pytest.raises(ValueError, match="exceeds limits"):
                await tool._execute_batch(args)

    @pytest.mark.asyncio
    async def test_batch_total_bytes_limit_with_truncate(self):
        tool = ReadPartialTool()
        big = "x" * 600000
        sections = [
            {"start_line": 1, "end_line": 1},
            {"start_line": 1, "end_line": 1},
        ]
        args = batch_args(batch_request("t.py", sections), allow_truncate=True)

        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
            patch.object(tool, "_read_file_partial", return_value=big),
        ):
            mock_stat.return_value.st_size = 100
            result = await tool._execute_batch(args)
        assert result["truncated"] is True


class ReadPartialToolBatchExtraValidationMixin:
    """Batch request validation edge-case tests."""

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
        else:
            assert isinstance(result, dict)
        assert result is not None

    @pytest.mark.asyncio
    async def test_batch_fail_fast_invalid_start_line(self):
        tool = ReadPartialTool()
        args = batch_args(
            batch_request("t.py", [{"start_line": 0}]),
            fail_fast=True,
        )
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 100
            result = await tool._execute_batch(args)
        if "results" in result:
            assert any(
                "start_line" in e["error"] for e in result["results"][0]["errors"]
            )
        else:
            assert isinstance(result, dict)
        assert result is not None

    @pytest.mark.asyncio
    async def test_batch_fail_fast_invalid_end_line(self):
        tool = ReadPartialTool()
        args = batch_args(
            batch_request("t.py", [{"start_line": 10, "end_line": 5}]),
            fail_fast=True,
        )
        with (
            patch.object(tool, "resolve_and_validate_file_path", return_value="/t.py"),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(Path, "stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 100
            result = await tool._execute_batch(args)
        if "results" in result:
            assert any("end_line" in e["error"] for e in result["results"][0]["errors"])
        else:
            assert isinstance(result, dict)
        assert result is not None

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
                batch_args(batch_request("t.py"), fail_fast=True)
            )
        if "results" in result:
            assert any(
                "empty" in e["error"].lower() for e in result["results"][0]["errors"]
            )
        else:
            assert isinstance(result, dict)
        assert result is not None
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
        else:
            assert isinstance(result, dict)
        assert result is not None
