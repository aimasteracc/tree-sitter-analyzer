#!/usr/bin/env python3
"""
Integration tests for OutputFormatValidator with SearchContentTool
"""

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


class TestSearchContentToolIntegration:
    """Test OutputFormatValidator integration with SearchContentTool."""

    def test_search_content_validates_mutual_exclusion(self, tmp_path):
        """Test that search_content_tool validates mutual exclusion."""
        tool = SearchContentTool(str(tmp_path))

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        # Test: Single format parameter should work
        tool.validate_arguments(
            {"query": "hello", "roots": [str(tmp_path)], "total_only": True}
        )

        # Test: Multiple format parameters should raise error
        with pytest.raises(ValueError, match="Output Format Parameter Error"):
            tool.validate_arguments(
                {
                    "query": "hello",
                    "roots": [str(tmp_path)],
                    "total_only": True,
                    "count_only_matches": True,
                }
            )

        with pytest.raises(ValueError, match="Output Format Parameter Error"):
            tool.validate_arguments(
                {
                    "query": "hello",
                    "roots": [str(tmp_path)],
                    "summary_only": True,
                    "group_by_file": True,
                }
            )

    def test_search_content_no_format_parameter(self, tmp_path):
        """Test that no format parameter is valid (normal mode)."""
        tool = SearchContentTool(str(tmp_path))

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        # No format parameter should be valid
        tool.validate_arguments({"query": "hello", "roots": [str(tmp_path)]})

    def test_error_message_multilingual(self, tmp_path):
        """Test that error messages are multilingual."""
        tool = SearchContentTool(str(tmp_path))

        try:
            tool.validate_arguments(
                {
                    "query": "test",
                    "roots": [str(tmp_path)],
                    "total_only": True,
                    "summary_only": True,
                }
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            error_msg = str(e)
            # Should contain key information
            assert "total_only" in error_msg
            assert "summary_only" in error_msg
            # Should contain either English or Japanese message
            assert "Mutually Exclusive" in error_msg or "相互排他的" in error_msg
