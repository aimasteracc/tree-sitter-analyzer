"""Tests for Return in Finally Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.return_in_finally import (
    ISSUE_RAISE_IN_FINALLY,
    ISSUE_RETURN_IN_FINALLY,
    ReturnInFinallyAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Python tests ──────────────────────────────────────────────


class TestPythonReturn:
    def test_return_in_finally(self, tmp_path: Path) -> None:
        code = (
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    finally:\n"
            "        return 1\n"
        )
        p = _write(tmp_path, "mod.py", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert r.total_finally_blocks == 1
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_RETURN_IN_FINALLY
        assert r.issues[0].severity == "high"

    def test_return_in_finally_with_except(self, tmp_path: Path) -> None:
        code = (
            "def f():\n"
            "    try:\n"
            "        risky()\n"
            "    except ValueError:\n"
            "        pass\n"
            "    finally:\n"
            "        return 42\n"
        )
        p = _write(tmp_path, "mod.py", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


class TestPythonRaise:
    def test_raise_in_finally(self, tmp_path: Path) -> None:
        code = (
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    finally:\n"
            "        raise RuntimeError()\n"
        )
        p = _write(tmp_path, "mod.py", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_RAISE_IN_FINALLY
        assert r.issues[0].severity == "medium"


class TestPythonNoIssue:
    def test_finally_without_return(self, tmp_path: Path) -> None:
        code = (
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    finally:\n"
            "        cleanup()\n"
        )
        p = _write(tmp_path, "mod.py", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert r.total_finally_blocks == 1
        assert len(r.issues) == 0

    def test_no_finally(self, tmp_path: Path) -> None:
        code = "x = 1\n"
        p = _write(tmp_path, "mod.py", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert r.total_finally_blocks == 0
        assert len(r.issues) == 0


# ── JavaScript tests ──────────────────────────────────────────


class TestJavaScript:
    def test_return_in_finally(self, tmp_path: Path) -> None:
        code = (
            "function f() {\n"
            "  try {\n"
            "    risky();\n"
            "  } finally {\n"
            "    return 1;\n"
            "  }\n"
            "}\n"
        )
        p = _write(tmp_path, "a.js", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert r.total_finally_blocks == 1
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_RETURN_IN_FINALLY

    def test_throw_in_finally(self, tmp_path: Path) -> None:
        code = (
            "function f() {\n"
            "  try {\n"
            "    risky();\n"
            "  } finally {\n"
            "    throw new Error();\n"
            "  }\n"
            "}\n"
        )
        p = _write(tmp_path, "a.js", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_RAISE_IN_FINALLY

    def test_finally_without_terminal(self, tmp_path: Path) -> None:
        code = (
            "function f() {\n"
            "  try {\n"
            "    risky();\n"
            "  } finally {\n"
            "    cleanup();\n"
            "  }\n"
            "}\n"
        )
        p = _write(tmp_path, "a.js", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── TypeScript tests ──────────────────────────────────────────


class TestTypeScript:
    def test_return_in_finally(self, tmp_path: Path) -> None:
        code = (
            "function f(): number {\n"
            "  try {\n"
            "    return risky();\n"
            "  } finally {\n"
            "    return 0;\n"
            "  }\n"
            "}\n"
        )
        p = _write(tmp_path, "a.ts", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self, tmp_path: Path) -> None:
        p = tmp_path / "nope.py"
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert r.total_finally_blocks == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "empty.py", "")
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert r.total_finally_blocks == 0

    def test_issue_line_number(self, tmp_path: Path) -> None:
        code = "try:\n    pass\nfinally:\n    return 1\n"
        p = _write(tmp_path, "mod.py", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert r.issues[0].line == 4

    def test_to_dict(self, tmp_path: Path) -> None:
        code = "try:\n    pass\nfinally:\n    return 1\n"
        p = _write(tmp_path, "mod.py", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert d["total_finally_blocks"] == 1
        assert d["issue_count"] == 1

    def test_go_file_no_finally(self, tmp_path: Path) -> None:
        code = "package main\nfunc main() {}\n"
        p = _write(tmp_path, "a.go", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert r.total_finally_blocks == 0

    def test_result_issue_count_property(self, tmp_path: Path) -> None:
        code = (
            "try:\n    pass\nfinally:\n    return 1\n"
            "\ntry:\n    pass\nfinally:\n    return 2\n"
        )
        p = _write(tmp_path, "mod.py", code)
        r = ReturnInFinallyAnalyzer().analyze_file(p)
        assert r.issue_count == 2
