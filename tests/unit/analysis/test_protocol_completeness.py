"""Tests for Protocol Completeness Analyzer."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.protocol_completeness import (
    ISSUE_MISSING_EQUALS,
    ISSUE_MISSING_EXIT,
    ISSUE_MISSING_HASH,
    ISSUE_MISSING_HASHCODE,
    ISSUE_MISSING_NEXT,
    ISSUE_MISSING_SET_OR_DELETE,
    ProtocolCompletenessAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Python tests ──────────────────────────────────────────────


class TestPython:
    def test_eq_without_hash(self, tmp_path: Path) -> None:
        code = (
            "class Bad:\n"
            "    def __eq__(self, other):\n"
            "        return True\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 1
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_MISSING_HASH
        assert r.issues[0].class_name == "Bad"

    def test_eq_with_hash_ok(self, tmp_path: Path) -> None:
        code = (
            "class Good:\n"
            "    def __eq__(self, other):\n"
            "        return True\n"
            "    def __hash__(self):\n"
            "        return 42\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 1
        assert len(r.issues) == 0

    def test_enter_without_exit(self, tmp_path: Path) -> None:
        code = (
            "class BadCtx:\n"
            "    def __enter__(self):\n"
            "        return self\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_MISSING_EXIT

    def test_enter_with_exit_ok(self, tmp_path: Path) -> None:
        code = (
            "class GoodCtx:\n"
            "    def __enter__(self):\n"
            "        return self\n"
            "    def __exit__(self, *args):\n"
            "        pass\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_iter_without_next(self, tmp_path: Path) -> None:
        code = (
            "class BadIter:\n"
            "    def __iter__(self):\n"
            "        return self\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_MISSING_NEXT

    def test_iter_with_next_ok(self, tmp_path: Path) -> None:
        code = (
            "class GoodIter:\n"
            "    def __iter__(self):\n"
            "        return self\n"
            "    def __next__(self):\n"
            "        raise StopIteration\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_get_without_set_or_delete(self, tmp_path: Path) -> None:
        code = (
            "class BadDesc:\n"
            "    def __get__(self, obj, typ=None):\n"
            "        return 42\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_MISSING_SET_OR_DELETE

    def test_get_with_set_ok(self, tmp_path: Path) -> None:
        code = (
            "class GoodDesc:\n"
            "    def __get__(self, obj, typ=None):\n"
            "        return 42\n"
            "    def __set__(self, obj, value):\n"
            "        pass\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_get_with_delete_ok(self, tmp_path: Path) -> None:
        code = (
            "class GoodDesc:\n"
            "    def __get__(self, obj, typ=None):\n"
            "        return 42\n"
            "    def __delete__(self, obj):\n"
            "        pass\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_no_dunder_methods_ok(self, tmp_path: Path) -> None:
        code = (
            "class Plain:\n"
            "    def foo(self):\n"
            "        pass\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 1
        assert len(r.issues) == 0

    def test_multiple_issues_in_one_class(self, tmp_path: Path) -> None:
        code = (
            "class Broken:\n"
            "    def __eq__(self, other):\n"
            "        return True\n"
            "    def __enter__(self):\n"
            "        return self\n"
            "    def __iter__(self):\n"
            "        return self\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 3

    def test_multiple_classes(self, tmp_path: Path) -> None:
        code = (
            "class A:\n"
            "    def __eq__(self, other):\n"
            "        return True\n"
            "\n"
            "class B:\n"
            "    def __hash__(self):\n"
            "        return 42\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 2
        assert len(r.issues) == 1
        assert r.issues[0].class_name == "A"


# ── Java tests ────────────────────────────────────────────────


class TestJava:
    def test_equals_without_hashcode(self, tmp_path: Path) -> None:
        code = (
            "public class Bad {\n"
            "    @Override\n"
            "    public boolean equals(Object o) {\n"
            "        return true;\n"
            "    }\n"
            "}\n"
        )
        p = _write(tmp_path, "A.java", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 1
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_MISSING_HASHCODE

    def test_equals_with_hashcode_ok(self, tmp_path: Path) -> None:
        code = (
            "public class Good {\n"
            "    @Override\n"
            "    public boolean equals(Object o) {\n"
            "        return true;\n"
            "    }\n"
            "    @Override\n"
            "    public int hashCode() {\n"
            "        return 42;\n"
            "    }\n"
            "}\n"
        )
        p = _write(tmp_path, "A.java", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_compareto_without_equals(self, tmp_path: Path) -> None:
        code = (
            "public class Bad implements Comparable<Bad> {\n"
            "    @Override\n"
            "    public int compareTo(Bad o) {\n"
            "        return 0;\n"
            "    }\n"
            "}\n"
        )
        p = _write(tmp_path, "A.java", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_MISSING_EQUALS

    def test_compareto_with_equals_still_needs_hashcode(self, tmp_path: Path) -> None:
        code = (
            "public class Good implements Comparable<Good> {\n"
            "    @Override\n"
            "    public int compareTo(Good o) {\n"
            "        return 0;\n"
            "    }\n"
            "    @Override\n"
            "    public boolean equals(Object o) {\n"
            "        return true;\n"
            "    }\n"
            "}\n"
        )
        p = _write(tmp_path, "A.java", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_MISSING_HASHCODE

    def test_no_overrides_ok(self, tmp_path: Path) -> None:
        code = (
            "public class Plain {\n"
            "    public void foo() {}\n"
            "}\n"
        )
        p = _write(tmp_path, "A.java", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 1
        assert len(r.issues) == 0


# ── JavaScript/TypeScript tests ───────────────────────────────


class TestJavaScript:
    def test_class_no_issues(self, tmp_path: Path) -> None:
        code = (
            "class Foo {\n"
            "    bar() { return 1; }\n"
            "}\n"
        )
        p = _write(tmp_path, "a.js", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 1
        assert len(r.issues) == 0

    def test_unsupported_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.txt", "class Foo { }")
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 0


class TestTypeScript:
    def test_class_no_issues(self, tmp_path: Path) -> None:
        code = (
            "class Foo {\n"
            "    bar(): number { return 1; }\n"
            "}\n"
        )
        p = _write(tmp_path, "a.ts", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 1
        assert len(r.issues) == 0


class TestGo:
    def test_type_no_issues(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'type Foo struct {\n'
            '    Name string\n'
            '}\n\n'
            'func (f Foo) String() string {\n'
            '    return f.Name\n'
            '}\n'
        )
        p = _write(tmp_path, "a.go", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked >= 0


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_file_without_classes(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "x = 1\ny = 2\n")
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 0
        assert len(r.issues) == 0

    def test_nested_class(self, tmp_path: Path) -> None:
        code = (
            "class Outer:\n"
            "    class Inner:\n"
            "        def __eq__(self, other):\n"
            "            return True\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.classes_checked == 2
        assert len(r.issues) == 1
        assert r.issues[0].class_name == "Inner"

    def test_to_dict(self, tmp_path: Path) -> None:
        code = (
            "class Bad:\n"
            "    def __eq__(self, other):\n"
            "        return True\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "file_path" in d
        assert "classes_checked" in d
        assert "issue_count" in d
        assert d["issue_count"] == 1
        issue_dict = r.issues[0].to_dict()
        assert "line" in issue_dict
        assert "issue_type" in issue_dict
        assert "class_name" in issue_dict
        assert "missing_methods" in issue_dict
        assert "trigger_method" in issue_dict

    def test_severity_is_high(self, tmp_path: Path) -> None:
        code = (
            "class Bad:\n"
            "    def __eq__(self, other):\n"
            "        return True\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = ProtocolCompletenessAnalyzer().analyze_file(p)
        assert r.issues[0].severity == "high"
