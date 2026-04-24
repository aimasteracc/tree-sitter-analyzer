"""Tests for MethodCohesionAnalyzer — Python, JS/TS, Java, Go."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.method_cohesion import (
    ISSUE_LOW_COHESION,
    MethodCohesionAnalyzer,
)


@pytest.fixture
def analyzer() -> MethodCohesionAnalyzer:
    return MethodCohesionAnalyzer()


def _write(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


# -- Python Tests ---------------------------------------------------------


class TestPythonCohesion:
    def test_low_cohesion_detected(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo:
            def __init__(self):
                self.x = 1
                self.y = 2

            def do_x(self):
                self.x += 1

            def do_y(self):
                self.y += 1
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_classes == 1
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.issue_type == ISSUE_LOW_COHESION
        assert issue.class_name == "Foo"
        assert issue.lcom4 == 2

    def test_cohesive_class_not_flagged(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo:
            def __init__(self):
                self.x = 1

            def inc_x(self):
                self.x += 1

            def get_x(self):
                return self.x
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_classes == 1
        assert len(result.issues) == 0

    def test_no_self_access(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo:
            def method_a(self):
                return 1

            def method_b(self):
                return 2
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_classes == 1
        assert len(result.issues) == 0

    def test_single_method_class(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo:
            def __init__(self):
                self.x = 1
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_classes == 1
        assert len(result.issues) == 0

    def test_three_component_split(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class KitchenSink:
            def __init__(self):
                self.a = 0
                self.b = 0
                self.c = 0

            def use_a(self):
                self.a = 1

            def use_b(self):
                self.b = 2

            def use_c(self):
                self.c = 3
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 1
        assert result.issues[0].lcom4 == 3

    def test_multiple_classes(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Cohesive:
            def __init__(self):
                self.x = 0

            def inc(self):
                self.x += 1

        class Split:
            def __init__(self):
                self.a = 0
                self.b = 0

            def use_a(self):
                self.a = 1

            def use_b(self):
                self.b = 2
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_classes == 2
        assert len(result.issues) == 1
        assert result.issues[0].class_name == "Split"

    def test_bridge_method_cohesion(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo:
            def __init__(self):
                self.x = 1
                self.y = 2

            def use_x(self):
                self.x += 1

            def use_both(self):
                self.x += self.y
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 0

    def test_no_class(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        def foo():
            pass
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_classes == 0
        assert len(result.issues) == 0

    def test_issue_to_dict(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo:
            def __init__(self):
                self.x = 1
                self.y = 2

            def use_x(self):
                self.x = 3

            def use_y(self):
                self.y = 4
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        d = result.issues[0].to_dict()
        assert d["class_name"] == "Foo"
        assert d["lcom4"] == 2
        assert d["method_count"] == 2
        assert d["component_count"] == 2
        assert "suggestion" in d


# -- JavaScript/TypeScript Tests -----------------------------------------


class TestJSCohesion:
    def test_js_low_cohesion(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo {
            constructor() {
                this.x = 1;
                this.y = 2;
            }
            useX() {
                this.x += 1;
            }
            useY() {
                this.y += 1;
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        assert result.total_classes == 1
        assert len(result.issues) == 1
        assert result.issues[0].lcom4 == 2

    def test_js_cohesive(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo {
            constructor() {
                this.x = 1;
            }
            inc() {
                this.x += 1;
            }
            get() {
                return this.x;
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        assert len(result.issues) == 0

    def test_ts_low_cohesion(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo {
            x: number = 0;
            y: number = 0;
            useX() {
                this.x = 1;
            }
            useY() {
                this.y = 2;
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.ts", code))
        assert len(result.issues) == 1
        assert result.issues[0].class_name == "Foo"

    def test_jsx_support(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo extends Bar {
            constructor() {
                super();
                this.a = 1;
                this.b = 2;
            }
            useA() { this.a = 3; }
            useB() { this.b = 4; }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.jsx", code))
        assert len(result.issues) == 1

    def test_tsx_support(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo {
            x: number = 0;
            y: number = 0;
            useX() { this.x = 1; }
            useY() { this.y = 2; }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.tsx", code))
        assert len(result.issues) == 1

    def test_js_no_class(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        function foo() { return 1; }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        assert result.total_classes == 0
        assert len(result.issues) == 0


# -- Java Tests -----------------------------------------------------------


class TestJavaCohesion:
    def test_java_low_cohesion(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        public class Foo {
            private int x;
            private int y;

            public void useX() {
                this.x = 1;
            }

            public void useY() {
                this.y = 2;
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "Foo.java", code))
        assert result.total_classes == 1
        assert len(result.issues) == 1
        assert result.issues[0].lcom4 == 2
        assert result.issues[0].class_name == "Foo"

    def test_java_cohesive(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        public class Foo {
            private int x;

            public void inc() {
                this.x += 1;
            }

            public int get() {
                return this.x;
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "Foo.java", code))
        assert len(result.issues) == 0

    def test_java_bridge_method(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        public class Foo {
            private int x;
            private int y;

            public void useX() { this.x = 1; }
            public void useBoth() { this.x = this.y; }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "Foo.java", code))
        assert len(result.issues) == 0

    def test_java_no_this_access(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        public class Foo {
            public void methodA() { return; }
            public void methodB() { return; }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "Foo.java", code))
        assert len(result.issues) == 0


# -- Go Tests -------------------------------------------------------------


class TestGoCohesion:
    def test_go_low_cohesion(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        package main

        type Foo struct {
            x int
            y int
        }

        func (f *Foo) useX() {
            f.x = 1
        }

        func (f *Foo) useY() {
            f.y = 2
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.go", code))
        assert result.total_classes >= 1
        assert len(result.issues) == 1
        assert result.issues[0].lcom4 == 2

    def test_go_cohesive(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        package main

        type Foo struct {
            x int
        }

        func (f *Foo) inc() {
            f.x += 1
        }

        func (f *Foo) get() int {
            return f.x
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.go", code))
        assert len(result.issues) == 0

    def test_go_single_method(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        package main

        type Foo struct {
            x int
        }

        func (f *Foo) inc() {
            f.x += 1
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.go", code))
        assert len(result.issues) == 0


# -- Edge Cases -----------------------------------------------------------


class TestEdgeCases:
    def test_file_not_found(
        self, analyzer: MethodCohesionAnalyzer,
    ) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_classes == 0
        assert len(result.issues) == 0

    def test_unsupported_extension(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        p = tmp_path / "a.rb"
        p.write_text("class Foo; end")
        result = analyzer.analyze_file(p)
        assert result.total_classes == 0

    def test_empty_file(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        p = tmp_path / "a.py"
        p.write_text("")
        result = analyzer.analyze_file(p)
        assert result.total_classes == 0
        assert len(result.issues) == 0

    def test_result_to_dict(
        self, analyzer: MethodCohesionAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Foo:
            def __init__(self):
                self.x = 1
                self.y = 2

            def use_x(self):
                self.x = 3

            def use_y(self):
                self.y = 4
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        d = result.to_dict()
        assert "file_path" in d
        assert "total_classes" in d
        assert "issues" in d
        assert d["total_classes"] == 1
