"""Tests for Self-Assignment Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.self_assignment import (
    ISSUE_SELF_ASSIGN,
    ISSUE_SELF_ASSIGN_MEMBER,
    SelfAssignmentAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Python tests ──────────────────────────────────────────────


class TestPythonVariable:
    def test_simple_self_assign(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = x\n")
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SELF_ASSIGN

    def test_self_assign_in_function(self, tmp_path: Path) -> None:
        code = "def f():\n    x = 1\n    x = x\n"
        p = _write(tmp_path, "a.py", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_different_value(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = y\n")
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_normal_assignment(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = 1\ny = 2\n")
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


class TestPythonMember:
    def test_self_member_assign(self, tmp_path: Path) -> None:
        code = "class C:\n    def f(self):\n        self.x = self.x\n"
        p = _write(tmp_path, "a.py", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SELF_ASSIGN_MEMBER

    def test_different_member_assign(self, tmp_path: Path) -> None:
        code = "class C:\n    def f(self, other):\n        self.x = other.x\n"
        p = _write(tmp_path, "a.py", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_self_member_different_field(self, tmp_path: Path) -> None:
        code = "class C:\n    def f(self):\n        self.x = self.y\n"
        p = _write(tmp_path, "a.py", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── JavaScript tests ──────────────────────────────────────────


class TestJavaScript:
    def test_simple_self_assign(self, tmp_path: Path) -> None:
        code = "let x = 1;\nx = x;\n"
        p = _write(tmp_path, "a.js", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SELF_ASSIGN

    def test_this_member_self_assign(self, tmp_path: Path) -> None:
        code = "class C {\n  f() {\n    this.x = this.x;\n  }\n}\n"
        p = _write(tmp_path, "a.js", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SELF_ASSIGN_MEMBER

    def test_normal_assign(self, tmp_path: Path) -> None:
        code = "let x = 1;\nlet y = x;\n"
        p = _write(tmp_path, "a.js", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── TypeScript tests ──────────────────────────────────────────


class TestTypeScript:
    def test_self_assign(self, tmp_path: Path) -> None:
        code = "let x: number = 1;\nx = x;\n"
        p = _write(tmp_path, "a.ts", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_this_self_assign(self, tmp_path: Path) -> None:
        code = "class C {\n  x: number = 0;\n  f() {\n    this.x = this.x;\n  }\n}\n"
        p = _write(tmp_path, "a.ts", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SELF_ASSIGN_MEMBER


# ── Go tests ──────────────────────────────────────────────────


class TestGo:
    def test_self_assign(self, tmp_path: Path) -> None:
        code = "package main\n\nfunc main() {\n  x := 1\n  x = x\n}\n"
        p = _write(tmp_path, "a.go", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_normal_assign(self, tmp_path: Path) -> None:
        code = "package main\n\nfunc main() {\n  x := 1\n  y := x\n}\n"
        p = _write(tmp_path, "a.go", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        r = SelfAssignmentAnalyzer().analyze_file(tmp_path / "nope.py")
        assert len(r.issues) == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.css", "body { color: red; }")
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_to_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = x\n")
        r = SelfAssignmentAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "issues" in d
        assert d["issue_count"] == 1

    def test_line_number(self, tmp_path: Path) -> None:
        code = "x = 1\ny = y\n"
        p = _write(tmp_path, "a.py", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].line == 2

    def test_multiple_self_assignments(self, tmp_path: Path) -> None:
        code = "x = x\ny = y\n"
        p = _write(tmp_path, "a.py", code)
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 2

    def test_augmented_assignment_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x += x\n")
        r = SelfAssignmentAnalyzer().analyze_file(p)
        assert len(r.issues) == 0
