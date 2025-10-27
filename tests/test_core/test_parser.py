#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.core.parser module.

This module tests the Parser class which handles Tree-sitter parsing
operations in the new architecture.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.core.parser import Parser, ParseResult


class TestParser:
    """Test cases for Parser class"""

    @pytest.fixture
    def parser(self) -> Parser:
        """Create a Parser instance for testing"""
        return Parser()

    @pytest.fixture
    def sample_java_file(self) -> str:
        """Create a temporary Java file for testing"""
        content = """
public class TestClass {
    private String name;

    public TestClass(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(content)
            return f.name

    @pytest.fixture
    def sample_python_file(self) -> str:
        """Create a temporary Python file for testing"""
        content = """
class TestClass:
    def __init__(self, name: str):
        self.name = name

    def get_name(self) -> str:
        return self.name
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            return f.name

    def test_parser_initialization(self, parser: Parser) -> None:
        """Test Parser initialization"""
        assert parser is not None
        assert hasattr(parser, "parse_file")
        assert hasattr(parser, "parse_code")

    def test_parse_file_java_success(
        self, parser: Parser, sample_java_file: str
    ) -> None:
        """Test successful Java file parsing"""
        try:
            result = parser.parse_file(sample_java_file, "java")

            assert isinstance(result, ParseResult)
            assert result.tree is not None
            assert result.source_code is not None
            assert result.language == "java"
            assert result.file_path == sample_java_file
            assert result.success is True
            assert result.error_message is None

        finally:
            os.unlink(sample_java_file)

    def test_parse_file_python_success(
        self, parser: Parser, sample_python_file: str
    ) -> None:
        """Test successful Python file parsing"""
        try:
            result = parser.parse_file(sample_python_file, "python")

            assert isinstance(result, ParseResult)
            assert result.tree is not None
            assert result.source_code is not None
            assert result.language == "python"
            assert result.file_path == sample_python_file
            assert result.success is True

        finally:
            os.unlink(sample_python_file)

    def test_parse_file_with_path_object(
        self, parser: Parser, sample_java_file: str
    ) -> None:
        """Test file parsing with Path object"""
        try:
            path_obj = Path(sample_java_file)
            result = parser.parse_file(path_obj, "java")

            assert isinstance(result, ParseResult)
            assert result.success is True
            assert result.file_path == str(path_obj)

        finally:
            os.unlink(sample_java_file)

    def test_parse_file_nonexistent(self, parser: Parser) -> None:
        """Test parsing of non-existent file"""
        result = parser.parse_file("/nonexistent/file.java", "java")

        assert isinstance(result, ParseResult)
        assert result.success is False
        assert result.tree is None
        assert result.error_message is not None
        assert (
            "not found" in result.error_message.lower()
            or "no such file" in result.error_message.lower()
        )

    def test_parse_file_unsupported_language(
        self, parser: Parser, sample_java_file: str
    ) -> None:
        """Test parsing with unsupported language"""
        try:
            result = parser.parse_file(sample_java_file, "unsupported_language")

            assert isinstance(result, ParseResult)
            assert result.success is False
            assert result.error_message is not None

        finally:
            os.unlink(sample_java_file)

    def test_parse_code_java_success(self, parser: Parser) -> None:
        """Test successful Java code parsing"""
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello");
    }
}
"""
        result = parser.parse_code(java_code, "java")

        assert isinstance(result, ParseResult)
        assert result.tree is not None
        assert result.source_code == java_code
        assert result.language == "java"
        assert result.success is True

    def test_parse_code_python_success(self, parser: Parser) -> None:
        """Test successful Python code parsing"""
        python_code = """
def test_function():
    print("Hello")
    return True
"""
        result = parser.parse_code(python_code, "python")

        assert isinstance(result, ParseResult)
        assert result.tree is not None
        assert result.source_code == python_code
        assert result.language == "python"
        assert result.success is True

    def test_parse_code_with_filename(self, parser: Parser) -> None:
        """Test code parsing with filename"""
        code = "def test(): pass"
        result = parser.parse_code(code, "python", filename="test.py")

        assert isinstance(result, ParseResult)
        assert result.file_path == "test.py"

    def test_parse_code_empty_content(self, parser: Parser) -> None:
        """Test parsing of empty code content"""
        result = parser.parse_code("", "java")

        assert isinstance(result, ParseResult)
        assert result.source_code == ""
        # Empty content should still parse successfully
        assert result.success is True

    def test_parse_code_malformed_content(self, parser: Parser) -> None:
        """Test parsing of malformed code content"""
        malformed_java = """
public class Test {
    // Missing closing brace
"""
        result = parser.parse_code(malformed_java, "java")

        # Should still parse but may have errors in the tree
        assert isinstance(result, ParseResult)
        assert result.tree is not None
        assert result.success is True

    def test_is_language_supported(self, parser: Parser) -> None:
        """Test language support checking"""
        assert parser.is_language_supported("java") is True
        assert parser.is_language_supported("python") is True
        assert parser.is_language_supported("cpp") is True
        assert parser.is_language_supported("javascript") is False  # Not currently supported
        assert parser.is_language_supported("unsupported_language") is False

    def test_get_supported_languages(self, parser: Parser) -> None:
        """Test getting list of supported languages"""
        languages = parser.get_supported_languages()

        assert isinstance(languages, list)
        assert len(languages) > 0
        assert "java" in languages
        assert "python" in languages

    def test_validate_ast_valid_tree(self, parser: Parser) -> None:
        """Test AST validation with valid tree"""
        code = "public class Test {}"
        result = parser.parse_code(code, "java")

        if result.success and result.tree:
            is_valid = parser.validate_ast(result.tree)
            assert isinstance(is_valid, bool)

    def test_validate_ast_none_tree(self, parser: Parser) -> None:
        """Test AST validation with None tree"""
        is_valid = parser.validate_ast(None)
        assert is_valid is False

    def test_get_parse_errors(self, parser: Parser) -> None:
        """Test getting parse errors from tree"""
        # Parse malformed code that should have errors
        malformed_code = """
public class Test {
    public void method( {
        // Missing closing parenthesis
    }
"""
        result = parser.parse_code(malformed_code, "java")

        if result.success and result.tree:
            errors = parser.get_parse_errors(result.tree)
            assert isinstance(errors, list)


class TestParserErrorHandling:
    """Test error handling in Parser"""

    @pytest.fixture
    def parser(self) -> Parser:
        """Create a Parser instance for testing"""
        return Parser()

    @patch("pathlib.Path.exists")
    @patch("tree_sitter_analyzer.core.parser.EncodingManager.read_file_safe")
    def test_parse_file_permission_error(
        self, mock_read_safe: Mock, mock_exists: Mock, parser: Parser
    ) -> None:
        """Test handling of file permission errors using mocks."""
        # Mock Path.exists() to return True, bypassing the file existence check
        mock_exists.return_value = True
        # Configure the mock to raise a PermissionError
        mock_read_safe.side_effect = PermissionError("Mocked permission denied")

        # Create a dummy file path for the test.
        dummy_path = "non_existent_dir/non_existent_file.java"

        # Execute the method
        result = parser.parse_file(dummy_path, "java")

        # Assert that the failure was handled correctly
        assert (
            result.success is False
        ), "Expected success to be False on PermissionError"
        assert result.error_message is not None, "Expected an error message on failure"
        assert (
            "permission denied" in result.error_message.lower()
        ), "Error message should indicate a permission issue"

    def test_parse_file_encoding_error(self, parser: Parser) -> None:
        """Test handling of file encoding errors"""
        # Create file with invalid UTF-8 bytes
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".java", delete=False) as f:
            f.write(b"public class Test { \xff\xfe }")  # Invalid UTF-8
            temp_path = f.name

        try:
            result = parser.parse_file(temp_path, "java")
            # Should handle encoding errors gracefully
            assert isinstance(result, ParseResult)

        finally:
            os.unlink(temp_path)

    @patch("tree_sitter_analyzer.core.parser.loader.create_parser_safely")
    def test_parse_code_parser_creation_failure(
        self, mock_create_parser: Mock, parser: Parser
    ) -> None:
        """Test handling of parser creation failure"""
        mock_create_parser.return_value = None

        result = parser.parse_code("test code", "java")

        assert isinstance(result, ParseResult)
        assert result.success is False
        assert result.error_message is not None

    def test_parse_code_with_unicode(self, parser: Parser) -> None:
        """Test parsing code with Unicode characters"""
        unicode_code = """
public class Test {
    // Comment with Unicode: English
    String message = "Hello World";
}
"""
        result = parser.parse_code(unicode_code, "java")

        assert isinstance(result, ParseResult)
        assert result.success is True
        assert result.source_code == unicode_code

    def test_parse_very_large_file(self, parser: Parser) -> None:
        """Test parsing of very large code content"""
        # Create a large code string
        large_code = "public class Test {\n"
        for i in range(1000):
            large_code += f"    public void method{i}() {{ }}\n"
        large_code += "}"

        result = parser.parse_code(large_code, "java")

        assert isinstance(result, ParseResult)
        # Should handle large content
        assert result.success is True


class TestParserIntegration:
    """Integration tests for Parser"""

    @pytest.fixture
    def parser(self) -> Parser:
        """Create a Parser instance for testing"""
        return Parser()

    def test_parse_multiple_languages(self, parser: Parser) -> None:
        """Test parsing multiple different languages"""
        test_cases = [
            ("public class Test {}", "java"),
            ("def test(): pass", "python"),
            ("function test() {}", "javascript"),
            ("fn test() {}", "rust"),
        ]

        for code, language in test_cases:
            if parser.is_language_supported(language):
                result = parser.parse_code(code, language)
                assert isinstance(result, ParseResult)
                assert result.language == language

    def test_parse_complex_java_file(self, parser: Parser) -> None:
        """Test parsing complex Java file"""
        complex_java = """
package com.example.test;

import java.util.*;
import java.io.*;

/**
 * Complex test class with various Java features
 */
public class ComplexTest extends BaseClass implements TestInterface {
    private static final String CONSTANT = "test";
    private List<String> items = new ArrayList<>();

    public ComplexTest() {
        super();
    }

    @Override
    public void interfaceMethod() {
        // Implementation
    }

    public <T> T genericMethod(T input) {
        return input;
    }

    public static void main(String[] args) {
        ComplexTest test = new ComplexTest();
        test.interfaceMethod();
    }

    private class InnerClass {
        void innerMethod() {}
    }
}
"""
        result = parser.parse_code(complex_java, "java")

        assert isinstance(result, ParseResult)
        assert result.success is True
        assert result.tree is not None

        # Validate the tree structure
        is_valid = parser.validate_ast(result.tree)
        assert is_valid is True

    def test_parse_complex_python_file(self, parser: Parser) -> None:
        """Test parsing complex Python file"""
        complex_python = '''
#!/usr/bin/env python3
"""
Complex Python module with various features
"""

import os
import sys
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class DataClass:
    name: str
    value: int = 0

class BaseClass(ABC):
    @abstractmethod
    def abstract_method(self) -> None:
        pass

class ComplexClass(BaseClass):
    def __init__(self, name: str):
        self.name = name
        self._private_attr = "private"

    @property
    def name_property(self) -> str:
        return self.name

    @staticmethod
    def static_method() -> str:
        return "static"

    @classmethod
    def class_method(cls) -> 'ComplexClass':
        return cls("default")

    def abstract_method(self) -> None:
        print(f"Implementation for {self.name}")

    async def async_method(self) -> None:
        await asyncio.sleep(1)

def function_with_decorators():
    @decorator
    def inner_function():
        pass
    return inner_function

if __name__ == "__main__":
    obj = ComplexClass("test")
    obj.abstract_method()
'''
        result = parser.parse_code(complex_python, "python")

        assert isinstance(result, ParseResult)
        assert result.success is True
        assert result.tree is not None

    def test_parse_result_namedtuple_properties(self, parser: Parser) -> None:
        """Test ParseResult NamedTuple properties"""
        code = "public class Test {}"
        result = parser.parse_code(code, "java")

        # Test NamedTuple properties
        assert hasattr(result, "tree")
        assert hasattr(result, "source_code")
        assert hasattr(result, "language")
        assert hasattr(result, "file_path")
        assert hasattr(result, "success")
        assert hasattr(result, "error_message")

        # Test immutability (NamedTuple should be immutable)
        with pytest.raises(AttributeError):
            result.language = "python"  # Should raise AttributeError
