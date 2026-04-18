"""Tests for Duplicate Condition Analyzer — Python + Multi-Language."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.duplicate_condition import (
    DuplicateConditionAnalyzer,
    DuplicateConditionResult,
    DuplicateCondition,
    _normalize,
)

ANALYZER = DuplicateConditionAnalyzer


# ── Normalize tests ─────────────────────────────────────────────────────


class TestNormalize:
    def test_strips_whitespace(self) -> None:
        assert _normalize("  x == 1  ") == "x == 1"

    def test_collapses_internal_whitespace(self) -> None:
        assert _normalize("x  ==   1") == "x == 1"

    def test_empty_string(self) -> None:
        assert _normalize("") == ""

    def test_newlines(self) -> None:
        assert _normalize("x\n==\n1") == "x == 1"


# ── Dataclass tests ────────────────────────────────────────────────────


class TestDataclasses:
    def test_duplicate_frozen(self) -> None:
        d = DuplicateCondition(
            condition="x == 1",
            occurrences=(10, 20),
            count=2,
        )
        assert d.condition == "x == 1"
        with pytest.raises(AttributeError):
            d.count = 3  # type: ignore[misc]

    def test_result_properties(self) -> None:
        result = DuplicateConditionResult(
            total_conditions=5,
            unique_conditions=3,
            duplicates=(),
            file_path="test.py",
        )
        assert result.total_conditions == 5
        assert result.unique_conditions == 3

    def test_result_to_dict(self) -> None:
        result = DuplicateConditionResult(
            total_conditions=4,
            unique_conditions=2,
            duplicates=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_conditions"] == 4
        assert d["unique_conditions"] == 2


# ── Edge case tests ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        result = ANALYZER().analyze_file("/nonexistent/file.py")
        assert result.total_conditions == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.rb"
        f.write_text("def foo; end")
        result = ANALYZER().analyze_file(f)
        assert result.total_conditions == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER().analyze_file(f)
        assert result.total_conditions == 0

    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_conditions == 0


# ── Python tests ───────────────────────────────────────────────────────


class TestPythonCondition:
    def test_no_ifs(self, tmp_path: Path) -> None:
        f = tmp_path / "simple.py"
        f.write_text("x = 1\ny = 2\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_conditions == 0
        assert len(result.duplicates) == 0

    def test_single_if_no_duplicates(self, tmp_path: Path) -> None:
        f = tmp_path / "single.py"
        f.write_text("if x == 1:\n    pass\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_conditions == 1
        assert len(result.duplicates) == 0

    def test_two_different_conditions(self, tmp_path: Path) -> None:
        f = tmp_path / "diff.py"
        f.write_text(
            "if x == 1:\n    pass\n"
            "if y == 2:\n    pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_conditions == 2
        assert result.unique_conditions == 2
        assert len(result.duplicates) == 0

    def test_exact_duplicate(self, tmp_path: Path) -> None:
        f = tmp_path / "dup.py"
        f.write_text(
            "if x > 0:\n    pass\n"
            "if x > 0:\n    pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_conditions == 2
        assert result.unique_conditions == 1
        assert len(result.duplicates) == 1
        assert result.duplicates[0].count == 2

    def test_three_times(self, tmp_path: Path) -> None:
        f = tmp_path / "three.py"
        f.write_text(
            "if x == 1:\n    pass\n"
            "if x == 1:\n    pass\n"
            "if x == 1:\n    pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.duplicates[0].count == 3

    def test_different_whitespace_same_condition(self, tmp_path: Path) -> None:
        f = tmp_path / "ws.py"
        f.write_text(
            "if x  >  0:\n    pass\n"
            "if x > 0:\n    pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.duplicates) == 1

    def test_mixed_duplicate_and_unique(self, tmp_path: Path) -> None:
        f = tmp_path / "mixed.py"
        f.write_text(
            "if x == 1:\n    pass\n"
            "if y == 2:\n    pass\n"
            "if x == 1:\n    pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_conditions == 3
        assert result.unique_conditions == 2
        assert len(result.duplicates) == 1

    def test_nested_ifs(self, tmp_path: Path) -> None:
        f = tmp_path / "nested.py"
        f.write_text(
            "if x == 1:\n"
            "    if x == 1:\n"
            "        pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_conditions == 2
        assert len(result.duplicates) == 1

    def test_elif_counted(self, tmp_path: Path) -> None:
        f = tmp_path / "elif.py"
        f.write_text(
            "if x == 1:\n    pass\n"
            "elif x == 2:\n    pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_conditions >= 2


# ── JavaScript / TypeScript tests ──────────────────────────────────────


class TestJavaScriptCondition:
    def test_no_duplicates(self, tmp_path: Path) -> None:
        f = tmp_path / "test.js"
        f.write_text(
            "if (x === 1) { console.log(1); }\n"
            "if (y === 2) { console.log(2); }\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.duplicates) == 0

    def test_duplicate_conditions(self, tmp_path: Path) -> None:
        f = tmp_path / "dup.js"
        f.write_text(
            "if (x > 0) { a(); }\n"
            "if (x > 0) { b(); }\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.duplicates) == 1
        assert result.duplicates[0].count == 2

    def test_typescript(self, tmp_path: Path) -> None:
        f = tmp_path / "test.ts"
        f.write_text(
            "if (x === 1) { a(); }\n"
            "if (x === 1) { b(); }\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.duplicates) == 1


# ── Java tests ─────────────────────────────────────────────────────────


class TestJavaCondition:
    def test_no_duplicates(self, tmp_path: Path) -> None:
        f = tmp_path / "Test.java"
        f.write_text(
            "public class Test {\n"
            "  void foo(int x, int y) {\n"
            "    if (x == 1) { return; }\n"
            "    if (y == 2) { return; }\n"
            "  }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.duplicates) == 0

    def test_duplicate_conditions(self, tmp_path: Path) -> None:
        f = tmp_path / "Dup.java"
        f.write_text(
            "public class Dup {\n"
            "  void foo(int x) {\n"
            "    if (x > 0) { a(); }\n"
            "    if (x > 0) { b(); }\n"
            "  }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.duplicates) == 1


# ── Go tests ───────────────────────────────────────────────────────────


class TestGoCondition:
    def test_no_duplicates(self, tmp_path: Path) -> None:
        f = tmp_path / "main.go"
        f.write_text(
            "package main\n\n"
            "func foo(x, y int) {\n"
            "    if x == 1 {\n"
            "        return\n"
            "    }\n"
            "    if y == 2 {\n"
            "        return\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.duplicates) == 0

    def test_duplicate_conditions(self, tmp_path: Path) -> None:
        f = tmp_path / "dup.go"
        f.write_text(
            "package main\n\n"
            "func foo(x int) {\n"
            "    if x > 0 {\n"
            "        a()\n"
            "    }\n"
            "    if x > 0 {\n"
            "        b()\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.duplicates) == 1
        assert result.duplicates[0].count == 2
