"""Tests for String Format Consistency Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.string_format_consistency import (
    ISSUE_LEGACY_DOT_FORMAT,
    ISSUE_LEGACY_FORMAT,
    ISSUE_MIXED_FORMAT,
    StringFormatConsistencyAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Mixed styles ──────────────────────────────────────────────


class TestMixedStyles:
    def test_percent_and_fstring(self, tmp_path: Path) -> None:
        code = 'x = "hello %s" % name\ny = f"hello {name}"\n'
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert any(i.issue_type == ISSUE_MIXED_FORMAT for i in r.issues)

    def test_dot_format_and_fstring(self, tmp_path: Path) -> None:
        code = 'x = "hello {}".format(name)\ny = f"hello {name}"\n'
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert any(i.issue_type == ISSUE_MIXED_FORMAT for i in r.issues)

    def test_all_three_styles(self, tmp_path: Path) -> None:
        code = (
            'x = "hello %s" % name\n'
            'y = "hello {}".format(name)\n'
            'z = f"hello {name}"\n'
        )
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert any(i.issue_type == ISSUE_MIXED_FORMAT for i in r.issues)
        assert r.percent_format_count == 1
        assert r.dot_format_count == 1
        assert r.fstring_count == 1

    def test_no_mixing_fstring_only(self, tmp_path: Path) -> None:
        code = 'x = f"hello {name}"\ny = f"world {place}"\n'
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Legacy format only ────────────────────────────────────────


class TestLegacyFormat:
    def test_percent_only(self, tmp_path: Path) -> None:
        code = 'x = "hello %s" % name\n'
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert any(i.issue_type == ISSUE_LEGACY_FORMAT for i in r.issues)

    def test_dot_format_only(self, tmp_path: Path) -> None:
        code = 'x = "hello {}".format(name)\n'
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert any(i.issue_type == ISSUE_LEGACY_DOT_FORMAT for i in r.issues)


# ── No issues ─────────────────────────────────────────────────


class TestNoIssues:
    def test_plain_strings(self, tmp_path: Path) -> None:
        code = 'x = "hello"\ny = "world"\n'
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_fstring_only(self, tmp_path: Path) -> None:
        code = 'x = f"hello {name}"\n'
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self, tmp_path: Path) -> None:
        r = StringFormatConsistencyAnalyzer().analyze_file(tmp_path / "nope.py")
        assert len(r.issues) == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", 'var x = "hello %s";\n')
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_to_dict(self, tmp_path: Path) -> None:
        code = 'x = "hello %s" % name\ny = f"hello {name}"\n'
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "issues" in d
        assert "percent_format_count" in d
        assert "dot_format_count" in d
        assert "fstring_count" in d

    def test_counts_correct(self, tmp_path: Path) -> None:
        code = (
            'x = "hello %s" % name\n'
            'y = "hello {}".format(name)\n'
            'z = f"hello {name}"\n'
        )
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert r.percent_format_count == 1
        assert r.dot_format_count == 1
        assert r.fstring_count == 1

    def test_string_without_placeholder_not_counted(self, tmp_path: Path) -> None:
        code = 'x = "hello"\n'
        p = _write(tmp_path, "a.py", code)
        r = StringFormatConsistencyAnalyzer().analyze_file(p)
        assert r.percent_format_count == 0
