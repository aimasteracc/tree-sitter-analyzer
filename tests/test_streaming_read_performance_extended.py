#!/usr/bin/env python3
"""
Extended performance tests for streaming read optimization.

This module tests the streaming implementation with very large files
to ensure it meets the performance requirements specified in the OpenSpec.
"""

import os
import tempfile
import time
import tracemalloc
from pathlib import Path

import pytest

from tree_sitter_analyzer.file_handler import read_file_partial
from tree_sitter_analyzer.encoding_utils import read_file_safe_streaming


class TestStreamingReadPerformanceExtended:
    """Extended test cases for streaming read performance optimization."""

    def test_very_large_file_performance(self):
        """Test performance with a very large file (100MB) - scaled down from 1GB for CI."""
        # Create a large temporary file (100MB instead of 1GB for CI efficiency)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            # Write 1,000,000 lines of 100 characters each (~100MB)
            for i in range(1000000):
                f.write(f"Line {i:07d}: " + "x" * 90 + "\n")
            temp_path = f.name

        try:
            # Test extracting lines 500,000 to 500,050 (similar to spec scenario)
            start_time = time.time()
            result = read_file_partial(temp_path, 500000, 500050)
            end_time = time.time()
            
            # Should complete in under 300ms (allowing for system variance)
            duration = end_time - start_time
            assert duration < 0.3, f"Operation took {duration:.3f}s, expected < 0.3s"
            
            # Verify we got the correct content
            lines = result.split('\n')
            # Should have 51 lines (500000-500050 inclusive) plus empty line from final \n
            assert len(lines) == 52  # 51 lines + 1 empty from split
            assert "Line 0499999:" in lines[0]  # 0-based indexing in content
            assert "Line 0500049:" in lines[50]

        finally:
            os.unlink(temp_path)

    def test_memory_usage_large_file(self):
        """Test that memory usage remains low during large file operations."""
        # Create a moderately large file (10MB)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            # Write 100,000 lines of 100 characters each (~10MB)
            for i in range(100000):
                f.write(f"Line {i:06d}: " + "x" * 90 + "\n")
            temp_path = f.name

        try:
            # Start memory tracking
            tracemalloc.start()
            
            # Take baseline memory snapshot
            baseline_snapshot = tracemalloc.take_snapshot()
            baseline_memory = sum(stat.size for stat in baseline_snapshot.statistics('filename'))
            
            # Perform the operation
            result = read_file_partial(temp_path, 50000, 50100)
            
            # Take memory snapshot after operation
            after_snapshot = tracemalloc.take_snapshot()
            after_memory = sum(stat.size for stat in after_snapshot.statistics('filename'))
            
            # Stop memory tracking
            tracemalloc.stop()
            
            # Memory increase should be minimal (less than 10MB as per spec)
            memory_increase = after_memory - baseline_memory
            max_allowed_increase = 10 * 1024 * 1024  # 10MB in bytes
            
            assert memory_increase < max_allowed_increase, \
                f"Memory increased by {memory_increase / 1024 / 1024:.2f}MB, expected < 10MB"
            
            # Verify we got the correct content
            lines = result.split('\n')
            assert len(lines) == 102  # 101 lines + 1 empty from split
            assert "Line 049999:" in lines[0]
            assert "Line 050099:" in lines[100]

        finally:
            os.unlink(temp_path)

    def test_beginning_of_large_file_performance(self):
        """Test extracting from the beginning of a large file (100MB)."""
        # Create a large temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            # Write 1,000,000 lines of 100 characters each (~100MB)
            for i in range(1000000):
                f.write(f"Line {i:07d}: " + "x" * 90 + "\n")
            temp_path = f.name

        try:
            # Test extracting lines 1 to 10 from beginning
            start_time = time.time()
            result = read_file_partial(temp_path, 1, 10)
            end_time = time.time()
            
            # Should complete in under 100ms (allowing for system variance)
            duration = end_time - start_time
            assert duration < 0.1, f"Operation took {duration:.3f}s, expected < 0.1s"
            
            # Verify we got the correct content
            lines = result.split('\n')
            assert len(lines) == 11  # 10 lines + 1 empty from split
            assert "Line 0000000:" in lines[0]
            assert "Line 0000009:" in lines[9]

        finally:
            os.unlink(temp_path)

    def test_end_of_large_file_performance(self):
        """Test extracting until the end of a large file."""
        # Create a large temporary file with known line count
        line_count = 100000
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            # Write 100,000 lines of 100 characters each (~10MB)
            for i in range(line_count):
                f.write(f"Line {i:06d}: " + "x" * 90 + "\n")
            temp_path = f.name

        try:
            # Test extracting last 11 lines (99990 to end)
            start_line = line_count - 10  # 99990 (1-based)
            start_time = time.time()
            result = read_file_partial(temp_path, start_line)  # end_line=None means to end
            end_time = time.time()
            
            # Should be memory-efficient and reasonably fast
            duration = end_time - start_time
            assert duration < 0.1, f"Operation took {duration:.3f}s, expected < 0.1s"
            
            # Verify we got the correct content (last 11 lines)
            lines = result.split('\n')
            # Should have 11 lines + 1 empty from final split
            assert len(lines) == 12
            assert "Line 099989:" in lines[0]  # 0-based in content
            assert "Line 099999:" in lines[10]

        finally:
            os.unlink(temp_path)

    def test_streaming_context_manager_large_file(self):
        """Test that the streaming context manager works efficiently with large files."""
        # Create a moderately large file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            # Write 50,000 lines
            for i in range(50000):
                f.write(f"Line {i:05d}: " + "x" * 90 + "\n")
            temp_path = f.name

        try:
            # Test streaming through the file
            start_time = time.time()
            
            line_count = 0
            target_line = None
            with read_file_safe_streaming(temp_path) as file_handle:
                for line_num, line in enumerate(file_handle, 1):
                    line_count += 1
                    if line_num == 25000:  # Middle of file
                        target_line = line
                    if line_num >= 25010:  # Stop after reading a bit past target
                        break
            
            end_time = time.time()
            
            # Should be efficient
            duration = end_time - start_time
            assert duration < 0.1, f"Streaming took {duration:.3f}s, expected < 0.1s"
            
            # Verify we read the expected content
            assert line_count >= 25010
            assert target_line is not None
            assert "Line 24999:" in target_line  # 0-based in content

        finally:
            os.unlink(temp_path)

    def test_multiple_operations_memory_stability(self):
        """Test that multiple operations don't cause memory leaks."""
        # Create a test file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            # Write 10,000 lines
            for i in range(10000):
                f.write(f"Line {i:05d}: " + "x" * 90 + "\n")
            temp_path = f.name

        try:
            # Start memory tracking
            tracemalloc.start()
            baseline_snapshot = tracemalloc.take_snapshot()
            baseline_memory = sum(stat.size for stat in baseline_snapshot.statistics('filename'))
            
            # Perform multiple operations
            for i in range(10):
                start_line = 1000 + i * 100
                end_line = start_line + 50
                result = read_file_partial(temp_path, start_line, end_line)
                assert result is not None
                assert len(result.split('\n')) == 52  # 51 lines + 1 empty
            
            # Check memory after operations
            after_snapshot = tracemalloc.take_snapshot()
            after_memory = sum(stat.size for stat in after_snapshot.statistics('filename'))
            tracemalloc.stop()
            
            # Memory should not have increased significantly
            memory_increase = after_memory - baseline_memory
            max_allowed_increase = 5 * 1024 * 1024  # 5MB
            
            assert memory_increase < max_allowed_increase, \
                f"Memory increased by {memory_increase / 1024 / 1024:.2f}MB after multiple operations"

        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])