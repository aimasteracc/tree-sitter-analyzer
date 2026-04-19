"""Tests for Inconsistent Return Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.inconsistent_return import (
    InconsistentReturnAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Python tests ──────────────────────────────────────────────


class TestPython:
    def test_value_and_bare_return(self, tmp_path: Path) -> None:
        code = "def f(x):\n    if x:\n        return 1\n    return\n"
        p = _write(tmp_path, "a.py", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].has_value_returns == 1
        assert r.issues[0].has_bare_returns == 1

    def test_value_return_and_implicit(self, tmp_path: Path) -> None:
        code = "def f(x):\n    if x:\n        return 1\n"
        p = _write(tmp_path, "a.py", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].has_value_returns == 1
        assert r.issues[0].has_implicit is True

    def test_all_value_returns_ok(self, tmp_path: Path) -> None:
        code = "def f(x):\n    if x:\n        return 1\n    return 0\n"
        p = _write(tmp_path, "a.py", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_all_bare_returns_ok(self, tmp_path: Path) -> None:
        code = "def f(x):\n    if x:\n        return\n    return\n"
        p = _write(tmp_path, "a.py", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_no_returns_ok(self, tmp_path: Path) -> None:
        code = "def f(x):\n    print(x)\n"
        p = _write(tmp_path, "a.py", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_function_name_extracted(self, tmp_path: Path) -> None:
        code = "def my_func(x):\n    if x:\n        return 1\n"
        p = _write(tmp_path, "a.py", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert r.issues[0].function_name == "my_func"

    def test_line_number_correct(self, tmp_path: Path) -> None:
        code = "x = 1\n\ndef f(x):\n    if x:\n        return 1\n"
        p = _write(tmp_path, "a.py", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert r.issues[0].line == 3

    def test_multiple_functions(self, tmp_path: Path) -> None:
        code = (
            "def good(x):\n    return x\n\n"
            "def bad(x):\n    if x:\n        return 1\n\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert r.total_functions == 2
        assert len(r.issues) == 1


# ── JavaScript tests ──────────────────────────────────────────


class TestJavaScript:
    def test_mixed_returns(self, tmp_path: Path) -> None:
        code = "function f(x) { if (x) { return 1; } return; }\n"
        p = _write(tmp_path, "a.js", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_all_value_returns_ok(self, tmp_path: Path) -> None:
        code = "function f(x) { if (x) { return 1; } return 0; }\n"
        p = _write(tmp_path, "a.js", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_arrow_function(self, tmp_path: Path) -> None:
        code = "const f = (x) => { if (x) { return 1; } return; };\n"
        p = _write(tmp_path, "a.js", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


class TestTypeScript:
    def test_mixed_returns_ts(self, tmp_path: Path) -> None:
        code = "function f(x: number) { if (x) { return 1; } return; }\n"
        p = _write(tmp_path, "a.ts", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_tsx_function(self, tmp_path: Path) -> None:
        code = "function C(props: any) { if (props.x) { return 1; } return; }\n"
        p = _write(tmp_path, "a.tsx", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


# ── Java tests ────────────────────────────────────────────────


class TestJava:
    def test_mixed_returns(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", "public class A { int f(int x) { if (x > 0) { return 1; } return; } }\n")
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_all_value_returns_ok(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", "public class A { int f(int x) { if (x > 0) { return 1; } return 0; } }\n")
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Go tests ──────────────────────────────────────────────────


class TestGo:
    def test_mixed_returns(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.go", "package main\nfunc f(x int) int { if x > 0 { return 1 }; return }\n")
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_all_value_returns_ok(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.go", "package main\nfunc f(x int) int { if x > 0 { return 1 }; return 0 }\n")
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_unsupported_extension(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.rb", "def f(x)\n  if x\n    return 1\n  end\nend\n")
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert r.total_functions == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = InconsistentReturnAnalyzer().analyze_file(p)
        assert r.total_functions == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        r = InconsistentReturnAnalyzer().analyze_file(tmp_path / "nope.py")
        assert r.total_functions == 0

    def test_result_to_dict(self, tmp_path: Path) -> None:
        code = "def f(x):\n    if x:\n        return 1\n    return\n"
        p = _write(tmp_path, "a.py", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert d["total_functions"] == 1
        assert d["issue_count"] == 1

    def test_issue_to_dict(self, tmp_path: Path) -> None:
        code = "def f(x):\n    if x:\n        return 1\n    return\n"
        p = _write(tmp_path, "a.py", code)
        r = InconsistentReturnAnalyzer().analyze_file(p)
        d = r.issues[0].to_dict()
        assert d["has_value_returns"] == 1
        assert d["has_bare_returns"] == 1
        assert d["has_implicit"] is False
