#!/usr/bin/env python3
"""
Tests for search_content tool parameter fixes.

Tests the following fixes:
1. Output format parameter mutual exclusion
2. max_count functionality
3. Cache key generation improvements
"""

from unittest.mock import AsyncMock, patch
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.utils.search_cache import SearchCache, clear_cache


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    """Clear cache before each test to avoid interference."""
    clear_cache()
    yield
    clear_cache()


# Use a valid test directory path that exists and is accessible
import os
TEST_ROOT = os.path.abspath("tests")


class TestOutputFormatParameterValidation:
    """Test cases for output format parameter mutual exclusion."""

    def test_single_output_format_allowed(self):
        """Test that single output format parameters are allowed."""
        tool = SearchContentTool(enable_cache=False)
        
        # Each output format should work individually
        valid_combinations = [
            {"query": "test", "roots": [TEST_ROOT], "total_only": True},
            {"query": "test", "roots": [TEST_ROOT], "count_only_matches": True},
            {"query": "test", "roots": [TEST_ROOT], "summary_only": True},
            {"query": "test", "roots": [TEST_ROOT], "group_by_file": True},
            {"query": "test", "roots": [TEST_ROOT], "optimize_paths": True},
        ]
        
        for args in valid_combinations:
            # Mock path validation to avoid security validator issues
            with patch.object(tool, '_validate_roots') as mock_validate:
                mock_validate.return_value = [TEST_ROOT]
                assert tool.validate_arguments(args) is True

    def test_multiple_output_formats_rejected(self):
        """Test that multiple output format parameters are rejected."""
        tool = SearchContentTool(enable_cache=False)
        
        # These combinations should raise validation errors
        invalid_combinations = [
            {"query": "test", "roots": [TEST_ROOT], "total_only": True, "count_only_matches": True},
            {"query": "test", "roots": [TEST_ROOT], "total_only": True, "summary_only": True},
            {"query": "test", "roots": [TEST_ROOT], "count_only_matches": True, "summary_only": True},
            {"query": "test", "roots": [TEST_ROOT], "group_by_file": True, "optimize_paths": True},
            {"query": "test", "roots": [TEST_ROOT], "total_only": True, "count_only_matches": True, "summary_only": True},
        ]
        
        for args in invalid_combinations:
            with pytest.raises(ValueError) as exc_info:
                tool.validate_arguments(args)
            
            # Error message should mention exclusivity
            assert "排他的" in str(exc_info.value) or "exclusive" in str(exc_info.value).lower()

    def test_output_format_error_message_details(self):
        """Test that error messages include specific parameter names."""
        tool = SearchContentTool(enable_cache=False)
        
        args = {"query": "test", "roots": [TEST_ROOT], "total_only": True, "count_only_matches": True}
        
        with pytest.raises(ValueError) as exc_info:
            tool.validate_arguments(args)
        
        error_message = str(exc_info.value)
        # Error should mention the conflicting parameters
        assert "total_only" in error_message
        assert "count_only_matches" in error_message


class TestMaxCountFunctionality:
    """Test cases for max_count parameter functionality."""

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture")
    @patch("tree_sitter_analyzer.mcp.tools.search_content_tool.SearchContentTool._validate_roots")
    async def test_max_count_applied_to_ripgrep(self, mock_validate_roots, mock_run_command):
        """Test that max_count parameter is properly applied to ripgrep command."""
        mock_validate_roots.return_value = [TEST_ROOT]
        mock_run_command.return_value = (0, b"test.py:1:test line\n", b"")
        
        tool = SearchContentTool(enable_cache=False)
        
        # Use a mock to capture the command that would be executed
        with patch("tree_sitter_analyzer.mcp.tools.fd_rg_utils.build_rg_command") as mock_build_cmd:
            mock_build_cmd.return_value = ["rg", "--json", "test"]
            
            await tool.execute({
                "query": "test",
                "roots": [TEST_ROOT],
                "max_count": 5
            })
            
            # Verify max_count was passed to build_rg_command
            mock_build_cmd.assert_called_once()
            call_kwargs = mock_build_cmd.call_args[1]  # Get keyword arguments
            assert call_kwargs["max_count"] == 5

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture")
    @patch("tree_sitter_analyzer.mcp.tools.search_content_tool.SearchContentTool._validate_roots")
    async def test_max_count_default_value(self, mock_validate_roots, mock_run_command):
        """Test that default max_count value is applied when not specified."""
        mock_validate_roots.return_value = [TEST_ROOT]
        mock_run_command.return_value = (0, b"test.py:1:test line\n", b"")
        
        tool = SearchContentTool(enable_cache=False)
        
        with patch("tree_sitter_analyzer.mcp.tools.fd_rg_utils.build_rg_command") as mock_build_cmd:
            mock_build_cmd.return_value = ["rg", "--json", "test"]
            
            await tool.execute({
                "query": "test",
                "roots": [TEST_ROOT]
            })
            
            # Verify default max_count was applied
            mock_build_cmd.assert_called_once()
            call_kwargs = mock_build_cmd.call_args[1]
            # Should use the default limit (2000)
            assert call_kwargs["max_count"] == 2000

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture")
    @patch("tree_sitter_analyzer.mcp.tools.search_content_tool.SearchContentTool._validate_roots")
    async def test_max_count_upper_limit(self, mock_validate_roots, mock_run_command):
        """Test that max_count is clamped to upper limit."""
        mock_validate_roots.return_value = [TEST_ROOT]
        mock_run_command.return_value = (0, b"test.py:1:test line\n", b"")
        
        tool = SearchContentTool(enable_cache=False)
        
        with patch("tree_sitter_analyzer.mcp.tools.fd_rg_utils.build_rg_command") as mock_build_cmd:
            mock_build_cmd.return_value = ["rg", "--json", "test"]
            
            await tool.execute({
                "query": "test",
                "roots": [TEST_ROOT],
                "max_count": 50000  # Exceeds hard cap
            })
            
            # Verify max_count was clamped to hard cap (10000)
            mock_build_cmd.assert_called_once()
            call_kwargs = mock_build_cmd.call_args[1]
            assert call_kwargs["max_count"] == 10000


class TestCacheKeyGeneration:
    """Test cases for improved cache key generation."""

    def test_different_output_formats_different_keys(self):
        """Test that different output formats generate different cache keys."""
        tool = SearchContentTool(enable_cache=True)
        cache = tool.cache
        
        # Same query, different output formats should have different keys
        args_total = {"query": "test", "roots": [TEST_ROOT], "total_only": True}
        args_count = {"query": "test", "roots": [TEST_ROOT], "count_only_matches": True}
        
        key1 = cache.create_cache_key(
            query=args_total["query"],
            roots=args_total["roots"],
            total_only=True
        )
        key2 = cache.create_cache_key(
            query=args_count["query"],
            roots=args_count["roots"],
            count_only_matches=True
        )
        
        assert key1 != key2

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture")
    @patch("tree_sitter_analyzer.mcp.tools.search_content_tool.SearchContentTool._validate_roots")
    async def test_cache_format_isolation(self, mock_validate_roots, mock_run_command):
        """Test that cached results respect output format isolation."""
        mock_validate_roots.return_value = [TEST_ROOT]
        
        # Mock different responses for different formats
        count_output = b"test.py:5\n"
        json_output = b'{"type":"match","data":{"path":{"text":"test.py"},"line_number":1,"lines":{"text":"test line"}}}\n'
        
        def mock_command_side_effect(cmd, timeout_ms=None):
            if "--count-matches" in cmd:
                return (0, count_output, b"")
            else:
                return (0, json_output, b"")
        
        mock_run_command.side_effect = mock_command_side_effect
        
        tool = SearchContentTool(enable_cache=True)
        
        # First request: total_only
        result1 = await tool.execute({
            "query": "test",
            "roots": [TEST_ROOT],
            "total_only": True
        })
        
        # Second request: summary_only (different format)
        result2 = await tool.execute({
            "query": "test",
            "roots": [TEST_ROOT],
            "summary_only": True
        })
        
        # Results should be different formats
        assert isinstance(result1, int)  # total_only returns integer
        assert isinstance(result2, dict)  # summary_only returns dict
        assert "summary" in result2  # summary_only should have summary field

    def test_cache_key_includes_output_format_params(self):
        """Test that cache keys include output format parameters."""
        cache = SearchCache()
        
        # Cache keys should include output format parameters
        key_with_format = cache.create_cache_key(
            query="test",
            roots=[TEST_ROOT],
            total_only=True
        )
        key_without_format = cache.create_cache_key(
            query="test",
            roots=[TEST_ROOT]
        )
        
        assert key_with_format != key_without_format
        assert "total_only" in key_with_format


class TestErrorHandling:
    """Test cases for enhanced error handling."""

    def test_invalid_max_count_type(self):
        """Test error handling for invalid max_count types."""
        tool = SearchContentTool(enable_cache=False)
        
        # String value should cause validation error
        with pytest.raises(ValueError) as exc_info:
            tool.validate_arguments({
                "query": "test",
                "roots": [TEST_ROOT],
                "max_count": "invalid"
            })
        
        error_message = str(exc_info.value)
        assert "max_count" in error_message
        assert "integer" in error_message.lower()

    def test_missing_query_parameter(self):
        """Test error handling for missing required parameters."""
        tool = SearchContentTool(enable_cache=False)
        
        with pytest.raises(ValueError) as exc_info:
            tool.validate_arguments({
                "roots": ["."]
                # Missing query
            })
        
        assert "query" in str(exc_info.value)

    def test_missing_search_target(self):
        """Test error handling when neither roots nor files are provided."""
        tool = SearchContentTool(enable_cache=False)
        
        with pytest.raises(ValueError) as exc_info:
            tool.validate_arguments({
                "query": "test"
                # Missing roots and files
            })
        
        error_message = str(exc_info.value)
        assert "roots" in error_message or "files" in error_message


class TestBackwardCompatibility:
    """Test cases for backward compatibility."""

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture")
    @patch("tree_sitter_analyzer.mcp.tools.search_content_tool.SearchContentTool._validate_roots")
    async def test_legacy_parameter_combinations(self, mock_validate_roots, mock_run_command):
        """Test that legacy parameter combinations still work."""
        mock_validate_roots.return_value = ["."]
        mock_run_command.return_value = (0, b'{"type":"match","data":{"path":{"text":"test.py"}}}\n', b"")
        
        tool = SearchContentTool(enable_cache=False)
        
        # Legacy style calls should still work
        legacy_calls = [
            {"query": "test", "roots": ["."]},
            {"query": "test", "roots": ["."], "case": "insensitive"},
            {"query": "test", "roots": ["."], "include_globs": ["*.py"]},
        ]
        
        for args in legacy_calls:
            result = await tool.execute(args)
            assert result["success"] is True

    def test_default_behavior_unchanged(self):
        """Test that default behavior is unchanged when no format params are specified."""
        tool = SearchContentTool(enable_cache=False)
        
        # Basic validation should work as before
        args = {"query": "test", "roots": [TEST_ROOT]}
        
        # Mock the path validation to avoid security validator issues
        with patch.object(tool, '_validate_roots') as mock_validate:
            mock_validate.return_value = [TEST_ROOT]
            assert tool.validate_arguments(args) is True
        
        # Format determination should return 'normal' for no format params
        format_type = tool._determine_requested_format(args)
        assert format_type == "normal"