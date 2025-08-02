#!/usr/bin/env python3
"""
Tests for Java Code Analyzer
"""

import sys

# Add project root to path
sys.path.insert(0, ".")

import os
import tempfile

import pytest

from tree_sitter_analyzer.java_analyzer import CodeAnalyzer
from tree_sitter_analyzer.query_loader import get_query


@pytest.fixture
def analyzer():
    """Set up test fixtures before each test method."""
    return CodeAnalyzer()


def create_temp_java_file(content: str) -> str:
    """Create a temporary Java file with given content."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".java", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        return f.name


def test_analyzer_initialization(analyzer):
    """Test that analyzer initializes correctly."""
    assert analyzer is not None
    assert analyzer.language is not None
    assert analyzer.parser is not None


def test_parse_simple_java_class(analyzer):
    """Test parsing a simple Java class."""
    java_content = """
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
    temp_file = create_temp_java_file(java_content)
    try:
        result = analyzer.parse_file(temp_file)
        assert result is True
        assert analyzer.tree is not None
    finally:
        os.unlink(temp_file)


def test_execute_class_query(analyzer):
    """Test executing a class query."""
    java_content = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello");
    }
}
"""
    temp_file = create_temp_java_file(java_content)
    try:
        analyzer.parse_file(temp_file)
        results = analyzer.execute_query(get_query("java", "class"))
        assert len(results) == 1
        assert results[0]["capture_name"] == "class"
        assert "TestClass" in results[0]["content"]
    finally:
        os.unlink(temp_file)


def test_execute_method_query(analyzer):
    """Test executing a method query."""
    java_content = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello");
    }

    private int getNumber() {
        return 42;
    }
}
"""
    temp_file = create_temp_java_file(java_content)
    try:
        analyzer.parse_file(temp_file)
        results = analyzer.execute_query(get_query("java", "method"))
        assert len(results) == 2
        method_names = [result["content"] for result in results]
        assert any("testMethod" in name for name in method_names)
        assert any("getNumber" in name for name in method_names)
    finally:
        os.unlink(temp_file)


def test_parse_nonexistent_file(analyzer):
    """Test parsing a non-existent file."""
    result = analyzer.parse_file("nonexistent_file.java")
    assert result is False


def test_execute_query_without_parsing(analyzer):
    """Test executing query without parsing a file first."""
    results = analyzer.execute_query(get_query("java", "class"))
    assert results == []
