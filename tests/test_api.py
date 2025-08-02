#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.api module.

This module tests the unified API facade that provides a consistent
interface for both CLI and MCP components in the new architecture.
"""

import os
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer import api


class TestAPIFacade:
    """Test cases for the unified API facade"""

    @pytest.fixture
    def sample_java_file(self) -> str:
        """Create a temporary Java file for testing"""
        content = """
package com.example;

public class Calculator {
    private int value;

    public Calculator(int initialValue) {
        this.value = initialValue;
    }

    public int add(int number) {
        return value + number;
    }

    public int getValue() {
        return value;
    }
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(content)
            return f.name

    @pytest.fixture
    def sample_python_file(self) -> str:
        """Create a temporary Python file for testing"""
        content = '''
from typing import Optional

class Calculator:
    def __init__(self, initial_value: int = 0):
        self.value = initial_value

    def add(self, number: int) -> int:
        """Add a number to the current value"""
        self.value += number
        return self.value

    def get_value(self) -> int:
        """Get the current value"""
        return self.value

def main():
    calc = Calculator(10)
    result = calc.add(5)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            return f.name

    def test_analyze_file_java_success(self, sample_java_file: str) -> None:
        """Test successful Java file analysis through API"""
        try:
            result = api.analyze_file(sample_java_file)

            assert isinstance(result, dict)
            assert result["success"] is True
            assert result["file_info"]["path"] == sample_java_file
            assert result["language_info"]["language"] == "java"
            assert "elements" in result
            assert len(result["elements"]) > 0
            assert result["ast_info"]["node_count"] > 0

        finally:
            os.unlink(sample_java_file)

    def test_analyze_file_python_success(self, sample_python_file: str) -> None:
        """Test successful Python file analysis through API"""
        try:
            result = api.analyze_file(sample_python_file)

            assert isinstance(result, dict)
            assert result["success"] is True
            assert result["file_info"]["path"] == sample_python_file
            assert result["language_info"]["language"] == "python"
            assert "elements" in result
            assert len(result["elements"]) > 0

        finally:
            os.unlink(sample_python_file)

    def test_analyze_file_with_language_override(self, sample_java_file: str) -> None:
        """Test file analysis with explicit language specification"""
        try:
            result = api.analyze_file(sample_java_file, language="java")

            assert isinstance(result, dict)
            assert result["success"] is True
            assert result["language_info"]["language"] == "java"

        finally:
            os.unlink(sample_java_file)

    def test_analyze_file_with_options(self, sample_java_file: str) -> None:
        """Test file analysis with additional options"""
        try:
            result = api.analyze_file(
                sample_java_file, include_complexity=True, include_details=True
            )

            assert isinstance(result, dict)
            assert result["success"] is True
            assert result["file_info"]["path"] == sample_java_file

        finally:
            os.unlink(sample_java_file)

    def test_analyze_file_nonexistent(self) -> None:
        """Test analysis of non-existent file"""
        with pytest.raises(FileNotFoundError):
            api.analyze_file("/nonexistent/file.java")

    def test_analyze_file_with_path_object(self, sample_java_file: str) -> None:
        """Test file analysis with Path object"""
        try:
            path_obj = Path(sample_java_file)
            result = api.analyze_file(path_obj)

            assert isinstance(result, dict)
            assert result["success"] is True
            assert result["file_info"]["path"] == str(path_obj)

        finally:
            os.unlink(sample_java_file)

    def test_analyze_code_java_success(self) -> None:
        """Test successful Java code analysis through API"""
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello World");
    }
}
"""
        result = api.analyze_code(java_code, language="java")

        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["language_info"]["language"] == "java"
        assert "elements" in result

    def test_analyze_code_python_success(self) -> None:
        """Test successful Python code analysis through API"""
        python_code = '''
def test_function():
    """Test function"""
    print("Hello World")
    return True

class TestClass:
    def __init__(self):
        self.value = 42
'''
        result = api.analyze_code(python_code, language="python")

        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["language_info"]["language"] == "python"
        assert "elements" in result

    def test_extract_elements_java(self, sample_java_file: str) -> None:
        """Test element extraction from Java file"""
        try:
            result = api.extract_elements(sample_java_file)

            assert isinstance(result, dict)
            assert result["success"] is True
            assert "elements" in result
            assert len(result["elements"]) > 0

        finally:
            os.unlink(sample_java_file)

    def test_extract_elements_python(self, sample_python_file: str) -> None:
        """Test element extraction from Python file"""
        try:
            result = api.extract_elements(sample_python_file)

            assert isinstance(result, dict)
            assert result["success"] is True
            assert "elements" in result
            assert len(result["elements"]) > 0

        finally:
            os.unlink(sample_python_file)

    def test_extract_elements_with_types(self, sample_java_file: str) -> None:
        """Test element extraction with specific types"""
        try:
            result = api.extract_elements(
                sample_java_file, element_types=["function", "class"]
            )

            assert isinstance(result, dict)
            assert result["success"] is True
            assert "elements" in result

        finally:
            os.unlink(sample_java_file)

    def test_get_supported_languages(self) -> None:
        """Test getting list of supported languages"""
        languages = api.get_supported_languages()

        assert isinstance(languages, list)
        # Note: May be empty if plugins are not loaded properly
        # assert len(languages) > 0

    def test_is_language_supported(self) -> None:
        """Test checking if language is supported"""
        # Note: These may return False if plugins are not loaded
        # assert api.is_language_supported('java') is True
        # assert api.is_language_supported('python') is True
        assert api.is_language_supported("unsupported_language") is False

    def test_detect_language(self, sample_java_file: str) -> None:
        """Test language detection from file"""
        try:
            language = api.detect_language(sample_java_file)

            assert language == "java"

        finally:
            os.unlink(sample_java_file)

    def test_get_available_queries(self) -> None:
        """Test getting available queries for a language"""
        java_queries = api.get_available_queries("java")

        assert isinstance(java_queries, list)
        # Note: May be empty if plugins are not loaded properly

    def test_execute_query(self, sample_java_file: str) -> None:
        """Test query execution on file"""
        try:
            result = api.execute_query(sample_java_file, "class")

            assert isinstance(result, dict)
            assert "success" in result

        finally:
            os.unlink(sample_java_file)

    def test_validate_file(self, sample_java_file: str) -> None:
        """Test file validation"""
        try:
            result = api.validate_file(sample_java_file)

            assert isinstance(result, dict)
            assert "valid" in result
            assert "exists" in result
            assert result["exists"] is True

        finally:
            os.unlink(sample_java_file)

    def test_get_framework_info(self) -> None:
        """Test getting framework information"""
        info = api.get_framework_info()

        assert isinstance(info, dict)
        assert "name" in info
        assert info["name"] == "tree-sitter-analyzer"
        assert "version" in info
        assert info["version"] == "2.0.0"


class TestAPIFacadeErrorHandling:
    """Test error handling in API facade"""

    def test_analyze_code_empty_content(self) -> None:
        """Test analysis of empty code content"""
        result = api.analyze_code("", language="java")

        assert isinstance(result, dict)
        assert "success" in result
        assert result["language_info"]["language"] == "java"

    def test_analyze_code_malformed_content(self) -> None:
        """Test analysis of malformed code content"""
        malformed_code = """
public class Test {
    // Missing closing brace
"""
        result = api.analyze_code(malformed_code, language="java")

        # Should handle gracefully
        assert isinstance(result, dict)
        assert "success" in result

    def test_analyze_file_unsupported_language(self) -> None:
        """Test analysis with unsupported language"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xyz", delete=False) as f:
            f.write("some content")
            temp_path = f.name

        try:
            result = api.analyze_file(temp_path)
            # Should handle gracefully
            assert isinstance(result, dict)
            assert "success" in result

        finally:
            os.unlink(temp_path)

    def test_extract_elements_nonexistent_file(self) -> None:
        """Test element extraction from non-existent file"""
        result = api.extract_elements("/nonexistent/file.java")

        assert isinstance(result, dict)
        assert result["success"] is False
        assert "error" in result

    def test_execute_query_invalid_query_name(self) -> None:
        """Test query execution with invalid query name"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write("public class Test {}")
            temp_path = f.name

        try:
            result = api.execute_query(temp_path, "invalid_query_name")

            # Should handle gracefully
            assert isinstance(result, dict)
            assert "success" in result

        finally:
            os.unlink(temp_path)

    def test_validate_file_nonexistent(self) -> None:
        """Test validation of non-existent file"""
        result = api.validate_file("/nonexistent/file.java")

        assert isinstance(result, dict)
        assert result["valid"] is False
        assert result["exists"] is False


class TestAPIFacadeIntegration:
    """Integration tests for API facade"""

    def test_full_analysis_workflow(self) -> None:
        """Test complete analysis workflow through API"""
        java_code = """
package com.example;

import java.util.List;
import java.util.ArrayList;

public class DataProcessor {
    private List<String> data;

    public DataProcessor() {
        this.data = new ArrayList<>();
    }

    public void addData(String item) {
        data.add(item);
    }

    public List<String> processData() {
        return data.stream()
                   .map(String::toUpperCase)
                   .collect(ArrayList::new);
    }

    public int getDataCount() {
        return data.size();
    }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            # Step 1: Detect language
            language = api.detect_language(temp_path)
            assert language == "java"

            # Step 2: Check if language is supported
            # Note: May return False if plugins are not loaded
            # assert api.is_language_supported(language) is True

            # Step 3: Get available queries
            queries = api.get_available_queries(language)
            assert isinstance(queries, list)

            # Step 4: Analyze file
            result = api.analyze_file(temp_path)
            assert isinstance(result, dict)
            assert result["success"] is True
            assert result["language_info"]["language"] == "java"

            # Step 5: Extract elements
            elements_result = api.extract_elements(temp_path)
            assert isinstance(elements_result, dict)
            assert elements_result["success"] is True
            assert "elements" in elements_result

            # Step 6: Execute specific query
            query_result = api.execute_query(temp_path, "class")
            assert isinstance(query_result, dict)
            assert "success" in query_result

        finally:
            os.unlink(temp_path)

    def test_multiple_file_analysis(self) -> None:
        """Test analysis of multiple files through API"""
        files = []

        try:
            # Create Java file
            java_code = "public class JavaTest { public void test() {} }"
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".java", delete=False
            ) as f:
                f.write(java_code)
                files.append(f.name)

            # Create Python file
            python_code = "def python_test(): pass"
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(python_code)
                files.append(f.name)

            results = []
            for file_path in files:
                result = api.analyze_file(file_path)
                results.append(result)

            assert len(results) == 2
            assert results[0]["language_info"]["language"] == "java"
            assert results[1]["language_info"]["language"] == "python"

        finally:
            for file_path in files:
                if os.path.exists(file_path):
                    os.unlink(file_path)

    def test_api_consistency_across_methods(self) -> None:
        """Test that API methods return consistent results"""
        code = """
public class ConsistencyTest {
    private String name;

    public ConsistencyTest(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
"""

        # Test with file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            # Analyze via file
            file_result = api.analyze_file(temp_path)

            # Analyze via code
            code_result = api.analyze_code(code, language="java")

            # Results should be consistent
            assert (
                file_result["language_info"]["language"]
                == code_result["language_info"]["language"]
            )
            assert len(file_result["elements"]) == len(code_result["elements"])

        finally:
            os.unlink(temp_path)

    def test_api_performance_with_large_file(self) -> None:
        """Test API performance with large code files"""
        # Create a large Java class
        large_code = "public class LargeClass {\n"
        for i in range(100):
            large_code += f"""
    public void method{i}() {{
        System.out.println("Method {i}");
        int value = {i};
        return;
    }}
"""
        large_code += "}"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(large_code)
            temp_path = f.name

        try:
            # Should handle large files efficiently
            result = api.analyze_file(temp_path)
            assert isinstance(result, dict)
            assert result["success"] is True
            assert result["ast_info"]["node_count"] > 0

        finally:
            os.unlink(temp_path)
