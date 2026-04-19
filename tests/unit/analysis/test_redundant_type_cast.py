"""Tests for Redundant Type Cast Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.redundant_type_cast import (
    ISSUE_REDUNDANT_BOOL,
    ISSUE_REDUNDANT_FLOAT,
    ISSUE_REDUNDANT_INT,
    ISSUE_REDUNDANT_LIST,
    ISSUE_REDUNDANT_SET,
    ISSUE_REDUNDANT_STR,
    ISSUE_REDUNDANT_TUPLE,
    RedundantTypeCastAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Python tests ──────────────────────────────────────────────


class TestPython:
    def test_str_str(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = str(str(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_REDUNDANT_STR

    def test_int_int(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = int(int(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_REDUNDANT_INT

    def test_float_float(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = float(float(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_REDUNDANT_FLOAT

    def test_list_list(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = list(list(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_REDUNDANT_LIST

    def test_tuple_tuple(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = tuple(tuple(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_REDUNDANT_TUPLE

    def test_set_set(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = set(set(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_REDUNDANT_SET

    def test_bool_bool(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = bool(bool(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_REDUNDANT_BOOL

    def test_normal_cast_ok(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = str(y)\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_different_casts_ok(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = str(int(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_multiple_args_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = int(int(y), 16)\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_nested_triple(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = int(int(int(y)))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 2

    def test_method_call_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = obj.str(obj.str(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── JavaScript/TypeScript tests ───────────────────────────────


class TestJavaScript:
    def test_string_string(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "const x = String(String(y));\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_REDUNDANT_STR

    def test_number_number(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "const x = Number(Number(y));\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_REDUNDANT_INT

    def test_normal_cast_ok(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "const x = String(y);\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


class TestTypeScript:
    def test_number_number(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.ts", "const x = Number(Number(y));\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


# ── Java tests ────────────────────────────────────────────────


class TestJava:
    def test_normal_code_ok(self, tmp_path: Path) -> None:
        code = (
            "public class A {\n"
            "    public void foo() {\n"
            "        String x = String.valueOf(42);\n"
            "    }\n"
            "}\n"
        )
        p = _write(tmp_path, "A.java", code)
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        r = RedundantTypeCastAnalyzer().analyze_file(tmp_path / "no.py")
        assert r.total_calls == 0

    def test_unsupported_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.go", 'package main\n')
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert r.total_calls == 0

    def test_to_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = str(str(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "file_path" in d
        assert "total_calls" in d
        assert "issue_count" in d
        assert d["issue_count"] == 1
        issue_dict = r.issues[0].to_dict()
        assert "line" in issue_dict
        assert "issue_type" in issue_dict
        assert "context" in issue_dict

    def test_severity_low(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = str(str(y))\n")
        r = RedundantTypeCastAnalyzer().analyze_file(p)
        assert r.issues[0].severity == "low"
