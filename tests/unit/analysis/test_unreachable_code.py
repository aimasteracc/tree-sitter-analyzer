"""Tests for Unreachable Code Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.unreachable_code import (
    ISSUE_AFTER_BREAK,
    ISSUE_AFTER_CONTINUE,
    ISSUE_AFTER_RAISE,
    ISSUE_AFTER_RETURN,
    ISSUE_AFTER_THROW,
    UnreachableCodeAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Python tests ──────────────────────────────────────────────


class TestPythonReturn:
    def test_code_after_return(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def f():\n    return 1\n    x = 2\n")
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_RETURN

    def test_multiple_lines_after_return(self, tmp_path: Path) -> None:
        code = "def f():\n    return 1\n    x = 2\n    y = 3\n"
        p = _write(tmp_path, "a.py", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 2
        assert all(i.issue_type == ISSUE_AFTER_RETURN for i in r.issues)

    def test_no_return_at_end(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def f():\n    x = 1\n    y = 2\n")
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_return_with_nothing_after(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "def f():\n    return 1\n")
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


class TestPythonBreak:
    def test_code_after_break(self, tmp_path: Path) -> None:
        code = "for i in range(10):\n    break\n    x = 1\n"
        p = _write(tmp_path, "a.py", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_BREAK


class TestPythonContinue:
    def test_code_after_continue(self, tmp_path: Path) -> None:
        code = "for i in range(10):\n    continue\n    x = 1\n"
        p = _write(tmp_path, "a.py", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_CONTINUE


class TestPythonRaise:
    def test_code_after_raise(self, tmp_path: Path) -> None:
        code = "def f():\n    raise ValueError\n    x = 1\n"
        p = _write(tmp_path, "a.py", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_RAISE


# ── JavaScript tests ──────────────────────────────────────────


class TestJavaScript:
    def test_code_after_return(self, tmp_path: Path) -> None:
        code = "function f() {\n  return 1;\n  var x = 2;\n}\n"
        p = _write(tmp_path, "a.js", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_RETURN

    def test_code_after_throw(self, tmp_path: Path) -> None:
        code = "function f() {\n  throw new Error();\n  var x = 1;\n}\n"
        p = _write(tmp_path, "a.js", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_THROW

    def test_code_after_break(self, tmp_path: Path) -> None:
        code = "for (let i = 0; i < 10; i++) {\n  break;\n  var x = 1;\n}\n"
        p = _write(tmp_path, "a.js", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_BREAK

    def test_no_issues(self, tmp_path: Path) -> None:
        code = "function f() {\n  var x = 1;\n  return x;\n}\n"
        p = _write(tmp_path, "a.js", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── TypeScript tests ──────────────────────────────────────────


class TestTypeScript:
    def test_code_after_return(self, tmp_path: Path) -> None:
        code = "function f(): number {\n  return 1;\n  const x = 2;\n}\n"
        p = _write(tmp_path, "a.ts", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_RETURN


# ── Java tests ────────────────────────────────────────────────


class TestJava:
    def test_code_after_return(self, tmp_path: Path) -> None:
        code = (
            "public class A {\n"
            "  int f() {\n"
            "    return 1;\n"
            "    int x = 2;\n"
            "  }\n"
            "}\n"
        )
        p = _write(tmp_path, "A.java", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_RETURN

    def test_code_after_throw(self, tmp_path: Path) -> None:
        code = (
            "public class A {\n"
            "  void f() {\n"
            "    throw new RuntimeException();\n"
            "    int x = 1;\n"
            "  }\n"
            "}\n"
        )
        p = _write(tmp_path, "A.java", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_THROW

    def test_no_issues(self, tmp_path: Path) -> None:
        code = (
            "public class A {\n"
            "  int f() {\n"
            "    int x = 1;\n"
            "    return x;\n"
            "  }\n"
            "}\n"
        )
        p = _write(tmp_path, "A.java", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Go tests ──────────────────────────────────────────────────


class TestGo:
    def test_code_after_return(self, tmp_path: Path) -> None:
        code = "package main\n\nfunc f() int {\n  return 1\n  x := 2\n}\n"
        p = _write(tmp_path, "a.go", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_RETURN

    def test_code_after_break(self, tmp_path: Path) -> None:
        code = (
            "package main\n\n"
            "func f() {\n"
            "  for i := 0; i < 10; i++ {\n"
            "    break\n"
            "    x := 1\n"
            "  }\n"
            "}\n"
        )
        p = _write(tmp_path, "a.go", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AFTER_BREAK


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        r = UnreachableCodeAnalyzer().analyze_file(tmp_path / "nope.py")
        assert len(r.issues) == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.css", "body { color: red; }")
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_issue_has_line_number(self, tmp_path: Path) -> None:
        code = "def f():\n    return 1\n    x = 2\n"
        p = _write(tmp_path, "a.py", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].line == 3

    def test_to_dict(self, tmp_path: Path) -> None:
        code = "def f():\n    return 1\n    x = 2\n"
        p = _write(tmp_path, "a.py", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "issues" in d
        assert d["issue_count"] == 1
        assert d["issues"][0]["line"] == 3
        assert "terminal_line" in d["issues"][0]

    def test_separate_functions_independent(self, tmp_path: Path) -> None:
        code = (
            "def f():\n"
            "    return 1\n"
            "    x = 2\n"
            "\n"
            "def g():\n"
            "    return 3\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = UnreachableCodeAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
