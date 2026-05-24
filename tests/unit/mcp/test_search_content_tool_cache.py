#!/usr/bin/env python3
"""
Tests for Search Content MCP Tool.

This module tests SearchContentTool class which provides
content search capabilities using ripgrep.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import (
    SearchContentTool,
)

# Use the OS-native tempdir instead of hard-coding ``/tmp`` so the
# cache-hit branch tests work on Windows runners where the system
# temporary directory is ``D:\Users\...\AppData\Local\Temp\...``
# and the SecurityValidator rejects ``/tmp`` as missing.
_TMPDIR = tempfile.gettempdir()


@pytest.fixture
def tool():
    """Create a fresh tool instance for each test."""
    return SearchContentTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    """Create a sample project structure for testing."""
    # Create directories
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()

    # Create files
    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42")
    (tmp_path / "tests" / "test_main.py").write_text("def test():\n    assert True")

    return tmp_path


class TestCacheHitBranches:
    """Tests for execute() cache-hit branches (lines 382-416)."""

    @pytest.mark.asyncio
    async def test_cache_hit_total_only_returns_int(self, tool):
        tool.cache = MagicMock()
        tool.cache.get.return_value = 42
        tool.cache.create_cache_key.return_value = "k1"
        arguments = {"query": "test", "roots": [_TMPDIR], "total_only": True}
        result = await tool.execute(arguments)
        assert result == 42

    @pytest.mark.asyncio
    async def test_cache_hit_total_only_dict_with_total_matches(self, tool):
        tool.cache = MagicMock()
        tool.cache.get.return_value = {"total_matches": 7, "success": True}
        tool.cache.create_cache_key.return_value = "k1"
        arguments = {"query": "test", "roots": [_TMPDIR], "total_only": True}
        result = await tool.execute(arguments)
        assert result == 7

    @pytest.mark.asyncio
    async def test_cache_hit_total_only_dict_with_count(self, tool):
        tool.cache = MagicMock()
        tool.cache.get.return_value = {"count": 3, "success": True}
        tool.cache.create_cache_key.return_value = "k1"
        arguments = {"query": "test", "roots": [_TMPDIR], "total_only": True}
        result = await tool.execute(arguments)
        assert result == 3

    @pytest.mark.asyncio
    async def test_cache_hit_total_only_dict_no_match_key(self, tool):
        tool.cache = MagicMock()
        tool.cache.get.return_value = {"success": True}
        tool.cache.create_cache_key.return_value = "k1"
        arguments = {"query": "test", "roots": [_TMPDIR], "total_only": True}
        result = await tool.execute(arguments)
        assert result == 0

    @pytest.mark.asyncio
    async def test_cache_hit_non_total_only_dict(self, tool):
        tool.cache = MagicMock()
        tool.cache.get.return_value = {"success": True, "count": 5}
        tool.cache.create_cache_key.return_value = "k1"
        arguments = {"query": "test", "roots": [_TMPDIR]}
        result = await tool.execute(arguments)
        assert result["cache_hit"] is True
        assert result["count"] == 5

    @pytest.mark.asyncio
    async def test_cache_hit_non_total_only_int(self, tool):
        tool.cache = MagicMock()
        tool.cache.get.return_value = 10
        tool.cache.create_cache_key.return_value = "k1"
        arguments = {"query": "test", "roots": [_TMPDIR]}
        result = await tool.execute(arguments)
        assert result["cache_hit"] is True
        assert result["count"] == 10
        assert result["total_matches"] == 10

    @pytest.mark.asyncio
    async def test_cache_hit_non_total_only_other_type(self, tool):
        tool.cache = MagicMock()
        tool.cache.get.return_value = "some_string"
        tool.cache.create_cache_key.return_value = "k1"
        arguments = {"query": "test", "roots": [_TMPDIR]}
        result = await tool.execute(arguments)
        assert result["cache_hit"] is True
        assert result["cached_result"] == "some_string"


class TestSummaryOutputPaths:
    """Tests for summary mode file output (lines 789-844)."""

    @pytest.mark.asyncio
    async def test_summary_with_output_file(self, tool, sample_project_structure):
        tool.cache = MagicMock()
        tool.cache.get.return_value = None
        tool.cache.create_cache_key.return_value = None
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b'{"type":"match","data":{"path":{"text":"f"},"lines":{"text":"test"},"line_number":1}}\n',
                    b"",
                )
                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "summary_only": True,
                    "output_file": "summary.json",
                    "output_format": "json",
                }
                result = await tool.execute(arguments)
                assert result["success"] is True
                assert "output_file" in result
                assert "file_saved" in result

    @pytest.mark.asyncio
    async def test_summary_with_output_file_error(self, tool, sample_project_structure):
        tool.cache = MagicMock()
        tool.cache.get.return_value = None
        tool.cache.create_cache_key.return_value = None
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b'{"type":"match","data":{"path":{"text":"f"},"lines":{"text":"test"},"line_number":1}}\n',
                    b"",
                )
                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_helpers.format_for_file_output",
                    side_effect=Exception("disk full"),
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "query": "test",
                        "summary_only": True,
                        "output_file": "summary.json",
                        "output_format": "json",
                    }
                    result = await tool.execute(arguments)
                    assert result["success"] is True
                    assert "file_save_error" in result

    @pytest.mark.asyncio
    async def test_summary_toon_format(self, tool, sample_project_structure):
        tool.cache = MagicMock()
        tool.cache.get.return_value = None
        tool.cache.create_cache_key.return_value = None
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b'{"type":"match","data":{"path":{"text":"f"},"lines":{"text":"test"},"line_number":1}}\n',
                    b"",
                )
                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "summary_only": True,
                    "output_format": "toon",
                }
                result = await tool.execute(arguments)
                assert result.get("format") == "toon" or result.get("success") is True


class TestSuppressOutputEndPath:
    """Tests for final suppress_output path without output_file (lines 914-919)."""

    @pytest.mark.asyncio
    async def test_suppress_output_no_file_returns_copy_without_results(
        self, tool, sample_project_structure
    ):
        tool.cache = MagicMock()
        tool.cache.get.return_value = None
        tool.cache.create_cache_key.return_value = None
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b'{"type":"match","data":{"path":{"text":"f"},"lines":{"text":"test"},"line_number":1}}\n',
                    b"",
                )
                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "suppress_output": True,
                    "output_format": "json",
                }
                result = await tool.execute(arguments)
                assert result["success"] is True
                assert "results" not in result


class TestCreateCountOnlyCacheKeyNoCache:
    """Tests for _create_count_only_cache_key when cache is None (line 317)."""

    def test_returns_none_when_no_cache(self):
        tool = SearchContentTool(enable_cache=False)
        assert tool._create_count_only_cache_key("key", {"query": "q"}) is None
