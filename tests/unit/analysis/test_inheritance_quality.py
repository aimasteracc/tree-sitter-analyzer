"""Tests for Inheritance Quality Analyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.inheritance_quality import (
    SEVERITY_HIGH,
    SEVERITY_INFO,
    SEVERITY_MEDIUM,
    InheritanceQualityAnalyzer,
)


@pytest.fixture
def analyzer() -> InheritanceQualityAnalyzer:
    return InheritanceQualityAnalyzer(depth_threshold=3)


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# ── Empty / non-existent files ─────────────────────────────────────────


class TestEmptyAndEdgeCases:
    def test_nonexistent_file(self, analyzer: InheritanceQualityAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_classes == 0
        assert result.total_issues == 0

    def test_empty_file(self, analyzer: InheritanceQualityAnalyzer) -> None:
        path = _write_tmp("")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 0
        finally:
            path.unlink()

    def test_unsupported_extension(self, analyzer: InheritanceQualityAnalyzer) -> None:
        path = _write_tmp("class Foo", suffix=".rb")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 0
        finally:
            path.unlink()

    def test_file_no_classes(self, analyzer: InheritanceQualityAnalyzer) -> None:
        path = _write_tmp("x = 1\ny = 2\n")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 0
            assert result.total_issues == 0
        finally:
            path.unlink()


# ── Python: deep inheritance ───────────────────────────────────────────


class TestPythonDeepInheritance:
    def test_single_class_no_issue(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = "class Foo:\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 1
            deep_issues = result.get_issues_by_type("deep_inheritance")
            assert len(deep_issues) == 0
        finally:
            path.unlink()

    def test_two_levels_no_issue(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Base:\n    pass\n\n"
            "class Child(Base):\n    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            deep_issues = result.get_issues_by_type("deep_inheritance")
            assert len(deep_issues) == 0
        finally:
            path.unlink()

    def test_deep_inheritance_detected(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class A:\n    pass\n\n"
            "class B(A):\n    pass\n\n"
            "class C(B):\n    pass\n\n"
            "class D(C):\n    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 4
            deep_issues = result.get_issues_by_type("deep_inheritance")
            assert len(deep_issues) >= 1
            assert deep_issues[0].severity == SEVERITY_HIGH
            assert "D" in deep_issues[0].class_name
        finally:
            path.unlink()

    def test_custom_depth_threshold(self) -> None:
        code = (
            "class A:\n    pass\n\n"
            "class B(A):\n    pass\n\n"
            "class C(B):\n    pass\n"
        )
        path = _write_tmp(code)
        try:
            a = InheritanceQualityAnalyzer(depth_threshold=2)
            result = a.analyze_file(path)
            deep = result.get_issues_by_type("deep_inheritance")
            assert len(deep) >= 1
        finally:
            path.unlink()

    def test_inheritance_chain_in_message(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class A:\n    pass\n\n"
            "class B(A):\n    pass\n\n"
            "class C(B):\n    pass\n\n"
            "class D(C):\n    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            deep = result.get_issues_by_type("deep_inheritance")
            assert len(deep) >= 1
            assert "->" in deep[0].detail
        finally:
            path.unlink()


# ── Python: missing super call ─────────────────────────────────────────


class TestPythonMissingSuper:
    def test_no_init_no_issue(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = "class Child(Base):\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            super_issues = result.get_issues_by_type("missing_super_call")
            assert len(super_issues) == 0
        finally:
            path.unlink()

    def test_init_with_super_no_issue(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Base:\n    def __init__(self):\n        pass\n\n"
            "class Child(Base):\n"
            "    def __init__(self):\n"
            "        super().__init__()\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            super_issues = result.get_issues_by_type("missing_super_call")
            assert len(super_issues) == 0
        finally:
            path.unlink()

    def test_init_without_super_detected(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Base:\n    def __init__(self):\n        pass\n\n"
            "class Child(Base):\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            super_issues = result.get_issues_by_type("missing_super_call")
            assert len(super_issues) == 1
            assert super_issues[0].severity == SEVERITY_MEDIUM
            assert "Child" in super_issues[0].class_name
        finally:
            path.unlink()

    def test_no_parent_no_issue(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Standalone:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            super_issues = result.get_issues_by_type("missing_super_call")
            assert len(super_issues) == 0
        finally:
            path.unlink()


# ── Python: diamond inheritance ────────────────────────────────────────


class TestPythonDiamond:
    def test_multiple_inheritance_detected(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class A:\n    pass\n\n"
            "class B:\n    pass\n\n"
            "class C(A, B):\n    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            diamond = result.get_issues_by_type("diamond_inheritance")
            assert len(diamond) == 1
            assert diamond[0].severity == SEVERITY_INFO
            assert "C" in diamond[0].class_name
        finally:
            path.unlink()

    def test_single_inheritance_no_diamond(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = "class Child(Base):\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            diamond = result.get_issues_by_type("diamond_inheritance")
            assert len(diamond) == 0
        finally:
            path.unlink()


# ── Python: empty override ─────────────────────────────────────────────


class TestPythonEmptyOverride:
    def test_empty_override_detected(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Base:\n"
            "    def process(self):\n"
            "        pass\n\n"
            "class Child(Base):\n"
            "    def process(self):\n"
            "        super().process()\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            empty = result.get_issues_by_type("empty_override")
            assert len(empty) == 1
            assert empty[0].severity == SEVERITY_INFO
            assert "process" in empty[0].message
        finally:
            path.unlink()

    def test_override_with_logic_no_issue(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Base:\n"
            "    def process(self):\n"
            "        pass\n\n"
            "class Child(Base):\n"
            "    def process(self):\n"
            "        super().process()\n"
            "        self.extra = True\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            empty = result.get_issues_by_type("empty_override")
            assert len(empty) == 0
        finally:
            path.unlink()

    def test_pass_body_no_override_issue(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Base:\n"
            "    def process(self):\n"
            "        pass\n\n"
            "class Child(Base):\n"
            "    def process(self):\n"
            "        pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            empty = result.get_issues_by_type("empty_override")
            assert len(empty) == 0
        finally:
            path.unlink()


# ── Python: decorated classes ──────────────────────────────────────────


class TestPythonDecorators:
    def test_decorated_class_detected(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "@dataclass\n"
            "class MyClass(Base):\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 1
            assert result.classes[0].name == "MyClass"
            super_issues = result.get_issues_by_type("missing_super_call")
            assert len(super_issues) == 1
        finally:
            path.unlink()


# ── JavaScript / TypeScript ────────────────────────────────────────────


class TestJavaScript:
    def test_js_deep_inheritance(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class A {}\n\n"
            "class B extends A {}\n\n"
            "class C extends B {}\n\n"
            "class D extends C {}\n"
        )
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 4
            deep = result.get_issues_by_type("deep_inheritance")
            assert len(deep) >= 1
        finally:
            path.unlink()

    def test_js_missing_super_in_constructor(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Base {\n"
            "    constructor() {}\n"
            "}\n\n"
            "class Child extends Base {\n"
            "    constructor() {\n"
            "        this.x = 1;\n"
            "    }\n"
            "}\n"
        )
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            super_issues = result.get_issues_by_type("missing_super_call")
            assert len(super_issues) == 1
        finally:
            path.unlink()

    def test_ts_extends(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Base {}\n\n"
            "class Child extends Base {}\n"
        )
        path = _write_tmp(code, suffix=".ts")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 2
        finally:
            path.unlink()

    def test_js_no_class_no_issues(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = "const x = 1;\nfunction foo() { return x; }\n"
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 0
        finally:
            path.unlink()


# ── Java ───────────────────────────────────────────────────────────────


class TestJava:
    def test_java_extends(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Base {\n"
            "    void process() {}\n"
            "}\n\n"
            "class Child extends Base {\n"
            "    void process() {\n"
            "        super.process();\n"
            "    }\n"
            "}\n"
        )
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 2
            empty = result.get_issues_by_type("empty_override")
            assert len(empty) == 1
        finally:
            path.unlink()

    def test_java_constructor_super(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class Base {\n"
            "    Base(int x) {}\n"
            "}\n\n"
            "class Child extends Base {\n"
            "    Child(int x) {\n"
            "        super(x);\n"
            "    }\n"
            "}\n"
        )
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            super_issues = result.get_issues_by_type("missing_super_call")
            assert len(super_issues) == 0
        finally:
            path.unlink()

    def test_java_implements(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "interface Runnable {\n"
            "    void run();\n"
            "}\n\n"
            "class Task implements Runnable {\n"
            "    public void run() {}\n"
            "}\n"
        )
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes >= 1
        finally:
            path.unlink()


# ── Go ─────────────────────────────────────────────────────────────────


class TestGo:
    def test_go_struct_embedding(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            'package main\n\n'
            'type Base struct {\n'
            '    Name string\n'
            '}\n\n'
            'type Child struct {\n'
            '    Base\n'
            '    Age int\n'
            '}\n'
        )
        path = _write_tmp(code, suffix=".go")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 2
        finally:
            path.unlink()

    def test_go_no_struct_no_issues(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            'package main\n\n'
            'func main() {\n'
            '    fmt.Println("hello")\n'
            '}\n'
        )
        path = _write_tmp(code, suffix=".go")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_classes == 0
        finally:
            path.unlink()


# ── Result filtering ───────────────────────────────────────────────────


class TestResultFiltering:
    def test_get_issues_by_severity(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class A:\n    pass\n\n"
            "class B:\n    pass\n\n"
            "class C(A, B):\n    pass\n\n"
            "class D(C):\n    pass\n\n"
            "class E(D):\n    pass\n\n"
            "class F(E):\n    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            high = result.get_issues_by_severity(SEVERITY_HIGH)
            info = result.get_issues_by_severity(SEVERITY_INFO)
            assert len(high) >= 1
            assert len(info) >= 1
        finally:
            path.unlink()

    def test_high_severity_count(self, analyzer: InheritanceQualityAnalyzer) -> None:
        code = (
            "class A:\n    pass\n\n"
            "class B(A):\n    pass\n\n"
            "class C(B):\n    pass\n\n"
            "class D(C):\n    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.high_severity_count >= 1
        finally:
            path.unlink()
