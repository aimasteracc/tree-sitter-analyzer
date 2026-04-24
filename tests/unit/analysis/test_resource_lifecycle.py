"""Tests for Resource Lifecycle Analyzer."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.resource_lifecycle import (
    RISK_HIGH,
    ResourceLifecycleAnalyzer,
)

ANALYZER = ResourceLifecycleAnalyzer()


class TestPythonResourceLifecycle:
    def test_unsafe_open(self, tmp_path: Path) -> None:
        code = (
            "def read_file(path):\n"
            "    f = open(path)\n"
            "    return f.read()\n"
        )
        f = tmp_path / "unsafe.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert len(result.issues) >= 1
        assert any(i.risk == RISK_HIGH for i in result.issues)

    def test_safe_with_open(self, tmp_path: Path) -> None:
        code = (
            "def read_file(path):\n"
            "    with open(path) as f:\n"
            "        return f.read()\n"
        )
        f = tmp_path / "safe.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert len(result.issues) == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER.analyze_file(f)
        assert len(result.issues) == 0

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert len(result.issues) == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.rb"
        f.write_text("File.open('x')")
        result = ANALYZER.analyze_file(f)
        assert len(result.issues) == 0


class TestJavaResourceLifecycle:
    def test_unsafe_stream(self, tmp_path: Path) -> None:
        code = (
            "public class Foo {\n"
            "  public void bar() {\n"
            "    new FileInputStream(\"data.txt\");\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Foo.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert len(result.issues) >= 1
        assert any(i.risk == RISK_HIGH for i in result.issues)
