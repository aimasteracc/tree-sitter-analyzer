"""Tests for Suspicious Type Check Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.suspicious_type_check import (
    ISSUE_EQ_TYPE_CHECK,
    ISSUE_NE_TYPE_CHECK,
    SuspiciousTypeCheckAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── type() == checks ──────────────────────────────────────────


class TestEqTypeCheck:
    def test_type_eq_right(self, tmp_path: Path) -> None:
        code = "if type(x) == int:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_EQ_TYPE_CHECK

    def test_type_eq_left(self, tmp_path: Path) -> None:
        code = "if int == type(x):\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_EQ_TYPE_CHECK

    def test_normal_eq(self, tmp_path: Path) -> None:
        code = "if x == 5:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── type() != checks ──────────────────────────────────────────


class TestNeTypeCheck:
    def test_type_ne(self, tmp_path: Path) -> None:
        code = "if type(x) != str:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_NE_TYPE_CHECK

    def test_normal_ne(self, tmp_path: Path) -> None:
        code = "if x != 5:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── isinstance is fine ────────────────────────────────────────


class TestIsinstanceOk:
    def test_isinstance_not_flagged(self, tmp_path: Path) -> None:
        code = "if isinstance(x, int):\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        r = SuspiciousTypeCheckAnalyzer().analyze_file(tmp_path / "nope.py")
        assert len(r.issues) == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "if (typeof x === 'string') {}\n")
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_to_dict(self, tmp_path: Path) -> None:
        code = "if type(x) == int:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "issues" in d
        assert d["issue_count"] == 1

    def test_line_number(self, tmp_path: Path) -> None:
        code = "x = 1\nif type(x) == int:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].line == 2

    def test_multiple_checks(self, tmp_path: Path) -> None:
        code = "if type(x) == int or type(y) == str:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        assert len(r.issues) == 2

    def test_isinstance_not_flagged_in_comparison(self, tmp_path: Path) -> None:
        code = "if isinstance(x, int) == True:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = SuspiciousTypeCheckAnalyzer().analyze_file(p)
        type_issues = [i for i in r.issues if i.issue_type in (ISSUE_EQ_TYPE_CHECK, ISSUE_NE_TYPE_CHECK)]
        assert len(type_issues) == 0
