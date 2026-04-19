"""Tests for Builtin Shadow Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.builtin_shadow import (
    ISSUE_SHADOWED_ASSIGNMENT,
    ISSUE_SHADOWED_CLASS,
    ISSUE_SHADOWED_FOR_TARGET,
    ISSUE_SHADOWED_FUNCTION,
    ISSUE_SHADOWED_IMPORT,
    ISSUE_SHADOWED_PARAMETER,
    BuiltinShadowAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Assignment shadowing ─────────────────────────────────────


class TestAssignmentShadow:
    def test_list_assignment(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "list = [1, 2, 3]\n")
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SHADOWED_ASSIGNMENT
        assert r.issues[0].name == "list"

    def test_dict_assignment(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "dict = {'a': 1}\n")
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].name == "dict"

    def test_id_assignment(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "id = 42\n")
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].name == "id"

    def test_normal_assignment_ok(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "my_list = [1, 2, 3]\n")
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_augmented_assignment_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = 1\nx += 1\n")
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Function shadowing ───────────────────────────────────────


class TestFunctionShadow:
    def test_function_shadows_id(self, tmp_path: Path) -> None:
        code = "def id(x):\n    return x\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SHADOWED_FUNCTION
        assert r.issues[0].name == "id"

    def test_function_shadows_input(self, tmp_path: Path) -> None:
        code = "def input(prompt):\n    return ''\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].name == "input"

    def test_normal_function_ok(self, tmp_path: Path) -> None:
        code = "def get_id(x):\n    return x\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Class shadowing ──────────────────────────────────────────


class TestClassShadow:
    def test_class_shadows_type(self, tmp_path: Path) -> None:
        code = "class type:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SHADOWED_CLASS
        assert r.issues[0].name == "type"

    def test_class_shadows_object(self, tmp_path: Path) -> None:
        code = "class object:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].name == "object"

    def test_normal_class_ok(self, tmp_path: Path) -> None:
        code = "class MyType:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Parameter shadowing ──────────────────────────────────────


class TestParameterShadow:
    def test_param_shadows_list(self, tmp_path: Path) -> None:
        code = "def foo(list):\n    return list\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) >= 1
        param_issues = [i for i in r.issues if i.issue_type == ISSUE_SHADOWED_PARAMETER]
        assert len(param_issues) == 1
        assert param_issues[0].name == "list"

    def test_typed_param_shadows_set(self, tmp_path: Path) -> None:
        code = "def foo(set: int) -> None:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        param_issues = [i for i in r.issues if i.issue_type == ISSUE_SHADOWED_PARAMETER]
        assert len(param_issues) == 1
        assert param_issues[0].name == "set"

    def test_default_param_shadows_dict(self, tmp_path: Path) -> None:
        code = "def foo(dict=None):\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        param_issues = [i for i in r.issues if i.issue_type == ISSUE_SHADOWED_PARAMETER]
        assert len(param_issues) == 1
        assert param_issues[0].name == "dict"

    def test_normal_param_ok(self, tmp_path: Path) -> None:
        code = "def foo(items):\n    return items\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        param_issues = [i for i in r.issues if i.issue_type == ISSUE_SHADOWED_PARAMETER]
        assert len(param_issues) == 0


# ── For-loop target shadowing ────────────────────────────────


class TestForTargetShadow:
    def test_for_shadows_list(self, tmp_path: Path) -> None:
        code = "for list in items:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SHADOWED_FOR_TARGET
        assert r.issues[0].name == "list"

    def test_for_normal_ok(self, tmp_path: Path) -> None:
        code = "for item in items:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Import shadowing ─────────────────────────────────────────


class TestImportShadow:
    def test_import_shadows_list(self, tmp_path: Path) -> None:
        code = "from os.path import list\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SHADOWED_IMPORT
        assert r.issues[0].name == "list"

    def test_aliased_import_ok(self, tmp_path: Path) -> None:
        code = "from typing import List as TList\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        import_issues = [i for i in r.issues if i.issue_type == ISSUE_SHADOWED_IMPORT]
        assert len(import_issues) == 0

    def test_normal_import_ok(self, tmp_path: Path) -> None:
        code = "import os\n"
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        import_issues = [i for i in r.issues if i.issue_type == ISSUE_SHADOWED_IMPORT]
        assert len(import_issues) == 0


# ── Edge cases ───────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        r = BuiltinShadowAnalyzer().analyze_file(tmp_path / "nonexistent.py")
        assert r.total_definitions == 0

    def test_unsupported_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "var list = [1, 2];")
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert r.total_definitions == 0

    def test_multiple_shadows(self, tmp_path: Path) -> None:
        code = (
            "list = [1, 2]\n"
            "dict = {}\n"
            "set = set()\n"
            "id = 42\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert len(r.issues) == 4

    def test_to_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "list = []\n")
        r = BuiltinShadowAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "file_path" in d
        assert "total_definitions" in d
        assert "issue_count" in d
        assert d["issue_count"] == 1
        issue_dict = r.issues[0].to_dict()
        assert "line" in issue_dict
        assert "issue_type" in issue_dict
        assert "name" in issue_dict

    def test_severity_high_for_assignment(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "list = []\n")
        r = BuiltinShadowAnalyzer().analyze_file(p)
        assert r.issues[0].severity == "high"
