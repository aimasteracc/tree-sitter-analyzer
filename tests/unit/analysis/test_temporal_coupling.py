"""Tests for TemporalCouplingAnalyzer."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.temporal_coupling import (
    ISSUE_TEMPORAL_COUPLING,
    TemporalCouplingAnalyzer,
    TemporalCouplingIssue,
    TemporalCouplingResult,
)


@pytest.fixture
def analyzer() -> TemporalCouplingAnalyzer:
    return TemporalCouplingAnalyzer()


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
        p = tmp_path / "test_module.go"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    return _create


class TestTemporalCouplingIssue:
    def test_to_dict(self) -> None:
        issue = TemporalCouplingIssue(
            line_number=10,
            issue_type=ISSUE_TEMPORAL_COUPLING,
            severity="medium",
            description="desc",
            reader_method="process",
            writer_method="init",
            variable_name="data",
        )
        d = issue.to_dict()
        assert d["line_number"] == 10
        assert d["issue_type"] == ISSUE_TEMPORAL_COUPLING
        assert d["reader_method"] == "process"
        assert d["writer_method"] == "init"
        assert d["variable_name"] == "data"
        assert "suggestion" in d

    def test_frozen(self) -> None:
        issue = TemporalCouplingIssue(
            line_number=1,
            issue_type=ISSUE_TEMPORAL_COUPLING,
            severity="medium",
            description="desc",
            reader_method="a",
            writer_method="b",
            variable_name="x",
        )
        with pytest.raises(AttributeError):
            issue.line_number = 2  # type: ignore[misc]


class TestTemporalCouplingResult:
    def test_to_dict_empty(self) -> None:
        result = TemporalCouplingResult(file_path="test.py")
        d = result.to_dict()
        assert d["file_path"] == "test.py"
        assert d["total_classes"] == 0
        assert d["issue_count"] == 0
        assert d["issues"] == []


class TestPythonTemporalCoupling:
    def test_basic_temporal_coupling(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Service:
                def configure(self):
                    self.data = [1, 2, 3]

                def process(self):
                    return sum(self.data)
        """)
        result = analyzer.analyze_file(str(p))
        assert result.total_classes == 1
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.reader_method == "process"
        assert issue.writer_method == "configure"
        assert issue.variable_name == "data"

    def test_no_coupling_when_both_read_write(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Service:
                def method_a(self):
                    self.data = [1, 2, 3]

                def method_b(self):
                    self.data = []
                    return sum(self.data)
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 0

    def test_init_not_flagged(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Service:
                def __init__(self):
                    self.data = []

                def configure(self):
                    self.data = [1, 2, 3]

                def process(self):
                    return sum(self.data)
        """)
        result = analyzer.analyze_file(str(p))
        assert result.total_classes == 1
        assert len(result.issues) == 1
        assert result.issues[0].reader_method == "process"
        assert result.issues[0].writer_method == "configure"

    def test_multiple_writers_no_coupling(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Service:
                def method_a(self):
                    self.data = [1]

                def method_b(self):
                    self.data = [2]

                def process(self):
                    return sum(self.data)
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 0

    def test_augmented_assignment_is_write(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Counter:
                def increment(self):
                    self.count += 1

                def get(self):
                    return self.count
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 1
        assert result.issues[0].reader_method == "get"
        assert result.issues[0].writer_method == "increment"
        assert result.issues[0].variable_name == "count"

    def test_self_in_nested_scope(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Service:
                def configure(self):
                    self.items = []

                def process(self):
                    return [x for x in self.items if x > 0]
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 1
        assert result.issues[0].variable_name == "items"

    def test_empty_class(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Empty:
                pass
        """)
        result = analyzer.analyze_file(str(p))
        assert result.total_classes == 1
        assert len(result.issues) == 0

    def test_single_method_no_coupling(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Single:
                def only_method(self):
                    self.x = 1
                    return self.x
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 0

    def test_no_self_access(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Pure:
                def compute(self, x):
                    return x * 2

                def compute2(self, y):
                    return y + 1
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 0

    def test_line_number_populated(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Service:
                def configure(self):
                    self.data = [1, 2, 3]

                def process(self):
                    return sum(self.data)
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 1
        assert result.issues[0].line_number > 0


class TestJSTemporalCoupling:
    def test_basic_js_coupling(self, analyzer, tmp_js_file) -> None:
        p = tmp_js_file("""\
            class Service {
                configure() {
                    this.data = [1, 2, 3];
                }
                process() {
                    return this.data.reduce((a, b) => a + b, 0);
                }
            }
        """)
        result = analyzer.analyze_file(str(p))
        assert result.total_classes == 1
        assert len(result.issues) == 1
        assert result.issues[0].reader_method == "process"
        assert result.issues[0].writer_method == "configure"
        assert result.issues[0].variable_name == "data"

    def test_constructor_excluded(self, analyzer, tmp_js_file) -> None:
        p = tmp_js_file("""\
            class Service {
                constructor() {
                    this.data = [];
                }
                process() {
                    return this.data.length;
                }
            }
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 0

    def test_no_coupling_in_js(self, analyzer, tmp_js_file) -> None:
        p = tmp_js_file("""\
            class Service {
                setX(val) { this.x = val; }
                setY(val) { this.y = val; }
            }
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 0


class TestJavaTemporalCoupling:
    def test_basic_java_coupling(self, analyzer, tmp_java_file) -> None:
        p = tmp_java_file("""\
            public class Service {
                private int count;

                public void increment() {
                    this.count = this.count + 1;
                }

                public int getCount() {
                    return this.count;
                }
            }
        """)
        result = analyzer.analyze_file(str(p))
        assert result.total_classes == 1
        assert len(result.issues) == 1
        assert result.issues[0].reader_method == "getCount"
        assert result.issues[0].writer_method == "increment"
        assert result.issues[0].variable_name == "count"

    def test_java_constructor_excluded(self, analyzer, tmp_java_file) -> None:
        p = tmp_java_file("""\
            public class Service {
                private String name;

                public Service(String name) {
                    this.name = name;
                }

                public String getName() {
                    return this.name;
                }
            }
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 0


class TestGoTemporalCoupling:
    def test_basic_go_coupling(self, analyzer, tmp_go_file) -> None:
        p = tmp_go_file("""\
            package main

            type Service struct {
                data []int
            }

            func (s *Service) Configure() {
                s.data = []int{1, 2, 3}
            }

            func (s *Service) Process() int {
                total := 0
                for _, v := range s.data {
                    total += v
                }
                return total
            }
        """)
        result = analyzer.analyze_file(str(p))
        assert result.total_classes == 1
        assert len(result.issues) == 1
        assert result.issues[0].reader_method == "Process"
        assert result.issues[0].writer_method == "Configure"
        assert result.issues[0].variable_name == "data"

    def test_no_go_coupling(self, analyzer, tmp_go_file) -> None:
        p = tmp_go_file("""\
            package main

            type Service struct{}

            func (s *Service) A() { s.x = 1 }
            func (s *Service) B() { s.x = 2 }
            func (s *Service) C() { return s.x }
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 0


class TestEdgeCases:
    def test_multiple_classes(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class A:
                def set_val(self):
                    self.val = 10

                def get_val(self):
                    return self.val

            class B:
                def compute(self, x):
                    return x * 2
        """)
        result = analyzer.analyze_file(str(p))
        assert result.total_classes == 2
        assert len(result.issues) == 1
        assert result.issues[0].reader_method == "get_val"

    def test_reader_writes_other_var(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Service:
                def setup(self):
                    self.data = []

                def process(self):
                    self.result = sum(self.data)
                    return self.result
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 1
        assert result.issues[0].variable_name == "data"
        assert result.issues[0].reader_method == "process"

    def test_post_init_excluded(self, analyzer, tmp_py_file) -> None:
        p = tmp_py_file("""\
            class Service:
                def __post_init__(self):
                    self.data = []

                def configure(self):
                    self.data = [1, 2]

                def process(self):
                    return self.data
        """)
        result = analyzer.analyze_file(str(p))
        assert len(result.issues) == 1
        assert result.issues[0].reader_method == "process"
