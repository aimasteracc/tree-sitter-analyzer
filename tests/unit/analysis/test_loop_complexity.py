"""Tests for Loop Complexity Analyzer — Python + Multi-Language."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.loop_complexity import (
    LoopComplexityAnalyzer,
    LoopComplexityResult,
    LoopHotspot,
    _estimate_complexity,
)

ANALYZER = LoopComplexityAnalyzer


# ── Complexity estimation tests ─────────────────────────────────────────


class TestComplexityEstimation:
    def test_no_loops(self) -> None:
        assert _estimate_complexity(0) == "O(1)"

    def test_single_loop(self) -> None:
        assert _estimate_complexity(1) == "O(n)"

    def test_double_loop(self) -> None:
        assert _estimate_complexity(2) == "O(n\u00b2)"

    def test_triple_loop(self) -> None:
        assert _estimate_complexity(3) == "O(n\u00b3)"

    def test_quad_loop(self) -> None:
        assert _estimate_complexity(4) == "O(n\u2074)"

    def test_deep_nesting(self) -> None:
        assert _estimate_complexity(5) == "O(n^5)"


# ── Dataclass tests ────────────────────────────────────────────────────


class TestDataclasses:
    def test_loop_hotspot_frozen(self) -> None:
        h = LoopHotspot(line_number=10, depth=2, complexity="O(n\u00b2)", loop_type="for")
        assert h.line_number == 10
        with pytest.raises(AttributeError):
            h.line_number = 5  # type: ignore[misc]

    def test_result_properties(self) -> None:
        result = LoopComplexityResult(
            max_loop_depth=2,
            estimated_complexity="O(n\u00b2)",
            hotspots=(),
            total_loops=3,
            file_path="test.py",
        )
        assert result.max_loop_depth == 2
        assert result.estimated_complexity == "O(n\u00b2)"
        assert result.total_loops == 3


# ── Edge case tests ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    pass\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_loops == 0


# ── Python tests ───────────────────────────────────────────────────────


class TestPythonLoops:
    def test_no_loops(self, tmp_path: Path) -> None:
        f = tmp_path / "noloop.py"
        f.write_text("def foo():\n    x = 1\n    return x\n")
        result = ANALYZER().analyze_file(f)
        assert result.max_loop_depth == 0
        assert result.estimated_complexity == "O(1)"

    def test_single_for(self, tmp_path: Path) -> None:
        f = tmp_path / "single.py"
        f.write_text("def foo(items):\n    for x in items:\n        print(x)\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_loops == 1
        assert result.max_loop_depth == 1
        assert result.estimated_complexity == "O(n)"

    def test_nested_for(self, tmp_path: Path) -> None:
        f = tmp_path / "nested.py"
        f.write_text(
            "def foo(matrix):\n"
            "    for row in matrix:\n"
            "        for col in row:\n"
            "            print(col)\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_loops == 2
        assert result.max_loop_depth == 2
        assert result.estimated_complexity == "O(n\u00b2)"

    def test_triple_nested(self, tmp_path: Path) -> None:
        f = tmp_path / "triple.py"
        f.write_text(
            "def foo(cube):\n"
            "    for x in cube:\n"
            "        for y in x:\n"
            "            for z in y:\n"
            "                print(z)\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_loop_depth == 3
        assert result.estimated_complexity == "O(n\u00b3)"

    def test_while_loop(self, tmp_path: Path) -> None:
        f = tmp_path / "while.py"
        f.write_text("def foo():\n    while True:\n        break\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_loops == 1
        assert result.max_loop_depth == 1

    def test_nested_for_while(self, tmp_path: Path) -> None:
        f = tmp_path / "mixed.py"
        f.write_text(
            "def foo(items):\n"
            "    for x in items:\n"
            "        while x > 0:\n"
            "            x -= 1\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_loops == 2
        assert result.max_loop_depth == 2
        assert result.estimated_complexity == "O(n\u00b2)"

    def test_list_comprehension(self, tmp_path: Path) -> None:
        f = tmp_path / "comprehension.py"
        f.write_text("def foo(items):\n    return [x for x in items]\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_loops >= 1
        assert result.max_loop_depth >= 1

    def test_nested_list_comprehension(self, tmp_path: Path) -> None:
        f = tmp_path / "nested_comp.py"
        f.write_text(
            "def foo(matrix):\n"
            "    return [x for row in matrix for x in row]\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_loop_depth >= 2

    def test_sibling_loops_not_nested(self, tmp_path: Path) -> None:
        f = tmp_path / "siblings.py"
        f.write_text(
            "def foo(a, b):\n"
            "    for x in a:\n"
            "        print(x)\n"
            "    for y in b:\n"
            "        print(y)\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_loops == 2
        assert result.max_loop_depth == 1
        assert result.estimated_complexity == "O(n)"

    def test_method_in_class(self, tmp_path: Path) -> None:
        f = tmp_path / "cls.py"
        f.write_text(
            "class Foo:\n"
            "    def bar(self, items):\n"
            "        for x in items:\n"
            "            for y in x:\n"
            "                pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_loop_depth == 2

    def test_loop_hotspot_location(self, tmp_path: Path) -> None:
        f = tmp_path / "hotspot.py"
        f.write_text(
            "def foo(matrix):\n"
            "    for row in matrix:\n"
            "        for col in row:\n"
            "            print(col)\n"
        )
        result = ANALYZER().analyze_file(f)
        assert len(result.hotspots) >= 2
        deep = [h for h in result.hotspots if h.depth >= 2]
        assert len(deep) >= 1
        assert deep[0].depth >= 2


# ── JavaScript / TypeScript tests ──────────────────────────────────────


class TestJavaScriptLoops:
    def test_single_for_loop(self, tmp_path: Path) -> None:
        f = tmp_path / "test.js"
        f.write_text("function foo(arr) { for (let i = 0; i < arr.length; i++) {} }")
        result = ANALYZER().analyze_file(f)
        assert result.total_loops >= 1
        assert result.max_loop_depth >= 1

    def test_nested_for(self, tmp_path: Path) -> None:
        f = tmp_path / "nested.js"
        f.write_text(
            "function foo(matrix) {\n"
            "  for (let i = 0; i < matrix.length; i++) {\n"
            "    for (let j = 0; j < matrix[i].length; j++) {\n"
            "      console.log(matrix[i][j]);\n"
            "    }\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_loop_depth == 2

    def test_while_loop(self, tmp_path: Path) -> None:
        f = tmp_path / "while.js"
        f.write_text("function foo() { while (true) { break; } }")
        result = ANALYZER().analyze_file(f)
        assert result.total_loops >= 1

    def test_for_of_loop(self, tmp_path: Path) -> None:
        f = tmp_path / "forof.js"
        f.write_text("function foo(arr) { for (const x of arr) { console.log(x); } }")
        result = ANALYZER().analyze_file(f)
        assert result.total_loops >= 1


# ── Java tests ─────────────────────────────────────────────────────────


class TestJavaLoops:
    def test_single_for(self, tmp_path: Path) -> None:
        f = tmp_path / "Test.java"
        f.write_text(
            "public class Test {\n"
            "  void foo(int[] arr) {\n"
            "    for (int i = 0; i < arr.length; i++) {}\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_loops >= 1
        assert result.max_loop_depth >= 1

    def test_nested_for(self, tmp_path: Path) -> None:
        f = tmp_path / "Matrix.java"
        f.write_text(
            "public class Matrix {\n"
            "  void foo(int[][] m) {\n"
            "    for (int i = 0; i < m.length; i++) {\n"
            "      for (int j = 0; j < m[i].length; j++) {\n"
            "        System.out.println(m[i][j]);\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_loop_depth == 2

    def test_while_loop(self, tmp_path: Path) -> None:
        f = tmp_path / "While.java"
        f.write_text(
            "public class While {\n"
            "  void foo() {\n"
            "    while (true) { break; }\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_loops >= 1

    def test_enhanced_for(self, tmp_path: Path) -> None:
        f = tmp_path / "Enhanced.java"
        f.write_text(
            "import java.util.List;\n"
            "public class Enhanced {\n"
            "  void foo(List<String> items) {\n"
            "    for (String s : items) { System.out.println(s); }\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_loops >= 1


# ── Go tests ───────────────────────────────────────────────────────────


class TestGoLoops:
    def test_single_for(self, tmp_path: Path) -> None:
        f = tmp_path / "main.go"
        f.write_text(
            "package main\n\n"
            "func foo(items []int) {\n"
            "    for i := range items {}\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_loops >= 1
        assert result.max_loop_depth >= 1

    def test_nested_for(self, tmp_path: Path) -> None:
        f = tmp_path / "nested.go"
        f.write_text(
            "package main\n\n"
            "func foo(matrix [][]int) {\n"
            "    for _, row := range matrix {\n"
            "        for _, v := range row {\n"
            "            _ = v\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_loop_depth == 2

    def test_triple_nested(self, tmp_path: Path) -> None:
        f = tmp_path / "triple.go"
        f.write_text(
            "package main\n\n"
            "func foo(cube [][][]int) {\n"
            "    for _, a := range cube {\n"
            "        for _, b := range a {\n"
            "            for _, c := range b {\n"
            "                _ = c\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_loop_depth == 3
        assert result.estimated_complexity == "O(n\u00b3)"
