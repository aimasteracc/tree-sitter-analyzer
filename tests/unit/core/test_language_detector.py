#!/usr/bin/env python3
"""
Tests for language_detector module
"""

import sys

# Add project root to path
sys.path.insert(0, ".")

import os
import tempfile

from tree_sitter_analyzer.language_detector import (
    detect_language_from_file,
    detector,
    is_language_supported,
)


def test_detect_from_extension_java():
    """Test Java file detection"""
    assert detector.detect_from_extension("Test.java") == "java"
    assert detector.detect_from_extension("package/Test.java") == "java"


def test_detect_from_extension_javascript():
    """Test JavaScript file detection"""
    assert detector.detect_from_extension("script.js") == "javascript"
    assert detector.detect_from_extension("src/script.js") == "javascript"


def test_detect_from_extension_python():
    """Test Python file detection"""
    assert detector.detect_from_extension("main.py") == "python"
    assert detector.detect_from_extension("src/main.py") == "python"


def test_detect_from_extension_typescript():
    """Test TypeScript file detection"""
    assert detector.detect_from_extension("app.ts") == "typescript"
    assert detector.detect_from_extension("src/app.ts") == "typescript"


def test_detect_from_extension_unknown():
    """Test unknown extension handling"""
    assert detector.detect_from_extension("file.xyz") == "unknown"
    assert detector.detect_from_extension("file.unknown") == "unknown"


def test_detect_language_with_content():
    """Test language detection using content analysis"""
    # Create temp files with specific content
    java_content = """
    public class TestClass {
        public static void main(String[] args) {
            System.out.println("Hello");
        }
    }
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
        f.write(java_content)
        temp_file = f.name

    try:
        language, confidence = detector.detect_language(temp_file, java_content)
        assert language == "java"
        assert confidence > 0.0
    finally:
        os.unlink(temp_file)


def test_detect_from_file_with_temp_files():
    """Test file detection with temporary files"""
    # Test Java file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
        f.write("public class Test {}")
        java_file = f.name

    try:
        assert detect_language_from_file(java_file) == "java"
    finally:
        os.unlink(java_file)

    # Test JavaScript file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write("function test() {}")
        js_file = f.name

    try:
        assert detect_language_from_file(js_file) == "javascript"
    finally:
        os.unlink(js_file)


def test_is_language_supported():
    """Test language support checking"""
    assert is_language_supported("java")
    assert is_language_supported("javascript")
    assert is_language_supported("python")
    assert is_language_supported("typescript")
    assert not is_language_supported("unknown_lang")


def test_detector_methods():
    """Test detector instance methods"""
    supported_langs = detector.get_supported_languages()
    assert "java" in supported_langs
    assert "javascript" in supported_langs
    assert "python" in supported_langs

    extensions = detector.get_supported_extensions()
    assert ".java" in extensions
    assert ".js" in extensions
    assert ".py" in extensions


def test_detector_content_heuristics():
    """Test content-based heuristics with detect_language method"""
    # Test TypeScript content detection
    ts_content = """
    interface User {
        name: string;
        age: number;
    }
    function greet(user: User): string {
        return `Hello ${user.name}`;
    }
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
        f.write(ts_content)
        temp_file = f.name

    try:
        language, confidence = detector.detect_language(temp_file, ts_content)
        assert language == "typescript"
    finally:
        os.unlink(temp_file)


def test_ambiguous_extensions():
    """Test handling of ambiguous file extensions"""
    # .h files could be C or C++
    result = detector.detect_from_extension("header.h")
    assert result in ["c", "cpp", "unknown"]  # Implementation dependent

    # .m files could be Objective-C or MATLAB
    result = detector.detect_from_extension("file.m")
    assert result in ["objc", "matlab", "unknown"]  # Implementation dependent
