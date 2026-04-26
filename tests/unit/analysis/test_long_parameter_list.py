"""Tests for Long Parameter List Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.long_parameter_list import (
    ISSUE_EXCESSIVE_PARAMS,
    ISSUE_MANY_PARAMS,
    LongParameterListAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Python tests ──────────────────────────────────────────────


class TestPython:
    def test_many_params_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def f(a, b, c, d, e):\n    pass\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_MANY_PARAMS
        assert r.issues[0].param_count == 5

    def test_excessive_params(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def f(a, b, c, d, e, f, g, h, i):\n    pass\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_EXCESSIVE_PARAMS
        assert r.issues[0].param_count == 9

    def test_few_params_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def f(a, b, c):\n    pass\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_four_params_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def f(a, b, c, d):\n    pass\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_function_name_extracted(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def my_func(a, b, c, d, e):\n    pass\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert r.issues[0].function_name == "my_func"

    def test_multiple_functions(self, tmp_path: Path) -> None:
        code = (
            "def small(a, b):\n    pass\n"
            "def big(a, b, c, d, e, f):\n    pass\n"
            "def medium(x, y, z):\n    pass\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = LongParameterListAnalyzer().analyze_file(p)
        assert r.total_functions == 3
        assert len(r.issues) == 1
        assert r.max_params == 6

    def test_custom_threshold(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def f(a, b, c):\n    pass\n")
        r = LongParameterListAnalyzer(threshold=3).analyze_file(p)
        assert len(r.issues) == 1

    def test_avg_params(self, tmp_path: Path) -> None:
        code = "def f(a, b):\n    pass\ndef g(x, y, z):\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = LongParameterListAnalyzer().analyze_file(p)
        assert r.avg_params == 2.5

    def test_line_number(self, tmp_path: Path) -> None:
        code = "x = 1\n\ndef f(a, b, c, d, e):\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = LongParameterListAnalyzer().analyze_file(p)
        assert r.issues[0].line == 3


# ── JavaScript tests ──────────────────────────────────────────


class TestJavaScript:
    def test_many_params(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "function f(a, b, c, d, e) {}\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].param_count == 5

    def test_arrow_function(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "const f = (a, b, c, d, e, f) => {};\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_short_function_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "function f(a, b) {}\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_method_definition(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "const obj = { method(a, b, c, d, e, f) {} };\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


class TestTypeScript:
    def test_many_params_ts(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.ts", "function f(a: number, b: string, c: bool, d: any, e: any) {}\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_short_ts_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.ts", "function f(a: number, b: string) {}\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_tsx_arrow(self, tmp_path: Path) -> None:
        code = "const C = (a, b, c, d, e, f, g, h, i) => <div/>;\n"
        p = _write(tmp_path, "a.tsx", code)
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_EXCESSIVE_PARAMS


# ── Java tests ────────────────────────────────────────────────


class TestJava:
    def test_many_params(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", "public class A { void f(int a, int b, int c, int d, int e) {} }\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].param_count == 5

    def test_short_method_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", "public class A { void f(int a, int b) {} }\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_constructor_counted(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", "public class A { A(int a, int b, int c, int d, int e, int f) {} }\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


# ── Go tests ──────────────────────────────────────────────────


class TestGo:
    def test_many_params(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.go", "package main\nfunc f(a int, b int, c int, d int, e int) {}\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_short_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.go", "package main\nfunc f(a int, b int) {}\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_method_with_receiver(self, tmp_path: Path) -> None:
        code = 'package main\ntype T struct{}\nfunc (t T) M(a int, b int, c int, d int, e int) {}\n'
        p = _write(tmp_path, "a.go", code)
        r = LongParameterListAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


# ── Unsupported / edge cases ──────────────────────────────────


class TestEdgeCases:
    def test_result_to_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def f(a, b, c, d, e):\n    pass\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert d["total_functions"] == 1
        assert d["issue_count"] == 1
        assert d["max_params"] == 5

    def test_issue_to_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def f(a, b, c, d, e):\n    pass\n")
        r = LongParameterListAnalyzer().analyze_file(p)
        d = r.issues[0].to_dict()
        assert d["function_name"] == "f"
        assert d["param_count"] == 5
