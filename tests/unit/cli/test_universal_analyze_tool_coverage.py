#!/usr/bin/env python3
"""
Additional tests for tree_sitter_analyzer.mcp.tools.universal_analyze_tool module.

This module provides additional test coverage for the UniversalAnalyzeTool
focusing on analysis types, metrics extraction, and validation.
Requirements: 3.2
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool


class TestUniversalAnalyzeToolAnalysisTypes:
    """Test different analysis types in UniversalAnalyzeTool."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def tool(self, temp_dir):
        """Create a UniversalAnalyzeTool instance for testing."""
        return UniversalAnalyzeTool(temp_dir)

    @pytest.fixture
    def sample_python_file(self, temp_dir):
        """Create a sample Python file for testing."""
        file_path = Path(temp_dir) / "sample.py"
        file_path.write_text("""
import os
import sys

class Calculator:
    '''A simple calculator class.'''

    def __init__(self):
        self.value = 0

    def add(self, a, b):
        '''Add two numbers.'''
        return a + b

    def multiply(self, a, b):
        '''Multiply two numbers.'''
        return a * b

def main():
    calc = Calculator()
    print(calc.add(2, 3))
""")
        return str(file_path)

    @pytest.fixture
    def sample_java_file(self, temp_dir):
        """Create a sample Java file for testing."""
        file_path = Path(temp_dir) / "Sample.java"
        file_path.write_text("""
package com.example;

import java.util.List;

public class Sample {
    private int value;

    public Sample() {
        this.value = 0;
    }

    public int add(int a, int b) {
        return a + b;
    }

    public int multiply(int a, int b) {
        return a * b;
    }
}
""")
        return str(file_path)

    @pytest.mark.asyncio
    async def test_execute_basic_analysis(self, tool, sample_python_file):
        """Test basic analysis type."""
        args = {"file_path": sample_python_file, "analysis_type": "basic"}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result
        assert result.get("analysis_type") == "basic"
        assert "metrics" in result

    @pytest.mark.asyncio
    async def test_execute_detailed_analysis(self, tool, sample_python_file):
        """Test detailed analysis type."""
        args = {"file_path": sample_python_file, "analysis_type": "detailed"}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result
        assert result.get("analysis_type") == "detailed"

    @pytest.mark.asyncio
    async def test_execute_structure_analysis(self, tool, sample_python_file):
        """Test structure analysis type."""
        args = {"file_path": sample_python_file, "analysis_type": "structure"}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result
        assert result.get("analysis_type") == "structure"

    @pytest.mark.asyncio
    async def test_execute_metrics_analysis(self, tool, sample_python_file):
        """Test metrics analysis type."""
        args = {"file_path": sample_python_file, "analysis_type": "metrics"}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result
        assert result.get("analysis_type") == "metrics"

    @pytest.mark.asyncio
    async def test_execute_with_include_ast(self, tool, sample_python_file):
        """Test analysis with include_ast option."""
        args = {"file_path": sample_python_file, "include_ast": True}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result
        # AST info may or may not be present depending on analyzer

    @pytest.mark.asyncio
    async def test_execute_with_include_queries(self, tool, sample_python_file):
        """Test analysis with include_queries option."""
        args = {
            "file_path": sample_python_file,
            "include_queries": True,
            "output_format": "json",
        }
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result
        assert "available_queries" in result

    @pytest.mark.asyncio
    async def test_execute_java_file_basic(self, tool, sample_java_file):
        """Test Java file analysis with basic type."""
        args = {"file_path": sample_java_file, "analysis_type": "basic"}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result
        assert result.get("language") == "java"

    @pytest.mark.asyncio
    async def test_execute_java_file_detailed(self, tool, sample_java_file):
        """Test Java file analysis with detailed type."""
        args = {"file_path": sample_java_file, "analysis_type": "detailed"}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result

    @pytest.mark.asyncio
    async def test_execute_java_file_structure(self, tool, sample_java_file):
        """Test Java file analysis with structure type."""
        args = {"file_path": sample_java_file, "analysis_type": "structure"}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result

    @pytest.mark.asyncio
    async def test_execute_java_file_metrics(self, tool, sample_java_file):
        """Test Java file analysis with metrics type."""
        args = {"file_path": sample_java_file, "analysis_type": "metrics"}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result

    @pytest.mark.asyncio
    async def test_execute_java_with_include_ast(self, tool, sample_java_file):
        """Test Java file analysis with include_ast option."""
        args = {"file_path": sample_java_file, "include_ast": True}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result

    @pytest.mark.asyncio
    async def test_execute_java_with_include_queries(self, tool, sample_java_file):
        """Test Java file analysis with include_queries option."""
        args = {
            "file_path": sample_java_file,
            "include_queries": True,
            "output_format": "json",
        }
        result = await tool.execute(args)

        assert isinstance(result, dict)
        assert "file_path" in result
        assert "available_queries" in result


class TestUniversalAnalyzeToolValidation:
    """Test argument validation in UniversalAnalyzeTool."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def tool(self, temp_dir):
        """Create a UniversalAnalyzeTool instance for testing."""
        return UniversalAnalyzeTool(temp_dir)

    def test_validate_arguments_valid(self, tool):
        """Test validate_arguments with valid arguments."""
        args = {"file_path": "/path/to/file.py"}
        assert tool.validate_arguments(args) is True

    def test_validate_arguments_missing_file_path(self, tool):
        """Test validate_arguments with missing file_path."""
        args = {}
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_file_path_type(self, tool):
        """Test validate_arguments with invalid file_path type."""
        args = {"file_path": 123}
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(args)

    def test_validate_arguments_empty_file_path(self, tool):
        """Test validate_arguments with empty file_path."""
        args = {"file_path": ""}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_language_type(self, tool):
        """Test validate_arguments with invalid language type."""
        args = {"file_path": "/path/to/file.py", "language": 123}
        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_analysis_type_type(self, tool):
        """Test validate_arguments with invalid analysis_type type."""
        args = {"file_path": "/path/to/file.py", "analysis_type": 123}
        with pytest.raises(ValueError, match="analysis_type must be a string"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_analysis_type_value(self, tool):
        """Test validate_arguments with invalid analysis_type value."""
        args = {"file_path": "/path/to/file.py", "analysis_type": "invalid"}
        with pytest.raises(ValueError, match="analysis_type must be one of"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_include_ast_type(self, tool):
        """Test validate_arguments with invalid include_ast type."""
        args = {"file_path": "/path/to/file.py", "include_ast": "true"}
        with pytest.raises(ValueError, match="include_ast must be a boolean"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_include_queries_type(self, tool):
        """Test validate_arguments with invalid include_queries type."""
        args = {"file_path": "/path/to/file.py", "include_queries": "true"}
        with pytest.raises(ValueError, match="include_queries must be a boolean"):
            tool.validate_arguments(args)


class TestUniversalAnalyzeToolConfiguration:
    """Test configuration methods in UniversalAnalyzeTool."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def tool(self, temp_dir):
        """Create a UniversalAnalyzeTool instance for testing."""
        return UniversalAnalyzeTool(temp_dir)

    def test_get_tool_definition(self, tool):
        """Test get_tool_definition returns valid schema."""
        definition = tool.get_tool_definition()

        assert isinstance(definition, dict)
        assert definition["name"] == "analyze_code_universal"
        assert "description" in definition
        assert "inputSchema" in definition

        schema = definition["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "file_path" in schema["properties"]
        assert "required" in schema
        assert "file_path" in schema["required"]

    def test_set_project_path(self, tool, temp_dir):
        """Test set_project_path updates the project path."""
        new_temp_dir = tempfile.mkdtemp()
        try:
            tool.set_project_path(new_temp_dir)
            # Verify the tool still works after path change
            assert tool.analysis_engine is not None
        finally:
            import shutil

            shutil.rmtree(new_temp_dir, ignore_errors=True)


class TestUniversalAnalyzeToolErrorHandling:
    """Test error handling in UniversalAnalyzeTool."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def tool(self, temp_dir):
        """Create a UniversalAnalyzeTool instance for testing."""
        return UniversalAnalyzeTool(temp_dir)

    @pytest.mark.asyncio
    async def test_execute_invalid_analysis_type(self, tool, temp_dir):
        """Test execute with invalid analysis_type."""
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        file_path = Path(temp_dir) / "test.py"
        file_path.write_text("def hello(): pass")

        args = {"file_path": str(file_path), "analysis_type": "invalid_type"}

        with pytest.raises(AnalysisError):
            await tool.execute(args)

    @pytest.mark.asyncio
    async def test_execute_unsupported_language(self, tool, temp_dir):
        """Test execute with unsupported language."""
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        file_path = Path(temp_dir) / "test.xyz"
        file_path.write_text("some content")

        args = {"file_path": str(file_path), "language": "unsupported_lang"}

        with pytest.raises(AnalysisError):
            await tool.execute(args)

    @pytest.mark.asyncio
    async def test_execute_unknown_file_extension(self, tool, temp_dir):
        """Test execute with unknown file extension."""
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        file_path = Path(temp_dir) / "test.unknown"
        file_path.write_text("some content")

        args = {"file_path": str(file_path)}

        with pytest.raises(AnalysisError):
            await tool.execute(args)

    @pytest.mark.asyncio
    async def test_execute_with_explicit_language(self, tool, temp_dir):
        """Test execute with explicitly specified language."""
        file_path = Path(temp_dir) / "test.txt"
        file_path.write_text("def hello(): pass")

        args = {"file_path": str(file_path), "language": "python"}

        result = await tool.execute(args)
        assert isinstance(result, dict)
        assert result.get("language") == "python"
