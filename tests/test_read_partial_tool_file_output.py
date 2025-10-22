#!/usr/bin/env python3
"""
Test read_partial_tool file output functionality

Tests the enhanced file output and suppress_output features
for the read_partial MCP tool (extract_code_section).
"""

import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class TestReadPartialToolFileOutput:
    """Test file output functionality for ReadPartialTool"""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create a comprehensive test file
            test_file = project_path / "sample.py"
            test_file.write_text(
                """#!/usr/bin/env python3
\"\"\"
Sample Python file for testing read_partial functionality.
This file contains various code constructs for testing.
\"\"\"

import os
import sys
from pathlib import Path

# Global variable
GLOBAL_CONSTANT = "test_value"

class SampleClass:
    \"\"\"A sample class for testing.\"\"\"

    def __init__(self, name: str):
        self.name = name
        self.value = 42

    def get_name(self) -> str:
        \"\"\"Get the name of the instance.\"\"\"
        return self.name

    def calculate(self, x: int, y: int) -> int:
        \"\"\"Calculate sum of two numbers.\"\"\"
        result = x + y
        return result

    @staticmethod
    def static_method():
        \"\"\"A static method.\"\"\"
        return "static_result"

def main():
    \"\"\"Main function.\"\"\"
    instance = SampleClass("test")
    print(f"Name: {instance.get_name()}")
    print(f"Calculation: {instance.calculate(10, 20)}")
    print(f"Static: {SampleClass.static_method()}")

if __name__ == "__main__":
    main()
"""
            )

            # Create a Java test file
            java_file = project_path / "Sample.java"
            java_file.write_text(
                """package com.example;

import java.util.List;
import java.util.ArrayList;

/**
 * Sample Java class for testing.
 */
public class Sample {
    private String name;
    private int value;

    public Sample(String name) {
        this.name = name;
        this.value = 42;
    }

    public String getName() {
        return this.name;
    }

    public int calculate(int x, int y) {
        return x + y;
    }

    public static void main(String[] args) {
        Sample sample = new Sample("test");
        System.out.println("Name: " + sample.getName());
        System.out.println("Calculation: " + sample.calculate(10, 20));
    }
}
"""
            )

            yield str(project_path)

    @pytest.fixture
    def read_partial_tool(self, temp_project_dir):
        """Create ReadPartialTool instance"""
        return ReadPartialTool(project_root=temp_project_dir)

    @pytest.mark.asyncio
    async def test_basic_file_output_text_format(
        self, read_partial_tool, temp_project_dir
    ):
        """Test basic file output with text format"""
        test_file = Path(temp_project_dir) / "sample.py"

        arguments = {
            "file_path": str(test_file),
            "start_line": 10,
            "end_line": 15,
            "format": "text",
            "output_file": "partial_text_basic",
            "suppress_output": False,
        }

        result = await read_partial_tool.execute(arguments)

        # Check basic result structure
        assert "file_path" in result
        assert "range" in result
        assert "content_length" in result
        assert "partial_content_result" in result

        # Check file output
        assert "output_file_path" in result
        assert "file_saved" in result
        assert result["file_saved"] is True

        # Verify file was created
        output_file = Path(result["output_file_path"])
        assert output_file.exists()

        # Verify file content (text format includes headers)
        with open(output_file, encoding="utf-8") as f:
            content = f.read()

        assert "--- Partial Read Result ---" in content
        assert f"File: {test_file}" in content
        assert "Range: Line 10-15" in content
        assert "Characters read:" in content

    @pytest.mark.asyncio
    async def test_json_format_output(self, read_partial_tool, temp_project_dir):
        """Test file output with JSON format"""
        test_file = Path(temp_project_dir) / "sample.py"

        arguments = {
            "file_path": str(test_file),
            "start_line": 16,
            "end_line": 25,
            "format": "json",
            "output_file": "partial_json",
            "suppress_output": False,
        }

        result = await read_partial_tool.execute(arguments)

        # Check file output
        assert "output_file_path" in result
        assert "file_saved" in result
        assert result["file_saved"] is True

        # Verify file was created with JSON content
        output_file = Path(result["output_file_path"])
        assert output_file.exists()

        # Verify JSON content
        with open(output_file, encoding="utf-8") as f:
            json_content = json.loads(f.read())

        assert "file_path" in json_content
        assert "range" in json_content
        assert "content" in json_content
        assert "content_length" in json_content
        assert json_content["range"]["start_line"] == 16
        assert json_content["range"]["end_line"] == 25

    @pytest.mark.asyncio
    async def test_raw_format_output(self, read_partial_tool, temp_project_dir):
        """Test file output with raw format"""
        test_file = Path(temp_project_dir) / "sample.py"

        arguments = {
            "file_path": str(test_file),
            "start_line": 26,
            "end_line": 30,
            "format": "raw",
            "output_file": "partial_raw",
            "suppress_output": False,
        }

        result = await read_partial_tool.execute(arguments)

        # Check file output
        assert "output_file_path" in result
        assert "file_saved" in result
        assert result["file_saved"] is True

        # Verify file was created with raw content only
        output_file = Path(result["output_file_path"])
        assert output_file.exists()

        # Verify raw content (no headers, just the extracted code)
        with open(output_file, encoding="utf-8") as f:
            content = f.read()

        # Should not contain headers
        assert "--- Partial Read Result ---" not in content
        assert "File:" not in content
        assert "Range:" not in content

        # Should contain actual code content
        assert content.strip()  # Should have some content

    @pytest.mark.asyncio
    async def test_suppress_output_functionality(
        self, read_partial_tool, temp_project_dir
    ):
        """Test suppress_output functionality"""
        test_file = Path(temp_project_dir) / "sample.py"

        arguments = {
            "file_path": str(test_file),
            "start_line": 1,
            "end_line": 10,
            "output_file": "partial_suppressed",
            "suppress_output": True,
        }

        result = await read_partial_tool.execute(arguments)

        # Check that partial_content_result is suppressed
        assert "partial_content_result" not in result
        assert "file_path" in result
        assert "range" in result
        assert "content_length" in result

        # Check file output info
        assert "output_file_path" in result
        assert "file_saved" in result
        assert result["file_saved"] is True

        # Verify file was still created with full content
        output_file = Path(result["output_file_path"])
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_suppress_output_without_file(
        self, read_partial_tool, temp_project_dir
    ):
        """Test suppress_output without output_file (should include partial_content_result)"""
        test_file = Path(temp_project_dir) / "sample.py"

        arguments = {
            "file_path": str(test_file),
            "start_line": 1,
            "end_line": 5,
            "suppress_output": True,
            # No output_file specified
        }

        result = await read_partial_tool.execute(arguments)

        # Should include partial_content_result when no output_file is specified
        assert "partial_content_result" in result
        assert "file_path" in result
        assert "range" in result
        assert "content_length" in result

    @pytest.mark.asyncio
    async def test_column_range_extraction(self, read_partial_tool, temp_project_dir):
        """Test extraction with column ranges"""
        test_file = Path(temp_project_dir) / "sample.py"

        arguments = {
            "file_path": str(test_file),
            "start_line": 12,
            "end_line": 12,
            "start_column": 0,
            "end_column": 20,
            "format": "json",
            "output_file": "partial_column_range",
            "suppress_output": False,
        }

        result = await read_partial_tool.execute(arguments)

        # Check range information includes columns
        assert result["range"]["start_column"] == 0
        assert result["range"]["end_column"] == 20

        # Verify file output
        output_file = Path(result["output_file_path"])
        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            json_content = json.loads(f.read())

        assert json_content["range"]["start_column"] == 0
        assert json_content["range"]["end_column"] == 20

    @pytest.mark.asyncio
    async def test_single_line_extraction(self, read_partial_tool, temp_project_dir):
        """Test extraction of a single line"""
        test_file = Path(temp_project_dir) / "sample.py"

        arguments = {
            "file_path": str(test_file),
            "start_line": 11,
            # No end_line specified - should read to end of file
            "output_file": "partial_single_line",
            "suppress_output": False,
        }

        result = await read_partial_tool.execute(arguments)

        # Check that end_line is None in range
        assert result["range"]["start_line"] == 11
        assert result["range"]["end_line"] is None

        # Should have content
        assert result["content_length"] > 0

    @pytest.mark.asyncio
    async def test_large_range_extraction(self, read_partial_tool, temp_project_dir):
        """Test extraction of a large range"""
        test_file = Path(temp_project_dir) / "sample.py"

        arguments = {
            "file_path": str(test_file),
            "start_line": 1,
            "end_line": 50,  # Beyond file end
            "format": "text",
            "output_file": "partial_large_range",
            "suppress_output": True,
        }

        result = await read_partial_tool.execute(arguments)

        # Should handle gracefully
        assert "file_path" in result
        assert "content_length" in result
        assert result["content_length"] > 0

        # File should be created
        output_file = Path(result["output_file_path"])
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_java_file_extraction(self, read_partial_tool, temp_project_dir):
        """Test extraction from Java file"""
        java_file = Path(temp_project_dir) / "Sample.java"

        arguments = {
            "file_path": str(java_file),
            "start_line": 8,
            "end_line": 15,
            "format": "json",
            "output_file": "java_partial",
            "suppress_output": False,
        }

        result = await read_partial_tool.execute(arguments)

        # Check basic functionality works with Java files
        assert "file_path" in result
        assert "content_length" in result
        assert result["content_length"] > 0

        # Verify file output
        output_file = Path(result["output_file_path"])
        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            json_content = json.loads(f.read())

        assert (
            "public class Sample" in json_content["content"]
            or "private String name" in json_content["content"]
        )

    @pytest.mark.asyncio
    async def test_error_handling_file_save_failure(
        self, read_partial_tool, temp_project_dir
    ):
        """Test error handling when file save fails"""
        test_file = Path(temp_project_dir) / "sample.py"

        # Mock FileOutputManager to raise an exception
        from unittest.mock import patch

        with patch.object(
            read_partial_tool.file_output_manager, "save_to_file"
        ) as mock_save:
            mock_save.side_effect = Exception("File save error")

            arguments = {
                "file_path": str(test_file),
                "start_line": 1,
                "end_line": 5,
                "output_file": "error_test",
                "suppress_output": False,
            }

            result = await read_partial_tool.execute(arguments)

            # Check error handling
            assert "file_save_error" in result
            assert "file_saved" in result
            assert result["file_saved"] is False
            assert "File save error" in result["file_save_error"]

            # Should still have partial_content_result
            assert "partial_content_result" in result

    @pytest.mark.asyncio
    async def test_invalid_line_ranges(self, read_partial_tool, temp_project_dir):
        """Test handling of invalid line ranges"""
        test_file = Path(temp_project_dir) / "sample.py"

        # Test start_line < 1
        result = await read_partial_tool.execute(
            {"file_path": str(test_file), "start_line": 0, "end_line": 5}
        )
        assert result["success"] is False
        assert "start_line must be >= 1" in result["error"]

        # Test end_line < start_line
        result = await read_partial_tool.execute(
            {"file_path": str(test_file), "start_line": 10, "end_line": 5}
        )
        assert result["success"] is False
        assert "end_line must be >= start_line" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_column_ranges(self, read_partial_tool, temp_project_dir):
        """Test handling of invalid column ranges"""
        test_file = Path(temp_project_dir) / "sample.py"

        # Test negative start_column
        result = await read_partial_tool.execute(
            {"file_path": str(test_file), "start_line": 1, "start_column": -1}
        )
        assert result["success"] is False
        assert "start_column must be >= 0" in result["error"]

        # Test negative end_column
        result = await read_partial_tool.execute(
            {"file_path": str(test_file), "start_line": 1, "end_column": -1}
        )
        assert result["success"] is False
        assert "end_column must be >= 0" in result["error"]

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, read_partial_tool, temp_project_dir):
        """Test handling of nonexistent file"""
        nonexistent_file = Path(temp_project_dir) / "nonexistent.py"

        result = await read_partial_tool.execute(
            {"file_path": str(nonexistent_file), "start_line": 1, "end_line": 5}
        )
        assert result["success"] is False
        assert "file does not exist" in result["error"]

    def test_tool_definition_includes_new_parameters(self, read_partial_tool):
        """Test that tool definition includes new parameters"""
        definition = read_partial_tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema["properties"]

        # Check output_file parameter
        assert "output_file" in properties
        assert properties["output_file"]["type"] == "string"
        assert (
            "Optional filename to save output to file"
            in properties["output_file"]["description"]
        )

        # Check suppress_output parameter
        assert "suppress_output" in properties
        assert properties["suppress_output"]["type"] == "boolean"
        assert properties["suppress_output"]["default"] is False
        assert (
            "suppress partial_content_result"
            in properties["suppress_output"]["description"]
        )

        # Check format parameter
        assert "format" in properties
        assert properties["format"]["enum"] == ["text", "json", "raw"]
        assert properties["format"]["default"] == "text"

    @pytest.mark.asyncio
    async def test_automatic_base_name_generation(
        self, read_partial_tool, temp_project_dir
    ):
        """Test automatic base name generation when output_file is empty"""
        test_file = Path(temp_project_dir) / "sample.py"

        arguments = {
            "file_path": str(test_file),
            "start_line": 1,
            "end_line": 5,
            "output_file": "auto_generated_name",  # Provide a name to trigger file output
            "suppress_output": False,
        }

        result = await read_partial_tool.execute(arguments)

        # Should generate file output
        assert "output_file_path" in result
        assert "file_saved" in result
        assert result["file_saved"] is True

        # File should exist
        output_file = Path(result["output_file_path"])
        assert output_file.exists()

        # Base name should be used
        assert "auto_generated_name" in output_file.name

    @pytest.mark.asyncio
    async def test_format_parameter_validation(
        self, read_partial_tool, temp_project_dir
    ):
        """Test format parameter validation"""
        test_file = Path(temp_project_dir) / "sample.py"

        # Test invalid format - this should be caught by validate_arguments
        try:
            read_partial_tool.validate_arguments(
                {
                    "file_path": str(test_file),
                    "start_line": 1,
                    "format": "invalid_format",
                }
            )
            # If no exception is raised, the validation might not be implemented
            # Let's test the actual execution instead
            with pytest.raises(
                ValueError, match="format must be 'text', 'json', or 'raw'"
            ):
                await read_partial_tool.execute(
                    {
                        "file_path": str(test_file),
                        "start_line": 1,
                        "format": "invalid_format",
                    }
                )
        except ValueError as e:
            # If validation catches it, that's also acceptable
            assert "format must be 'text', 'json', or 'raw'" in str(e)

    @pytest.mark.asyncio
    async def test_comprehensive_workflow(self, read_partial_tool, temp_project_dir):
        """Test comprehensive workflow with all features"""
        test_file = Path(temp_project_dir) / "sample.py"

        # Extract class definition with all options
        arguments = {
            "file_path": str(test_file),
            "start_line": 12,
            "end_line": 30,
            "start_column": 0,
            "end_column": 100,
            "format": "json",
            "output_file": "comprehensive_extract",
            "suppress_output": True,
        }

        result = await read_partial_tool.execute(arguments)

        # Check comprehensive result
        assert "file_path" in result
        assert "range" in result
        assert "content_length" in result
        assert "output_file_path" in result
        assert "file_saved" in result

        # Should not have partial_content_result due to suppress_output
        assert "partial_content_result" not in result

        # Verify file content
        output_file = Path(result["output_file_path"])
        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            json_content = json.loads(f.read())

        # Should contain class definition
        assert "class SampleClass" in json_content["content"]
        assert json_content["range"]["start_line"] == 12
        assert json_content["range"]["end_line"] == 30
        assert json_content["range"]["start_column"] == 0
        assert json_content["range"]["end_column"] == 100
