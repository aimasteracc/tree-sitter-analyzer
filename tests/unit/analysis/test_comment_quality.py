"""Tests for Comment Quality Analyzer."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.comment_quality import (
    CommentIssue,
    CommentQualityAnalyzer,
    CommentQualityResult,
    IssueType,
    Severity,
    _extract_javadoc_params,
    _extract_jsdoc_params,
    _extract_python_docstring_params,
    _find_todos,
)


@pytest.fixture
def analyzer() -> CommentQualityAnalyzer:
    return CommentQualityAnalyzer()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    def _write(code: str) -> Path:
        p = tmp_path / "test_file.py"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p
    return _write  # type: ignore[return-value]


@pytest.fixture
def tmp_js(tmp_path: Path) -> Path:
    def _write(code: str) -> Path:
        p = tmp_path / "test_file.js"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p
    return _write  # type: ignore[return-value]


@pytest.fixture
def tmp_java(tmp_path: Path) -> Path:
    def _write(code: str) -> Path:
        p = tmp_path / "TestFile.java"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p
    return _write  # type: ignore[return-value]


@pytest.fixture
def tmp_go(tmp_path: Path) -> Path:
    def _write(code: str) -> Path:
        p = tmp_path / "test_file.go"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p
    return _write  # type: ignore[return-value]


# --- Python docstring param extraction tests ---

class TestPythonDocstringParams:
    def test_sphinx_style_params(self) -> None:
        doc = ":param x: The x value\n:param y: The y value\n:returns: sum"
        params, has_return = _extract_python_docstring_params(doc)
        assert params == ["x", "y"]
        assert has_return is True

    def test_google_style_params(self) -> None:
        doc = "Summary.\n\nArgs:\n    x: The x value\n    y: The y value\n\nReturns:\n    sum"
        params, has_return = _extract_python_docstring_params(doc)
        assert "x" in params
        assert "y" in params
        assert has_return is True

    def test_no_params(self) -> None:
        doc = "A simple function."
        params, has_return = _extract_python_docstring_params(doc)
        assert params == []
        assert has_return is False

    def test_return_only(self) -> None:
        doc = "Calculate.\n\n:rtype: int"
        params, has_return = _extract_python_docstring_params(doc)
        assert params == []
        assert has_return is True


class TestJSDocParams:
    def test_basic_params(self) -> None:
        doc = "/**\n * @param {number} x - The x\n * @param {number} y - The y\n * @returns {number}\n */"
        params, has_return = _extract_jsdoc_params(doc)
        assert params == ["x", "y"]
        assert has_return is True

    def test_no_params(self) -> None:
        doc = "/**\n * A function.\n */"
        params, has_return = _extract_jsdoc_params(doc)
        assert params == []
        assert has_return is False


class TestJavaDocParams:
    def test_basic_params(self) -> None:
        doc = "/**\n * @param x the x\n * @param y the y\n * @return sum\n */"
        params, has_return = _extract_javadoc_params(doc)
        assert params == ["x", "y"]
        assert has_return is True

    def test_no_return(self) -> None:
        doc = "/**\n * @param x the x\n */"
        params, has_return = _extract_javadoc_params(doc)
        assert params == ["x"]
        assert has_return is False


# --- TODO detection tests ---

class TestFindTodos:
    def test_finds_todo(self) -> None:
        source = "# TODO: fix this later\nx = 1"
        issues = _find_todos(source, "test.py")
        assert len(issues) == 1
        assert issues[0].issue_type == IssueType.STALE_TODO
        assert issues[0].element_name == "TODO"
        assert issues[0].severity == Severity.LOW

    def test_finds_fixme(self) -> None:
        source = "// FIXME: broken code\n"
        issues = _find_todos(source, "test.js")
        assert len(issues) == 1
        assert issues[0].element_name == "FIXME"
        assert issues[0].severity == Severity.HIGH

    def test_finds_hack(self) -> None:
        source = "/* HACK: workaround */\n"
        issues = _find_todos(source, "test.java")
        assert len(issues) == 1
        assert issues[0].element_name == "HACK"
        assert issues[0].severity == Severity.MEDIUM

    def test_no_todos(self) -> None:
        source = "def foo():\n    pass\n"
        issues = _find_todos(source, "test.py")
        assert len(issues) == 0

    def test_multiple_todos(self) -> None:
        source = "# TODO: first\n# FIXME: second\n# HACK: third\n"
        issues = _find_todos(source, "test.py")
        assert len(issues) == 3


# --- Python analysis tests ---

class TestPythonAnalysis:
    def test_matching_params(self, analyzer: CommentQualityAnalyzer, tmp_py: Path) -> None:
        path = tmp_py('''
        def add(x, y):
            """Add two numbers.

            :param x: First number
            :param y: Second number
            :returns: Sum
            """
            return x + y
        ''')
        result = analyzer.analyze_file(path)
        param_issues = result.get_issues_by_type(IssueType.PARAM_MISMATCH)
        assert len(param_issues) == 0

    def test_missing_doc_params(self, analyzer: CommentQualityAnalyzer, tmp_py: Path) -> None:
        path = tmp_py('''
        def add(x, y):
            """Add numbers.

            :param x: First number
            """
            return x + y
        ''')
        result = analyzer.analyze_file(path)
        missing = result.get_issues_by_type(IssueType.MISSING_PARAM_DOC)
        assert len(missing) == 1
        assert "y" in missing[0].message

    def test_stale_doc_params(self, analyzer: CommentQualityAnalyzer, tmp_py: Path) -> None:
        path = tmp_py('''
        def add(x):
            """Add numbers.

            :param x: First number
            :param y: Second number
            :returns: Sum
            """
            return x
        ''')
        result = analyzer.analyze_file(path)
        stale = result.get_issues_by_type(IssueType.EXTRA_DOC_PARAM)
        assert len(stale) == 1
        assert "y" in stale[0].message
        assert stale[0].severity == Severity.HIGH

    def test_missing_return_doc(self, analyzer: CommentQualityAnalyzer, tmp_py: Path) -> None:
        path = tmp_py('''
        def get_name() -> str:
            """Get the name."""
            return "hello"
        ''')
        result = analyzer.analyze_file(path)
        ret_issues = result.get_issues_by_type(IssueType.MISSING_RETURN_DOC)
        assert len(ret_issues) == 1

    def test_self_ignored(self, analyzer: CommentQualityAnalyzer, tmp_py: Path) -> None:
        path = tmp_py('''
        class Foo:
            def bar(self, x):
                """Bar method.

                :param x: The value
                """
                pass
        ''')
        result = analyzer.analyze_file(path)
        param_issues = [
            i for i in result.issues
            if i.issue_type in (IssueType.MISSING_PARAM_DOC, IssueType.EXTRA_DOC_PARAM)
        ]
        assert len(param_issues) == 0

    def test_google_style_docstring(self, analyzer: CommentQualityAnalyzer, tmp_py: Path) -> None:
        path = tmp_py('''
        def process(data, verbose):
            """Process data.

            Args:
                data: Input data
                verbose: Print output

            Returns:
                Result
            """
            pass
        ''')
        result = analyzer.analyze_file(path)
        param_issues = [
            i for i in result.issues
            if i.issue_type in (IssueType.MISSING_PARAM_DOC, IssueType.EXTRA_DOC_PARAM)
        ]
        assert len(param_issues) == 0

    def test_todo_in_python(self, analyzer: CommentQualityAnalyzer, tmp_py: Path) -> None:
        path = tmp_py('''
        def foo():
            # TODO: implement later
            pass
        ''')
        result = analyzer.analyze_file(path)
        todos = result.get_issues_by_type(IssueType.STALE_TODO)
        assert len(todos) == 1

    def test_no_issues(self, analyzer: CommentQualityAnalyzer, tmp_py: Path) -> None:
        path = tmp_py('''
        def simple():
            """A simple function."""
            pass
        ''')
        result = analyzer.analyze_file(path)
        assert result.quality_score == 100.0


class TestJSAnalysis:
    def test_jsdoc_matching(self, analyzer: CommentQualityAnalyzer, tmp_js: Path) -> None:
        path = tmp_js('''
        /**
         * Add numbers.
         * @param {number} x - First
         * @param {number} y - Second
         * @returns {number} Sum
         */
        function add(x, y) {
            return x + y;
        }
        ''')
        result = analyzer.analyze_file(path)
        param_issues = [
            i for i in result.issues
            if i.issue_type in (IssueType.MISSING_PARAM_DOC, IssueType.EXTRA_DOC_PARAM)
        ]
        assert len(param_issues) == 0

    def test_jsdoc_missing_param(self, analyzer: CommentQualityAnalyzer, tmp_js: Path) -> None:
        path = tmp_js('''
        /**
         * @param {number} x - First
         */
        function add(x, y) {
            return x + y;
        }
        ''')
        result = analyzer.analyze_file(path)
        missing = result.get_issues_by_type(IssueType.MISSING_PARAM_DOC)
        assert len(missing) == 1
        assert "y" in missing[0].message

    def test_jsdoc_stale_param(self, analyzer: CommentQualityAnalyzer, tmp_js: Path) -> None:
        path = tmp_js('''
        /**
         * @param {number} x
         * @param {number} y
         * @param {number} z
         */
        function add(x) {
            return x;
        }
        ''')
        result = analyzer.analyze_file(path)
        stale = result.get_issues_by_type(IssueType.EXTRA_DOC_PARAM)
        assert len(stale) >= 1


# --- Java analysis tests ---

class TestJavaAnalysis:
    def test_javadoc_matching(self, analyzer: CommentQualityAnalyzer, tmp_java: Path) -> None:
        path = tmp_java('''
        /**
         * Add numbers.
         * @param x First number
         * @param y Second number
         * @return Sum
         */
        public int add(int x, int y) {
            return x + y;
        }
        ''')
        result = analyzer.analyze_file(path)
        param_issues = [
            i for i in result.issues
            if i.issue_type in (IssueType.MISSING_PARAM_DOC, IssueType.EXTRA_DOC_PARAM)
        ]
        assert len(param_issues) == 0

    def test_javadoc_missing_param(self, analyzer: CommentQualityAnalyzer, tmp_java: Path) -> None:
        path = tmp_java('''
        /**
         * @param x First number
         */
        public int add(int x, int y) {
            return x + y;
        }
        ''')
        result = analyzer.analyze_file(path)
        missing = result.get_issues_by_type(IssueType.MISSING_PARAM_DOC)
        assert len(missing) == 1
        assert "y" in missing[0].message

    def test_javadoc_missing_return(self, analyzer: CommentQualityAnalyzer, tmp_java: Path) -> None:
        path = tmp_java('''
        /**
         * Get name.
         * @return Name
         */
        public void doSomething() {
        }
        ''')
        result = analyzer.analyze_file(path)
        ret_issues = result.get_issues_by_type(IssueType.MISSING_RETURN_DOC)
        # void method should not trigger missing return
        assert len(ret_issues) == 0


# --- Go analysis tests ---

class TestGoAnalysis:
    def test_exported_missing_doc(self, analyzer: CommentQualityAnalyzer, tmp_go: Path) -> None:
        path = tmp_go('''
        package main

        func Process(data string) error {
            return nil
        }
        ''')
        result = analyzer.analyze_file(path)
        missing = result.get_issues_by_type(IssueType.MISSING_PARAM_DOC)
        assert len(missing) == 1
        assert "Process" in missing[0].message

    def test_exported_with_doc(self, analyzer: CommentQualityAnalyzer, tmp_go: Path) -> None:
        path = tmp_go('''
        package main

        // Process handles data
        func Process(data string) error {
            return nil
        }
        ''')
        result = analyzer.analyze_file(path)
        missing = result.get_issues_by_type(IssueType.MISSING_PARAM_DOC)
        assert len(missing) == 0

    def test_unexported_no_warning(self, analyzer: CommentQualityAnalyzer, tmp_go: Path) -> None:
        path = tmp_go('''
        package main

        func process(data string) error {
            return nil
        }
        ''')
        result = analyzer.analyze_file(path)
        missing = result.get_issues_by_type(IssueType.MISSING_PARAM_DOC)
        assert len(missing) == 0


# --- Result tests ---

class TestResult:
    def test_get_issues_by_type(self) -> None:
        issues = (
            CommentIssue("param_mismatch", "high", "msg1", "f.py", 1, "foo"),
            CommentIssue("stale_todo", "low", "msg2", "f.py", 2, "TODO"),
        )
        result = CommentQualityResult(
            issues=issues, total_elements=10, elements_with_docs=8,
            issue_count=2, quality_score=85.0,
        )
        assert len(result.get_issues_by_type("param_mismatch")) == 1
        assert len(result.get_issues_by_type("stale_todo")) == 1
        assert len(result.get_issues_by_type("nonexistent")) == 0

    def test_get_issues_by_severity(self) -> None:
        issues = (
            CommentIssue("param_mismatch", "high", "msg1", "f.py", 1, "foo"),
            CommentIssue("stale_todo", "low", "msg2", "f.py", 2, "TODO"),
        )
        result = CommentQualityResult(
            issues=issues, total_elements=10, elements_with_docs=8,
            issue_count=2, quality_score=85.0,
        )
        assert len(result.get_issues_by_severity("high")) == 1
        assert len(result.get_issues_by_severity("low")) == 1
