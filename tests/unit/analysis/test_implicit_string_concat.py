"""Tests for Implicit String Concatenation Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.implicit_string_concat import (
    ISSUE_IMPLICIT_CONCAT,
    ISSUE_MISSING_COMMA,
    ImplicitStringConcatAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Basic implicit concatenation ──────────────────────────────


class TestBasicConcatenation:
    def test_adjacent_strings(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = "hello" "world"\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_IMPLICIT_CONCAT

    def test_triple_quote_concat(self, tmp_path: Path) -> None:
        code = 'x = """hello""" """world"""\n'
        p = _write(tmp_path, "a.py", code)
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) >= 1

    def test_no_concatenation(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = "hello"\ny = "world"\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_explicit_plus(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = "hello" + "world"\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Missing comma in collections ──────────────────────────────


class TestMissingCommaInList:
    def test_list_missing_comma(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = ["a" "b"]\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        missing_comma = [i for i in r.issues if i.issue_type == ISSUE_MISSING_COMMA]
        assert len(missing_comma) >= 1

    def test_list_with_comma(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = ["a", "b"]\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_list_three_strings_missing_comma(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = ["a" "b" "c"]\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) >= 1


class TestMissingCommaInSet:
    def test_set_missing_comma(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = {"a" "b"}\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        missing_comma = [i for i in r.issues if i.issue_type == ISSUE_MISSING_COMMA]
        assert len(missing_comma) >= 1


class TestMissingCommaInTuple:
    def test_tuple_missing_comma(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = ("a" "b",)\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) >= 1


# ── Severity ──────────────────────────────────────────────────


class TestSeverity:
    def test_collection_is_medium(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = ["a" "b"]\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        for issue in r.issues:
            if issue.issue_type == ISSUE_MISSING_COMMA:
                assert issue.severity == "medium"

    def test_standalone_is_low(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = "a" "b"\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        for issue in r.issues:
            if issue.issue_type == ISSUE_IMPLICIT_CONCAT:
                assert issue.severity == "low"


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        r = ImplicitStringConcatAnalyzer().analyze_file(tmp_path / "nope.py")
        assert len(r.issues) == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", 'var x = "a" "b";\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_to_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = "a" "b"\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "issues" in d
        assert d["issue_count"] >= 1

    def test_single_string(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'x = "hello"\n')
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_multiline_string_no_concat(self, tmp_path: Path) -> None:
        code = 'x = (\n    "hello"\n)\n'
        p = _write(tmp_path, "a.py", code)
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_line_number_correct(self, tmp_path: Path) -> None:
        code = 'x = "a" "b"\n'
        p = _write(tmp_path, "a.py", code)
        r = ImplicitStringConcatAnalyzer().analyze_file(p)
        assert len(r.issues) >= 1
        assert r.issues[0].line == 1
