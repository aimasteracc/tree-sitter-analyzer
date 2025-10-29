#!/usr/bin/env python3
"""
Tests for streaming read performance optimization.

This module tests the new streaming implementation of read_file_partial
to ensure it works correctly and efficiently.
"""

import os
import tempfile
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.file_handler import read_file_partial
from tree_sitter_analyzer.encoding_utils import read_file_safe_streaming


class TestStreamingReadPerformance:
    """Test cases for streaming read performance optimization."""

    def test_read_file_safe_streaming_context_manager(self):
        """Test that read_file_safe_streaming works as a context manager."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            test_content = "Line 1\nLine 2\nLine 3\n"
            f.write(test_content)
            temp_path = f.name

        try:
            # Test streaming context manager
            with read_file_safe_streaming(temp_path) as file_handle:
                lines = list(file_handle)
                assert len(lines) == 3
                assert lines[0] == "Line 1\n"
                assert lines[1] == "Line 2\n"
                assert lines[2] == "Line 3\n"
        finally:
            os.unlink(temp_path)

    def test_read_file_partial_small_file(self):
        """Test read_file_partial with a small file."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            test_content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
            f.write(test_content)
            temp_path = f.name

        try:
            # Test reading lines 2-4
            result = read_file_partial(temp_path, 2, 4)
            expected = "Line 2\nLine 3\nLine 4\n"
            assert result == expected

            # Test reading from line 3 to end
            result = read_file_partial(temp_path, 3)
            expected = "Line 3\nLine 4\nLine 5\n"
            assert result == expected

            # Test reading single line
            result = read_file_partial(temp_path, 1, 1)
            expected = "Line 1\n"
            assert result == expected

        finally:
            os.unlink(temp_path)

    def test_read_file_partial_with_columns(self):
        """Test read_file_partial with column specifications."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            test_content = "0123456789\nabcdefghij\nABCDEFGHIJ\n"
            f.write(test_content)
            temp_path = f.name

        try:
            # Test reading with start column
            result = read_file_partial(temp_path, 1, 1, start_column=3)
            expected = "3456789"
            assert result == expected

            # Test reading with start and end columns
            result = read_file_partial(temp_path, 2, 2, start_column=2, end_column=5)
            expected = "cde"
            assert result == expected

        finally:
            os.unlink(temp_path)

    def test_read_file_partial_edge_cases(self):
        """Test edge cases for read_file_partial."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            test_content = "Line 1\nLine 2\n"
            f.write(test_content)
            temp_path = f.name

        try:
            # Test reading beyond file length
            result = read_file_partial(temp_path, 10, 15)
            assert result == ""

            # Test invalid parameters
            result = read_file_partial(temp_path, 0, 1)
            assert result is None

            result = read_file_partial(temp_path, 2, 1)
            assert result is None

        finally:
            os.unlink(temp_path)

    def test_read_file_partial_nonexistent_file(self):
        """Test read_file_partial with nonexistent file."""
        result = read_file_partial("/nonexistent/file.txt", 1, 5)
        assert result is None

    def test_streaming_performance_large_file(self):
        """Test that streaming approach is efficient for large files."""
        # Create a large temporary file (1MB)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            # Write 10,000 lines of 100 characters each (~1MB)
            for i in range(10000):
                f.write(f"Line {i:05d}: " + "x" * 90 + "\n")
            temp_path = f.name

        try:
            # Measure time to read a small section from the middle
            start_time = time.time()
            result = read_file_partial(temp_path, 5000, 5010)
            end_time = time.time()
            
            # Should complete quickly (under 200ms as per spec)
            duration = end_time - start_time
            assert duration < 0.2, f"Operation took {duration:.3f}s, expected < 0.2s"
            
            # Verify we got the correct content
            lines = result.split('\n')
            # Should have 11 lines (5000-5010 inclusive) plus empty line from final \n
            assert len(lines) == 12  # 11 lines + 1 empty from split
            assert "Line 04999:" in lines[0]
            assert "Line 05009:" in lines[10]

        finally:
            os.unlink(temp_path)

    def test_empty_file(self):
        """Test read_file_partial with empty file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            # Write nothing (empty file)
            temp_path = f.name

        try:
            result = read_file_partial(temp_path, 1, 5)
            assert result == ""

        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__])