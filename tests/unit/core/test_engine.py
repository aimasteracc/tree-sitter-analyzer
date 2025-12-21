#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.core.engine module.
"""

import os
import tempfile

import pytest

from tree_sitter_analyzer.core import AnalysisEngine
from tree_sitter_analyzer.models import AnalysisResult


@pytest.fixture
def engine():
    """Fixture to provide an AnalysisEngine instance."""
    return AnalysisEngine()


class TestAnalysisEngine:
    """Test cases for the core AnalysisEngine."""

    def test_initialization(self, engine):
        """Test that the AnalysisEngine initializes correctly."""
        assert engine.parser is not None
        assert engine.query_executor is not None
        assert engine.language_detector is not None
        assert engine.plugin_manager is not None

    def test_analyze_java_file(self, engine):
        """Test analyzing a simple Java file."""
        java_code = """
        package com.example;
        public class MyClass {
            public void myMethod() {
                System.out.println("Hello");
            }
        }
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_file = f.name

        try:
            result = engine.analyze_file(temp_file)
            assert isinstance(result, AnalysisResult)
            assert result.success
            assert result.language == "java"
            assert result.file_path == temp_file
            assert len(result.elements) > 0
        finally:
            os.unlink(temp_file)

    def test_analyze_python_code(self, engine):
        """Test analyzing a Python code string."""
        python_code = """
import os

def greet(name):
    print(f"Hello, {name}")

class Greeter:
    def __init__(self, greeting):
        self.greeting = greeting

    def greet(self, name):
        return f"{self.greeting}, {name}"
"""
        result = engine.analyze_code(python_code, language="python")
        assert isinstance(result, AnalysisResult)
        assert result.success
        assert result.language == "python"
        assert result.file_path == ""  # 新しいアーキテクチャでは空文字列
        assert len(result.elements) > 0

        element_types = [elem.element_type for elem in result.elements]
        assert "import" in element_types
        assert "function" in element_types
        assert "class" in element_types

    def test_analyze_nonexistent_file(self, engine):
        """Test analysis of a file that does not exist."""
        with pytest.raises(FileNotFoundError):
            engine.analyze_file("nonexistent_file.java")

    def test_analyze_unsupported_language(self, engine):
        """Test analysis with an unsupported language."""
        code = "let x = 1;"
        # This should not raise an error, but return a result with success=False
        result = engine.analyze_code(code, language="unsupportedlang")
        assert not result.success
        assert "Unsupported language" in result.error_message

    def test_language_detection(self, engine):
        """Test automatic language detection from file extension."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("print('hello')")
            temp_file = f.name

        try:
            result = engine.analyze_file(temp_file)
            assert result.language == "python"
        finally:
            os.unlink(temp_file)

    def test_malformed_code_handling(self, engine):
        """Test that the engine handles malformed code gracefully."""
        malformed_code = "public class MyClass { void myMethod() { "
        result = engine.analyze_code(malformed_code, language="java")
        # Parsing might partially succeed or fail gracefully
        assert isinstance(result, AnalysisResult)
        # Depending on the severity, it might be a success with errors or a failure
        # For now, we just check it doesn't crash

    def test_get_supported_languages(self, engine):
        """Test retrieving the list of supported languages."""
        supported_languages = engine.get_supported_languages()
        assert isinstance(supported_languages, list)
        assert "java" in supported_languages
        assert "python" in supported_languages


if __name__ == "__main__":
    pytest.main([__file__])
