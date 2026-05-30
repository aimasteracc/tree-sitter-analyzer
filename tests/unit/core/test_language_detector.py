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


def test_detect_language_non_string_path():
    assert detector.detect_language(None) == ("unknown", 0.0)
    assert detector.detect_language(123) == ("unknown", 0.0)


def test_detect_from_extension_empty_and_none():
    assert detector.detect_from_extension("") == "unknown"
    assert detector.detect_from_extension(None) == "unknown"
    assert detector.detect_from_extension(42) == "unknown"


def test_detect_language_h_extension_map_overrides_ambiguity():
    # .h is in extension_map with ("c", 0.7), so extension_map wins
    lang, conf = detector.detect_language("header.h")
    assert lang == "c"
    assert conf == 0.7


def test_resolve_ambiguity_h_no_match():
    result = detector._resolve_ambiguity(".h", "/* plain comment */")
    assert result in ("c", "cpp", "objc")


def test_detect_language_m_extension_map_returns_objc():
    lang, conf = detector.detect_language("file.m")
    assert lang == "objc"
    assert conf == 0.7


def test_resolve_ambiguity_m_objc_content():
    objc_content = "#import <UIKit/UIKit.h>\n@interface MyView : UIView @end"
    result = detector._resolve_ambiguity(".m", objc_content)
    assert result == "objc"


def test_resolve_ambiguity_m_matlab_content():
    matlab_content = "function result = add(a, b)\n  disp(a+b);\nend;"
    result = detector._resolve_ambiguity(".m", matlab_content)
    assert result == "matlab"


def test_resolve_ambiguity_m_tie_falls_to_first_candidate():
    result = detector._resolve_ambiguity(".m", "blah blah")
    assert result == "objc"


def test_detect_language_sql_ambiguous_with_content():
    lang, conf = detector.detect_language("query.sql", "SELECT * FROM users;")
    assert lang == "sql"


def test_detect_language_sql_without_content():
    lang, conf = detector.detect_language("query.sql")
    assert lang == "sql"
    assert conf >= 0.7


def test_resolve_ambiguity_non_ambiguous_extension():
    result = detector._resolve_ambiguity(".java", "class Foo {}")
    assert result == "java"


def test_detect_language_unknown_extension_returns_unknown():
    assert detector.detect_language("file.xyz123") == ("unknown", 0.0)


def test_detect_language_from_file_nonexistent():
    result = detect_language_from_file("/nonexistent/path/to/file.java")
    assert result == "java"


def test_detect_language_from_file_relative_with_project_root():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("print('hello')")
        tmp = f.name
    try:
        import os

        result = detect_language_from_file(
            os.path.basename(tmp), project_root=os.path.dirname(tmp)
        )
        assert result == "python"
    finally:
        os.unlink(tmp)


def test_is_supported_unknown_language():
    assert not detector.is_supported("brainfuck")
    assert not detector.is_supported("")


def test_add_extension_mapping():
    detector.add_extension_mapping(".zig", "zig")
    lang, conf = detector.detect_language("main.zig")
    assert lang == "zig"
    # cleanup
    del detector.EXTENSION_MAPPING[".zig"]


def test_get_language_info():
    info = detector.get_language_info("java")
    assert info["name"] == "java"
    assert ".java" in info["extensions"]
    assert info["supported"] is True
    assert info["tree_sitter_available"] is True


def test_get_language_info_unknown():
    info = detector.get_language_info("brainfuck")
    assert info["name"] == "brainfuck"
    assert info["supported"] is False
    assert info["tree_sitter_available"] is False


def test_detect_c_family_no_match():
    result = detector._detect_c_family("just some text", ["c", "cpp"])
    assert result == "c"  # first candidate
