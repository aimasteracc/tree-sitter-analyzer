"""Tests for Boolean Complexity Analyzer — Python + Multi-Language."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.boolean_complexity import (
    BooleanComplexityAnalyzer,
    BooleanComplexityResult,
    BooleanHotspot,
    _rating,
)

ANALYZER = BooleanComplexityAnalyzer


# ── Rating tests ────────────────────────────────────────────────────────


class TestRating:
    def test_good_1(self) -> None:
        assert _rating(1) == "good"

    def test_good_2(self) -> None:
        assert _rating(2) == "good"

    def test_good_3(self) -> None:
        assert _rating(3) == "good"

    def test_warning_4(self) -> None:
        assert _rating(4) == "warning"

    def test_critical_5(self) -> None:
        assert _rating(5) == "critical"

    def test_critical_10(self) -> None:
        assert _rating(10) == "critical"


# ── Dataclass tests ────────────────────────────────────────────────────


class TestDataclasses:
    def test_hotspot_frozen(self) -> None:
        h = BooleanHotspot(
            line_number=10, condition_count=4, expression="a && b && c && d",
        )
        assert h.line_number == 10
        with pytest.raises(AttributeError):
            h.line_number = 5  # type: ignore[misc]

    def test_result_properties(self) -> None:
        result = BooleanComplexityResult(
            max_conditions=4,
            total_expressions=5,
            hotspots=(),
            file_path="test.py",
        )
        assert result.max_conditions == 4
        assert result.total_expressions == 5


# ── Edge case tests ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        result = ANALYZER().analyze_file("/nonexistent/file.py")
        assert result.total_expressions == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.rb"
        f.write_text("def foo; end")
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions == 0

    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_expressions == 0


# ── Python tests ───────────────────────────────────────────────────────


class TestPythonBoolean:
    def test_no_boolean_expressions(self, tmp_path: Path) -> None:
        f = tmp_path / "simple.py"
        f.write_text("x = 1\ny = 2\nprint(x + y)\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions == 0
        assert result.max_conditions == 0

    def test_simple_boolean(self, tmp_path: Path) -> None:
        f = tmp_path / "simple_bool.py"
        f.write_text("x = True and False\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions >= 1

    def test_and_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "and_chain.py"
        f.write_text("if a and b and c and d:\n    pass\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions >= 1
        assert result.max_conditions >= 4

    def test_or_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "or_chain.py"
        f.write_text("if a or b or c or d:\n    pass\n")
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 4

    def test_mixed_and_or(self, tmp_path: Path) -> None:
        f = tmp_path / "mixed.py"
        f.write_text("if (a and b) or (c and d):\n    pass\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions >= 1

    def test_not_operator_not_counted(self, tmp_path: Path) -> None:
        f = tmp_path / "not.py"
        f.write_text("if not a:\n    pass\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions == 0

    def test_complex_if_condition(self, tmp_path: Path) -> None:
        f = tmp_path / "complex.py"
        f.write_text(
            "def check(a, b, c, d, e):\n"
            "    if a and b and c and d and e:\n"
            "        return True\n"
            "    return False\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 5
        assert len(result.hotspots) >= 1
        assert result.hotspots[0].condition_count >= 5

    def test_while_condition(self, tmp_path: Path) -> None:
        f = tmp_path / "while.py"
        f.write_text("while a and b and c and d:\n    pass\n")
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 4

    def test_assignment_boolean(self, tmp_path: Path) -> None:
        f = tmp_path / "assign.py"
        f.write_text("x = a and b and c\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions >= 1

    def test_return_boolean(self, tmp_path: Path) -> None:
        f = tmp_path / "ret.py"
        f.write_text("def foo():\n    return a and b and c and d\n")
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 4

    def test_sibling_expressions(self, tmp_path: Path) -> None:
        f = tmp_path / "siblings.py"
        f.write_text(
            "if a and b:\n    pass\n"
            "if c and d:\n    pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions >= 2
        assert result.max_conditions == 2

    def test_nested_function(self, tmp_path: Path) -> None:
        f = tmp_path / "nested.py"
        f.write_text(
            "def foo(a, b, c, d, e, f):\n"
            "    if a and b or c and d or e and f:\n"
            "        return 1\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 4


# ── JavaScript / TypeScript tests ──────────────────────────────────────


class TestJavaScriptBoolean:
    def test_simple_and(self, tmp_path: Path) -> None:
        f = tmp_path / "test.js"
        f.write_text("if (a && b) { console.log('ok'); }")
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions >= 1

    def test_complex_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "complex.js"
        f.write_text(
            "if (a && b && c && d && e) { return 1; }"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 5

    def test_or_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "or.js"
        f.write_text("if (a || b || c || d) { return 1; }")
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 4

    def test_mixed_operators(self, tmp_path: Path) -> None:
        f = tmp_path / "mixed.js"
        f.write_text("if ((a && b) || (c && d)) { return 1; }")
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions >= 1


# ── Java tests ─────────────────────────────────────────────────────────


class TestJavaBoolean:
    def test_simple_and(self, tmp_path: Path) -> None:
        f = tmp_path / "Test.java"
        f.write_text(
            "public class Test {\n"
            "  boolean foo(boolean a, boolean b) {\n"
            "    return a && b;\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions >= 1

    def test_complex_condition(self, tmp_path: Path) -> None:
        f = tmp_path / "Complex.java"
        f.write_text(
            "public class Complex {\n"
            "  void foo(boolean a, boolean b, boolean c, boolean d) {\n"
            "    if (a && b && c && d) {}\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 4

    def test_or_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "Or.java"
        f.write_text(
            "public class Or {\n"
            "  void foo(int x) {\n"
            "    if (x == 1 || x == 2 || x == 3 || x == 4) {}\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 4


# ── Go tests ───────────────────────────────────────────────────────────


class TestGoBoolean:
    def test_simple_and(self, tmp_path: Path) -> None:
        f = tmp_path / "main.go"
        f.write_text(
            "package main\n\n"
            "func foo(a, b bool) bool {\n"
            "    return a && b\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_expressions >= 1

    def test_complex_condition(self, tmp_path: Path) -> None:
        f = tmp_path / "complex.go"
        f.write_text(
            "package main\n\n"
            "func foo(a, b, c, d bool) {\n"
            "    if a && b && c && d {\n"
            "        return\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 4

    def test_or_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "or.go"
        f.write_text(
            "package main\n\n"
            "func foo(x int) {\n"
            "    if x == 1 || x == 2 || x == 3 || x == 4 {\n"
            "        return\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_conditions >= 4
