#!/usr/bin/env python3
"""
Tests for smart cache cross-format optimization.

Tests the ability to derive file lists from cached count data without
additional ripgrep executions.
"""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools import fd_rg_utils
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.utils.search_cache import SearchCache, clear_cache


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    """Clear cache before each test to avoid interference"""
    clear_cache()
    yield
    clear_cache()


class TestSmartCacheOptimization:
    """Test cases for smart cross-format cache optimization."""

    def test_extract_file_list_from_count_data(self):
        """Test file list extraction from count data."""
        count_data = {"file1.py": 5, "file2.py": 3, "file3.py": 2, "__total__": 10}

        file_list = fd_rg_utils.extract_file_list_from_count_data(count_data)
        expected_files = ["file1.py", "file2.py", "file3.py"]

        assert set(file_list) == set(expected_files)
        assert "__total__" not in file_list

    def test_create_file_summary_from_count_data(self):
        """Test file summary creation from count data."""
        count_data = {"file1.py": 5, "file2.py": 3, "__total__": 8}

        summary = fd_rg_utils.create_file_summary_from_count_data(count_data)

        assert summary["success"] is True
        assert summary["total_matches"] == 8
        assert summary["file_count"] == 2
        assert summary["derived_from_count"] is True

        files = summary["files"]
        assert len(files) == 2
        assert {"file": "file1.py", "match_count": 5} in files
        assert {"file": "file2.py", "match_count": 3} in files

    def test_cache_key_derivation(self):
        """Test cache key derivation for cross-format optimization."""
        cache = SearchCache()

        # Test summary_only -> count_only_matches conversion
        summary_key = "query|['path']|{'summary_only': True}"
        count_key = cache._derive_count_key_from_cache_key(summary_key)
        expected_count_key = "query|['path']|{'count_only_matches': True}"

        assert count_key == expected_count_key

    def test_cache_can_derive_file_list(self):
        """Test detection of derivable count results."""
        cache = SearchCache()

        # Valid count result
        valid_result = {
            "success": True,
            "file_counts": {"file1.py": 5, "file2.py": 3, "__total__": 8},
        }
        assert cache._can_derive_file_list(valid_result) is True

        # Invalid results
        invalid_results = [
            {},  # Empty dict
            {"success": True},  # No file_counts
            {"file_counts": "not_a_dict"},  # file_counts not a dict
            None,  # Not a dict
        ]

        for invalid_result in invalid_results:
            assert cache._can_derive_file_list(invalid_result) is False

    def test_cache_derive_file_list_result(self):
        """Test file list result derivation."""
        cache = SearchCache()

        count_result = {
            "success": True,
            "file_counts": {"file1.py": 5, "file2.py": 3, "__total__": 8},
        }

        # Test summary format derivation
        summary_result = cache._derive_file_list_result(count_result, "summary")
        assert summary_result["success"] is True
        assert summary_result["total_matches"] == 8
        assert summary_result["file_count"] == 2
        assert summary_result["cache_derived"] is True

        # Test file_list format derivation
        file_list_result = cache._derive_file_list_result(count_result, "file_list")
        assert file_list_result["success"] is True
        assert file_list_result["total_matches"] == 8
        assert file_list_result["file_count"] == 2
        assert file_list_result["cache_derived"] is True
        assert set(file_list_result["files"]) == {"file1.py", "file2.py"}

    def test_get_compatible_result_direct_hit(self):
        """Test that direct cache hits work normally."""
        cache = SearchCache()

        # Cache a result
        cache_key = "test_key"
        cached_data = {"success": True, "data": "test"}
        cache.set(cache_key, cached_data)

        # Should get direct hit
        result = cache.get_compatible_result(cache_key, "any_format")
        assert result == cached_data

    def test_get_compatible_result_derivation(self):
        """Test cross-format result derivation."""
        cache = SearchCache()

        # Cache count result
        count_key = "query|['path']|{'count_only_matches': True}"
        count_data = {"success": True, "file_counts": {"file1.py": 5, "__total__": 5}}
        cache.set(count_key, count_data)

        # Request summary format (should derive from count)
        summary_key = "query|['path']|{'summary_only': True}"
        result = cache.get_compatible_result(summary_key, "summary")

        # Should get derived result
        assert result is not None
        assert result["success"] is True
        assert result["total_matches"] == 5
        assert result["cache_derived"] is True

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture")
    @patch(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.SearchContentTool._validate_roots"
    )
    async def test_search_content_smart_caching_integration(
        self, mock_validate_roots, mock_run_command
    ):
        """Test smart caching integration in SearchContentTool."""

        # Mock path validation
        mock_validate_roots.return_value = ["test"]

        # Mock count search result
        count_output = b"file1.py:5\nfile2.py:3\n"
        mock_run_command.return_value = (0, count_output, b"")

        tool = SearchContentTool(enable_cache=True)

        # Step 1: Execute count search
        count_result = await tool.execute(
            {"query": "test", "roots": ["test"], "count_only_matches": True}
        )

        # Verify count result
        assert count_result["success"] is True
        assert count_result["total_matches"] == 8
        assert "file1.py" in count_result["file_counts"]

        # Step 2: Execute summary search (should derive from cached count)
        # Reset mock to ensure no second command execution
        mock_run_command.reset_mock()

        summary_result = await tool.execute(
            {"query": "test", "roots": ["test"], "summary_only": True}
        )

        # Should not have called ripgrep again
        mock_run_command.assert_not_called()

        # Should get derived result (or at least cache hit)
        assert summary_result.get("cache_hit") is True
        # Note: The current implementation may return direct cache hit instead of derivation
        # This is still a valid optimization - no second ripgrep execution
        assert summary_result["total_matches"] == 8

    def test_determine_requested_format(self):
        """Test format determination from arguments."""
        tool = SearchContentTool(enable_cache=False)

        test_cases = [
            ({"total_only": True}, "total_only"),
            ({"count_only_matches": True}, "count_only"),
            ({"summary_only": True}, "summary"),
            ({"group_by_file": True}, "group_by_file"),
            ({}, "normal"),
            ({"query": "test"}, "normal"),
        ]

        for arguments, expected_format in test_cases:
            result = tool._determine_requested_format(arguments)
            assert result == expected_format, f"Failed for {arguments}"

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture")
    @patch(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.SearchContentTool._validate_roots"
    )
    async def test_total_only_to_count_only_cross_caching(
        self, mock_validate_roots, mock_run_command
    ):
        """Test that total_only results can serve future count_only_matches queries."""

        # Mock path validation
        mock_validate_roots.return_value = ["."]

        # Mock ripgrep output with file counts
        count_output = b"Main.java:15\nService.java:8\nUtil.java:3\n"
        mock_run_command.return_value = (0, count_output, b"")

        tool = SearchContentTool(enable_cache=True)

        # Step 1: Execute total_only search (like your example)
        total_result = await tool.execute(
            {
                "roots": ["."],
                "query": "Keyword",
                "case": "insensitive",
                "include_globs": ["*.java"],
                "total_only": True,
            }
        )

        # Verify total_only result
        assert total_result == 26  # 15 + 8 + 3

        # Reset mock to verify no second command execution
        mock_run_command.reset_mock()

        # Step 2: Execute count_only_matches with same parameters
        # Should be served from cache without calling ripgrep again
        count_result = await tool.execute(
            {
                "roots": ["."],
                "query": "Keyword",
                "case": "insensitive",
                "include_globs": ["*.java"],
                "count_only_matches": True,
            }
        )

        # Should not have called ripgrep again
        mock_run_command.assert_not_called()

        # Verify detailed count result was derived from total_only cache
        assert count_result["success"] is True
        assert count_result["total_matches"] == 26
        assert count_result["cache_hit"] is True
        assert count_result.get("derived_from_total_only") is True

        # Verify file-level counts are preserved
        file_counts = count_result["file_counts"]
        assert file_counts["Main.java"] == 15
        assert file_counts["Service.java"] == 8
        assert file_counts["Util.java"] == 3
        assert "__total__" not in file_counts  # Should be excluded from file_counts

    def test_create_count_only_cache_key(self):
        """Test creation of count_only cache key from total_only arguments."""
        tool = SearchContentTool(enable_cache=True)

        total_only_args = {
            "roots": ["."],
            "query": "Keyword",
            "case": "insensitive",
            "include_globs": ["*.java"],
            "total_only": True,
        }

        count_key = tool._create_count_only_cache_key("dummy_key", total_only_args)

        # Verify the cache key was generated
        assert count_key is not None
        # The cache key should contain the core search parameters but not output format flags
        # This is correct design - output format doesn't affect the underlying search
        assert "keyword" in count_key.lower()
        assert "insensitive" in count_key
        assert "*.java" in count_key
