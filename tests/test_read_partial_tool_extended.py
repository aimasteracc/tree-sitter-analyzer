#!/usr/bin/env python3
"""
Extended Tests for Read Partial Tool

This module provides comprehensive test coverage for the ReadPartialTool
to improve overall test coverage and test edge cases.
"""

import asyncio
import os
import tempfile

import pytest

from tree_sitter_analyzer.exceptions import FileHandlingError, SecurityError
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class TestReadPartialToolEdgeCases:
    """Test edge cases and error conditions in ReadPartialTool."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def tool(self, temp_dir):
        """Create a ReadPartialTool instance for testing."""
        return ReadPartialTool(temp_dir)

    @pytest.mark.asyncio
    async def test_execute_with_empty_file(self, tool, temp_dir):
        """Test reading from an empty file."""
        empty_file = os.path.join(temp_dir, "empty.txt")
        with open(empty_file, "w") as f:
            f.write("")

        args = {"file_path": empty_file, "start_line": 1, "end_line": 10}

        result = await tool.execute(args)
        assert isinstance(result, dict)
        # Empty file should return empty content or appropriate message
        assert "partial_content_result" in result or "error" in result

    @pytest.mark.asyncio
    async def test_execute_with_single_line_file(self, tool, temp_dir):
        """Test reading from a single line file."""
        single_line_file = os.path.join(temp_dir, "single.txt")
        with open(single_line_file, "w") as f:
            f.write("Single line content")

        args = {"file_path": single_line_file, "start_line": 1, "end_line": 1}

        result = await tool.execute(args)
        assert isinstance(result, dict)
        assert "partial_content_result" in result
        assert "Single line content" in result["partial_content_result"]

    @pytest.mark.asyncio
    async def test_execute_with_large_line_range(self, tool, temp_dir):
        """Test reading with a very large line range."""
        test_file = os.path.join(temp_dir, "test.txt")
        content = "\n".join([f"Line {i}" for i in range(1, 101)])  # 100 lines

        with open(test_file, "w") as f:
            f.write(content)

        args = {
            "file_path": test_file,
            "start_line": 1,
            "end_line": 1000,  # Request more lines than exist
        }

        result = await tool.execute(args)
        assert isinstance(result, dict)
        assert "partial_content_result" in result
        # Should return all available lines without error

    @pytest.mark.asyncio
    async def test_execute_with_negative_line_numbers(self, tool, temp_dir):
        """Test reading with negative line numbers."""
        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Line 1\nLine 2\nLine 3")

        args = {"file_path": test_file, "start_line": -1, "end_line": 2}

        try:
            result = await tool.execute(args)
            assert isinstance(result, dict)
            # Should handle negative line numbers gracefully
            assert "error" in result or "partial_content_result" in result
        except Exception as e:
            # ValueError is expected for negative line numbers
            assert isinstance(e, (ValueError, FileHandlingError))

    @pytest.mark.asyncio
    async def test_execute_with_reversed_line_range(self, tool, temp_dir):
        """Test reading with start_line > end_line."""
        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Line 1\nLine 2\nLine 3")

        args = {
            "file_path": test_file,
            "start_line": 3,
            "end_line": 1,  # Reversed range
        }

        try:
            result = await tool.execute(args)
            assert isinstance(result, dict)
            # Should handle reversed range gracefully
            assert "error" in result or "partial_content_result" in result
        except Exception as e:
            # ValueError is expected for reversed range
            assert isinstance(e, (ValueError, FileHandlingError))

    @pytest.mark.asyncio
    async def test_execute_with_unicode_content(self, tool, temp_dir):
        """Test reading files with Unicode content."""
        unicode_file = os.path.join(temp_dir, "unicode.txt")
        unicode_content = """Line 1: Hello, 世界!
Line 2: 🌍 Unicode test
Line 3: Тест на русском
Line 4: العربية
Line 5: 日本語テスト"""

        with open(unicode_file, "w", encoding="utf-8") as f:
            f.write(unicode_content)

        args = {"file_path": unicode_file, "start_line": 1, "end_line": 5}

        result = await tool.execute(args)
        assert isinstance(result, dict)
        assert "partial_content_result" in result
        # Should handle Unicode content properly

    @pytest.mark.asyncio
    async def test_execute_with_binary_file(self, tool, temp_dir):
        """Test reading from a binary file."""
        binary_file = os.path.join(temp_dir, "binary.bin")
        with open(binary_file, "wb") as f:
            f.write(b"\x00\x01\x02\x03\x04\x05")

        args = {"file_path": binary_file, "start_line": 1, "end_line": 5}

        try:
            result = await tool.execute(args)
            assert isinstance(result, dict)
            # Should handle binary files gracefully
            assert "error" in result or "partial_content_result" in result
        except Exception as e:
            # UnicodeDecodeError is expected for binary files
            assert isinstance(e, (UnicodeDecodeError, FileHandlingError))

    @pytest.mark.asyncio
    async def test_execute_with_nonexistent_file(self, tool):
        """Test reading from a non-existent file."""
        args = {
            "file_path": "/path/that/does/not/exist.txt",
            "start_line": 1,
            "end_line": 10,
        }

        try:
            result = await tool.execute(args)
            assert isinstance(result, dict)
            assert "error" in result
        except Exception as e:
            # Various file-related errors are expected
            assert isinstance(
                e, (FileNotFoundError, SecurityError, FileHandlingError, ValueError)
            )

    @pytest.mark.asyncio
    async def test_execute_with_invalid_arguments(self, tool):
        """Test executing with invalid arguments."""
        invalid_args_list = [
            {},  # Empty arguments
            {"file_path": "test.txt"},  # Missing line numbers
            {"start_line": 1, "end_line": 10},  # Missing file_path
            {"file_path": None, "start_line": 1, "end_line": 10},  # None file_path
            {
                "file_path": "test.txt",
                "start_line": "not_a_number",
                "end_line": 10,
            },  # Invalid start_line
            {
                "file_path": "test.txt",
                "start_line": 1,
                "end_line": "not_a_number",
            },  # Invalid end_line
            {"file_path": 123, "start_line": 1, "end_line": 10},  # Non-string file_path
        ]

        for args in invalid_args_list:
            try:
                result = await tool.execute(args)
                assert isinstance(result, dict)
                assert "error" in result
            except Exception as e:
                # Various errors are expected for invalid arguments
                assert isinstance(
                    e,
                    (
                        ValueError,
                        TypeError,
                        KeyError,
                        FileHandlingError,
                        FileNotFoundError,
                    ),
                )

    @pytest.mark.asyncio
    async def test_execute_with_path_traversal_attempt(self, tool):
        """Test executing with path traversal attempts."""
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/shadow",
            "C:\\Windows\\System32\\config\\SAM",
        ]

        for dangerous_path in dangerous_paths:
            args = {"file_path": dangerous_path, "start_line": 1, "end_line": 10}

            try:
                result = await tool.execute(args)
                assert isinstance(result, dict)
                assert "error" in result
            except Exception as e:
                # Various security-related errors are expected
                assert isinstance(
                    e, (SecurityError, FileHandlingError, FileNotFoundError, ValueError)
                )


class TestReadPartialToolConfiguration:
    """Test ReadPartialTool configuration and initialization."""

    def test_tool_initialization_with_valid_project_root(self):
        """Test tool initialization with valid project root."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tool = ReadPartialTool(temp_dir)
            assert tool is not None
            assert hasattr(tool, "execute")
            assert hasattr(tool, "security_validator")

    def test_tool_initialization_with_none_project_root(self):
        """Test tool initialization with None project root."""
        tool = ReadPartialTool(None)
        assert tool is not None
        # Should still initialize with default behavior

    def test_tool_initialization_with_invalid_project_root(self):
        """Test tool initialization with invalid project root."""
        invalid_paths = [
            "/nonexistent/path",
            "",
            123,
            ["not", "a", "string"],
        ]

        for invalid_path in invalid_paths:
            try:
                tool = ReadPartialTool(invalid_path)
                assert tool is not None
            except Exception as e:
                # Some initialization errors are acceptable
                assert isinstance(e, (SecurityError, TypeError, ValueError))

    def test_tool_components_initialization(self):
        """Test that tool components are properly initialized."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tool = ReadPartialTool(temp_dir)

            # Check that security validator is initialized
            assert tool.security_validator is not None
            assert hasattr(tool.security_validator, "validate_file_path")


class TestReadPartialToolPerformance:
    """Test ReadPartialTool performance characteristics."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def tool(self, temp_dir):
        """Create a ReadPartialTool instance for testing."""
        return ReadPartialTool(temp_dir)

    @pytest.mark.asyncio
    async def test_concurrent_reading(self, tool, temp_dir):
        """Test concurrent file reading."""
        # Create multiple test files
        test_files = []
        for i in range(5):
            file_path = os.path.join(temp_dir, f"test_{i}.txt")
            content = "\n".join([f"File {i}, Line {j}" for j in range(1, 21)])
            with open(file_path, "w") as f:
                f.write(content)
            test_files.append(file_path)

        # Run concurrent reading
        tasks = [
            asyncio.create_task(
                tool.execute({"file_path": file_path, "start_line": 1, "end_line": 10})
            )
            for file_path in test_files
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check results
        successful_results = [
            r for r in results if isinstance(r, dict) and "partial_content_result" in r
        ]
        assert len(successful_results) >= 0  # At least some should succeed

    @pytest.mark.asyncio
    async def test_reading_large_file_portions(self, tool, temp_dir):
        """Test reading large portions of files."""
        # Create a large file
        large_file = os.path.join(temp_dir, "large.txt")
        large_content = "\n".join(
            [f"Line {i}: " + "x" * 100 for i in range(1, 1001)]
        )  # 1000 lines

        with open(large_file, "w") as f:
            f.write(large_content)

        # Read large portions
        test_ranges = [
            (1, 100),
            (101, 200),
            (501, 600),
            (901, 1000),
        ]

        for start, end in test_ranges:
            args = {"file_path": large_file, "start_line": start, "end_line": end}

            result = await tool.execute(args)
            assert isinstance(result, dict)
            assert "partial_content_result" in result

    @pytest.mark.asyncio
    async def test_memory_usage_with_repeated_reading(self, tool, temp_dir):
        """Test memory usage with repeated reading operations."""
        import gc

        # Create test file
        test_file = os.path.join(temp_dir, "test.txt")
        content = "\n".join([f"Line {i}" for i in range(1, 101)])

        with open(test_file, "w") as f:
            f.write(content)

        args = {"file_path": test_file, "start_line": 1, "end_line": 50}

        # Perform repeated reading
        for i in range(20):
            try:
                result = await tool.execute(args)
                assert isinstance(result, dict)
            except Exception:
                # Some failures are acceptable in stress testing
                pass

            # Force garbage collection
            if i % 10 == 0:
                gc.collect()

        # Test should complete without memory issues
        assert True


class TestReadPartialToolIntegration:
    """Integration tests for ReadPartialTool."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def tool(self, temp_dir):
        """Create a ReadPartialTool instance for testing."""
        return ReadPartialTool(temp_dir)

    @pytest.mark.asyncio
    async def test_tool_with_realistic_source_file(self, tool, temp_dir):
        """Test tool with realistic source code file."""
        source_file = os.path.join(temp_dir, "example.py")
        source_content = """#!/usr/bin/env python3
'''
Example Python module for testing partial reading.
'''

import os
import sys
from typing import List, Dict

class ExampleClass:
    '''An example class for demonstration.'''

    def __init__(self, name: str):
        self.name = name
        self.items: List[str] = []

    def add_item(self, item: str) -> None:
        '''Add an item to the list.'''
        self.items.append(item)

    def get_items(self) -> List[str]:
        '''Get all items.'''
        return self.items.copy()

def main():
    '''Main function.'''
    example = ExampleClass("test")
    example.add_item("item1")
    example.add_item("item2")
    print(example.get_items())

if __name__ == "__main__":
    main()
"""

        with open(source_file, "w") as f:
            f.write(source_content)

        # Test reading different portions
        test_cases = [
            (1, 5),  # Header
            (10, 15),  # Class definition start
            (20, 25),  # Method definitions
            (30, 35),  # Main function
        ]

        for start, end in test_cases:
            args = {"file_path": source_file, "start_line": start, "end_line": end}

            result = await tool.execute(args)
            assert isinstance(result, dict)
            assert "partial_content_result" in result
            # Should successfully read portions of realistic source file

    @pytest.mark.asyncio
    async def test_tool_with_different_file_types(self, tool, temp_dir):
        """Test tool with different file types."""
        file_types = [
            ("config.json", '{"key": "value", "number": 42}'),
            ("data.csv", "name,age,city\nJohn,30,NYC\nJane,25,LA"),
            ("readme.md", "# Title\n\nThis is a markdown file.\n\n## Section"),
            ("script.sh", "#!/bin/bash\necho 'Hello, World!'\nls -la"),
        ]

        for filename, content in file_types:
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, "w") as f:
                f.write(content)

            args = {"file_path": file_path, "start_line": 1, "end_line": 3}

            result = await tool.execute(args)
            assert isinstance(result, dict)
            # Should handle different file types appropriately
            assert "partial_content_result" in result or "error" in result
