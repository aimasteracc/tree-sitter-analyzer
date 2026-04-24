"""Tests for Exception Signature Analyzer."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.exception_signature import (
    ExceptionSignatureAnalyzer,
    ExceptionSignatureIssue,
    ExceptionSignatureResult,
    FindingType,
    Severity,
    _extract_java_exception_type,
    _extract_js_exception_type,
    _extract_python_exception_type,
    _is_exception_caught,
    _normalize_exception_name,
)


@pytest.fixture
def analyzer() -> ExceptionSignatureAnalyzer:
    return ExceptionSignatureAnalyzer()


@pytest.fixture
def tmp_py_file(tmp_path: Path):
    def _create(code: str) -> Path:
        p = tmp_path / "test_module.py"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    return _create


@pytest.fixture
def tmp_js_file(tmp_path: Path):
    def _create(code: str) -> Path:
        p = tmp_path / "test_module.js"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    return _create


@pytest.fixture
def tmp_java_file(tmp_path: Path):
    def _create(code: str) -> Path:
        p = tmp_path / "TestModule.java"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    return _create


@pytest.fixture
def tmp_go_file(tmp_path: Path):
    def _create(code: str) -> Path:
        p = tmp_path / "main.go"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    return _create


# --- Helper function tests ---


class TestNormalizeExceptionName:
    def test_simple_name(self) -> None:
        assert _normalize_exception_name("ValueError") == "ValueError"

    def test_dotted_name(self) -> None:
        assert _normalize_exception_name("errors.ValueError") == "ValueError"

    def test_deeply_nested(self) -> None:
        assert _normalize_exception_name("pkg.module.errors.ValueError") == "ValueError"


class TestIsExceptionCaught:
    def test_catch_all(self) -> None:
        assert _is_exception_caught("ValueError", [], is_catch_all=True) is True

    def test_exact_match(self) -> None:
        assert _is_exception_caught("ValueError", ["ValueError"], is_catch_all=False) is True

    def test_no_match(self) -> None:
        assert _is_exception_caught("ValueError", ["TypeError"], is_catch_all=False) is False

    def test_empty_caught(self) -> None:
        assert _is_exception_caught("ValueError", [], is_catch_all=False) is False


# --- Python tests ---


class TestPythonAnalysis:
    def test_function_with_uncaught_raise(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def process(data):
                if not data:
                    raise ValueError("empty data")
                return data.strip()
        """)
        result = analyzer.analyze_file(path)
        assert result.functions_scanned == 1
        sig_findings = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig_findings) == 1
        assert "ValueError" in sig_findings[0].exception_types

    def test_function_with_caught_raise(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def process(data):
                try:
                    if not data:
                        raise ValueError("empty data")
                except ValueError:
                    pass
                return data
        """)
        result = analyzer.analyze_file(path)
        sig_findings = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig_findings) == 0

    def test_function_with_bare_except_catches_all(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def process(data):
                try:
                    raise ValueError("error")
                except:
                    pass
                return data
        """)
        result = analyzer.analyze_file(path)
        sig_findings = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig_findings) == 0

    def test_function_with_partial_catch(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def process(data):
                try:
                    if not data:
                        raise ValueError("empty")
                    if data == "bad":
                        raise TypeError("bad type")
                except ValueError:
                    pass
                return data
        """)
        result = analyzer.analyze_file(path)
        sig_findings = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig_findings) == 1
        assert "TypeError" in sig_findings[0].exception_types
        assert "ValueError" not in sig_findings[0].exception_types

    def test_undocumented_exception(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def process(data):
                raise ValueError("empty data")
        """)
        result = analyzer.analyze_file(path)
        undoc = [f for f in result.issues if f.finding_type == "undocumented_exception"]
        assert len(undoc) == 1
        assert "ValueError" in undoc[0].exception_types

    def test_documented_exception_no_warning(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def process(data):
                \"\"\"Process data.

                :raises ValueError: when data is empty
                \"\"\"
                raise ValueError("empty data")
        """)
        result = analyzer.analyze_file(path)
        undoc = [f for f in result.issues if f.finding_type == "undocumented_exception"]
        assert len(undoc) == 0

    def test_no_raise_no_findings(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def process(data):
                return data.strip()
        """)
        result = analyzer.analyze_file(path)
        assert result.total_findings == 0
        assert result.functions_scanned == 1

    def test_nested_function_excluded(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def outer(data):
                def inner():
                    raise ValueError("inner error")
                return data
        """)
        result = analyzer.analyze_file(path)
        # Inner function's raise should not affect outer's signature
        outer_sigs = [
            f for f in result.issues
            if f.finding_type == "exception_signature" and f.function_name == "outer"
        ]
        assert len(outer_sigs) == 0

    def test_multiple_exceptions(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def validate(data):
                if not data:
                    raise ValueError("empty")
                if len(data) > 100:
                    raise TypeError("too long")
                raise RuntimeError("unknown")
        """)
        result = analyzer.analyze_file(path)
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 1
        assert set(sig[0].exception_types) == {"ValueError", "TypeError", "RuntimeError"}

    def test_class_method(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            class Handler:
                def process(self, data):
                    if not data:
                        raise ValueError("empty")
                    return data
        """)
        result = analyzer.analyze_file(path)
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 1
        assert sig[0].function_name == "process"

    def test_exception_as_pattern(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def process(data):
                try:
                    raise ValueError("error")
                except ValueError as e:
                    pass
                return data
        """)
        result = analyzer.analyze_file(path)
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 0

    def test_tuple_except(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def process(data):
                try:
                    raise ValueError("error")
                except (ValueError, TypeError):
                    pass
                return data
        """)
        result = analyzer.analyze_file(path)
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 0


# --- JavaScript tests ---


class TestJavaScriptAnalysis:
    def test_throw_new_error(self, analyzer: ExceptionSignatureAnalyzer, tmp_js_file: Path) -> None:
        path = tmp_js_file("""\
            function validate(data) {
                if (!data) {
                    throw new Error("empty");
                }
                return data;
            }
        """)
        result = analyzer.analyze_file(path)
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 1
        assert "Error" in sig[0].exception_types

    def test_throw_new_type_error(self, analyzer: ExceptionSignatureAnalyzer, tmp_js_file: Path) -> None:
        path = tmp_js_file("""\
            function validate(data) {
                throw new TypeError("bad type");
            }
        """)
        result = analyzer.analyze_file(path)
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 1
        assert "TypeError" in sig[0].exception_types

    def test_caught_throw(self, analyzer: ExceptionSignatureAnalyzer, tmp_js_file: Path) -> None:
        path = tmp_js_file("""\
            function validate(data) {
                try {
                    throw new Error("error");
                } catch (e) {
                    return null;
                }
            }
        """)
        result = analyzer.analyze_file(path)
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 0

    def test_jsdoc_documented_exception(self, analyzer: ExceptionSignatureAnalyzer, tmp_js_file: Path) -> None:
        path = tmp_js_file("""\
            /**
             * @throws {Error} when data is empty
             */
            function validate(data) {
                throw new Error("empty");
            }
        """)
        result = analyzer.analyze_file(path)
        undoc = [f for f in result.issues if f.finding_type == "undocumented_exception"]
        assert len(undoc) == 0

    def test_arrow_function(self, analyzer: ExceptionSignatureAnalyzer, tmp_js_file: Path) -> None:
        path = tmp_js_file("""\
            const validate = (data) => {
                throw new Error("bad");
            };
        """)
        result = analyzer.analyze_file(path)
        assert result.functions_scanned >= 1

    def test_no_throw_no_findings(self, analyzer: ExceptionSignatureAnalyzer, tmp_js_file: Path) -> None:
        path = tmp_js_file("""\
            function process(data) {
                return data.trim();
            }
        """)
        result = analyzer.analyze_file(path)
        assert result.total_findings == 0


# --- Java tests ---


class TestJavaAnalysis:
    def test_throw_in_method(self, analyzer: ExceptionSignatureAnalyzer, tmp_java_file: Path) -> None:
        path = tmp_java_file("""\
            public class Handler {
                public void process(String data) {
                    if (data == null) {
                        throw new IllegalArgumentException("null data");
                    }
                }
            }
        """)
        result = analyzer.analyze_file(path)
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 1
        assert "IllegalArgumentException" in sig[0].exception_types

    def test_caught_throw(self, analyzer: ExceptionSignatureAnalyzer, tmp_java_file: Path) -> None:
        path = tmp_java_file("""\
            public class Handler {
                public void process(String data) {
                    try {
                        throw new IllegalArgumentException("error");
                    } catch (IllegalArgumentException e) {
                        return;
                    }
                }
            }
        """)
        result = analyzer.analyze_file(path)
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 0

    def test_throws_clause_excluded(self, analyzer: ExceptionSignatureAnalyzer, tmp_java_file: Path) -> None:
        path = tmp_java_file("""\
            public class Handler {
                public void process(String data) throws IOException {
                    throw new IOException("file error");
                }
            }
        """)
        result = analyzer.analyze_file(path)
        # IOException declared in throws clause should be excluded
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 0

    def test_javadoc_documented(self, analyzer: ExceptionSignatureAnalyzer, tmp_java_file: Path) -> None:
        path = tmp_java_file("""\
            public class Handler {
                /**
                 * Process data.
                 * @throws IllegalArgumentException when data is null
                 */
                public void process(String data) {
                    throw new IllegalArgumentException("null");
                }
            }
        """)
        result = analyzer.analyze_file(path)
        undoc = [f for f in result.issues if f.finding_type == "undocumented_exception"]
        assert len(undoc) == 0


# --- Go tests ---


class TestGoAnalysis:
    def test_panic_detection(self, analyzer: ExceptionSignatureAnalyzer, tmp_go_file: Path) -> None:
        path = tmp_go_file("""\
            package main

            func process(data string) string {
                if data == "" {
                    panic("empty data")
                }
                return data
            }
        """)
        result = analyzer.analyze_file(path)
        sig = [f for f in result.issues if f.finding_type == "exception_signature"]
        assert len(sig) == 1
        assert "panic" in sig[0].exception_types

    def test_no_panic_no_findings(self, analyzer: ExceptionSignatureAnalyzer, tmp_go_file: Path) -> None:
        path = tmp_go_file("""\
            package main

            func process(data string) string {
                return data
            }
        """)
        result = analyzer.analyze_file(path)
        assert result.total_findings == 0


# --- Edge cases ---


class TestEdgeCases:
    def test_unsupported_extension(self, analyzer: ExceptionSignatureAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "data.csv"
        p.write_text("a,b,c", encoding="utf-8")
        result = analyzer.analyze_file(p)
        assert result.total_findings == 0

    def test_nonexistent_file(self, analyzer: ExceptionSignatureAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/path.py")
        assert result.total_findings == 0

    def test_result_to_dict(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("""\
            def process(data):
                raise ValueError("error")
        """)
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "file_path" in d
        assert "total_findings" in d
        assert "issues" in d
        assert d["total_findings"] == 2  # signature + undocumented

    def test_empty_file(self, analyzer: ExceptionSignatureAnalyzer, tmp_py_file: Path) -> None:
        path = tmp_py_file("")
        result = analyzer.analyze_file(path)
        assert result.total_findings == 0

    def test_analyze_project(self, analyzer: ExceptionSignatureAnalyzer, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text(
            "def f():\n    raise ValueError('x')\n", encoding="utf-8"
        )
        (tmp_path / "b.py").write_text(
            "def g():\n    return 1\n", encoding="utf-8"
        )
        results = analyzer.analyze_project(tmp_path)
        assert len(results) == 1
        assert results[0].total_findings > 0
