"""Tests for Assert-on-Tuple Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.assert_on_tuple import (
    ISSUE_ASSERT_ON_TUPLE,
    AssertOnTupleAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Detection ─────────────────────────────────────────────────


class TestDetect:
    def test_assert_on_tuple_with_message(self, tmp_path: Path) -> None:
        code = 'assert (x > 0, "must be positive")\n'
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_ASSERT_ON_TUPLE
        assert r.issues[0].severity == "high"

    def test_assert_on_tuple_no_message(self, tmp_path: Path) -> None:
        code = "assert (x, y)\n"
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert len(r.issues) == 1

    def test_assert_on_tuple_trailing_comma(self, tmp_path: Path) -> None:
        code = "assert (x > 0,)\n"
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert len(r.issues) == 1


class TestNoIssue:
    def test_correct_assert_with_message(self, tmp_path: Path) -> None:
        code = 'assert x > 0, "must be positive"\n'
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert len(r.issues) == 0

    def test_correct_assert_no_message(self, tmp_path: Path) -> None:
        code = "assert x > 0\n"
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert len(r.issues) == 0

    def test_assert_with_parens_condition(self, tmp_path: Path) -> None:
        code = 'assert (x > 0), "must be positive"\n'
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert len(r.issues) == 0

    def test_no_asserts(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "mod.py", "x = 1\n")
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 0
        assert len(r.issues) == 0

    def test_assert_with_boolean_op(self, tmp_path: Path) -> None:
        code = 'assert x > 0 and y > 0, "both must be positive"\n'
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert len(r.issues) == 0


class TestEdgeCases:
    def test_nonexistent_file(self, tmp_path: Path) -> None:
        p = tmp_path / "nope.py"
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "empty.py", "")
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 0

    def test_js_file_ignored(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "function f() { assert(true); }\n")
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 0

    def test_issue_line_number(self, tmp_path: Path) -> None:
        code = "x = 1\nassert (x > 0, 'bad')\n"
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.issues[0].line == 2

    def test_to_dict(self, tmp_path: Path) -> None:
        code = "assert (True, 'msg')\n"
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert d["total_asserts"] == 1
        assert d["issue_count"] == 1
        assert "issues" in d

    def test_issue_to_dict(self, tmp_path: Path) -> None:
        code = "assert (x, 'msg')\n"
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        d = r.issues[0].to_dict()
        assert d["issue_type"] == ISSUE_ASSERT_ON_TUPLE
        assert "description" in d
        assert "suggestion" in d

    def test_multiple_asserts_mixed(self, tmp_path: Path) -> None:
        code = (
            "assert x > 0\n"
            "assert (y > 0, 'bad')\n"
            "assert z, 'ok'\n"
        )
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.total_asserts == 3
        assert len(r.issues) == 1

    def test_result_issue_count_property(self, tmp_path: Path) -> None:
        code = "assert (a, b)\nassert (c, d)\n"
        p = _write(tmp_path, "mod.py", code)
        r = AssertOnTupleAnalyzer().analyze_file(p)
        assert r.issue_count == 2
