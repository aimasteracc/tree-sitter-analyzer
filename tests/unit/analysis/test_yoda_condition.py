"""Tests for Yoda Condition Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.yoda_condition import (
    ISSUE_YODA_EQ,
    ISSUE_YODA_NEQ,
    YodaConditionAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Python tests ──────────────────────────────────────────────


class TestPython:
    def test_yoda_string_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'if "hello" == name:\n    pass\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert r.total_comparisons >= 1
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_YODA_EQ

    def test_yoda_string_neq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'if "hello" != name:\n    pass\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_YODA_NEQ

    def test_yoda_number_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "if 0 == x:\n    pass\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_YODA_EQ

    def test_normal_comparison_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'if x == "hello":\n    pass\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_literal_vs_literal_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'if "a" == "b":\n    pass\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_yoda_none_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "if None == x:\n    pass\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_yoda_true_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "if True == flag:\n    pass\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_yoda_false_neq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "if False != result:\n    pass\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_YODA_NEQ

    def test_variable_eq_variable_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "if a == b:\n    pass\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_multiple_yoda_in_file(self, tmp_path: Path) -> None:
        code = (
            'if "expected" == actual:\n'
            "    pass\n"
            "if 42 == count:\n"
            "    pass\n"
            'if name == "world":\n'
            "    pass\n"
        )
        p = _write(tmp_path, "a.py", code)
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 2

    def test_line_number_correct(self, tmp_path: Path) -> None:
        code = "x = 1\ny = 2\nif 0 == x:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].line == 3


# ── JavaScript/TypeScript tests ───────────────────────────────


class TestJavaScript:
    def test_yoda_string_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", 'if ("hello" === name) { return; }\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 0  # === not ==

    def test_yoda_string_loose_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", 'if ("hello" == name) { return; }\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_YODA_EQ

    def test_yoda_number_neq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "if (0 != count) { return; }\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_YODA_NEQ

    def test_yoda_null_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "if (null == obj) { return; }\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_yoda_undefined_neq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "if (undefined != val) { return; }\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_normal_js_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", 'if (name === "hello") { return; }\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


class TestTypeScript:
    def test_yoda_string_eq_ts(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.ts", 'if ("expected" == actual) { return; }\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_yoda_number_eq_tsx(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.tsx", "if (0 == count) { return; }\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_normal_ts_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.ts", 'if (actual === "expected") { return; }\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Java tests ────────────────────────────────────────────────


class TestJava:
    def test_yoda_string_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", 'public class A { void f() { if ("hello" == name) {} } }\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_YODA_EQ

    def test_yoda_number_neq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", "public class A { void f() { if (0 != count) {} } }\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_YODA_NEQ

    def test_yoda_null_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", "public class A { void f() { if (null == obj) {} } }\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_normal_java_not_flagged(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", 'public class A { void f() { if (name == "hello") {} } }\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_yoda_true_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "A.java", "public class A { void f() { if (true == flag) {} } }\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


# ── Go tests ──────────────────────────────────────────────────


class TestGo:
    def test_yoda_string_eq(self, tmp_path: Path) -> None:
        code = 'package main\nfunc main() { if "hello" == name {} }\n'
        p = _write(tmp_path, "a.go", code)
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_yoda_number_neq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.go", "package main\nfunc main() { if 0 != count {} }\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_normal_go_not_flagged(self, tmp_path: Path) -> None:
        code = 'package main\nfunc main() { if name == "hello" {} }\n'
        p = _write(tmp_path, "a.go", code)
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_yoda_nil_eq(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.go", "package main\nfunc main() { if nil == err {} }\n")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


# ── Unsupported language ──────────────────────────────────────


class TestUnsupported:
    def test_unsupported_extension(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.rb", 'if "hello" == name\n  puts name\nend\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        assert r.total_comparisons == 0
        assert len(r.issues) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        p = tmp_path / "nonexistent.py"
        r = YodaConditionAnalyzer().analyze_file(p)
        assert r.total_comparisons == 0
        assert len(r.issues) == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = YodaConditionAnalyzer().analyze_file(p)
        assert r.total_comparisons == 0
        assert len(r.issues) == 0


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_result_to_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'if "hello" == name:\n    pass\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "file_path" in d
        assert "total_comparisons" in d
        assert "issues" in d
        assert d["issue_count"] == 1

    def test_issue_to_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", 'if "hello" == name:\n    pass\n')
        r = YodaConditionAnalyzer().analyze_file(p)
        d = r.issues[0].to_dict()
        assert d["issue_type"] == ISSUE_YODA_EQ
        assert "line" in d
        assert "severity" in d
