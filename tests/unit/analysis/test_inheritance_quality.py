"""Tests for Inheritance Quality Analyzer."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.inheritance_quality import (
    InheritanceQualityAnalyzer,
)

ANALYZER = InheritanceQualityAnalyzer()


class TestPythonInheritance:
    def test_missing_super_call(self, tmp_path: Path) -> None:
        code = (
            "class Base:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "\n"
            "class Child(Base):\n"
            "    def __init__(self):\n"
            "        self.y = 2\n"
        )
        f = tmp_path / "nosuper.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == "missing_super_call" for i in result.issues)

    def test_diamond_inheritance(self, tmp_path: Path) -> None:
        code = (
            "class A:\n"
            "    pass\n"
            "\n"
            "class B:\n"
            "    pass\n"
            "\n"
            "class C(A, B):\n"
            "    pass\n"
        )
        f = tmp_path / "diamond.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == "diamond_inheritance" for i in result.issues)

    def test_empty_override(self, tmp_path: Path) -> None:
        code = (
            "class Base:\n"
            "    def greet(self):\n"
            "        return 'hello'\n"
            "\n"
            "class Child(Base):\n"
            "    def greet(self):\n"
            "        super().greet()\n"
        )
        f = tmp_path / "override.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == "empty_override" for i in result.issues)

    def test_no_issues(self, tmp_path: Path) -> None:
        code = (
            "class Animal:\n"
            "    def speak(self):\n"
            "        return '...'\n"
            "\n"
            "class Dog(Animal):\n"
            "    def speak(self):\n"
            "        return 'woof'\n"
        )
        f = tmp_path / "clean.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_classes == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER.analyze_file(f)
        assert result.total_classes == 0
