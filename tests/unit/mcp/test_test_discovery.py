"""Unit tests for language-aware test file discovery."""

import tempfile
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.utils.test_discovery import (
    detect_language_from_ext,
    find_test_files,
)


class TestDetectLanguageFromExt:
    def test_python(self):
        assert detect_language_from_ext(".py") == "python"

    def test_java(self):
        assert detect_language_from_ext(".java") == "java"

    def test_go(self):
        assert detect_language_from_ext(".go") == "go"

    def test_rust(self):
        assert detect_language_from_ext(".rs") == "rust"

    def test_javascript(self):
        assert detect_language_from_ext(".js") == "javascript"

    def test_typescript(self):
        assert detect_language_from_ext(".ts") == "typescript"

    def test_c(self):
        assert detect_language_from_ext(".c") == "c"

    def test_cpp(self):
        assert detect_language_from_ext(".cpp") == "cpp"

    def test_csharp(self):
        assert detect_language_from_ext(".cs") == "csharp"

    def test_kotlin(self):
        assert detect_language_from_ext(".kt") == "kotlin"

    def test_ruby(self):
        assert detect_language_from_ext(".rb") == "ruby"

    def test_php(self):
        assert detect_language_from_ext(".php") == "php"

    def test_unknown(self):
        assert detect_language_from_ext(".xyz") is None


class TestFindTestFilesPython:
    def test_finds_python_test_in_unit_dir(self):
        """Finds tests/unit/module/test_file.py for file.py."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src" / "module" / "calculator.py"
            source.parent.mkdir(parents=True)
            source.write_text("def add(): pass")

            test = root / "tests" / "unit" / "module" / "test_calculator.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_add(): pass")

            results = find_test_files(str(source), tmp)
            assert any("test_calculator.py" in r for r in results)

    def test_finds_python_test_in_tests_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "health_scorer.py"
            source.write_text("pass")
            test = root / "tests" / "test_health_scorer.py"
            test.parent.mkdir()
            test.write_text("pass")

            results = find_test_files(str(source), tmp)
            assert any("test_health_scorer" in r for r in results)


class TestFindTestFilesJava:
    def test_finds_java_test_maven_structure(self):
        """Finds src/test/java for src/main/java source."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src" / "main" / "java" / "com" / "Calculator.java"
            source.parent.mkdir(parents=True)
            source.write_text("class Calculator {}")

            test = root / "src" / "test" / "java" / "com" / "CalculatorTest.java"
            test.parent.mkdir(parents=True)
            test.write_text("class CalculatorTest {}")

            results = find_test_files(str(source), tmp)
            assert any("CalculatorTest.java" in r for r in results)


class TestFindTestFilesGo:
    def test_finds_go_colocated_test(self):
        """Finds _test.go file co-located with source."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "handler.go"
            source.write_text("package main")

            test = root / "handler_test.go"
            test.write_text("package main")

            results = find_test_files(str(source), tmp)
            assert any("handler_test.go" in r for r in results)


class TestFindTestFilesRuby:
    def test_finds_ruby_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lib" / "parser.rb"
            source.parent.mkdir(parents=True)
            source.write_text("class Parser; end")

            test = root / "test" / "test_parser.rb"
            test.parent.mkdir(parents=True)
            test.write_text("require 'test/unit'")

            results = find_test_files(str(source), tmp)
            assert any("test_parser.rb" in r for r in results)


class TestFindTestFilesJavascript:
    def test_finds_js_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src" / "utils.js"
            source.parent.mkdir(parents=True)
            source.write_text("export function foo() {}")

            test = root / "tests" / "utils.test.js"
            test.parent.mkdir(parents=True)
            test.write_text("test('foo', () => {})")

            results = find_test_files(str(source), tmp)
            assert any("utils.test.js" in r for r in results)
