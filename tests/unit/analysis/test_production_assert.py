"""Tests for Production Assert Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.production_assert import (
    ISSUE_ASSERT_WITH_MESSAGE,
    ISSUE_PRODUCTION_ASSERT,
    ProductionAssertAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Basic detection ───────────────────────────────────────────


class TestBasicAssert:
    def test_simple_assert(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "module.py", "assert x > 0\n")
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_PRODUCTION_ASSERT
        assert r.issues[0].severity == "low"

    def test_assert_with_message(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "module.py", 'assert x > 0, "must be positive"\n')
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_ASSERT_WITH_MESSAGE
        assert r.issues[0].severity == "medium"

    def test_multiple_asserts(self, tmp_path: Path) -> None:
        code = "assert x\nassert y, 'bad'\nassert z\n"
        p = _write(tmp_path, "module.py", code)
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 3
        assert len(r.issues) == 3

    def test_no_asserts(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "module.py", "x = 1\ny = 2\n")
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 0
        assert len(r.issues) == 0

    def test_assert_in_function(self, tmp_path: Path) -> None:
        code = "def validate(data):\n    assert data is not None\n    return data\n"
        p = _write(tmp_path, "module.py", code)
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert len(r.issues) == 1

    def test_assert_in_class_method(self, tmp_path: Path) -> None:
        code = (
            "class Service:\n"
            "    def process(self, x):\n"
            "        assert x >= 0, 'negative'\n"
            "        return x * 2\n"
        )
        p = _write(tmp_path, "module.py", code)
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
        assert r.issues[0].issue_type == ISSUE_ASSERT_WITH_MESSAGE


# ── Test file exclusion ───────────────────────────────────────


class TestFileExclusion:
    def test_test_file_skipped(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "test_module.py", "assert x > 0\n")
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 0
        assert len(r.issues) == 0

    def test_conftest_skipped(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "conftest.py", "assert True\n")
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 0

    def test_tests_dir_skipped(self, tmp_path: Path) -> None:
        d = tmp_path / "tests"
        d.mkdir()
        p = _write(d, "test_foo.py", "assert True\n")
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 0

    def test_spec_file_skipped(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "spec_handler.py", "assert True\n")
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 0


# ── Non-Python files ──────────────────────────────────────────


class TestNonPython:
    def test_js_file_ignored(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "function f() { console.assert(true); }\n")
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 0

    def test_java_file_ignored(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", "class A { void f() { assert true; } }\n")
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 0


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self, tmp_path: Path) -> None:
        p = tmp_path / "nonexistent.py"
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "empty.py", "")
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 0
        assert len(r.issues) == 0

    def test_issue_line_number(self, tmp_path: Path) -> None:
        code = "x = 1\nassert x > 0\n"
        p = _write(tmp_path, "mod.py", code)
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.issues[0].line == 2

    def test_to_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "mod.py", "assert True\n")
        r = ProductionAssertAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert d["total_asserts"] == 1
        assert d["issue_count"] == 1
        assert len(d["issues"]) == 1

    def test_issue_to_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "mod.py", 'assert False, "msg"\n')
        r = ProductionAssertAnalyzer().analyze_file(p)
        d = r.issues[0].to_dict()
        assert d["issue_type"] == ISSUE_ASSERT_WITH_MESSAGE
        assert d["severity"] == "medium"
        assert "description" in d
        assert "suggestion" in d
        assert "line" in d
        assert "context" in d

    def test_result_issue_count_property(self, tmp_path: Path) -> None:
        code = "assert x\nassert y\n"
        p = _write(tmp_path, "mod.py", code)
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.issue_count == 2

    def test_nested_assert_in_if(self, tmp_path: Path) -> None:
        code = "if mode:\n    assert check()\n"
        p = _write(tmp_path, "mod.py", code)
        r = ProductionAssertAnalyzer().analyze_file(p)
        assert r.total_asserts == 1
