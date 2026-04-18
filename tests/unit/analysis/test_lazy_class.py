"""Tests for Lazy Class Analyzer — Python + Multi-Language."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.lazy_class import (
    LazyClassAnalyzer,
    LazyClassResult,
    LazyClassInfo,
    _severity,
)

ANALYZER = LazyClassAnalyzer


# ── Severity tests ──────────────────────────────────────────────────────


class TestSeverity:
    def test_zero_methods_candidate(self) -> None:
        assert _severity(0, 1) == "removal_candidate"

    def test_one_method_lazy(self) -> None:
        assert _severity(1, 1) == "lazy"


# ── Dataclass tests ────────────────────────────────────────────────────


class TestDataclasses:
    def test_info_frozen(self) -> None:
        info = LazyClassInfo(
            class_name="Foo",
            line_number=1,
            method_count=0,
            field_count=1,
            severity="removal_candidate",
        )
        assert info.class_name == "Foo"
        with pytest.raises(AttributeError):
            info.class_name = "Bar"  # type: ignore[misc]

    def test_result_properties(self) -> None:
        result = LazyClassResult(
            total_classes=5,
            lazy_classes=(),
            file_path="test.py",
        )
        assert result.total_classes == 5

    def test_result_to_dict(self) -> None:
        result = LazyClassResult(
            total_classes=3,
            lazy_classes=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_classes"] == 3


# ── Edge case tests ────────────────────────────────────────────────────


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


# ── Python tests ───────────────────────────────────────────────────────


class TestPythonLazyClass:
    def test_no_classes(self, tmp_path: Path) -> None:
        f = tmp_path / "nopy.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 0

    def test_healthy_class_not_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "healthy.py"
        f.write_text(
            "class Service:\n"
            "    def __init__(self):\n"
            "        self.name = ''\n"
            "    def method_a(self):\n"
            "        pass\n"
            "    def method_b(self):\n"
            "        pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1
        assert len(result.lazy_classes) == 0

    def test_lazy_class_one_method(self, tmp_path: Path) -> None:
        f = tmp_path / "lazy.py"
        f.write_text(
            "class Config:\n"
            "    def get(self):\n"
            "        return self.value\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.lazy_classes) >= 1
        assert result.lazy_classes[0].severity == "lazy"

    def test_empty_class_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "empty_class.py"
        f.write_text("class Empty:\n    pass\n")
        result = ANALYZER().analyze_file(f)
        assert len(result.lazy_classes) >= 1
        assert result.lazy_classes[0].severity == "removal_candidate"

    def test_data_class_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "data.py"
        f.write_text(
            "class Data:\n"
            "    x = 1\n"
            "    y = 2\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 1

    def test_multiple_classes(self, tmp_path: Path) -> None:
        f = tmp_path / "multi.py"
        f.write_text(
            "class Lazy:\n    pass\n\n"
            "class Healthy:\n"
            "    def a(self): pass\n"
            "    def b(self): pass\n"
            "    def c(self): pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_classes == 2
        assert len(result.lazy_classes) >= 1


# ── JavaScript / TypeScript tests ──────────────────────────────────────


class TestJavaScriptLazyClass:
    def test_healthy_class(self, tmp_path: Path) -> None:
        f = tmp_path / "healthy.js"
        f.write_text(
            "class Service {\n"
            "  constructor() { this.name = ''; }\n"
            "  methodA() { return 1; }\n"
            "  methodB() { return 2; }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.lazy_classes) == 0

    def test_lazy_class(self, tmp_path: Path) -> None:
        f = tmp_path / "lazy.js"
        f.write_text(
            "class Config {\n"
            "  get() { return this.value; }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.lazy_classes) >= 1

    def test_typescript(self, tmp_path: Path) -> None:
        f = tmp_path / "test.ts"
        f.write_text("class Empty {}\n")
        result = ANALYZER().analyze_file(f)
        assert len(result.lazy_classes) >= 1


# ── Java tests ─────────────────────────────────────────────────────────


class TestJavaLazyClass:
    def test_healthy_class(self, tmp_path: Path) -> None:
        f = tmp_path / "Service.java"
        f.write_text(
            "public class Service {\n"
            "  private String name;\n"
            "  public void methodA() {}\n"
            "  public void methodB() {}\n"
            "  public void methodC() {}\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.lazy_classes) == 0

    def test_lazy_class(self, tmp_path: Path) -> None:
        f = tmp_path / "Config.java"
        f.write_text(
            "public class Config {\n"
            "  private String value;\n"
            "  public String get() { return value; }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.lazy_classes) >= 1

    def test_empty_class(self, tmp_path: Path) -> None:
        f = tmp_path / "Empty.java"
        f.write_text(
            "public class Empty {\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.lazy_classes) >= 1
        assert result.lazy_classes[0].severity == "removal_candidate"


# ── Go tests ───────────────────────────────────────────────────────────


class TestGoLazyClass:
    def test_healthy_struct(self, tmp_path: Path) -> None:
        f = tmp_path / "service.go"
        f.write_text(
            "package main\n\n"
            "type Service struct {\n"
            "    Name string\n"
            "    Age  int\n"
            "    Addr string\n"
            "}\n\n"
            "func (s *Service) MethodA() {}\n"
            "func (s *Service) MethodB() {}\n"
            "func (s *Service) MethodC() {}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_classes >= 1

    def test_lazy_struct(self, tmp_path: Path) -> None:
        f = tmp_path / "lazy.go"
        f.write_text(
            "package main\n\n"
            "type Config struct {\n"
            "    Value string\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_classes >= 1
