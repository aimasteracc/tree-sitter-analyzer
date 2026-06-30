#!/usr/bin/env python3
"""
Extended Tests for Language Detector

Additional test cases to improve coverage for language detection functionality.
"""

import sys
import unittest.mock

import pytest

# Add project root to path
sys.path.insert(0, ".")

from tree_sitter_analyzer.language_detector import (
    LanguageDetector,
    detect_language_from_file,
    detector,
    is_language_supported,
)


@pytest.fixture
def language_detector():
    """Fixture to provide a LanguageDetector instance"""
    return LanguageDetector()


# ---------------------------------------------------------------------------
# detect_language() — extension-based, clear languages (was 4 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "file_path,content,expected_language,expected_confidence",
    [
        pytest.param(
            "test.java",
            """
    package com.example;

    public class TestClass {
        @Override
        public void method() {
            System.out.println("Hello");
        }
    }
    """,
            "java",
            0.9,
            id="java-extension-and-content",
        ),
        pytest.param(
            "test.py",
            """
    def main():
        import os
        from sys import argv

        if __name__ == "__main__":
            print("Hello World")
    """,
            "python",
            0.9,
            id="python-extension-and-content",
        ),
        pytest.param(
            "test.js",
            """
    function greet(name) {
        var message = "Hello";
        let greeting = `${message}, ${name}!`;
        const result = greeting;
        console.log(result);
        return result;
    }
    """,
            "javascript",
            0.9,
            id="javascript-extension-and-content",
        ),
        pytest.param(
            "test.ts",
            """
    interface User {
        name: string;
        age: number;
    }

    type UserType = User;

    export class UserService {
        getUser(): User {
            return { name: "John", age: 30 };
        }
    }
    """,
            "typescript",
            0.9,
            id="typescript-extension-and-content",
        ),
    ],
)
def test_detect_language_with_content(
    language_detector, file_path, content, expected_language, expected_confidence
):
    """Test language detection with clear extension + content — Extension-based detection confidence = 0.9"""
    language, confidence = language_detector.detect_language(file_path, content)
    assert language == expected_language
    assert confidence == expected_confidence


# ---------------------------------------------------------------------------
# detect_language() — ambiguous extensions (.h / .m) with content
# (was 8 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "file_path,content,expected_language,expected_confidence",
    [
        pytest.param(
            "test.h",
            """
    #include <iostream>

    namespace MyNamespace {
        class MyClass {
        public:
            void method() {
                std::cout << "Hello" << std::endl;
            }
        };

        template<typename T>
        void templateFunction(T value) {
            std::cout << value << std::endl;
        }
    }
    """,
            "c",
            0.7,
            id="h-cpp-content-defaults-to-c",
            # .h files default to C when content-based detection doesn't
            # provide strong enough signals (ambiguous extension)
        ),
        pytest.param(
            "test.h",
            """
    #include <stdio.h>
    #include <stdlib.h>

    typedef struct {
        int id;
        char name[50];
    } Person;

    int main() {
        printf("Hello, World!\\n");
        Person* p = malloc(sizeof(Person));
        return 0;
    }
    """,
            "c",
            0.7,
            id="h-c-content",
        ),
        pytest.param(
            "test.h",
            """
    #import <Foundation/Foundation.h>

    @interface MyClass : NSObject
    @property (nonatomic, strong) NSString *name;
    - (void)doSomething;
    @end

    @implementation MyClass
    - (void)doSomething {
        NSString *message = [[NSString alloc] initWithString:@"Hello"];
    }
    @end
    """,
            "c",
            0.7,
            id="h-objc-content-defaults-to-c",
            # .h files default to C even with Objective-C content (ambiguous
            # extension); content-based detection requires stronger patterns
        ),
        pytest.param(
            "test.m",
            """
    #import "MyClass.h"

    @implementation MyClass
    - (void)doSomething {
        NSString *message = [[NSString alloc] initWithString:@"Hello"];
    }
    @end
    """,
            "objc",
            0.7,
            id="m-objc-content",
        ),
        pytest.param(
            "test.m",
            """
    function result = calculateSum(a, b)
        clc;
        clear all;

        result = a + b;
        disp(['Result: ', num2str(result)]);
    end;

    % Main script
    x = 5;
    y = 10;
    sum_result = calculateSum(x, y);
    """,
            "objc",
            0.7,
            id="m-matlab-content-defaults-to-objc",
            # .m files default to Objective-C (more common in modern dev)
        ),
        pytest.param(
            "test.h",
            None,
            "c",
            0.7,
            id="h-no-content-defaults-to-c",
        ),
        pytest.param(
            "test.h",
            "",
            "c",
            0.7,
            id="h-empty-content-defaults-to-c",
        ),
    ],
)
def test_detect_language_ambiguous_extension(
    language_detector, file_path, content, expected_language, expected_confidence
):
    """Test detect_language for ambiguous extensions (.h / .m) with various content"""
    if content is None:
        language, confidence = language_detector.detect_language(file_path, content)
    else:
        language, confidence = language_detector.detect_language(file_path, content)
    assert language == expected_language
    assert confidence == expected_confidence


def test_detect_language_ambiguous_without_content(language_detector):
    """Test ambiguous extension without content — default .h → c, confidence 0.7"""
    language, confidence = language_detector.detect_language("test.h")
    assert language == "c"
    assert confidence == 0.7


# ---------------------------------------------------------------------------
# detect_language() — unknown / edge-case inputs (was 5 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "file_path,expected_language,expected_confidence",
    [
        pytest.param("test.unknown", "unknown", 0.0, id="unknown-extension"),
        pytest.param("", "unknown", 0.0, id="empty-string-path"),
        pytest.param("README", "unknown", 0.0, id="no-extension"),
        pytest.param(None, "unknown", 0.0, id="none-input"),
    ],
)
def test_detect_language_edge_inputs(
    language_detector, file_path, expected_language, expected_confidence
):
    """Test detect_language returns ('unknown', 0.0) for unresolvable or invalid paths"""
    language, confidence = language_detector.detect_language(file_path)
    assert language == expected_language
    assert confidence == expected_confidence


def test_file_path_with_multiple_dots(language_detector):
    """Test file path with multiple dots — last extension wins"""
    language, confidence = language_detector.detect_language("test.backup.java")
    assert language == "java"
    assert confidence == 0.9  # Extension-based detection confidence


# ---------------------------------------------------------------------------
# detect_from_extension() — various languages (already parametrized; kept)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "file_path,expected_language",
    [
        ("test.java", "java"),
        ("test.py", "python"),
        ("test.js", "javascript"),
        ("test.ts", "typescript"),
        ("test.cpp", "cpp"),
        ("test.rs", "rust"),
        ("test.go", "go"),
        ("test.rb", "ruby"),
        ("test.php", "php"),
        ("test.swift", "swift"),
        ("test.kt", "kotlin"),
        ("test.scala", "scala"),
        ("test.unknown", "unknown"),
    ],
)
def test_detect_from_extension_various_files(
    language_detector, file_path, expected_language
):
    """Test extension-based detection for various files"""
    language = language_detector.detect_from_extension(file_path)
    assert language == expected_language


# ---------------------------------------------------------------------------
# detect_from_extension() — invalid / non-string inputs (was 2 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_input",
    [
        pytest.param(None, id="none"),
        pytest.param(123, id="integer"),
    ],
)
def test_detect_from_extension_invalid_input(language_detector, bad_input):
    """detect_from_extension with non-string or None returns 'unknown'"""
    assert language_detector.detect_from_extension(bad_input) == "unknown"


# ---------------------------------------------------------------------------
# Case-insensitive extension handling (already parametrized; kept)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "file_path,expected_language",
    [
        ("test.JAVA", "java"),
        ("test.PY", "python"),
        ("test.JS", "javascript"),
        ("test.Cpp", "cpp"),
    ],
)
def test_case_insensitive_extensions(language_detector, file_path, expected_language):
    """Test case insensitive extension handling"""
    language = language_detector.detect_from_extension(file_path)
    assert language == expected_language


# ---------------------------------------------------------------------------
# is_supported() (already parametrized; kept)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "language",
    [
        "java",
        "javascript",
        "typescript",
        "python",
        "c",
        "cpp",
        "rust",
        "go",
        "php",
        "ruby",
        "swift",
    ],
)
def test_is_supported_supported_languages(language_detector, language):
    """Test support status for supported languages"""
    assert language_detector.is_supported(language) is True


@pytest.mark.parametrize("language", ["unknown", "klingon", "made-up-lang"])
def test_is_supported_unsupported_languages(language_detector, language):
    """Test support status for unsupported languages.

    Note: ``scala`` used to live here as an example unsupported language,
    but post-consolidation it ships as a real plugin
    (``languages/scala_plugin.py``). Use truly unknown placeholders.
    """
    assert language_detector.is_supported(language) is False


# ---------------------------------------------------------------------------
# get_supported_extensions / get_supported_languages (standalone — different shape)
# ---------------------------------------------------------------------------

def test_get_supported_extensions(language_detector):
    """Test getting supported extensions"""
    extensions = language_detector.get_supported_extensions()

    assert isinstance(extensions, list)
    assert ".java" in extensions
    assert ".py" in extensions
    assert ".js" in extensions
    assert ".ts" in extensions
    assert ".cpp" in extensions
    # Should be sorted
    assert extensions == sorted(extensions)


def test_get_supported_languages(language_detector):
    """Test getting supported languages"""
    languages = language_detector.get_supported_languages()

    assert isinstance(languages, list)
    assert "java" in languages
    assert "python" in languages
    assert "javascript" in languages
    assert "typescript" in languages
    assert "cpp" in languages
    assert "php" in languages
    assert "ruby" in languages
    assert "swift" in languages
    # Should be sorted
    assert languages == sorted(languages)


# ---------------------------------------------------------------------------
# add_extension_mapping (standalone — stateful mutation test)
# ---------------------------------------------------------------------------

def test_add_extension_mapping(language_detector):
    """Test adding custom extension mapping"""
    # Add a custom mapping
    language_detector.add_extension_mapping(".custom", "customlang")

    # Test the new mapping
    language = language_detector.detect_from_extension("test.custom")
    assert language == "customlang"

    # Test case insensitivity
    language_detector.add_extension_mapping(".UPPER", "upperlang")
    language = language_detector.detect_from_extension("test.upper")
    assert language == "upperlang"


# ---------------------------------------------------------------------------
# get_language_info() (was 2 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "lang,expected_extension",
    [
        pytest.param("java", ".java", id="java"),
        pytest.param("swift", ".swift", id="swift"),
    ],
)
def test_get_language_info_supported(language_detector, lang, expected_extension):
    """Test getting language information for supported languages"""
    info = language_detector.get_language_info(lang)

    assert isinstance(info, dict)
    assert info["name"] == lang
    assert expected_extension in info["extensions"]
    assert info["supported"] is True
    assert info["tree_sitter_available"] is True


# ---------------------------------------------------------------------------
# _resolve_ambiguity() (was 9 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "extension,content,expected",
    [
        pytest.param(".java", "public class Test {}", "java", id="non-ambiguous-java"),
        pytest.param(".unknown", "some content", "unknown", id="unknown-extension"),
        pytest.param(
            ".h",
            "#include <iostream>\nstd::cout << 'hi';",
            "cpp",
            id="h-cpp-signals",
        ),
        pytest.param(
            ".h",
            '#include <stdio.h>\nprintf("hi");',
            "c",
            id="h-c-signals",
        ),
        pytest.param(
            ".h",
            "#import <Foundation/Foundation.h>\n@interface Foo\nNSString *s; alloc]",
            "objc",
            id="h-objc-signals",
        ),
        pytest.param(
            ".m",
            '#import "Foo.h"\n@interface Bar\nalloc]',
            "objc",
            id="m-objc-signals",
        ),
        pytest.param(
            ".m",
            "function y = f(x)\nclc;\nclear all\ndisp(x)\nend;",
            "matlab",
            id="m-matlab-signals",
        ),
        pytest.param(".sql", "SELECT 1", "sql", id="sql-fallback"),
        pytest.param(".json", "{}", "json", id="json-fallback"),
    ],
)
def test_resolve_ambiguity(language_detector, extension, content, expected):
    """_resolve_ambiguity routes correctly based on extension and content signals"""
    result = language_detector._resolve_ambiguity(extension, content)
    assert result == expected


# ---------------------------------------------------------------------------
# _detect_c_family() (was 5 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "content,candidates,expected",
    [
        pytest.param(
            "// Just a comment\nint x = 5;",
            ["c", "cpp", "objc"],
            "c",
            id="no-matches-returns-first-candidate",
        ),
        pytest.param(
            "#include <iostream>\nusing namespace std;\nstd::vector<int> v;",
            ["c", "cpp"],
            "cpp",
            id="cpp-patterns-win",
        ),
        pytest.param(
            '#include <stdio.h>\nprintf("hello");\nmalloc(64);\ntypedef struct',
            ["c", "cpp"],
            "c",
            id="c-patterns-win",
        ),
        pytest.param(
            "#import <Foundation/Foundation.h>\n@interface Foo\nalloc]",
            ["c", "cpp", "objc"],
            "objc",
            id="objc-patterns-win",
        ),
        pytest.param(
            "#import <Foundation/Foundation.h>\n@interface Test",
            ["c", "cpp"],  # objc not in candidates
            "c",
            id="objc-wins-but-not-in-candidates-falls-back",
        ),
    ],
)
def test_detect_c_family(language_detector, content, candidates, expected):
    """_detect_c_family selects the correct C-family language from content signals.

    The 'objc-wins-but-not-in-candidates-falls-back' case expects 'c' as the
    documented first-candidate fallback; the result must be in candidates.
    """
    result = language_detector._detect_c_family(content, candidates)
    # Every result must be drawn from the provided candidates
    assert result in candidates
    # And must equal the specific expected value documented per case
    assert result == expected


# ---------------------------------------------------------------------------
# _detect_objc_vs_matlab() (was 3 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "content,candidates,expected",
    [
        pytest.param(
            "// No specific patterns",
            ["objc", "matlab"],
            "objc",
            id="tie-returns-first-candidate",
        ),
        pytest.param(
            '#import "Foo.h"\n@interface MyClass\n@implementation MyClass\nNSString *s = [[NSString alloc] init]',
            ["objc", "matlab"],
            "objc",
            id="clear-objc-content",
        ),
        pytest.param(
            "function result = calc()\nclc;\nclear all\ndisp('hello')\nend;",
            ["objc", "matlab"],
            "matlab",
            id="clear-matlab-content",
        ),
    ],
)
def test_detect_objc_vs_matlab(language_detector, content, candidates, expected):
    """_detect_objc_vs_matlab selects the correct language from content signals"""
    result = language_detector._detect_objc_vs_matlab(content, candidates)
    assert result == expected


# ---------------------------------------------------------------------------
# Global convenience functions
# ---------------------------------------------------------------------------

def test_detect_language_from_file():
    """Test global detect_language_from_file function"""
    language = detect_language_from_file("test.java")
    assert language == "java"

    language = detect_language_from_file("test.py")
    assert language == "python"

    language = detect_language_from_file("test.unknown")
    assert language == "unknown"


def test_is_language_supported_global():
    """Test global is_language_supported function"""
    assert is_language_supported("java") is True
    assert is_language_supported("python") is True
    assert is_language_supported("swift") is True
    assert is_language_supported("unknown") is False


def test_global_detector_instance():
    """Test global detector instance"""
    assert isinstance(detector, LanguageDetector)

    # Test that it works
    language = detector.detect_from_extension("test.java")
    assert language == "java"


# ---------------------------------------------------------------------------
# detect_language_from_file() — invalid inputs (was 2 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_input",
    [
        pytest.param("", id="empty-string"),
        pytest.param(None, id="none"),
    ],
)
def test_detect_language_from_file_invalid_input(bad_input):
    """detect_language_from_file with empty or None returns 'unknown'"""
    assert detect_language_from_file(bad_input) == "unknown"  # type: ignore


def test_detect_language_from_file_with_project_root():
    """detect_language_from_file with relative path and project_root"""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a real file so mtime_ns is captured
        fpath = os.path.join(tmpdir, "test.py")
        with open(fpath, "w") as f:
            f.write("print('hello')")
        result = detect_language_from_file("test.py", project_root=tmpdir)
        assert result == "python"


# ---------------------------------------------------------------------------
# Force ambiguity path by removing a known extension from the map
# (was 2 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "content,expected_language,expected_confidence",
    [
        pytest.param(
            "SELECT * FROM table",
            "sql",
            0.7,
            id="with-content-ambiguity-path",
        ),
        pytest.param(
            None,
            "sql",
            0.7,
            id="without-content-ambiguity-path",
        ),
    ],
)
def test_detect_language_forced_ambiguity(
    language_detector, content, expected_language, expected_confidence
):
    """Force ambiguity resolution by removing .sql from extension_map"""
    language_detector.extension_map.pop(".sql", None)
    if content is not None:
        language, confidence = language_detector.detect_language("test.sql", content)
    else:
        language, confidence = language_detector.detect_language("test.sql")
    assert language == expected_language
    assert confidence == expected_confidence


# ---------------------------------------------------------------------------
# is_supported / is_language_supported with PluginManager failure
# (was 2 separate funcs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fn,label",
    [
        pytest.param(
            lambda ld: ld.is_supported("cobol"),
            "instance-method",
            id="instance-method",
        ),
        pytest.param(
            lambda _: is_language_supported("cobol"),
            "global-function",
            id="global-function",
        ),
    ],
)
def test_is_supported_with_plugin_manager_failure(language_detector, fn, label):
    """is_supported and is_language_supported fall back gracefully when PluginManager raises"""
    with unittest.mock.patch(
        "tree_sitter_analyzer.plugins.manager.PluginManager",
        side_effect=ImportError("nope"),
    ):
        assert fn(language_detector) is False
