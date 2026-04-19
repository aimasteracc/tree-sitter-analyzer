"""Tests for Function Redefinition Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.function_redefinition import (
    ISSUE_FUNC_REDEF,
    ISSUE_METHOD_REDEF,
    FunctionRedefinitionAnalyzer,
)

analyzer = FunctionRedefinitionAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False,
    )
    f.write(content)
    f.close()
    return Path(f.name)


# ── Python: function redefinition ──


def test_python_func_redefined() -> None:
    path = _write_tmp(
        "def foo():\n    pass\n\ndef foo():\n    return 42\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1
    assert any(
        i.issue_type == ISSUE_FUNC_REDEF for i in result.issues
    )


def test_python_func_unique() -> None:
    path = _write_tmp(
        "def foo():\n    pass\n\ndef bar():\n    pass\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_python_method_redefined() -> None:
    path = _write_tmp(
        "class C:\n"
        "    def method(self):\n"
        "        pass\n"
        "    def method(self):\n"
        "        return 1\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1
    assert any(
        i.issue_type == ISSUE_METHOD_REDEF for i in result.issues
    )


def test_python_method_unique() -> None:
    path = _write_tmp(
        "class C:\n"
        "    def foo(self):\n"
        "        pass\n"
        "    def bar(self):\n"
        "        pass\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_python_func_and_method_same_name_ok() -> None:
    """Function and method with same name are in different scopes."""
    path = _write_tmp(
        "def process():\n    pass\n\n"
        "class C:\n    def process(self):\n        pass\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_python_triple_redefinition() -> None:
    path = _write_tmp(
        "def f():\n    pass\n\ndef f():\n    pass\n\ndef f():\n    pass\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count == 2


def test_python_generator_redefined() -> None:
    path = _write_tmp(
        "def gen():\n    yield 1\n\ndef gen():\n    yield 2\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


# ── JavaScript ──


def test_js_func_redefined() -> None:
    path = _write_tmp(
        "function foo() {}\nfunction foo() {}\n",
        suffix=".js",
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


def test_js_func_unique() -> None:
    path = _write_tmp(
        "function foo() {}\nfunction bar() {}\n",
        suffix=".js",
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


# ── TypeScript ──


def test_ts_func_redefined() -> None:
    path = _write_tmp(
        "function foo(): void {}\nfunction foo(): void {}\n",
        suffix=".ts",
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


# ── Java ──


def test_java_method_redefined() -> None:
    path = _write_tmp(
        "class Foo {\n"
        "    void bar() {}\n"
        "    void bar() {}\n"
        "}\n",
        suffix=".java",
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


# ── Edge cases ──


def test_empty_file() -> None:
    path = _write_tmp("", suffix=".py")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0
    assert result.total_functions == 0


def test_file_not_found() -> None:
    result = analyzer.analyze_file("/nonexistent/file.py")
    assert result.issue_count == 0


def test_unsupported_extension() -> None:
    path = _write_tmp("def f(): pass\n", suffix=".rb")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_result_to_dict() -> None:
    path = _write_tmp("def f():\n    pass\n\ndef f():\n    pass\n")
    result = analyzer.analyze_file(path)
    d = result.to_dict()
    assert "file_path" in d
    assert "total_functions" in d
    assert "issue_count" in d
    assert "issues" in d


def test_issue_to_dict() -> None:
    path = _write_tmp("def f():\n    pass\n\ndef f():\n    pass\n")
    result = analyzer.analyze_file(path)
    if result.issues:
        d = result.issues[0].to_dict()
        assert "line" in d
        assert "issue_type" in d
        assert "original_line" in d


def test_original_line_tracked() -> None:
    path = _write_tmp("def f():\n    pass\n\ndef f():\n    pass\n")
    result = analyzer.analyze_file(path)
    if result.issues:
        assert result.issues[0].original_line == 1


def test_go_func_unique() -> None:
    path = _write_tmp(
        "package main\nfunc foo() {}\nfunc bar() {}\n",
        suffix=".go",
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_nested_class_methods_dont_conflict() -> None:
    """Methods in different classes with same name are fine."""
    path = _write_tmp(
        "class A:\n    def process(self):\n        pass\n\n"
        "class B:\n    def process(self):\n        pass\n"
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0
