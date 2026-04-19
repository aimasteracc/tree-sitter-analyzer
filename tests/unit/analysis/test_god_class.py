"""Tests for God Class Detector — Python + Multi-Language."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.god_class import (
    ISSUE_GOD_CLASS,
    ISSUE_LARGE_CLASS,
    ISSUE_LOW_COHESION,
    ClassStats,
    GodClassAnalyzer,
    GodClassIssue,
    GodClassResult,
    _classify_issue,
)

ANALYZER = GodClassAnalyzer


# ── Classification tests ──────────────────────────────────────────────────


class TestClassification:
    def test_god_class(self) -> None:
        assert _classify_issue(10, 8) == ISSUE_GOD_CLASS

    def test_god_class_higher(self) -> None:
        assert _classify_issue(20, 15) == ISSUE_GOD_CLASS

    def test_large_class(self) -> None:
        assert _classify_issue(7, 5) == ISSUE_LARGE_CLASS

    def test_large_class_nine_methods(self) -> None:
        assert _classify_issue(9, 6) == ISSUE_LARGE_CLASS

    def test_healthy_class(self) -> None:
        assert _classify_issue(3, 2) is None

    def test_many_methods_few_fields(self) -> None:
        assert _classify_issue(12, 3) is None

    def test_few_methods_many_fields(self) -> None:
        assert _classify_issue(4, 12) is None

    def test_boundary_god_class(self) -> None:
        assert _classify_issue(10, 8) == ISSUE_GOD_CLASS

    def test_boundary_large_class(self) -> None:
        assert _classify_issue(7, 5) == ISSUE_LARGE_CLASS

    def test_just_below_large_class(self) -> None:
        assert _classify_issue(6, 5) is None


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = GodClassIssue(
            class_name="Foo",
            line_number=1,
            issue_type=ISSUE_GOD_CLASS,
            method_count=10,
            field_count=8,
            severity="high",
        )
        assert issue.class_name == "Foo"
        with pytest.raises(AttributeError):
            issue.class_name = "Bar"  # type: ignore[misc]

    def test_issue_to_dict(self) -> None:
        issue = GodClassIssue(
            class_name="Foo",
            line_number=1,
            issue_type=ISSUE_GOD_CLASS,
            method_count=10,
            field_count=8,
            severity="high",
        )
        d = issue.to_dict()
        assert d["class_name"] == "Foo"
        assert d["issue_type"] == ISSUE_GOD_CLASS
        assert "description" in d
        assert "suggestion" in d

    def test_issue_properties(self) -> None:
        issue = GodClassIssue(
            class_name="A",
            line_number=1,
            issue_type=ISSUE_GOD_CLASS,
            method_count=10,
            field_count=8,
            severity="high",
        )
        assert len(issue.description) > 0
        assert len(issue.suggestion) > 0

    def test_stats_to_dict(self) -> None:
        stats = ClassStats(
            class_name="B",
            line_number=1,
            method_count=5,
            field_count=3,
        )
        d = stats.to_dict()
        assert d["method_count"] == 5

    def test_result_to_dict(self) -> None:
        result = GodClassResult(
            total_classes=3,
            issues=(),
            class_stats=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_classes"] == 3
        assert d["issue_count"] == 0


# ── Edge case tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        result = ANALYZER().analyze_file("/nonexistent/file.py")
        assert result.total_classes == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.rb"
        f.write_text("class Foo; end")
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 0

    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_classes == 0


# ── Python tests ─────────────────────────────────────────────────────────


class TestPythonGodClass:
    def test_no_classes(self, tmp_path: Path) -> None:
        f = tmp_path / "nopy.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 0

    def test_healthy_class_not_flagged(self, tmp_path: Path) -> None:
        code = (
            "class Healthy:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "    def method_a(self):\n"
            "        pass\n"
            "    def method_b(self):\n"
            "        pass\n"
        )
        f = tmp_path / "healthy.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        assert len(result.issues) == 0

    def test_god_class_detected(self, tmp_path: Path) -> None:
        methods = "\n".join(f"    def m{i}(self): pass" for i in range(12))
        fields = "\n".join(f"        self.f{i} = {i}" for i in range(9))
        code = f"class GodClass:\n    def __init__(self):\n{fields}\n{methods}\n"
        f = tmp_path / "god.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        assert len(result.issues) >= 1
        assert any(i.issue_type == ISSUE_GOD_CLASS for i in result.issues)

    def test_large_class_detected(self, tmp_path: Path) -> None:
        methods = "\n".join(f"    def m{i}(self): pass" for i in range(8))
        fields = "\n".join(f"        self.f{i} = {i}" for i in range(6))
        code = f"class LargeClass:\n    def __init__(self):\n{fields}\n{methods}\n"
        f = tmp_path / "large.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        assert any(i.issue_type == ISSUE_LARGE_CLASS for i in result.issues)

    def test_low_cohesion_detected(self, tmp_path: Path) -> None:
        methods = "\n".join(f"    def m{i}(self): pass" for i in range(8))
        fields = "\n".join(f"        self.f{i} = {i}" for i in range(3))
        code = f"class LowCohesion:\n    def __init__(self):\n{fields}\n{methods}\n"
        f = tmp_path / "low_cohesion.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_LOW_COHESION for i in result.issues)

    def test_multiple_classes(self, tmp_path: Path) -> None:
        code = (
            "class A:\n"
            "    def ma(self): pass\n"
            "class B:\n"
            "    def mb(self): pass\n"
        )
        f = tmp_path / "multi.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 2
        assert len(result.issues) == 0

    def test_class_stats_recorded(self, tmp_path: Path) -> None:
        code = (
            "class MyClass:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "    def method_a(self):\n"
            "        pass\n"
        )
        f = tmp_path / "stats.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert len(result.class_stats) == 1
        assert result.class_stats[0].class_name == "MyClass"

    def test_nested_class(self, tmp_path: Path) -> None:
        methods = "\n".join(f"        def m{i}(self): pass" for i in range(11))
        fields = "\n".join(f"            self.f{i} = {i}" for i in range(9))
        code = (
            "class Outer:\n"
            "    def __init__(self):\n"
            "        self.outer_field = 1\n"
            "    def outer_method(self):\n"
            "        pass\n"
            "    class Inner:\n"
            "        def __init__(self):\n"
            f"{fields}\n"
            f"{methods}\n"
        )
        f = tmp_path / "nested.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 2


# ── JavaScript/TypeScript tests ──────────────────────────────────────────


class TestJavaScriptGodClass:
    def test_healthy_js_class(self, tmp_path: Path) -> None:
        code = (
            "class Healthy {\n"
            "  constructor() { this.x = 1; }\n"
            "  methodA() {}\n"
            "  methodB() {}\n"
            "}\n"
        )
        f = tmp_path / "healthy.js"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        assert len(result.issues) == 0

    def test_god_class_js(self, tmp_path: Path) -> None:
        methods = "\n".join(f"  m{i}() {{}}" for i in range(11))
        fields = "\n".join(f"  f{i} = {i};" for i in range(9))
        code = f"class GodClass {{\n  constructor() {{}}\n{fields}\n{methods}\n}}\n"
        f = tmp_path / "god.js"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        assert any(i.issue_type == ISSUE_GOD_CLASS for i in result.issues)

    def test_typescript_class(self, tmp_path: Path) -> None:
        methods = "\n".join(f"  m{i}() {{}}" for i in range(11))
        fields = "\n".join(f"  f{i}: number = {i};" for i in range(9))
        code = f"class GodClass {{\n{fields}\n{methods}\n}}\n"
        f = tmp_path / "god.ts"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        assert any(i.issue_type == ISSUE_GOD_CLASS for i in result.issues)


# ── Java tests ────────────────────────────────────────────────────────────


class TestJavaGodClass:
    def test_healthy_java_class(self, tmp_path: Path) -> None:
        code = (
            "public class Healthy {\n"
            "  private int x;\n"
            "  public void methodA() {}\n"
            "  public void methodB() {}\n"
            "}\n"
        )
        f = tmp_path / "Healthy.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        assert len(result.issues) == 0

    def test_god_class_java(self, tmp_path: Path) -> None:
        fields = "\n".join(f"  private int f{i};" for i in range(9))
        methods = "\n".join(f"  public void m{i}() {{}}" for i in range(11))
        code = f"public class GodClass {{\n{fields}\n{methods}\n}}\n"
        f = tmp_path / "GodClass.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        assert any(i.issue_type == ISSUE_GOD_CLASS for i in result.issues)

    def test_java_constructor_counts_as_method(self, tmp_path: Path) -> None:
        fields = "\n".join(f"  private int f{i};" for i in range(9))
        methods = "\n".join(f"  public void m{i}() {{}}" for i in range(10))
        code = (
            f"public class WithConstructor {{\n"
            f"{fields}\n"
            f"  public WithConstructor() {{}}\n"
            f"{methods}\n"
            f"}}\n"
        )
        f = tmp_path / "WithConstructor.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        god_issues = [i for i in result.issues if i.issue_type == ISSUE_GOD_CLASS]
        assert len(god_issues) >= 1


# ── Go tests ──────────────────────────────────────────────────────────────


class TestGoGodClass:
    def test_healthy_go_struct(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'type Small struct {\n'
            '    x int\n'
            '    y int\n'
            '}\n\n'
            'func (s *Small) MethodA() {}\n'
            'func (s *Small) MethodB() {}\n'
        )
        f = tmp_path / "small.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1

    def test_god_class_go(self, tmp_path: Path) -> None:
        """Go methods are declared at file level with receiver type."""
        fields = "\n".join(f"    f{i} int" for i in range(9))
        methods = "\n".join(
            f"func (g *GodStruct) M{i}() {{}}" for i in range(11)
        )
        code = (
            'package main\n\n'
            f'type GodStruct struct {{\n{fields}\n}}\n\n'
            f'{methods}\n'
        )
        f = tmp_path / "god.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        god_issues = [i for i in result.issues if i.issue_type == ISSUE_GOD_CLASS]
        assert len(god_issues) >= 1
        assert god_issues[0].class_name == "GodStruct"


# ── Line number tests ────────────────────────────────────────────────────


class TestLineNumbers:
    def test_correct_line_numbers(self, tmp_path: Path) -> None:
        code = (
            "# comment\n"
            "# comment\n"
            "class GodClass:\n"
            "    def __init__(self):\n"
            + "\n".join(f"        self.f{i} = {i}" for i in range(9))
            + "\n"
            + "\n".join(f"    def m{i}(self): pass" for i in range(11))
            + "\n"
        )
        f = tmp_path / "lines.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        god_issues = [i for i in result.issues if i.issue_type == ISSUE_GOD_CLASS]
        assert len(god_issues) >= 1
        assert god_issues[0].line_number == 3
