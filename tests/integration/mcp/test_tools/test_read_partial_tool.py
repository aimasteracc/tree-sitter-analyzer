#!/usr/bin/env python3
"""
Test cases for read_partial_file MCP tool

Tests the partial file reading tool that provides selective
content extraction from files.
"""


# Mock functionality now provided by pytest-mock

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class TestReadPartialToolSchema:
    """Test read_partial_file tool schema and validation"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.tool = ReadPartialTool()

    def test_tool_schema_structure(self) -> None:
        """Test that tool schema has required structure"""
        schema = self.tool.get_tool_schema()

        # Test schema structure
        assert "type" in schema
        assert "properties" in schema

        # Test schema type
        assert schema["type"] == "object"

        # Test properties
        properties = schema["properties"]
        assert "file_path" in properties
        assert "start_line" in properties
        assert "end_line" in properties
        assert "start_column" in properties
        assert "end_column" in properties
        assert "format" in properties

    def test_input_parameters_validation(self) -> None:
        """Test input parameter validation"""
        # Valid arguments
        valid_args = {
            "file_path": "/path/to/file.java",
            "start_line": 1,
            "end_line": 10,
            "format": "json",
        }

        # Should not raise exception
        result = self.tool.validate_arguments(valid_args)
        assert result is True

    def test_required_parameters(self) -> None:
        """Test required parameter validation"""
        # Missing file_path
        invalid_args = {"start_line": 1, "end_line": 10}

        with pytest.raises(ValueError) as exc_info:
            self.tool.validate_arguments(invalid_args)
        assert "file_path" in str(exc_info.value)


class TestReadPartialToolFunctionality:
    """Test read_partial_file tool core functionality"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.tool = ReadPartialTool()
        self.sample_content = """Line 1: package com.example;
Line 2:
Line 3: import java.util.List;
Line 4:
Line 5: /**
Line 6:  * Sample class
Line 7:  */
Line 8: public class Sample {
Line 9:     private String name;
Line 10:
Line 11:     public String getName() {
Line 12:         return name;
Line 13:     }
Line 14: }
Line 15: """


class TestReadPartialToolErrorHandling:
    """Test error handling in read_partial_file tool"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.tool = ReadPartialTool()

    def test_invalid_arguments(self) -> None:
        """Test validation of invalid arguments"""
        # Invalid line range
        invalid_args = {
            "file_path": "/path/to/file.java",
            "start_line": 10,
            "end_line": 5,  # end < start
        }

        with pytest.raises(ValueError):
            self.tool.validate_arguments(invalid_args)


class TestReadPartialToolIntegration:
    """Test integration with existing file handling components"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.tool = ReadPartialTool()

    def test_integration_with_file_handler(self) -> None:
        """Test integration with file handling utilities"""
        from tree_sitter_analyzer.file_handler import read_file_partial

        # Verify file handler exists and is callable
        # Function-based API, no handler object needed
        assert callable(read_file_partial)


if __name__ == "__main__":
    pytest.main([__file__])
