"""Tests for Variable Mutability Analyzer."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.variable_mutability import (
    MUTABILITY_LOOP_MUTATION,
    MUTABILITY_REASSIGNED_CONST,
    MUTABILITY_SHADOW,
    MUTABILITY_UNUSED,
    VariableMutabilityAnalyzer,
)

ANALYZER = VariableMutabilityAnalyzer()


class TestPythonMutability:
    def test_shadow_variable(self, tmp_path: Path) -> None:
        code = (
            "def outer():\n"
            "    x = 10\n"
            "    def inner():\n"
            "        x = 20\n"
        )
        f = tmp_path / "shadow.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == MUTABILITY_SHADOW for i in result.issues)

    def test_reassigned_constant(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    MAX_SIZE = 100\n"
            "    MAX_SIZE = 200\n"
        )
        f = tmp_path / "const.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == MUTABILITY_REASSIGNED_CONST for i in result.issues)

    def test_loop_mutation(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    total = 0\n"
            "    for i in range(10):\n"
            "        total += 1\n"
        )
        f = tmp_path / "loop.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == MUTABILITY_LOOP_MUTATION for i in result.issues)

    def test_unused_assignment(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    x = 10\n"
        )
        f = tmp_path / "unused.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == MUTABILITY_UNUSED for i in result.issues)

    def test_no_issues(self, tmp_path: Path) -> None:
        code = (
            "def add(a, b):\n"
            "    result = a + b\n"
            "    return result\n"
        )
        f = tmp_path / "clean.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0
        assert result.quality_score == 100.0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0


class TestJavaScriptMutability:
    def test_shadow_variable_js(self, tmp_path: Path) -> None:
        code = (
            "function outer() {\n"
            "  var x = 10;\n"
            "  function inner() {\n"
            "    var x = 20;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "shadow.js"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == MUTABILITY_SHADOW for i in result.issues)
