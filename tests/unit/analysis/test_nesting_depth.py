"""Tests for Nesting Depth Analyzer — Python + Multi-Language."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.nesting_depth import (
    DepthHotspot,
    FunctionNesting,
    NestingDepthAnalyzer,
    NestingDepthResult,
    _rating,
)

ANALYZER = NestingDepthAnalyzer


# ── Rating tests ────────────────────────────────────────────────────────


class TestRating:
    def test_good_0(self) -> None:
        assert _rating(0) == "good"

    def test_good_1(self) -> None:
        assert _rating(1) == "good"

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
    def test_depth_hotspot_frozen(self) -> None:
        h = DepthHotspot(line_number=10, depth=3, node_type="if_statement")
        assert h.line_number == 10
        with pytest.raises(AttributeError):
            h.line_number = 5  # type: ignore[misc]

    def test_function_nesting_frozen(self) -> None:
        fn = FunctionNesting(
            name="foo", start_line=1, end_line=10,
            max_depth=3, avg_depth=1.5, hotspots=(),
            rating="good", element_type="function",
        )
        assert fn.max_depth == 3
        with pytest.raises(AttributeError):
            fn.max_depth = 99  # type: ignore[misc]

    def test_result_get_deep_functions(self) -> None:
        f1 = FunctionNesting("a", 1, 5, 2, 1.0, (), "good", "function")
        f2 = FunctionNesting("b", 6, 20, 5, 2.0, (), "critical", "function")
        result = NestingDepthResult(
            functions=(f1, f2), total_functions=2,
            max_depth=5, avg_depth=3.5, deep_functions=1,
            file_path="test.py",
        )
        deep = result.get_deep_functions(threshold=4)
        assert len(deep) == 1
        assert deep[0].name == "b"


# ── Edge case tests ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        analyzer = ANALYZER()
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_functions == 0
        assert result.max_depth == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.rb"
        f.write_text("def foo; end")
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 0

    def test_file_with_no_functions(self, tmp_path: Path) -> None:
        f = tmp_path / "nocode.py"
        f.write_text("x = 1\ny = 2\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 0

    def test_function_no_body(self, tmp_path: Path) -> None:
        f = tmp_path / "stub.py"
        f.write_text("def foo(): pass\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert result.functions[0].max_depth == 0

    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("def foo(): pass\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_functions == 1


# ── Python tests ───────────────────────────────────────────────────────


class TestPythonNesting:
    def test_flat_function(self, tmp_path: Path) -> None:
        f = tmp_path / "flat.py"
        f.write_text("def foo():\n    x = 1\n    return x\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert result.functions[0].max_depth == 0
        assert result.functions[0].rating == "good"

    def test_one_level_if(self, tmp_path: Path) -> None:
        f = tmp_path / "one.py"
        f.write_text("def foo(x):\n    if x:\n        return 1\n    return 0\n")
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 1

    def test_two_levels(self, tmp_path: Path) -> None:
        f = tmp_path / "two.py"
        f.write_text(
            "def foo(x, y):\n"
            "    if x:\n"
            "        if y:\n"
            "            return 1\n"
            "    return 0\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 2
        assert result.functions[0].rating == "good"

    def test_three_levels_good(self, tmp_path: Path) -> None:
        f = tmp_path / "three.py"
        f.write_text(
            "def foo(a, b, c):\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                return 1\n"
            "    return 0\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 3
        assert result.functions[0].rating == "good"

    def test_four_levels_warning(self, tmp_path: Path) -> None:
        f = tmp_path / "four.py"
        f.write_text(
            "def foo(a, b, c, d):\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    return 1\n"
            "    return 0\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 4
        assert result.functions[0].rating == "warning"
        assert result.deep_functions == 1

    def test_five_levels_critical(self, tmp_path: Path) -> None:
        f = tmp_path / "five.py"
        f.write_text(
            "def foo(a, b, c, d, e):\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    if e:\n"
            "                        return 1\n"
            "    return 0\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 5
        assert result.functions[0].rating == "critical"

    def test_for_loop_nesting(self, tmp_path: Path) -> None:
        f = tmp_path / "for.py"
        f.write_text(
            "def foo(items):\n"
            "    for i in items:\n"
            "        for j in i:\n"
            "            pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 2

    def test_while_nesting(self, tmp_path: Path) -> None:
        f = tmp_path / "while.py"
        f.write_text(
            "def foo():\n"
            "    while True:\n"
            "        while False:\n"
            "            break\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 2

    def test_try_nesting(self, tmp_path: Path) -> None:
        f = tmp_path / "try.py"
        f.write_text(
            "def foo():\n"
            "    try:\n"
            "        if True:\n"
            "            pass\n"
            "    except Exception:\n"
            "        pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 2

    def test_with_statement(self, tmp_path: Path) -> None:
        f = tmp_path / "with.py"
        f.write_text(
            "def foo():\n"
            "    with open('f') as f:\n"
            "        if f:\n"
            "            pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 2

    def test_method_in_class(self, tmp_path: Path) -> None:
        f = tmp_path / "cls.py"
        f.write_text(
            "class Foo:\n"
            "    def bar(self, x):\n"
            "        if x:\n"
            "            if x > 0:\n"
            "                return 1\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert result.functions[0].name == "bar"
        assert result.functions[0].element_type == "method"
        assert result.functions[0].max_depth == 2

    def test_multiple_functions(self, tmp_path: Path) -> None:
        f = tmp_path / "multi.py"
        f.write_text(
            "def flat():\n"
            "    return 1\n"
            "\n"
            "def deep(a, b, c, d):\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    return 1\n"
            "    return 0\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 2
        assert result.max_depth == 4
        assert result.deep_functions == 1

    def test_hotspots_tracked(self, tmp_path: Path) -> None:
        f = tmp_path / "hot.py"
        f.write_text(
            "def foo(x, y):\n"       # line 1
            "    if x:\n"             # line 2
            "        if y:\n"         # line 3
            "            pass\n"
        )
        result = ANALYZER().analyze_file(f)
        fn = result.functions[0]
        assert len(fn.hotspots) == 2
        assert fn.hotspots[0].depth == 1
        assert fn.hotspots[1].depth == 2

    def test_decorated_function(self, tmp_path: Path) -> None:
        f = tmp_path / "deco.py"
        f.write_text(
            "@staticmethod\n"
            "def foo(x):\n"
            "    if x:\n"
            "        return 1\n"
            "    return 0\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert result.functions[0].max_depth == 1


# ── JavaScript / TypeScript tests ──────────────────────────────────────


class TestJavaScriptNesting:
    def test_flat_js_function(self, tmp_path: Path) -> None:
        f = tmp_path / "flat.js"
        f.write_text("function foo() { return 1; }\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert result.functions[0].max_depth == 0

    def test_nested_if_js(self, tmp_path: Path) -> None:
        f = tmp_path / "nested.js"
        f.write_text(
            "function foo(a, b, c) {\n"
            "  if (a) {\n"
            "    if (b) {\n"
            "      if (c) {\n"
            "        return 1;\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 3

    def test_arrow_function_js(self, tmp_path: Path) -> None:
        f = tmp_path / "arrow.js"
        f.write_text("const foo = (x) => { if (x) { return 1; } };\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_functions >= 1

    def test_method_in_class_js(self, tmp_path: Path) -> None:
        f = tmp_path / "cls.js"
        f.write_text(
            "class Foo {\n"
            "  bar(x) {\n"
            "    if (x) {\n"
            "      if (x > 0) {\n"
            "        return 1;\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_functions >= 1
        bar_fn = [fn for fn in result.functions if fn.name == "bar"]
        assert len(bar_fn) == 1
        assert bar_fn[0].max_depth == 2

    def test_switch_nesting_js(self, tmp_path: Path) -> None:
        f = tmp_path / "switch.js"
        f.write_text(
            "function foo(x) {\n"
            "  switch (x) {\n"
            "    case 1:\n"
            "      if (true) {\n"
            "        return 1;\n"
            "      }\n"
            "  }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 2

    def test_for_loop_js(self, tmp_path: Path) -> None:
        f = tmp_path / "for.js"
        f.write_text(
            "function foo() {\n"
            "  for (let i = 0; i < 10; i++) {\n"
            "    for (let j = 0; j < 10; j++) {\n"
            "      if (i === j) {\n"
            "        return i;\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 3

    def test_typescript_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.ts"
        f.write_text(
            "function foo(x: number): number {\n"
            "  if (x > 0) {\n"
            "    return 1;\n"
            "  }\n"
            "  return 0;\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_functions >= 1


# ── Java tests ─────────────────────────────────────────────────────────


class TestJavaNesting:
    def test_flat_java_method(self, tmp_path: Path) -> None:
        f = tmp_path / "Flat.java"
        f.write_text(
            "public class Flat {\n"
            "    public int foo() { return 1; }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert result.functions[0].max_depth == 0

    def test_nested_if_java(self, tmp_path: Path) -> None:
        f = tmp_path / "Nested.java"
        f.write_text(
            "public class Nested {\n"
            "    public int foo(int a, int b) {\n"
            "        if (a > 0) {\n"
            "            if (b > 0) {\n"
            "                return 1;\n"
            "            }\n"
            "        }\n"
            "        return 0;\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 2

    def test_for_loop_java(self, tmp_path: Path) -> None:
        f = tmp_path / "Loop.java"
        f.write_text(
            "public class Loop {\n"
            "    public void foo() {\n"
            "        for (int i = 0; i < 10; i++) {\n"
            "            for (int j = 0; j < 10; j++) {\n"
            "                if (i == j) {\n"
            "                    return;\n"
            "                }\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 3

    def test_constructor_java(self, tmp_path: Path) -> None:
        f = tmp_path / "Ctor.java"
        f.write_text(
            "public class Ctor {\n"
            "    public Ctor(int x) {\n"
            "        if (x > 0) {\n"
            "            if (x > 10) {\n"
            "                throw new Error();\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert result.functions[0].name == "<init>"
        assert result.functions[0].max_depth == 2

    def test_synchronized_java(self, tmp_path: Path) -> None:
        f = tmp_path / "Sync.java"
        f.write_text(
            "public class Sync {\n"
            "    public void foo() {\n"
            "        synchronized (this) {\n"
            "            if (true) {\n"
            "                return;\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 2


# ── Go tests ───────────────────────────────────────────────────────────


class TestGoNesting:
    def test_flat_go_function(self, tmp_path: Path) -> None:
        f = tmp_path / "flat.go"
        f.write_text(
            "package main\n\n"
            "func foo() int {\n"
            "    return 1\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert result.functions[0].max_depth == 0

    def test_nested_if_go(self, tmp_path: Path) -> None:
        f = tmp_path / "nested.go"
        f.write_text(
            "package main\n\n"
            "func foo(a, b int) int {\n"
            "    if a > 0 {\n"
            "        if b > 0 {\n"
            "            return 1\n"
            "        }\n"
            "    }\n"
            "    return 0\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 2

    def test_for_loop_go(self, tmp_path: Path) -> None:
        f = tmp_path / "loop.go"
        f.write_text(
            "package main\n\n"
            "func foo() {\n"
            "    for i := 0; i < 10; i++ {\n"
            "        for j := 0; j < 10; j++ {\n"
            "            if i == j {\n"
            "                return\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 3

    def test_go_method(self, tmp_path: Path) -> None:
        f = tmp_path / "method.go"
        f.write_text(
            "package main\n\n"
            "type Foo struct{}\n\n"
            "func (f Foo) Bar(x int) int {\n"
            "    if x > 0 {\n"
            "        return 1\n"
            "    }\n"
            "    return 0\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert result.functions[0].name == "Bar"
        assert result.functions[0].element_type == "method"

    def test_switch_go(self, tmp_path: Path) -> None:
        f = tmp_path / "switch.go"
        f.write_text(
            "package main\n\n"
            "func foo(x int) int {\n"
            "    switch x {\n"
            "    case 1:\n"
            "        if true {\n"
            "            return 1\n"
            "        }\n"
            "    }\n"
            "    return 0\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 2

    def test_critical_depth_go(self, tmp_path: Path) -> None:
        f = tmp_path / "critical.go"
        f.write_text(
            "package main\n\n"
            "func foo(a, b, c, d, e int) int {\n"
            "    if a > 0 {\n"
            "        if b > 0 {\n"
            "            if c > 0 {\n"
            "                if d > 0 {\n"
            "                    if e > 0 {\n"
            "                        return 1\n"
            "                    }\n"
            "                }\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    return 0\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.functions[0].max_depth == 5
        assert result.functions[0].rating == "critical"
