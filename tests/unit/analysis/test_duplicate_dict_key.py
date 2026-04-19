"""Tests for Duplicate Dict Key Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.duplicate_dict_key import (
    ISSUE_DUPLICATE_DICT_KEY,
    DuplicateDictKeyAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Python tests ──────────────────────────────────────────────


class TestPython:
    def test_duplicate_string_key(self, tmp_path: Path) -> None:
        code = 'd = {"a": 1, "a": 2}\n'
        p = _write(tmp_path, "mod.py", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.total_dicts == 1
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_DUPLICATE_DICT_KEY
        assert r.issues[0].key == '"a"'

    def test_duplicate_identifier_key(self, tmp_path: Path) -> None:
        code = "d = {a: 1, a: 2}\n"
        p = _write(tmp_path, "mod.py", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_triple_duplicate(self, tmp_path: Path) -> None:
        code = 'd = {"x": 1, "x": 2, "x": 3}\n'
        p = _write(tmp_path, "mod.py", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert len(r.issues) == 2

    def test_no_duplicates(self, tmp_path: Path) -> None:
        code = 'd = {"a": 1, "b": 2}\n'
        p = _write(tmp_path, "mod.py", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.total_dicts == 1
        assert len(r.issues) == 0

    def test_empty_dict(self, tmp_path: Path) -> None:
        code = "d = {}\n"
        p = _write(tmp_path, "mod.py", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.total_dicts == 1
        assert len(r.issues) == 0

    def test_nested_dicts(self, tmp_path: Path) -> None:
        code = 'd = {"a": {"b": 1, "b": 2}}\n'
        p = _write(tmp_path, "mod.py", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.total_dicts == 2
        assert len(r.issues) == 1


# ── JavaScript tests ──────────────────────────────────────────


class TestJavaScript:
    def test_duplicate_key(self, tmp_path: Path) -> None:
        code = "const obj = { a: 1, a: 2 };\n"
        p = _write(tmp_path, "a.js", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.total_dicts == 1
        assert len(r.issues) == 1

    def test_no_duplicates(self, tmp_path: Path) -> None:
        code = "const obj = { a: 1, b: 2 };\n"
        p = _write(tmp_path, "a.js", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── TypeScript tests ──────────────────────────────────────────


class TestTypeScript:
    def test_duplicate_key(self, tmp_path: Path) -> None:
        code = "const obj: Record<string, number> = { a: 1, a: 2 };\n"
        p = _write(tmp_path, "a.ts", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self, tmp_path: Path) -> None:
        p = tmp_path / "nope.py"
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.total_dicts == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "empty.py", "")
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.total_dicts == 0

    def test_java_file_ignored(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", 'class A { void f() { Map m = Map.of("a",1,"a",2); } }')
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.total_dicts == 0

    def test_issue_line_number(self, tmp_path: Path) -> None:
        code = 'd = {\n    "a": 1,\n    "a": 2\n}\n'
        p = _write(tmp_path, "mod.py", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.issues[0].line == 3

    def test_to_dict(self, tmp_path: Path) -> None:
        code = 'd = {"a": 1, "a": 2}\n'
        p = _write(tmp_path, "mod.py", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert d["total_dicts"] == 1
        assert d["issue_count"] == 1
        assert "key" in d["issues"][0]

    def test_result_issue_count_property(self, tmp_path: Path) -> None:
        code = 'd = {"a": 1, "a": 2, "b": 3, "b": 4}\n'
        p = _write(tmp_path, "mod.py", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.issue_count == 2

    def test_multiple_dicts(self, tmp_path: Path) -> None:
        code = 'd1 = {"a": 1}\nd2 = {"b": 1, "b": 2}\n'
        p = _write(tmp_path, "mod.py", code)
        r = DuplicateDictKeyAnalyzer().analyze_file(p)
        assert r.total_dicts == 2
        assert len(r.issues) == 1
