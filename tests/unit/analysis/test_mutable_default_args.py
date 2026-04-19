"""Tests for Mutable Default Arguments Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.mutable_default_args import (
    MutableDefaultArg,
    MutableDefaultArgsAnalyzer,
    MutableDefaultArgsResult,
)


@pytest.fixture
def analyzer() -> MutableDefaultArgsAnalyzer:
    return MutableDefaultArgsAnalyzer()


@pytest.fixture
def tmp_dir() -> Path:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _write(dir_path: Path, code: str, name: str = "test.py") -> Path:
    p = dir_path / name
    p.write_text(code)
    return p


# --- Detection tests ---


class TestListDefaults:
    def test_empty_list(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=[]):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "list"
        assert r.violations[0].severity == "high"

    def test_list_with_values(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=[1, 2, 3]):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "list"

    def test_list_comprehension(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=[i for i in range(10)]):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "list_comprehension"


class TestDictDefaults:
    def test_empty_dict(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x={}):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "dict"

    def test_dict_with_items(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, 'def foo(x={"a": 1}):\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "dict"

    def test_dict_comprehension(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x={k: v for k, v in items}):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "dict_comprehension"


class TestSetDefaults:
    def test_set_literal(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x={1, 2}):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "set"

    def test_set_comprehension(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x={i for i in range(10)}):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "set_comprehension"

    def test_set_constructor(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=set()):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "set"

    def test_list_constructor(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=list()):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "list"

    def test_dict_constructor(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=dict()):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].default_type == "dict"


class TestSafeDefaults:
    def test_none_default(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=None):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 0

    def test_int_default(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=0):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 0

    def test_string_default(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, 'def foo(x="hello"):\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.violation_count == 0

    def test_bool_default(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=True):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 0

    def test_tuple_default(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=(1, 2)):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 0

    def test_frozenset_default(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=frozenset()):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 0

    def test_tuple_constructor(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(x=tuple()):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 0

    def test_str_constructor(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, 'def foo(x=str()):\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.violation_count == 0


class TestVariableReference:
    def test_variable_ref_flagged(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "MY_LIST = []\ndef foo(x=MY_LIST):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count >= 1
        medium_violations = [v for v in r.violations if v.severity == "medium"]
        assert len(medium_violations) >= 1


class TestMultipleParameters:
    def test_mixed_params(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(a, b=[], c=None, d={}):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 2

    def test_all_safe(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(a, b=None, c=0, d=''):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 0


class TestMultipleFunctions:
    def test_two_functions(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, (
            "def foo(x=[]):\n    pass\n\ndef bar(y={}):\n    pass\n"
        ))
        r = analyzer.analyze_file(p)
        assert r.total_functions == 2
        assert r.violation_count == 2

    def test_class_method(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, (
            "class Foo:\n"
            "    def bar(self, x=[]):\n"
            "        pass\n"
        ))
        r = analyzer.analyze_file(p)
        assert r.violation_count == 1
        assert r.violations[0].function_name == "bar"


class TestEdgeCases:
    def test_no_functions(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "x = 1\ny = 2\n")
        r = analyzer.analyze_file(p)
        assert r.total_functions == 0
        assert r.violation_count == 0
        assert r.is_clean

    def test_file_not_found(self, analyzer: MutableDefaultArgsAnalyzer) -> None:
        r = analyzer.analyze_file("/nonexistent/test.py")
        assert r.violation_count == 0

    def test_non_python_file(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = tmp_dir / "test.js"
        p.write_text("function foo(x = []) {}\n")
        r = analyzer.analyze_file(p)
        assert r.violation_count == 0

    def test_function_name_in_result(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def my_func(x=[]):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violations[0].function_name == "my_func"

    def test_parameter_name_in_result(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "def foo(items=[]):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violations[0].parameter_name == "items"

    def test_line_number(self, analyzer: MutableDefaultArgsAnalyzer, tmp_dir: Path) -> None:
        p = _write(tmp_dir, "\n\ndef foo(x=[]):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.violations[0].line_number == 3


class TestResultStructure:
    def test_dataclass_fields(self) -> None:
        v = MutableDefaultArg(
            line_number=5,
            function_name="foo",
            parameter_name="x",
            default_type="list",
            severity="high",
        )
        assert v.function_name == "foo"
        assert v.severity == "high"

    def test_is_clean(self) -> None:
        clean = MutableDefaultArgsResult(
            total_functions=1, violation_count=0,
            violations=(), file_path="test.py",
        )
        assert clean.is_clean

        dirty = MutableDefaultArgsResult(
            total_functions=1, violation_count=1,
            violations=(MutableDefaultArg(
                line_number=1, function_name="f",
                parameter_name="x", default_type="list",
                severity="high",
            ),),
            file_path="test.py",
        )
        assert not dirty.is_clean
