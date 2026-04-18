"""Unit tests for type annotation coverage analysis."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.type_annotation_coverage import (
    TypeAnnotationAnalyzer,
)


@pytest.fixture
def analyzer() -> TypeAnnotationAnalyzer:
    return TypeAnnotationAnalyzer()


def _write(code: bytes) -> Path:
    f = Path(tempfile.mktemp(suffix=".py"))
    f.write_bytes(code)
    return f


def test_fully_annotated_function(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b"def foo(x: int, y: str) -> bool:\n    return True\n")
    result = analyzer.analyze(p)
    assert result.coverage_pct == 100.0
    assert result.annotated_elements == result.total_elements


def test_no_annotations(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b"def foo(x, y):\n    return True\n")
    result = analyzer.analyze(p)
    params = [s for s in result.stats if s.kind == "parameter"]
    unannotated = [s for s in params if not s.has_annotation]
    assert len(unannotated) >= 2


def test_partial_annotations(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b"def foo(x: int, y):\n    return True\n")
    result = analyzer.analyze(p)
    assert 0 < result.coverage_pct < 100


def test_return_type_annotated(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b"def foo() -> int:\n    return 42\n")
    result = analyzer.analyze(p)
    returns = [s for s in result.stats if s.kind == "return_type"]
    assert len(returns) == 1
    assert returns[0].has_annotation is True
    assert returns[0].annotation_type == "int"


def test_return_type_missing(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b"def foo():\n    return 42\n")
    result = analyzer.analyze(p)
    returns = [s for s in result.stats if s.kind == "return_type"]
    assert len(returns) == 1
    assert returns[0].has_annotation is False


def test_variable_annotation(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b"x: int = 42\n")
    result = analyzer.analyze(p)
    vars_ = [s for s in result.stats if s.kind == "variable"]
    assert len(vars_) == 1
    assert vars_[0].has_annotation is True
    assert vars_[0].annotation_type == "int"


def test_variable_without_annotation_not_counted(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b"x = 42\n")
    result = analyzer.analyze(p)
    vars_ = [s for s in result.stats if s.kind == "variable"]
    assert len(vars_) == 0


def test_self_parameter_skipped(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b"class Foo:\n    def bar(self, x: int) -> None:\n        pass\n")
    result = analyzer.analyze(p)
    params = [s for s in result.stats if s.kind == "parameter"]
    self_params = [s for s in params if s.name == "self"]
    assert len(self_params) == 0


def test_default_parameter_annotated(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b'def foo(x: int = 0) -> int:\n    return x\n')
    result = analyzer.analyze(p)
    params = [s for s in result.stats if s.kind == "parameter"]
    assert all(s.has_annotation for s in params)


def test_default_parameter_not_annotated(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b'def foo(x=0):\n    return x\n')
    result = analyzer.analyze(p)
    params = [s for s in result.stats if s.kind == "parameter"]
    assert all(not s.has_annotation for s in params)


def test_empty_file(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b"")
    result = analyzer.analyze(p)
    assert result.total_elements == 0
    assert result.coverage_pct == 100.0


def test_coverage_result_to_dict(analyzer: TypeAnnotationAnalyzer) -> None:
    p = _write(b"def foo(x: int) -> str:\n    return 'hi'\n")
    result = analyzer.analyze(p)
    d = result.to_dict()
    assert "file_path" in d
    assert "coverage_pct" in d
    assert "total_elements" in d
    assert "stats" in d


def test_analyze_directory(analyzer: TypeAnnotationAnalyzer) -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "a.py").write_text("def foo(x: int) -> int:\n    return x\n")
        (Path(td) / "b.py").write_text("def bar(y):\n    return y\n")
        results = analyzer.analyze_directory(td)
        assert len(results) == 2
        coverages = [r.coverage_pct for r in results]
        assert any(c == 100.0 for c in coverages)
        assert any(c < 100.0 for c in coverages)
