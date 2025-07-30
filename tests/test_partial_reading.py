#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for partial file reading functionality
"""

import os
import sys
import tempfile
import pytest
import pytest_asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, ".")

from tree_sitter_analyzer.file_handler import read_file_lines_range, read_file_partial


@pytest.fixture
def test_file():
    """Create a test Java file for testing"""
    content = """public class TestClass {
    private String name;
    private int age;
    
    public TestClass(String name, int age) {
        this.name = name;
        this.age = age;
    }
    
    public String getName() {
        return name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
    
    public int getAge() {
        return age;
    }
    
    public void setAge(int age) {
        this.age = age;
    }
    
    @Override
    public String toString() {
        return "TestClass{name='" + name + "', age=" + age + "}";
    }
}"""

    # Create temporary file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".java", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        file_path = f.name

    yield file_path

    # Cleanup
    if os.path.exists(file_path):
        os.unlink(file_path)


@pytest.fixture
def empty_file():
    """Create an empty test file"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        file_path = f.name

    yield file_path

    # Cleanup
    if os.path.exists(file_path):
        os.unlink(file_path)


@pytest.fixture
def single_line_file():
    """Create a single line test file"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write("Single line content")
        file_path = f.name

    yield file_path

    # Cleanup
    if os.path.exists(file_path):
        os.unlink(file_path)


@pytest.fixture
def cli_test_file():
    """Create a test file for CLI integration tests"""
    content = """public class CLITestClass {
    public void method1() {
        System.out.println("Method 1");
    }
    
    public void method2() {
        System.out.println("Method 2");
    }
}"""

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".java", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        file_path = f.name

    yield file_path

    # Cleanup
    if os.path.exists(file_path):
        os.unlink(file_path)


def test_read_line_range_1_to_5(test_file):
    """Test reading lines 1-5"""
    result = read_file_partial(test_file, 1, 5)

    assert result is not None
    assert "public class TestClass" in result
    assert "private String name" in result
    assert "private int age" in result
    assert "public TestClass(String name, int age)" in result
    assert len(result) == 121


def test_read_single_line_5(test_file):
    """Test reading single line (line 5)"""
    result = read_file_partial(test_file, 5, 5)

    assert result is not None
    assert "public TestClass(String name, int age)" in result
    assert len(result) == 45


def test_read_column_range_line_1_cols_5_to_15(test_file):
    """Test reading columns 5-15 of line 1"""
    result = read_file_partial(test_file, 1, 1, 5, 15)

    assert result is not None
    assert result == "c class Te"
    assert len(result) == 10


def test_read_from_line_10_to_end(test_file):
    """Test reading from line 10 to end of file"""
    result = read_file_partial(test_file, 10)

    assert result is not None
    lines = result.split("\n")
    assert len(lines) > 15  # Should have multiple lines
    assert "public String getName()" in result
    assert "return name" in result
    assert len(result) == 382


def test_read_file_lines_range_function(test_file):
    """Test read_file_lines_range function (lines 2-4)"""
    result = read_file_lines_range(test_file, 2, 4)

    assert result is not None
    assert "private String name" in result
    assert "private int age" in result
    assert len(result) == 51


def test_invalid_start_line_zero(test_file):
    """Test error case with invalid start line (0)"""
    result = read_file_partial(test_file, 0, 5)

    assert result is None


def test_invalid_range_end_before_start(test_file):
    """Test error case with invalid range (end < start)"""
    result = read_file_partial(test_file, 10, 5)

    assert result is None


def test_nonexistent_file():
    """Test reading from nonexistent file"""
    result = read_file_partial("/path/that/does/not/exist.java", 1, 5)

    assert result is None


def test_read_beyond_file_end(test_file):
    """Test reading beyond file end"""
    result = read_file_partial(test_file, 100, 200)

    # Should return None or empty string for lines beyond file end
    assert result is None or result == ""


def test_read_file_lines_range_invalid_range(test_file):
    """Test read_file_lines_range with invalid range"""
    result = read_file_lines_range(test_file, 10, 5)

    assert result is None


def test_read_file_lines_range_nonexistent_file():
    """Test read_file_lines_range with nonexistent file"""
    result = read_file_lines_range("/path/that/does/not/exist.java", 1, 5)

    assert result is None


# Edge cases tests
def test_read_empty_file(empty_file):
    """Test reading from empty file"""
    result = read_file_partial(empty_file, 1, 1)

    assert result is None or result == ""


def test_read_single_line_file(single_line_file):
    """Test reading from single line file"""
    result = read_file_partial(single_line_file, 1, 1)

    assert result is not None
    assert result.strip() == "Single line content"


def test_read_beyond_single_line(single_line_file):
    """Test reading beyond single line file"""
    result = read_file_partial(single_line_file, 2, 5)

    assert result is None or result == ""


def test_column_range_beyond_line_length(single_line_file):
    """Test column range beyond line length"""
    result = read_file_partial(single_line_file, 1, 1, 50, 100)

    # Should handle gracefully, might return empty or partial content
    assert result is None or isinstance(result, str)


# CLI integration tests
def test_cli_compatible_line_range_reading(cli_test_file):
    """Test that partial reading works for CLI scenarios"""
    # Test various scenarios that CLI might use

    # Read first few lines
    result1 = read_file_partial(cli_test_file, 1, 3)
    assert result1 is not None
    assert "public class CLITestClass" in result1

    # Read middle section
    result2 = read_file_partial(cli_test_file, 2, 4)
    assert result2 is not None
    assert "public void method1()" in result2

    # Read from specific line to end
    result3 = read_file_partial(cli_test_file, 5)
    assert result3 is not None
    assert "public void method2()" in result3


def test_cli_error_handling_scenarios(cli_test_file):
    """Test error handling scenarios that CLI might encounter"""

    # Invalid line numbers
    assert read_file_partial(cli_test_file, 0, 1) is None
    assert read_file_partial(cli_test_file, -1, 5) is None

    # Invalid ranges
    assert read_file_partial(cli_test_file, 5, 2) is None

    # Nonexistent file
    assert read_file_partial("nonexistent.java", 1, 5) is None
