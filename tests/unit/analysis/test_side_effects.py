"""Tests for Side Effect Analyzer."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.side_effects import (
    ISSUE_GLOBAL_MUTATION,
    ISSUE_PARAMETER_MUTATION,
    SideEffectAnalyzer,
)

ANALYZER = SideEffectAnalyzer()


class TestPythonSideEffects:
    def test_global_state_mutation(self, tmp_path: Path) -> None:
        code = (
            "counter = 0\n"
            "\n"
            "def increment():\n"
            "    global counter\n"
            "    counter += 1\n"
        )
        f = tmp_path / "global.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_GLOBAL_MUTATION for i in result.issues)

    def test_parameter_mutation(self, tmp_path: Path) -> None:
        code = (
            "def update_name(item):\n"
            "    item.name = 'new_name'\n"
        )
        f = tmp_path / "param.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_PARAMETER_MUTATION for i in result.issues)

    def test_clean_function(self, tmp_path: Path) -> None:
        code = (
            "def add(a, b):\n"
            "    return a + b\n"
        )
        f = tmp_path / "clean.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0


class TestJavaSideEffects:
    def test_static_field_mutation(self, tmp_path: Path) -> None:
        code = (
            "public class Counter {\n"
            "  private static int count = 0;\n"
            "  public void increment() {\n"
            "    count = count + 1;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Counter.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_GLOBAL_MUTATION for i in result.issues)
