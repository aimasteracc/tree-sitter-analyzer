#!/usr/bin/env python3
"""
Test file output enhancement for extract_code_section and query_code tools.

This test suite verifies that both tools support the new output_file and
suppress_output parameters for token optimization.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class TestFileOutputEnhancement:
    """Test file output enhancement for MCP tools"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def sample_python_file(self, temp_dir):
        """Create a sample Python file for testing"""
        content = '''def hello_world():
    """A simple hello world function"""
    print("Hello, World!")
    return "Hello, World!"

class Calculator:
    """A simple calculator class"""

    def add(self, a, b):
        """Add two numbers"""
        return a + b

    def multiply(self, a, b):
        """Multiply two numbers"""
        return a * b

if __name__ == "__main__":
    hello_world()
    calc = Calculator()
    print(calc.add(2, 3))
'''
        file_path = Path(temp_dir) / "sample.py"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    @pytest.fixture
    def sample_javascript_file(self, temp_dir):
        """Create a sample JavaScript file for testing"""
        content = """function greetUser(name) {
    console.log(`Hello, ${name}!`);
    return `Hello, ${name}!`;
}

class MathUtils {
    static add(a, b) {
        return a + b;
    }

    static multiply(a, b) {
        return a * b;
    }
}

// Main execution
greetUser("World");
console.log(MathUtils.add(5, 3));
"""
        file_path = Path(temp_dir) / "sample.js"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    @pytest.mark.asyncio
    async def test_extract_code_section_with_file_output(
        self, sample_python_file, temp_dir
    ):
        """Test extract_code_section tool with file output functionality"""
        tool = ReadPartialTool(temp_dir)

        # Test with file output enabled
        arguments = {
            "file_path": sample_python_file,
            "start_line": 1,
            "end_line": 4,
            "output_file": "extract_test",
            "suppress_output": False,
        }

        result = await tool.execute(arguments)

        # Verify result structure
        assert "file_path" in result
        assert "range" in result
        assert "content_length" in result
        assert "partial_content_result" in result  # Not suppressed
        assert "output_file_path" in result
        assert "file_saved" in result
        assert result["file_saved"] is True

        # Verify file was created
        output_file_path = result["output_file_path"]
        assert Path(output_file_path).exists()

        # Verify file content
        with open(output_file_path, encoding="utf-8") as f:
            saved_content = f.read()

        assert "def hello_world():" in saved_content
        assert "Partial Read Result" in saved_content

    @pytest.mark.asyncio
    async def test_extract_code_section_with_suppress_output(
        self, sample_python_file, temp_dir
    ):
        """Test extract_code_section tool with output suppression"""
        tool = ReadPartialTool(temp_dir)

        # Test with output suppressed
        arguments = {
            "file_path": sample_python_file,
            "start_line": 6,
            "end_line": 10,
            "output_file": "extract_suppressed",
            "suppress_output": True,
        }

        result = await tool.execute(arguments)

        # Verify result structure
        assert "file_path" in result
        assert "range" in result
        assert "content_length" in result
        assert "partial_content_result" not in result  # Suppressed
        assert "output_file_path" in result
        assert "file_saved" in result
        assert result["file_saved"] is True

        # Verify file was created
        output_file_path = result["output_file_path"]
        assert Path(output_file_path).exists()

    @pytest.mark.asyncio
    async def test_query_code_with_file_output(self, sample_javascript_file, temp_dir):
        """Test query_code tool with file output functionality"""
        tool = QueryTool(temp_dir)

        # Mock the query service to return sample results
        mock_results = [
            {
                "capture_name": "function",
                "node_type": "function_declaration",
                "content": "function greetUser(name) {\n    console.log(`Hello, ${name}!`);\n    return `Hello, ${name}!`;\n}",
                "start_line": 1,
                "end_line": 4,
                "start_column": 0,
                "end_column": 1,
            }
        ]

        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_results

            # Test with file output enabled
            arguments = {
                "file_path": sample_javascript_file,
                "query_key": "functions",
                "output_format": "json",
                "output_file": "query_test",
                "suppress_output": False,
            }

            result = await tool.execute(arguments)

            # Verify result structure
            assert "success" in result
            assert "results" in result
            assert "count" in result
            assert "file_path" in result
            assert "language" in result
            assert "query" in result
            assert "output_file_path" in result
            assert "file_saved" in result
            assert result["file_saved"] is True

            # Verify file was created
            output_file_path = result["output_file_path"]
            assert Path(output_file_path).exists()

            # Verify file content is valid JSON
            with open(output_file_path, encoding="utf-8") as f:
                saved_content = f.read()

            saved_data = json.loads(saved_content)
            assert "results" in saved_data
            assert len(saved_data["results"]) == 1

    @pytest.mark.asyncio
    async def test_query_code_with_suppress_output(self, sample_python_file, temp_dir):
        """Test query_code tool with output suppression"""
        tool = QueryTool(temp_dir)

        # Mock the query service to return sample results
        mock_results = [
            {
                "capture_name": "function",
                "node_type": "function_declaration",
                "content": 'def hello_world():\n    print("Hello, World!")\n    return "Hello, World!"',
                "start_line": 1,
                "end_line": 4,
                "start_column": 0,
                "end_column": 25,
            }
        ]

        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_results

            # Test with output suppressed
            arguments = {
                "file_path": sample_python_file,
                "query_key": "functions",
                "output_format": "json",
                "output_file": "query_suppressed",
                "suppress_output": True,
            }

            result = await tool.execute(arguments)

            # Verify result structure (minimal when suppressed)
            assert "success" in result
            assert "count" in result
            assert "file_path" in result
            assert "language" in result
            assert "query" in result
            assert "results" not in result  # Suppressed
            assert "output_file_path" in result
            assert "file_saved" in result
            assert result["file_saved"] is True

            # Verify file was created
            output_file_path = result["output_file_path"]
            assert Path(output_file_path).exists()

    @pytest.mark.asyncio
    async def test_query_code_summary_format_with_file_output(
        self, sample_python_file, temp_dir
    ):
        """Test query_code tool with summary format and file output"""
        tool = QueryTool(temp_dir)

        # Mock the query service to return sample results
        mock_results = [
            {
                "capture_name": "function",
                "node_type": "function_declaration",
                "content": 'def hello_world():\n    print("Hello, World!")\n    return "Hello, World!"',
                "start_line": 1,
                "end_line": 4,
                "start_column": 0,
                "end_column": 25,
            },
            {
                "capture_name": "function",
                "node_type": "function_declaration",
                "content": "def add(self, a, b):\n    return a + b",
                "start_line": 9,
                "end_line": 11,
                "start_column": 4,
                "end_column": 20,
            },
        ]

        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_results

            # Test with summary format and file output
            arguments = {
                "file_path": sample_python_file,
                "query_key": "functions",
                "output_format": "summary",
                "output_file": "query_summary",
                "suppress_output": False,
            }

            result = await tool.execute(arguments)

            # Verify result structure
            assert "success" in result
            assert "query_type" in result
            assert "language" in result
            assert "total_count" in result
            assert "captures" in result
            assert "output_file_path" in result
            assert "file_saved" in result
            assert result["file_saved"] is True

            # Verify file was created
            output_file_path = result["output_file_path"]
            assert Path(output_file_path).exists()

            # Verify file content is valid JSON
            with open(output_file_path, encoding="utf-8") as f:
                saved_content = f.read()

            saved_data = json.loads(saved_content)
            assert "captures" in saved_data
            assert "function" in saved_data["captures"]

    def test_extract_code_section_argument_validation(self, temp_dir):
        """Test argument validation for extract_code_section tool"""
        tool = ReadPartialTool(temp_dir)

        # Test output_file validation
        arguments = {
            "file_path": "test.py",
            "start_line": 1,
            "output_file": "",  # Empty string
        }

        with pytest.raises(ValueError, match="output_file cannot be empty"):
            tool.validate_arguments(arguments)

        # Test suppress_output validation
        arguments = {
            "file_path": "test.py",
            "start_line": 1,
            "suppress_output": "true",  # String instead of boolean
        }

        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            tool.validate_arguments(arguments)

    def test_query_code_argument_validation(self, temp_dir):
        """Test argument validation for query_code tool"""
        tool = QueryTool(temp_dir)

        # Test output_file validation
        arguments = {
            "file_path": "test.py",
            "query_key": "functions",
            "output_file": "",  # Empty string
        }

        with pytest.raises(ValueError, match="output_file cannot be empty"):
            tool.validate_arguments(arguments)

        # Test suppress_output validation
        arguments = {
            "file_path": "test.py",
            "query_key": "functions",
            "suppress_output": "false",  # String instead of boolean
        }

        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            tool.validate_arguments(arguments)

    @pytest.mark.asyncio
    async def test_file_output_error_handling(self, sample_python_file, temp_dir):
        """Test error handling when file output fails"""
        tool = ReadPartialTool(temp_dir)

        # Mock file_output_manager to raise an exception
        with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
            mock_save.side_effect = OSError("Permission denied")

            arguments = {
                "file_path": sample_python_file,
                "start_line": 1,
                "end_line": 4,
                "output_file": "error_test",
                "suppress_output": False,
            }

            result = await tool.execute(arguments)

            # Verify error handling
            assert "file_save_error" in result
            assert "file_saved" in result
            assert result["file_saved"] is False
            assert "Permission denied" in result["file_save_error"]

            # Main result should still be present
            assert "partial_content_result" in result

    @pytest.mark.asyncio
    async def test_automatic_extension_detection(self, sample_python_file, temp_dir):
        """Test automatic file extension detection"""
        tool = QueryTool(temp_dir)

        # Mock the query service to return sample results
        mock_results = [{"capture_name": "test", "content": "test"}]

        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_results

            arguments = {
                "file_path": sample_python_file,
                "query_key": "functions",
                "output_format": "json",
                "output_file": "auto_extension_test",  # No extension
                "suppress_output": True,
            }

            result = await tool.execute(arguments)

            # Verify file was created with .json extension
            output_file_path = result["output_file_path"]
            assert output_file_path.endswith(".json")
            assert Path(output_file_path).exists()


if __name__ == "__main__":
    pytest.main([__file__])
