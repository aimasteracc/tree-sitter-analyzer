"""Unit tests for Exception Handling Quality Analyzer."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.exception_quality import (
    QUALITY_BROAD,
    QUALITY_SWALLOWED,
    ExceptionQualityAnalyzer,
    _compute_quality_score,
    _empty_result,
)


@pytest.fixture
def analyzer() -> ExceptionQualityAnalyzer:
    return ExceptionQualityAnalyzer()


def _write_py(tmp_path: Path, code: str, name: str = "sample.py") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


def _write_js(tmp_path: Path, code: str, name: str = "sample.js") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


def _write_java(tmp_path: Path, code: str, name: str = "Sample.java") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


def _write_go(tmp_path: Path, code: str, name: str = "sample.go") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


# --- Core ---

class TestExceptionQualityAnalyzer:
    def test_empty_file(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        p = _write_py(tmp_path, "")
        result = analyzer.analyze_file(p)
        assert result.total_try_blocks == 0
        assert result.total_issues == 0

    def test_nonexistent_file(self, analyzer: ExceptionQualityAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_try_blocks == 0

    def test_unsupported_extension(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "file.rb"
        p.write_text("begin; rescue; end")
        result = analyzer.analyze_file(p)
        assert result.total_try_blocks == 0

    def test_file_without_try(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        p = _write_py(tmp_path, "def hello():\n    pass\n")
        result = analyzer.analyze_file(p)
        assert result.total_try_blocks == 0
        assert result.quality_score == 100.0


# --- Python ---

class TestPythonBroadCatch:
    def test_bare_except(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try:
            risky()
        except:
            pass
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_try_blocks == 1
        broad = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_BROAD]
        assert len(broad) >= 1

    def test_exception_is_broad(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try:
            risky()
        except Exception:
            handle()
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        broad = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_BROAD]
        assert len(broad) >= 1

    def test_specific_exception_is_ok(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try:
            risky()
        except ValueError as e:
            handle(e)
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        broad = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_BROAD]
        assert len(broad) == 0


class TestPythonSwallowedException:
    def test_empty_except(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try:
            risky()
        except ValueError:
            pass
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        swallowed = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_SWALLOWED]
        assert len(swallowed) >= 1

    def test_except_with_comment_only(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try:
            risky()
        except ValueError:
            # TODO: handle this
            pass
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        swallowed = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_SWALLOWED]
        assert len(swallowed) >= 1

    def test_except_with_logging_is_ok(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try:
            risky()
        except ValueError as e:
            logger.error("Failed: %s", e)
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        swallowed = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_SWALLOWED]
        assert len(swallowed) == 0


# --- JavaScript/TypeScript ---

class TestJavaScriptCatch:
    def test_broad_catch(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try {
            risky();
        } catch (e) {
            // nothing
        }
        """
        p = _write_js(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_try_blocks == 1
        swallowed = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_SWALLOWED]
        assert len(swallowed) >= 1

    def test_catch_with_logging_ok(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try {
            risky();
        } catch (e) {
            console.error("Failed:", e);
        }
        """
        p = _write_js(tmp_path, code)
        result = analyzer.analyze_file(p)
        swallowed = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_SWALLOWED]
        assert len(swallowed) == 0

    def test_typescript_file(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try {
            risky();
        } catch (e) {
        }
        """
        p = _write_js(tmp_path, code, name="sample.ts")
        result = analyzer.analyze_file(p)
        assert result.total_try_blocks == 1


# --- Java ---

class TestJavaCatch:
    def test_broad_exception(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Foo {
            void bar() {
                try {
                    risky();
                } catch (Exception e) {
                    // nothing
                }
            }
        }
        """
        p = _write_java(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_try_blocks == 1
        broad = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_BROAD]
        assert len(broad) >= 1

    def test_specific_catch_ok(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Foo {
            void bar() {
                try {
                    risky();
                } catch (IOException e) {
                    logger.error("IO failed", e);
                }
            }
        }
        """
        p = _write_java(tmp_path, code)
        result = analyzer.analyze_file(p)
        broad = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_BROAD]
        assert len(broad) == 0

    def test_empty_catch_block(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Foo {
            void bar() {
                try {
                    risky();
                } catch (IOException e) {
                }
            }
        }
        """
        p = _write_java(tmp_path, code)
        result = analyzer.analyze_file(p)
        swallowed = [i for i in result.try_blocks[0].issues if i.issue_type == QUALITY_SWALLOWED]
        assert len(swallowed) >= 1


# --- Go ---

class TestGoRecover:
    def test_defer_recover_no_logging(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        package main
        func risky() {
            defer func() {
                recover()
            }()
            panic("oops")
        }
        """
        p = _write_go(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_try_blocks >= 1
        swallowed = [
            i
            for b in result.try_blocks
            for i in b.issues
            if i.issue_type == QUALITY_SWALLOWED
        ]
        assert len(swallowed) >= 1

    def test_defer_recover_with_logging_ok(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        package main
        import "log"
        func risky() {
            defer func() {
                if r := recover(); r != nil {
                    log.Printf("recovered: %v", r)
                }
            }()
            panic("oops")
        }
        """
        p = _write_go(tmp_path, code)
        result = analyzer.analyze_file(p)
        swallowed = [
            i
            for b in result.try_blocks
            for i in b.issues
            if i.issue_type == QUALITY_SWALLOWED
        ]
        assert len(swallowed) == 0

    def test_no_recover_no_issues(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        package main
        func hello() {
            fmt.Println("hi")
        }
        """
        p = _write_go(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_try_blocks == 0


# --- Quality Score ---

class TestQualityScore:
    def test_perfect_score(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try:
            risky()
        except ValueError as e:
            logger.error("Failed: %s", e)
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.quality_score == 100.0

    def test_score_decreases_with_issues(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try:
            risky()
        except:
            pass
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.quality_score < 100.0

    def test_compute_score_directly(self) -> None:
        assert _compute_quality_score(0, []) == 100.0
        assert _compute_quality_score(1, []) == 100.0

    def test_empty_result(self) -> None:
        result = _empty_result("foo.py")
        assert result.total_try_blocks == 0
        assert result.quality_score == 100.0


# --- Multi-Block ---

class TestMultiBlock:
    def test_multiple_try_blocks(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try:
            a()
        except ValueError as e:
            handle(e)

        try:
            b()
        except:
            pass
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_try_blocks == 2
        assert len(result.try_blocks[0].issues) == 0
        assert len(result.try_blocks[1].issues) > 0

    def test_issue_counts(self, analyzer: ExceptionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        try:
            risky()
        except:
            pass
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_issues > 0
        assert QUALITY_BROAD in result.issue_counts
        assert QUALITY_SWALLOWED in result.issue_counts
