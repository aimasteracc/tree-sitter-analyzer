"""Tests for Commented-Out Code Detector."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.analysis.commented_code import (
    ISSUE_ASSIGNMENT,
    ISSUE_CALL,
    ISSUE_DECLARATION,
    ISSUE_IMPORT,
    CommentedCodeDetector,
)


@pytest.fixture
def detector() -> CommentedCodeDetector:
    return CommentedCodeDetector()


# --- Python tests ---

class TestPythonAnalysis:
    def test_detects_commented_assignment(self, detector: CommentedCodeDetector) -> None:
        code = "# result = process(data)\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.items[0].issue_type in (ISSUE_ASSIGNMENT, ISSUE_CALL)

    def test_detects_commented_import(self, detector: CommentedCodeDetector) -> None:
        code = "# import os\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.items[0].issue_type == ISSUE_IMPORT

    def test_detects_commented_function_def(self, detector: CommentedCodeDetector) -> None:
        code = "# def calculate(x, y):\n#     return x + y\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count >= 1
        assert any(s.issue_type == ISSUE_DECLARATION for s in result.items)

    def test_no_false_positive_on_description(self, detector: CommentedCodeDetector) -> None:
        code = "# This function calculates the total price\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0

    def test_no_false_positive_on_todo(self, detector: CommentedCodeDetector) -> None:
        code = "# TODO: refactor this later\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0

    def test_detects_from_import(self, detector: CommentedCodeDetector) -> None:
        code = "# from collections import defaultdict\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.items[0].issue_type == ISSUE_IMPORT

    def test_clean_file(self, detector: CommentedCodeDetector) -> None:
        code = "# Configuration section\nimport logging\nlogger = logging.getLogger(__name__)\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0


# --- JS/TS tests ---

class TestJSAnalysis:
    def test_detects_commented_assignment(self, detector: CommentedCodeDetector) -> None:
        code = '// const result = await fetchData();\n'
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.items[0].issue_type == ISSUE_DECLARATION

    def test_detects_commented_require(self, detector: CommentedCodeDetector) -> None:
        code = '// const fs = require("fs");\n'
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1

    def test_detects_block_comment_code(self, detector: CommentedCodeDetector) -> None:
        code = '/* const x = compute(y); */\n'
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1

    def test_no_false_positive_on_jsdoc(self, detector: CommentedCodeDetector) -> None:
        code = '/**\n * Calculates the sum of two numbers.\n * @param a first number\n */\n'
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0

    def test_typescript_file(self, detector: CommentedCodeDetector) -> None:
        code = '// import { Component } from "react";\n'
        with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.items[0].issue_type == ISSUE_IMPORT


# --- Java tests ---

class TestJavaAnalysis:
    def test_detects_commented_method(self, detector: CommentedCodeDetector) -> None:
        code = 'public class T {\n  // public void process() {\n  //   doSomething();\n  // }\n}\n'
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count >= 1
        assert any(s.issue_type == ISSUE_DECLARATION for s in result.items)

    def test_detects_commented_system_out(self, detector: CommentedCodeDetector) -> None:
        code = 'public class T {\n  // System.out.println("debug");\n}\n'
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count >= 1

    def test_no_false_positive_on_javadoc(self, detector: CommentedCodeDetector) -> None:
        code = '/**\n * This method processes data.\n * @param input the data\n * @return result\n */\n'
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0


# --- Go tests ---

class TestGoAnalysis:
    def test_detects_commented_assignment(self, detector: CommentedCodeDetector) -> None:
        code = 'package main\n// result := compute(input)\nfunc main() {}\n'
        with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 1
        assert result.items[0].issue_type == ISSUE_ASSIGNMENT

    def test_detects_commented_func(self, detector: CommentedCodeDetector) -> None:
        code = 'package main\n// func helper() string {\n//     return "ok"\n// }\nfunc main() {}\n'
        with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count >= 1
        assert any(s.issue_type == ISSUE_DECLARATION for s in result.items)

    def test_no_false_positive_on_go_doc(self, detector: CommentedCodeDetector) -> None:
        code = 'package main\n// Package main provides the entry point.\nfunc main() {}\n'
        with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0


# --- Edge cases ---

class TestEdgeCases:
    def test_nonexistent_file(self, detector: CommentedCodeDetector) -> None:
        result = detector.analyze_file("/nonexistent/file.py")
        assert result.total_count == 0
        assert result.items == ()

    def test_unsupported_extension(self, detector: CommentedCodeDetector) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write('# result = compute(data)')
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0

    def test_empty_file(self, detector: CommentedCodeDetector) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("")
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count == 0

    def test_to_dict(self, detector: CommentedCodeDetector) -> None:
        code = '# result = process(data)\n'
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        d = result.to_dict()
        assert "file_path" in d
        assert "items" in d
        assert "total_count" in d
        assert "by_type" in d
        assert d["total_count"] == 1

    def test_item_to_dict(self, detector: CommentedCodeDetector) -> None:
        code = '# result = process(data)\n'
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        d = result.items[0].to_dict()
        assert "line" in d
        assert "issue_type" in d
        assert "content" in d
        assert "severity" in d

    def test_by_type_counts(self, detector: CommentedCodeDetector) -> None:
        code = '# import os\n# result = compute(x)\n# def foo(): pass\n'
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            f.flush()
            result = detector.analyze_file(f.name)
        assert result.total_count >= 2
        assert len(result.by_type) >= 2
