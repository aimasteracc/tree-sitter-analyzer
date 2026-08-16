#!/usr/bin/env python3
"""
Test query_tool file output functionality - Extended tests

Tests multi-language support, error handling, and integration scenarios
for the query MCP tool (query_code).
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool


class TestQueryToolFileOutputExtended:
    """Extended tests for file output functionality - multi-language, errors, integration"""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create a comprehensive Python test file
            python_file = project_path / "sample.py"
            python_file.write_text(
                """#!/usr/bin/env python3
\"\"\"
Sample Python file for testing query functionality.
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
    return instance

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
    }
}
"""
            )

            # Create a JavaScript test file
            js_file = project_path / "sample.js"
            js_file.write_text(
                """/**
 * Sample JavaScript file for testing.
 */

const GLOBAL_CONSTANT = "test_value";

class SampleClass {
    constructor(name) {
        this.name = name;
        this.value = 42;
    }

    getName() {
        return this.name;
    }

    calculate(x, y) {
        return x + y;
    }

    static staticMethod() {
        return "static_result";
    }
}

function main() {
    const instance = new SampleClass("test");
    console.log(`Name: ${instance.getName()}`);
    return instance;
}

if (typeof module !== 'undefined') {
    module.exports = { SampleClass, main };
}
"""
            )

            yield str(project_path)

    @pytest.fixture
    def query_tool(self, temp_project_dir):
        """Create QueryTool instance"""
        return QueryTool(project_root=temp_project_dir)

    def create_mock_query_results(self, query_type="functions"):
        """Create mock query results for different query types"""
        if query_type == "functions":
            return [
                {
                    "capture_name": "function",
                    "content": "def __init__(self, name: str):",
                    "start_line": 15,
                    "end_line": 17,
                    "node_type": "function_definition",
                },
                {
                    "capture_name": "function",
                    "content": "def get_name(self) -> str:",
                    "start_line": 19,
                    "end_line": 21,
                    "node_type": "function_definition",
                },
                {
                    "capture_name": "function",
                    "content": "def calculate(self, x: int, y: int) -> int:",
                    "start_line": 23,
                    "end_line": 26,
                    "node_type": "function_definition",
                },
            ]
        elif query_type == "classes":
            return [
                {
                    "capture_name": "class",
                    "content": "class SampleClass:",
                    "start_line": 12,
                    "end_line": 30,
                    "node_type": "class_definition",
                }
            ]
        elif query_type == "imports":
            return [
                {
                    "capture_name": "import",
                    "content": "import os",
                    "start_line": 6,
                    "end_line": 6,
                    "node_type": "import_statement",
                },
                {
                    "capture_name": "import",
                    "content": "import sys",
                    "start_line": 7,
                    "end_line": 7,
                    "node_type": "import_statement",
                },
            ]
        else:
            return []

    # =========================================================================
    # Multi-Language Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_java_file_query(self, query_tool, temp_project_dir):
        """Test querying Java file"""
        java_file = Path(temp_project_dir) / "Sample.java"

        with patch.object(query_tool.query_service, "execute_query") as mock_query:
            # Mock Java-specific results
            java_results = [
                {
                    "capture_name": "method",
                    "content": "public Sample(String name)",
                    "start_line": 11,
                    "end_line": 14,
                    "node_type": "constructor_declaration",
                },
                {
                    "capture_name": "method",
                    "content": "public String getName()",
                    "start_line": 16,
                    "end_line": 18,
                    "node_type": "method_declaration",
                },
            ]
            mock_query.return_value = java_results

            arguments = {
                "file_path": str(java_file),
                "query_key": "methods",
                "language": "java",
                "output_file": "java_query_methods",
                "suppress_output": False,
                "output_format": "json",  # Use JSON format for test assertions
            }

            result = await query_tool.execute(arguments)

            # Check Java-specific results
            assert result["success"] is True
            assert result["language"] == "java"
            assert result["count"] == 2

            # Verify file output
            output_file = Path(result["output_file_path"])
            assert output_file.exists()

    @pytest.mark.asyncio
    async def test_javascript_file_query(self, query_tool, temp_project_dir):
        """Test querying JavaScript file"""
        js_file = Path(temp_project_dir) / "sample.js"

        with patch.object(query_tool.query_service, "execute_query") as mock_query:
            # Mock JavaScript-specific results
            js_results = [
                {
                    "capture_name": "function",
                    "content": "constructor(name)",
                    "start_line": 7,
                    "end_line": 10,
                    "node_type": "method_definition",
                },
                {
                    "capture_name": "function",
                    "content": "getName()",
                    "start_line": 12,
                    "end_line": 14,
                    "node_type": "method_definition",
                },
            ]
            mock_query.return_value = js_results

            arguments = {
                "file_path": str(js_file),
                "query_key": "functions",
                "output_file": "js_query_functions",
                "suppress_output": False,
                "output_format": "json",  # Use JSON format for test assertions
            }

            result = await query_tool.execute(arguments)

            # Check JavaScript-specific results
            assert result["success"] is True
            assert result["language"] == "javascript"
            assert result["count"] == 2

    # =========================================================================
    # Error Handling Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_error_handling_file_save_failure(self, query_tool, temp_project_dir):
        """Test error handling when file save fails"""
        python_file = Path(temp_project_dir) / "sample.py"

        with patch.object(query_tool.query_service, "execute_query") as mock_query:
            mock_query.return_value = self.create_mock_query_results("functions")

            # Mock FileOutputManager to raise an exception
            with patch.object(
                query_tool.file_output_manager, "save_to_file"
            ) as mock_save:
                mock_save.side_effect = Exception("File save error")

                arguments = {
                    "file_path": str(python_file),
                    "query_key": "functions",
                    "output_file": "error_test",
                    "suppress_output": False,
                    "output_format": "json",  # Use JSON format for test assertions
                }

                result = await query_tool.execute(arguments)

                # Check error handling - file_save_error may or may not be present
                assert "file_saved" in result
                assert result["file_saved"] is False

                # Should still have query results
                assert "results" in result
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_query_execution_failure(self, query_tool, temp_project_dir):
        """Test handling of query execution failure"""
        python_file = Path(temp_project_dir) / "sample.py"

        with patch.object(query_tool.query_service, "execute_query") as mock_query:
            mock_query.side_effect = Exception("Query execution failed")

            arguments = {
                "file_path": str(python_file),
                "query_key": "functions",
                "output_file": "query_error_test",
            }

            result = await query_tool.execute(arguments)

            # Check error result
            assert result["success"] is False
            assert "error" in result
            assert "Query execution failed" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_file_path(self, query_tool, temp_project_dir):
        """Test handling of invalid file path"""
        nonexistent_file = Path(temp_project_dir) / "nonexistent.py"

        # The behavior may vary - could raise ValueError or return error result
        try:
            result = await query_tool.execute(
                {"file_path": str(nonexistent_file), "query_key": "functions"}
            )
            # If it returns a result, it should indicate failure
            assert result["success"] is False
            assert "error" in result
        except ValueError as e:
            # If it raises ValueError, that's also acceptable
            assert "Invalid" in str(e) or "not found" in str(e) or "unsafe" in str(e)
        except Exception as e:
            # Other exceptions are also acceptable for invalid file paths
            assert "not found" in str(e).lower() or "invalid" in str(e).lower()

    @pytest.mark.asyncio
    async def test_missing_query_parameters(self, query_tool, temp_project_dir):
        """Test handling of missing query parameters"""
        python_file = Path(temp_project_dir) / "sample.py"

        # The error handling may vary - could raise ValueError or AnalysisError
        try:
            result = await query_tool.execute(
                {
                    "file_path": str(python_file)
                    # No query_key or query_string
                }
            )
            # If it returns a result, it should indicate failure
            assert result["success"] is False
            assert "error" in result
        except Exception as e:
            # Should raise some kind of error about missing parameters
            error_msg = str(e).lower()
            assert "query" in error_msg and (
                "required" in error_msg or "must be provided" in error_msg
            )

    @pytest.mark.asyncio
    async def test_both_query_parameters_provided(self, query_tool, temp_project_dir):
        """Test handling when both query_key and query_string are provided"""
        python_file = Path(temp_project_dir) / "sample.py"

        # The error handling may vary - could raise ValueError or AnalysisError
        try:
            result = await query_tool.execute(
                {
                    "file_path": str(python_file),
                    "query_key": "functions",
                    "query_string": "(function_definition) @function",
                }
            )
            # If it returns a result, it should indicate failure
            assert result["success"] is False
            assert "error" in result
        except Exception as e:
            # Should raise some kind of error about conflicting parameters
            error_msg = str(e).lower()
            assert (
                "both" in error_msg
                or "cannot provide" in error_msg
                or "conflict" in error_msg
            )

    # =========================================================================
    # Tool Definition Tests
    # =========================================================================

    def test_tool_definition_includes_new_parameters(self, query_tool):
        """Test that tool definition includes new parameters"""
        definition = query_tool.get_tool_definition()
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
            "suppress detailed output" in properties["suppress_output"]["description"]
        )

        # Check output_format parameter
        assert "output_format" in properties
        assert properties["output_format"]["enum"] == ["json", "toon"]
        assert (
            properties["output_format"]["default"] == "toon"
        )  # Default is toon for token optimization

    # =========================================================================
    # Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_language_auto_detection(self, query_tool, temp_project_dir):
        """Test automatic language detection"""
        python_file = Path(temp_project_dir) / "sample.py"

        with patch.object(query_tool.query_service, "execute_query") as mock_query:
            mock_query.return_value = self.create_mock_query_results("functions")

            arguments = {
                "file_path": str(python_file),
                "query_key": "functions",
                # No language specified - should auto-detect
                "output_file": "auto_detect_test",
                "output_format": "json",  # Use JSON format for test assertions
            }

            result = await query_tool.execute(arguments)

            # Should auto-detect Python
            assert result["language"] == "python"
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_filter_parameter(self, query_tool, temp_project_dir):
        """Test filter parameter functionality"""
        python_file = Path(temp_project_dir) / "sample.py"

        with patch.object(query_tool.query_service, "execute_query") as mock_query:
            # Mock filtered results
            filtered_results = [
                {
                    "capture_name": "function",
                    "content": "def get_name(self) -> str:",
                    "start_line": 19,
                    "end_line": 21,
                    "node_type": "function_definition",
                }
            ]
            mock_query.return_value = filtered_results

            arguments = {
                "file_path": str(python_file),
                "query_key": "functions",
                "filter": "name=~get*",
                "output_file": "filtered_query",
                "suppress_output": False,
            }

            result = await query_tool.execute(arguments)

            # Check that filter was applied
            assert result["success"] is True
            assert result["count"] == 1

            # Verify query service was called with filter
            mock_query.assert_called_once()
            call_args = mock_query.call_args[0]
            assert call_args[4] == "name=~get*"  # filter_expression parameter

    @pytest.mark.asyncio
    async def test_comprehensive_workflow(self, query_tool, temp_project_dir):
        """Test comprehensive workflow with all features"""
        python_file = Path(temp_project_dir) / "sample.py"

        with patch.object(query_tool.query_service, "execute_query") as mock_query:
            mock_query.return_value = self.create_mock_query_results("functions")

            arguments = {
                "file_path": str(python_file),
                "language": "python",
                "query_key": "functions",
                "filter": "name=~.*",
                "result_format": "summary",
                "output_file": "comprehensive_query",
                "suppress_output": True,
                "output_format": "json",  # Use JSON format for test assertions
            }

            result = await query_tool.execute(arguments)

            # Check comprehensive result
            assert "success" in result
            assert "count" in result
            assert "file_path" in result
            assert "language" in result
            assert "query" in result
            assert "output_file_path" in result
            assert "file_saved" in result

            # Should not have detailed results due to suppress_output
            assert "results" not in result
            assert "captures" not in result

            # Verify file content
            output_file = Path(result["output_file_path"])
            assert output_file.exists()

            with open(output_file, encoding="utf-8") as f:
                saved_content = json.loads(f.read())

            # Should contain summary format
            assert "query_type" in saved_content
            assert "captures" in saved_content
            assert "total_count" in saved_content
