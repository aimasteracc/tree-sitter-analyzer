"""Tests for Error Handling Pattern Analyzer."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.error_handling import (
    BROAD_EXCEPTION_NAMES,
    ErrorHandlingAnalyzer,
    ErrorHandlingIssue,
    ErrorHandlingResult,
    PatternSeverity,
    PatternType,
)


@pytest.fixture
def tmp_py_file(tmp_path: Path):
    """Create a temp Python file and return its path."""

    def _create(code: str) -> Path:
        p = tmp_path / "test_module.py"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    return _create


@pytest.fixture
def tmp_js_file(tmp_path: Path):
    """Create a temp JS file and return its path."""

    def _create(code: str) -> Path:
        p = tmp_path / "test_module.js"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    return _create


@pytest.fixture
def tmp_java_file(tmp_path: Path):
    """Create a temp Java file and return its path."""

    def _create(code: str) -> Path:
        p = tmp_path / "TestModule.java"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    return _create


@pytest.fixture
def tmp_go_file(tmp_path: Path):
    """Create a temp Go file and return its path."""

    def _create(code: str) -> Path:
        p = tmp_path / "main.go"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    return _create


@pytest.fixture
def analyzer(tmp_path: Path):
    return ErrorHandlingAnalyzer(project_root=tmp_path)


# --- Dataclass Tests ---


class TestErrorHandlingIssue:
    def test_frozen_issue(self):
        issue = ErrorHandlingIssue(
            pattern_type="bare_except",
            severity="error",
            message="Bare except",
            file_path="test.py",
            line_number=1,
            end_line=1,
            code_snippet="except:",
            suggestion="Add type",
            language="python",
        )
        assert issue.pattern_type == "bare_except"
        with pytest.raises(AttributeError):
            issue.severity = "warning"  # type: ignore[misc]


class TestErrorHandlingResult:
    def test_add_issue_updates_counts(self):
        result = ErrorHandlingResult(file_path="test.py")
        issue = ErrorHandlingIssue(
            pattern_type="bare_except",
            severity="error",
            message="Bare except",
            file_path="test.py",
            line_number=1,
            end_line=1,
            code_snippet="except:",
            suggestion="Add type",
            language="python",
        )
        result.add_issue(issue)
        assert result.total_issues == 1
        assert result.by_severity["error"] == 1
        assert result.by_pattern["bare_except"] == 1

    def test_multiple_issues(self):
        result = ErrorHandlingResult(file_path="test.py")
        for i in range(3):
            result.add_issue(ErrorHandlingIssue(
                pattern_type="bare_except",
                severity="error",
                message=f"Issue {i}",
                file_path="test.py",
                line_number=i + 1,
                end_line=i + 1,
                code_snippet="except:",
                suggestion="Fix",
                language="python",
            ))
        assert result.total_issues == 3
        assert result.by_severity["error"] == 3


# --- Python Tests ---


class TestPythonBareExcept:
    def test_detects_bare_except(self, analyzer: ErrorHandlingAnalyzer, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except:
                pass
        """)
        result = analyzer.analyze_file(path)
        bare = [i for i in result.issues if i.pattern_type == PatternType.BARE_EXCEPT.value]
        assert len(bare) == 1
        assert bare[0].severity == PatternSeverity.ERROR.value
        assert bare[0].line_number == 3

    def test_no_bare_except_with_type(self, analyzer: ErrorHandlingAnalyzer, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except ValueError as e:
                pass
        """)
        result = analyzer.analyze_file(path)
        bare = [i for i in result.issues if i.pattern_type == PatternType.BARE_EXCEPT.value]
        assert len(bare) == 0

    def test_multiple_bare_excepts(self, analyzer: ErrorHandlingAnalyzer, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except:
                pass

            try:
                y = 2
            except:
                pass
        """)
        result = analyzer.analyze_file(path)
        bare = [i for i in result.issues if i.pattern_type == PatternType.BARE_EXCEPT.value]
        assert len(bare) == 2


class TestPythonSwallowedErrors:
    def test_detects_empty_except_block(self, analyzer: ErrorHandlingAnalyzer, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except ValueError:
                pass
        """)
        result = analyzer.analyze_file(path)
        swallowed = [i for i in result.issues if i.pattern_type == PatternType.SWALLOWED_ERROR.value]
        assert len(swallowed) == 1
        assert swallowed[0].severity == PatternSeverity.WARNING.value

    def test_no_swallowed_with_handling(self, analyzer: ErrorHandlingAnalyzer, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except ValueError as e:
                logger.error(f"Failed: {e}")
                raise
        """)
        result = analyzer.analyze_file(path)
        swallowed = [i for i in result.issues if i.pattern_type == PatternType.SWALLOWED_ERROR.value]
        assert len(swallowed) == 0

    def test_only_comment_is_swallowed(self, analyzer: ErrorHandlingAnalyzer, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except ValueError:
                # just ignore
                pass
        """)
        result = analyzer.analyze_file(path)
        swallowed = [i for i in result.issues if i.pattern_type == PatternType.SWALLOWED_ERROR.value]
        assert len(swallowed) == 1


class TestPythonBroadExceptions:
    def test_detects_exception(self, analyzer: ErrorHandlingAnalyzer, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except Exception as e:
                logger.error(e)
        """)
        result = analyzer.analyze_file(path)
        broad = [i for i in result.issues if i.pattern_type == PatternType.BROAD_EXCEPTION.value]
        assert len(broad) == 1
        assert "Exception" in broad[0].message

    def test_detects_base_exception(self, analyzer: ErrorHandlingAnalyzer, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except BaseException:
                pass
        """)
        result = analyzer.analyze_file(path)
        broad = [i for i in result.issues if i.pattern_type == PatternType.BROAD_EXCEPTION.value]
        assert len(broad) == 1

    def test_specific_exception_not_flagged(self, analyzer: ErrorHandlingAnalyzer, tmp_py_file):
        path = tmp_py_file("""\
            try:
                x = 1
            except ValueError as e:
                logger.error(e)
        """)
        result = analyzer.analyze_file(path)
        broad = [i for i in result.issues if i.pattern_type == PatternType.BROAD_EXCEPTION.value]
        assert len(broad) == 0

    def test_broad_exception_types_constant(self):
        assert "Exception" in BROAD_EXCEPTION_NAMES
        assert "BaseException" in BROAD_EXCEPTION_NAMES
        assert "RuntimeException" in BROAD_EXCEPTION_NAMES
        assert "ValueError" not in BROAD_EXCEPTION_NAMES


# --- JavaScript/TypeScript Tests ---


class TestJSSwallowedErrors:
    def test_detects_empty_catch(self, analyzer: ErrorHandlingAnalyzer, tmp_js_file):
        path = tmp_js_file("""\
            try {
                const x = 1;
            } catch (e) {
            }
        """)
        result = analyzer.analyze_file(path)
        swallowed = [i for i in result.issues if i.pattern_type == PatternType.SWALLOWED_ERROR.value]
        assert len(swallowed) == 1
        assert swallowed[0].language == "javascript"

    def test_no_swallowed_with_handling(self, analyzer: ErrorHandlingAnalyzer, tmp_js_file):
        path = tmp_js_file("""\
            try {
                const x = 1;
            } catch (e) {
                console.error(e);
                throw e;
            }
        """)
        result = analyzer.analyze_file(path)
        swallowed = [i for i in result.issues if i.pattern_type == PatternType.SWALLOWED_ERROR.value]
        assert len(swallowed) == 0


class TestJSCatchAll:
    def test_detects_catch_without_type_check(self, analyzer: ErrorHandlingAnalyzer, tmp_js_file):
        path = tmp_js_file("""\
            try {
                const x = doSomething();
            } catch (e) {
                console.log(e);
            }
        """)
        result = analyzer.analyze_file(path)
        broad = [i for i in result.issues if i.pattern_type == PatternType.BROAD_EXCEPTION.value]
        assert len(broad) == 1

    def test_no_flag_with_instanceof(self, analyzer: ErrorHandlingAnalyzer, tmp_js_file):
        path = tmp_js_file("""\
            try {
                const x = doSomething();
            } catch (e) {
                if (e instanceof TypeError) {
                    console.error(e);
                }
            }
        """)
        result = analyzer.analyze_file(path)
        broad = [i for i in result.issues if i.pattern_type == PatternType.BROAD_EXCEPTION.value]
        assert len(broad) == 0


# --- Java Tests ---


class TestJavaSwallowedErrors:
    def test_detects_empty_catch(self, analyzer: ErrorHandlingAnalyzer, tmp_java_file):
        path = tmp_java_file("""\
            public class Test {
                public void test() {
                    try {
                        int x = 1;
                    } catch (Exception e) {
                    }
                }
            }
        """)
        result = analyzer.analyze_file(path)
        swallowed = [i for i in result.issues if i.pattern_type == PatternType.SWALLOWED_ERROR.value]
        assert len(swallowed) == 1
        assert swallowed[0].language == "java"

    def test_no_swallowed_with_handling(self, analyzer: ErrorHandlingAnalyzer, tmp_java_file):
        path = tmp_java_file("""\
            public class Test {
                public void test() {
                    try {
                        int x = 1;
                    } catch (Exception e) {
                        log.error("Failed", e);
                    }
                }
            }
        """)
        result = analyzer.analyze_file(path)
        swallowed = [i for i in result.issues if i.pattern_type == PatternType.SWALLOWED_ERROR.value]
        assert len(swallowed) == 0


class TestJavaBroadExceptions:
    def test_detects_exception_catch(self, analyzer: ErrorHandlingAnalyzer, tmp_java_file):
        path = tmp_java_file("""\
            public class Test {
                public void test() {
                    try {
                        int x = 1;
                    } catch (Exception e) {
                        log.error("Failed", e);
                    }
                }
            }
        """)
        result = analyzer.analyze_file(path)
        broad = [i for i in result.issues if i.pattern_type == PatternType.BROAD_EXCEPTION.value]
        assert len(broad) == 1

    def test_specific_exception_not_flagged(self, analyzer: ErrorHandlingAnalyzer, tmp_java_file):
        path = tmp_java_file("""\
            public class Test {
                public void test() {
                    try {
                        int x = 1;
                    } catch (IOException e) {
                        log.error("Failed", e);
                    }
                }
            }
        """)
        result = analyzer.analyze_file(path)
        broad = [i for i in result.issues if i.pattern_type == PatternType.BROAD_EXCEPTION.value]
        assert len(broad) == 0


# --- Go Tests ---


class TestGoUncheckedErrors:
    def test_detects_unchecked_error(self, analyzer: ErrorHandlingAnalyzer, tmp_go_file):
        path = tmp_go_file("""\
            package main

            func main() {
                err := doSomething()
                fmt.Println("done")
            }
        """)
        result = analyzer.analyze_file(path)
        unchecked = [i for i in result.issues if i.pattern_type == PatternType.UNCHECKED_ERROR.value]
        assert len(unchecked) >= 1

    def test_no_flag_with_err_check(self, analyzer: ErrorHandlingAnalyzer, tmp_go_file):
        path = tmp_go_file("""\
            package main

            func main() {
                err := doSomething()
                if err != nil {
                    return err
                }
                fmt.Println("done")
            }
        """)
        result = analyzer.analyze_file(path)
        unchecked = [i for i in result.issues if i.pattern_type == PatternType.UNCHECKED_ERROR.value]
        assert len(unchecked) == 0


# --- Project-Level Tests ---


class TestProjectAnalysis:
    def test_analyze_project_finds_issues(self, tmp_path: Path):
        analyzer = ErrorHandlingAnalyzer(project_root=tmp_path)

        # Create Python file with bare except
        py_file = tmp_path / "module.py"
        py_file.write_text(textwrap.dedent("""\
            try:
                x = 1
            except:
                pass
        """))

        results = analyzer.analyze_project(tmp_path)
        assert len(results) == 1
        assert results[0].total_issues >= 1

    def test_analyze_project_excludes_dirs(self, tmp_path: Path):
        analyzer = ErrorHandlingAnalyzer(project_root=tmp_path)

        # Create file in excluded dir
        excluded = tmp_path / "node_modules" / "test.js"
        excluded.parent.mkdir(parents=True)
        excluded.write_text("try { x } catch(e) { }")

        results = analyzer.analyze_project(tmp_path)
        assert len(results) == 0

    def test_unsupported_file_returns_empty(self, analyzer: ErrorHandlingAnalyzer, tmp_path: Path):
        txt = tmp_path / "readme.txt"
        txt.write_text("try: pass")
        result = analyzer.analyze_file(txt)
        assert result.total_issues == 0


# --- Severity Threshold Tests ---


class TestSeverityThreshold:
    def test_severity_enum_values(self):
        assert PatternSeverity.ERROR.value == "error"
        assert PatternSeverity.WARNING.value == "warning"
        assert PatternSeverity.INFO.value == "info"

    def test_pattern_type_enum_values(self):
        assert PatternType.BARE_EXCEPT.value == "bare_except"
        assert PatternType.SWALLOWED_ERROR.value == "swallowed_error"
        assert PatternType.BROAD_EXCEPTION.value == "broad_exception"
        assert PatternType.UNCHECKED_ERROR.value == "unchecked_error"
