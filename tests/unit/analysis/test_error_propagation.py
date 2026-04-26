"""Tests for Error Propagation Analyzer."""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.error_propagation import (
    ErrorPropagationAnalyzer,
    ErrorPropagationIssue,
    PropagationGapType,
)


@pytest.fixture
def analyzer() -> ErrorPropagationAnalyzer:
    return ErrorPropagationAnalyzer()


def _write_tmp(content: str, suffix: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


# --- Python tests ---

class TestPythonErrorPropagation:
    def test_detect_unhandled_raise(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def foo():
                raise ValueError("bad")
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_gaps >= 1
        types = [g.gap_type for g in result.gaps]
        assert PropagationGapType.UNHANDLED_RAISE.value in types

    def test_caught_exception_not_flagged(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def foo():
                try:
                    raise ValueError("bad")
                except ValueError:
                    pass
        """, ".py")
        result = analyzer.analyze_file(path)
        unhandled = [g for g in result.gaps
                     if g.gap_type == PropagationGapType.UNHANDLED_RAISE.value]
        assert len(unhandled) == 0

    def test_swallowed_without_reraise(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def bar():
                try:
                    risky()
                except Exception:
                    log("error")
        """, ".py")
        result = analyzer.analyze_file(path)
        types = [g.gap_type for g in result.gaps]
        assert PropagationGapType.SWALLOWED_NO_PROPAGATION.value in types

    def test_reraise_detected(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def bar():
                try:
                    risky()
                except ValueError:
                    logger.error("oops")
                    raise
        """, ".py")
        result = analyzer.analyze_file(path)
        swallowed = [g for g in result.gaps
                     if g.gap_type == PropagationGapType.SWALLOWED_NO_PROPAGATION.value]
        assert len(swallowed) == 0

    def test_bare_except_swallowed(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def baz():
                try:
                    dangerous()
                except:
                    pass
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_gaps >= 1

    def test_nested_try_except(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def nested():
                try:
                    try:
                        inner()
                    except ValueError:
                        pass
                except Exception:
                    pass
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_gaps >= 2

    def test_finally_without_catch(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def cleanup():
                try:
                    risky()
                finally:
                    cleanup()
        """, ".py")
        result = analyzer.analyze_file(path)
        types = [g.gap_type for g in result.gaps]
        assert PropagationGapType.FINALLY_NO_CATCH.value in types

    def test_raise_from_detected(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def wrap():
                try:
                    low_level()
                except OSError as e:
                    raise RuntimeError("wrap") from e
        """, ".py")
        result = analyzer.analyze_file(path)
        swallowed = [g for g in result.gaps
                     if g.gap_type == PropagationGapType.SWALLOWED_NO_PROPAGATION.value]
        assert len(swallowed) == 0

    def test_custom_exception_raise(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            class MyError(Exception):
                pass

            def custom():
                raise MyError("custom")
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_gaps >= 1

    def test_function_with_no_errors(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def safe():
                x = 1 + 2
                return x
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_gaps == 0

    def test_exception_type_tracked(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def typed():
                raise ValueError("a")
                raise TypeError("b")
        """, ".py")
        result = analyzer.analyze_file(path)
        exc_types: set[str] = set()
        for g in result.gaps:
            exc_types.update(g.exception_types)
        assert "ValueError" in exc_types
        assert "TypeError" in exc_types

    def test_risk_levels(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def risky():
                raise ValueError("bad")

            def safe():
                try:
                    raise ValueError("bad")
                except ValueError:
                    pass
        """, ".py")
        result = analyzer.analyze_file(path)
        risks = {g.risk_level for g in result.gaps}
        assert len(risks) >= 1


class TestJSErrorPropagation:
    def test_unhandled_throw(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            function foo() {
                throw new Error("bad");
            }
        """, ".js")
        result = analyzer.analyze_file(path)
        assert result.total_gaps >= 1

    def test_caught_throw(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            function foo() {
                try {
                    throw new Error("bad");
                } catch (e) {
                    console.error(e);
                }
            }
        """, ".js")
        result = analyzer.analyze_file(path)
        unhandled = [g for g in result.gaps
                     if g.gap_type == PropagationGapType.UNHANDLED_THROW.value]
        assert len(unhandled) == 0

    def test_swallowed_catch(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            function bar() {
                try {
                    risky();
                } catch (e) {
                    // swallowed
                }
            }
        """, ".js")
        result = analyzer.analyze_file(path)
        types = [g.gap_type for g in result.gaps]
        assert PropagationGapType.SWALLOWED_NO_PROPAGATION.value in types

    def test_rethrow_detected(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            function bar() {
                try {
                    risky();
                } catch (e) {
                    console.error(e);
                    throw e;
                }
            }
        """, ".js")
        result = analyzer.analyze_file(path)
        swallowed = [g for g in result.gaps
                     if g.gap_type == PropagationGapType.SWALLOWED_NO_PROPAGATION.value]
        assert len(swallowed) == 0

    def test_typescript_throw(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            function foo(): never {
                throw new Error("bad");
            }
        """, ".ts")
        result = analyzer.analyze_file(path)
        assert result.total_gaps >= 1

    def test_finally_without_catch(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            function cleanup() {
                try {
                    risky();
                } finally {
                    cleanup();
                }
            }
        """, ".js")
        result = analyzer.analyze_file(path)
        types = [g.gap_type for g in result.gaps]
        assert PropagationGapType.FINALLY_NO_CATCH.value in types

    def test_nested_catch(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            function nested() {
                try {
                    try {
                        inner();
                    } catch (e) {
                        // swallowed inner
                    }
                } catch (e) {
                    console.error(e);
                }
            }
        """, ".js")
        result = analyzer.analyze_file(path)
        assert result.total_gaps >= 1

    def test_empty_catch_block(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            function foo() {
                try {
                    risky();
                } catch (e) {
                }
            }
        """, ".js")
        result = analyzer.analyze_file(path)
        assert result.total_gaps >= 1


# --- Java tests ---

class TestJavaErrorPropagation:
    def test_unhandled_throw(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            public class Foo {
                public void foo() throws RuntimeException {
                    throw new RuntimeException("bad");
                }
            }
        """, ".java")
        result = analyzer.analyze_file(path)
        assert result.total_gaps >= 1

    def test_caught_exception(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            public class Foo {
                public void foo() {
                    try {
                        throw new RuntimeException("bad");
                    } catch (RuntimeException e) {
                        log.error(e);
                    }
                }
            }
        """, ".java")
        result = analyzer.analyze_file(path)
        unhandled = [g for g in result.gaps
                     if g.gap_type == PropagationGapType.UNHANDLED_THROW.value]
        assert len(unhandled) == 0

    def test_swallowed_catch(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            public class Foo {
                public void bar() {
                    try {
                        risky();
                    } catch (Exception e) {
                        // swallowed
                    }
                }
            }
        """, ".java")
        result = analyzer.analyze_file(path)
        types = [g.gap_type for g in result.gaps]
        assert PropagationGapType.SWALLOWED_NO_PROPAGATION.value in types

    def test_finally_without_catch(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            public class Foo {
                public void cleanup() {
                    try {
                        risky();
                    } finally {
                        cleanup();
                    }
                }
            }
        """, ".java")
        result = analyzer.analyze_file(path)
        types = [g.gap_type for g in result.gaps]
        assert PropagationGapType.FINALLY_NO_CATCH.value in types

    def test_reraise_in_java(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            public class Foo {
                public void wrap() {
                    try {
                        risky();
                    } catch (Exception e) {
                        log.error(e);
                        throw new RuntimeException(e);
                    }
                }
            }
        """, ".java")
        result = analyzer.analyze_file(path)
        swallowed = [g for g in result.gaps
                     if g.gap_type == PropagationGapType.SWALLOWED_NO_PROPAGATION.value]
        assert len(swallowed) == 0


# --- Result structure tests ---

class TestResultStructure:
    def test_result_has_fields(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def foo():
                raise ValueError("bad")
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.file_path == str(path)
        assert isinstance(result.total_gaps, int)
        assert isinstance(result.gaps, list)
        assert isinstance(result.by_risk_level, dict)
        assert isinstance(result.by_gap_type, dict)

    def test_issue_has_fields(self) -> None:
        issue = ErrorPropagationIssue(
            gap_type="unhandled_raise",
            severity="high",
            message="Unhandled raise",
            file_path="test.py",
            line_number=10,
            end_line=10,
            code_snippet="raise ValueError()",
            suggestion="Add try/except or declare in function signature",
            language="python",
            exception_types=["ValueError"],
            risk_level="high",
            function_name="foo",
        )
        assert issue.gap_type == "unhandled_raise"
        assert issue.exception_types == ["ValueError"]
        assert issue.risk_level == "high"
        assert issue.function_name == "foo"

    def test_unsupported_file_returns_empty(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("data", ".csv")
        result = analyzer.analyze_file(path)
        assert result.total_gaps == 0
        assert len(result.gaps) == 0

    def test_to_dict(self, analyzer: ErrorPropagationAnalyzer) -> None:
        path = _write_tmp("""
            def foo():
                raise ValueError("bad")
        """, ".py")
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "file_path" in d
        assert "total_gaps" in d
        assert "gaps" in d
        assert "by_risk_level" in d
        assert "by_gap_type" in d


# --- Multiple languages in one session ---

class TestMultiLanguage:
    def test_all_languages_detect_unhandled(self, analyzer: ErrorPropagationAnalyzer) -> None:
        py = _write_tmp("def f():\n    raise ValueError('x')\n", ".py")
        js = _write_tmp("function f() { throw new Error('x'); }\n", ".js")
        java = _write_tmp("public class C { void f() { throw new RuntimeException(\"x\"); } }\n", ".java")

        for p in [py, js, java]:
            result = analyzer.analyze_file(p)
            assert result.total_gaps >= 1, f"No gaps detected for {p.suffix}"
