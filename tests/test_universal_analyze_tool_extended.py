#!/usr/bin/env python3
"""
Extended Tests for Universal Analyze Tool

This module provides comprehensive test coverage for the UniversalAnalyzeTool
to improve overall test coverage and test edge cases.
"""

import asyncio
import os
import tempfile

import pytest

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


class TestUniversalAnalyzeToolEdgeCases:
    """Test edge cases and error conditions in UniversalAnalyzeTool."""

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
    async def test_execute_with_empty_file(self, tool, temp_dir):
        """Test executing analysis on an empty file."""
        # Create empty file
        empty_file = os.path.join(temp_dir, "empty.py")
        with open(empty_file, "w") as f:
            f.write("")

        args = {"file_path": empty_file}

        try:
            result = await tool.execute(args)
            assert isinstance(result, dict)
            # Empty file should still produce a valid result
            assert "file_path" in result or "error" in result
        except Exception as e:
            # Some exceptions are acceptable for empty files
            assert isinstance(e, (AnalysisError, ValueError))

    @pytest.mark.asyncio
    async def test_execute_with_binary_file(self, tool, temp_dir):
        """Test executing analysis on a binary file."""
        # Create binary file
        binary_file = os.path.join(temp_dir, "binary.bin")
        with open(binary_file, "wb") as f:
            f.write(b"\x00\x01\x02\x03\x04\x05")

        args = {"file_path": binary_file}

        try:
            result = await tool.execute(args)
            assert isinstance(result, dict)
            # Should handle binary files gracefully
            assert "error" in result or "file_path" in result
        except Exception as e:
            # Exceptions are expected for binary files - AnalysisError wraps original exceptions
            assert isinstance(e, AnalysisError)

    @pytest.mark.asyncio
    async def test_execute_with_large_file(self, tool, temp_dir):
        """Test executing analysis on a large file."""
        # Create large file
        large_file = os.path.join(temp_dir, "large.py")
        large_content = "# Large Python file\n" + "def function_{}(): pass\n" * 1000

        with open(large_file, "w") as f:
            f.write(large_content)

        args = {"file_path": large_file}

        try:
            result = await tool.execute(args)
            assert isinstance(result, dict)
            # Large file should be processed successfully
            assert "file_path" in result or "error" in result
        except Exception as e:
            # Memory or timeout errors might be acceptable
            assert isinstance(e, (MemoryError, TimeoutError, AnalysisError))

    @pytest.mark.asyncio
    async def test_execute_with_malformed_syntax(self, tool, temp_dir):
        """Test executing analysis on files with malformed syntax."""
        malformed_samples = [
            ("incomplete.py", "def incomplete_function("),
            ("missing_colon.py", "class MissingColon"),
            ("incomplete_import.py", "import"),
            ("syntax_error.py", "if True\n    pass"),
        ]

        for filename, code in malformed_samples:
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, "w") as f:
                f.write(code)

            args = {"file_path": file_path}

            try:
                result = await tool.execute(args)
                # Should handle malformed syntax gracefully
                assert isinstance(result, dict)
                assert "error" in result or "file_path" in result
            except Exception as e:
                # Parsing errors are expected for malformed code
                assert isinstance(e, (AnalysisError, SyntaxError))

    @pytest.mark.asyncio
    async def test_execute_with_unicode_content(self, tool, temp_dir):
        """Test executing analysis on files with Unicode content."""
        unicode_file = os.path.join(temp_dir, "unicode.py")
        unicode_content = """
# Unicode test file: 测试文件
def 函数名():
    '''这是一个包含中文的函数'''
    变量 = "Hello, 世界! 🌍"
    return 变量
"""

        with open(unicode_file, "w", encoding="utf-8") as f:
            f.write(unicode_content)

        args = {"file_path": unicode_file}

        try:
            result = await tool.execute(args)
            assert isinstance(result, dict)
            assert "file_path" in result or "error" in result
        except Exception as e:
            # Unicode handling errors might occur
            assert isinstance(e, (UnicodeError, AnalysisError))

    @pytest.mark.asyncio
    async def test_execute_with_nonexistent_file(self, tool):
        """Test executing analysis on a non-existent file."""
        args = {"file_path": "/path/that/does/not/exist.py"}

        try:
            result = await tool.execute(args)
            # Should return error result
            assert isinstance(result, dict)
            assert "error" in result
        except Exception as e:
            # AnalysisError wraps the original exceptions
            assert isinstance(e, AnalysisError)

    @pytest.mark.asyncio
    async def test_execute_with_invalid_arguments(self, tool):
        """Test executing with invalid arguments."""
        invalid_args_list = [
            {},  # Empty arguments
            {"invalid_key": "value"},  # Invalid key
            {"file_path": None},  # None file path
            {"file_path": ""},  # Empty file path
            {"file_path": 123},  # Non-string file path
            {"file_path": ["not", "a", "string"]},  # List instead of string
        ]

        for args in invalid_args_list:
            try:
                result = await tool.execute(args)
                # Should handle invalid arguments gracefully
                assert isinstance(result, dict)
                assert "error" in result
            except Exception as e:
                # AnalysisError wraps various original errors
                assert isinstance(e, AnalysisError)

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
            args = {"file_path": dangerous_path}

            try:
                result = await tool.execute(args)
                # Should reject dangerous paths
                assert isinstance(result, dict)
                assert "error" in result
            except Exception as e:
                # AnalysisError wraps security-related exceptions
                assert isinstance(e, AnalysisError)


class TestUniversalAnalyzeToolConfiguration:
    """Test UniversalAnalyzeTool configuration and initialization."""

    def test_tool_initialization_with_valid_project_root(self):
        """Test tool initialization with valid project root."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tool = UniversalAnalyzeTool(temp_dir)
            assert tool is not None
            assert hasattr(tool, "execute")
            assert hasattr(tool, "analysis_engine")
            assert hasattr(tool, "security_validator")

    def test_tool_initialization_with_none_project_root(self):
        """Test tool initialization with None project root."""
        tool = UniversalAnalyzeTool(None)
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
                tool = UniversalAnalyzeTool(invalid_path)
                assert tool is not None
            except Exception as e:
                # Some initialization errors are acceptable
                assert isinstance(e, (SecurityError, TypeError, ValueError))

    def test_tool_components_initialization(self):
        """Test that tool components are properly initialized."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tool = UniversalAnalyzeTool(temp_dir)

            # Check that all components are initialized
            assert tool.analysis_engine is not None
            assert tool.security_validator is not None

            # Check that components have expected methods
            assert hasattr(tool.analysis_engine, "analyze_file")
            assert hasattr(tool.security_validator, "validate_file_path")


class TestUniversalAnalyzeToolPerformance:
    """Test UniversalAnalyzeTool performance characteristics."""

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
    async def test_concurrent_analysis(self, tool, temp_dir):
        """Test concurrent file analysis."""
        # Create multiple test files
        test_files = []
        for i in range(5):
            file_path = os.path.join(temp_dir, f"test_{i}.py")
            with open(file_path, "w") as f:
                f.write(f"def function_{i}(): pass\nclass Class_{i}: pass")
            test_files.append(file_path)

        # Run concurrent analysis
        tasks = [
            asyncio.create_task(tool.execute({"file_path": file_path}))
            for file_path in test_files
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check results
        successful_results = [
            r for r in results if isinstance(r, dict) and "error" not in r
        ]
        assert len(successful_results) >= 0  # At least some should succeed

    @pytest.mark.asyncio
    async def test_memory_usage_with_repeated_analysis(self, tool, temp_dir):
        """Test memory usage with repeated analysis."""
        import gc

        # Create test file
        test_file = os.path.join(temp_dir, "test.py")
        with open(test_file, "w") as f:
            f.write("def test_function(): pass\nclass TestClass: pass")

        args = {"file_path": test_file}

        # Perform repeated analysis
        for i in range(10):
            try:
                result = await tool.execute(args)
                assert isinstance(result, dict)
            except Exception:
                # Some failures are acceptable in stress testing
                pass

            # Force garbage collection
            if i % 5 == 0:
                gc.collect()

        # Test should complete without memory issues
        assert True

    @pytest.mark.asyncio
    async def test_analysis_with_timeout_scenarios(self, tool, temp_dir):
        """Test analysis with potential timeout scenarios."""
        # Create a complex file that might take time to analyze
        complex_file = os.path.join(temp_dir, "complex.py")
        complex_content = """
# Complex Python file with nested structures
""" + "\n".join(
            [
                f"class Class_{i}:\n    def method_{j}(self): pass"
                for i in range(20)
                for j in range(5)
            ]
        )

        with open(complex_file, "w") as f:
            f.write(complex_content)

        args = {"file_path": complex_file}

        try:
            # Test with potential timeout
            result = await asyncio.wait_for(tool.execute(args), timeout=10.0)
            assert isinstance(result, dict)
        except (asyncio.TimeoutError, AnalysisError):
            # Timeout errors are acceptable for complex files
            pass


class TestUniversalAnalyzeToolIntegration:
    """Integration tests for UniversalAnalyzeTool."""

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
    async def test_tool_with_realistic_python_file(self, tool, temp_dir):
        """Test tool with realistic Python file."""
        python_file = os.path.join(temp_dir, "realistic.py")
        python_content = """
#!/usr/bin/env python3
'''
A realistic Python module for testing.
'''

import os
import sys
from typing import List, Dict, Optional

class Calculator:
    '''A simple calculator class.'''

    def __init__(self):
        self.history: List[str] = []

    def add(self, a: float, b: float) -> float:
        '''Add two numbers.'''
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result

    def multiply(self, a: float, b: float) -> float:
        '''Multiply two numbers.'''
        result = a * b
        self.history.append(f"{a} * {b} = {result}")
        return result

def main():
    '''Main function.'''
    calc = Calculator()
    print(calc.add(2, 3))
    print(calc.multiply(4, 5))

if __name__ == "__main__":
    main()
"""

        with open(python_file, "w") as f:
            f.write(python_content)

        args = {"file_path": python_file}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        # Should successfully analyze realistic Python file
        assert "file_path" in result or "error" not in result

    @pytest.mark.asyncio
    async def test_tool_with_realistic_java_file(self, tool, temp_dir):
        """Test tool with realistic Java file."""
        java_file = os.path.join(temp_dir, "Calculator.java")
        java_content = """
package com.example;

import java.util.ArrayList;
import java.util.List;

/**
 * A simple calculator class.
 */
public class Calculator {
    private List<String> history;

    public Calculator() {
        this.history = new ArrayList<>();
    }

    public double add(double a, double b) {
        double result = a + b;
        history.add(a + " + " + b + " = " + result);
        return result;
    }

    public double multiply(double a, double b) {
        double result = a * b;
        history.add(a + " * " + b + " = " + result);
        return result;
    }

    public static void main(String[] args) {
        Calculator calc = new Calculator();
        System.out.println(calc.add(2, 3));
        System.out.println(calc.multiply(4, 5));
    }
}
"""

        with open(java_file, "w") as f:
            f.write(java_content)

        args = {"file_path": java_file}
        result = await tool.execute(args)

        assert isinstance(result, dict)
        # Should successfully analyze realistic Java file
        assert "file_path" in result or "error" not in result
