"""Tests for String Concat in Loops Analyzer — Python + Multi-Language."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.string_concat_loop import (
    ConcatHotspot,
    StringConcatLoopAnalyzer,
    StringConcatLoopResult,
    _severity,
)

ANALYZER = StringConcatLoopAnalyzer


# ── Severity tests ──────────────────────────────────────────────────────


class TestSeverity:
    def test_low_depth_0(self) -> None:
        assert _severity(0) == "low"

    def test_medium_depth_1(self) -> None:
        assert _severity(1) == "medium"

    def test_high_depth_2(self) -> None:
        assert _severity(2) == "high"

    def test_high_depth_3(self) -> None:
        assert _severity(3) == "high"


# ── Dataclass tests ────────────────────────────────────────────────────


class TestDataclasses:
    def test_hotspot_frozen(self) -> None:
        h = ConcatHotspot(
            line_number=10,
            loop_type="for",
            concat_operator="+=",
            severity="medium",
            variable="result",
        )
        assert h.line_number == 10
        with pytest.raises(AttributeError):
            h.line_number = 5  # type: ignore[misc]

    def test_result_properties(self) -> None:
        result = StringConcatLoopResult(
            total_hotspots=2,
            hotspots=(),
            file_path="test.py",
        )
        assert result.total_hotspots == 2

    def test_result_to_dict(self) -> None:
        result = StringConcatLoopResult(
            total_hotspots=1,
            hotspots=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_hotspots"] == 1


# ── Edge case tests ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_hotspots == 0


# ── Python tests ───────────────────────────────────────────────────────


class TestPythonConcat:
    def test_no_loops(self, tmp_path: Path) -> None:
        f = tmp_path / "noloop.py"
        f.write_text("result = 'hello'\nresult += ' world'\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots == 0

    def test_no_concat_in_loop(self, tmp_path: Path) -> None:
        f = tmp_path / "noloop2.py"
        f.write_text("for i in range(10):\n    x = i * 2\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots == 0

    def test_simple_concat_in_for(self, tmp_path: Path) -> None:
        f = tmp_path / "for_concat.py"
        f.write_text("result = ''\nfor s in items:\n    result += s\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1
        assert result.hotspots[0].concat_operator == "+="
        assert result.hotspots[0].loop_type == "for"

    def test_concat_in_while(self, tmp_path: Path) -> None:
        f = tmp_path / "while_concat.py"
        f.write_text(
            "result = ''\ni = 0\n"
            "while i < 10:\n"
            "    result += str(i)\n"
            "    i += 1\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1
        assert result.hotspots[0].loop_type == "while"

    def test_nested_loop_high_severity(self, tmp_path: Path) -> None:
        f = tmp_path / "nested.py"
        f.write_text(
            "result = ''\n"
            "for i in range(10):\n"
            "    for j in range(10):\n"
            "        result += str(i)\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1
        assert result.hotspots[0].severity == "high"

    def test_multiple_concats(self, tmp_path: Path) -> None:
        f = tmp_path / "multi.py"
        f.write_text(
            "result = ''\nheader = ''\n"
            "for s in items:\n"
            "    result += s\n"
            "    header += s[0]\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 2

    def test_different_augmented_not_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "other_op.py"
        f.write_text("total = 0\nfor i in range(10):\n    total += i\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1

    def test_concat_in_function(self, tmp_path: Path) -> None:
        f = tmp_path / "func.py"
        f.write_text(
            "def build(items):\n"
            "    result = ''\n"
            "    for s in items:\n"
            "        result += s\n"
            "    return result\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1


# ── JavaScript / TypeScript tests ──────────────────────────────────────


class TestJavaScriptConcat:
    def test_concat_in_for(self, tmp_path: Path) -> None:
        f = tmp_path / "for.js"
        f.write_text(
            "let result = '';\n"
            "for (let i = 0; i < 10; i++) {\n"
            "    result += i.toString();\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1

    def test_concat_in_while(self, tmp_path: Path) -> None:
        f = tmp_path / "while.js"
        f.write_text(
            "let s = '';\n"
            "while (cond) {\n"
            "    s += 'x';\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1

    def test_no_concat(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.js"
        f.write_text(
            "for (let i = 0; i < 10; i++) {\n"
            "    console.log(i);\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots == 0

    def test_typescript(self, tmp_path: Path) -> None:
        f = tmp_path / "test.ts"
        f.write_text(
            "let result: string = '';\n"
            "for (const item of items) {\n"
            "    result += item;\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1


# ── Java tests ─────────────────────────────────────────────────────────


class TestJavaConcat:
    def test_concat_in_for(self, tmp_path: Path) -> None:
        f = tmp_path / "Test.java"
        f.write_text(
            "public class Test {\n"
            "  String foo(List<String> items) {\n"
            "    String result = \"\";\n"
            "    for (String s : items) {\n"
            "      result += s;\n"
            "    }\n"
            "    return result;\n"
            "  }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1

    def test_no_concat(self, tmp_path: Path) -> None:
        f = tmp_path / "Clean.java"
        f.write_text(
            "public class Clean {\n"
            "  void foo() {\n"
            "    for (int i = 0; i < 10; i++) {\n"
            "      System.out.println(i);\n"
            "    }\n"
            "  }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots == 0


# ── Go tests ───────────────────────────────────────────────────────────


class TestGoConcat:
    def test_concat_in_for(self, tmp_path: Path) -> None:
        f = tmp_path / "main.go"
        f.write_text(
            "package main\n\n"
            "func foo(items []string) string {\n"
            "    result := \"\"\n"
            "    for _, s := range items {\n"
            "        result += s\n"
            "    }\n"
            "    return result\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1

    def test_no_concat(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.go"
        f.write_text(
            "package main\n\n"
            "func foo(items []string) {\n"
            "    for _, s := range items {\n"
            "        println(s)\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots == 0

    def test_nested_loop(self, tmp_path: Path) -> None:
        f = tmp_path / "nested.go"
        f.write_text(
            "package main\n\n"
            "func foo(n int) string {\n"
            "    result := \"\"\n"
            "    for i := 0; i < n; i++ {\n"
            "        for j := 0; j < n; j++ {\n"
            "            result += \"x\"\n"
            "        }\n"
            "    }\n"
            "    return result\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_hotspots >= 1
        assert result.hotspots[0].severity == "high"
