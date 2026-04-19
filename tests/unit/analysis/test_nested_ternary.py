"""Tests for Nested Ternary Detector."""
from __future__ import annotations

import os
import tempfile

from tree_sitter_analyzer.analysis.nested_ternary import (
    NestedTernaryAnalyzer,
    NestedTernaryResult,
)


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


# ── Python Tests ──


class TestPythonNestedTernary:
    def test_detects_double_nested(self) -> None:
        code = """\
def f(a, b, c):
    x = 1 if a else 2 if b else 3
"""
        path = _write_tmp(code, ".py")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert isinstance(result, NestedTernaryResult)
            assert result.total_issues >= 1
            assert result.issues[0].depth == 2
        finally:
            os.unlink(path)

    def test_detects_triple_nested(self) -> None:
        code = """\
def f(a, b, c, d):
    x = 1 if a else 2 if b else 3 if c else 4
"""
        path = _write_tmp(code, ".py")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].depth == 3
            assert result.issues[0].severity == "high"
        finally:
            os.unlink(path)

    def test_no_issue_single_ternary(self) -> None:
        code = """\
def f(a):
    x = 1 if a else 2
"""
        path = _write_tmp(code, ".py")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues == 0
            assert result.total_ternaries == 1
        finally:
            os.unlink(path)

    def test_no_issue_no_ternary(self) -> None:
        code = """\
def f(a):
    if a:
        x = 1
    else:
        x = 2
"""
        path = _write_tmp(code, ".py")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues == 0
            assert result.total_ternaries == 0
        finally:
            os.unlink(path)


# ── JavaScript Tests ──


class TestJSNestedTernary:
    def test_detects_nested_js(self) -> None:
        code = """\
function f(a, b) {
    const x = a ? 1 : b ? 2 : 3;
}
"""
        path = _write_tmp(code, ".js")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].depth == 2
        finally:
            os.unlink(path)

    def test_no_issue_single_js(self) -> None:
        code = """\
function f(a) {
    const x = a ? 1 : 2;
}
"""
        path = _write_tmp(code, ".js")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── TypeScript Tests ──


class TestTSNestedTernary:
    def test_detects_nested_ts(self) -> None:
        code = """\
function f(a: boolean, b: boolean): number {
    return a ? 1 : b ? 2 : 3;
}
"""
        path = _write_tmp(code, ".ts")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].depth == 2
        finally:
            os.unlink(path)


# ── Java Tests ──


class TestJavaNestedTernary:
    def test_detects_nested_java(self) -> None:
        code = """\
public class Foo {
    public int f(boolean a, boolean b) {
        return a ? 1 : b ? 2 : 3;
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].depth == 2
        finally:
            os.unlink(path)

    def test_no_issue_single_java(self) -> None:
        code = """\
public class Foo {
    public int f(boolean a) {
        return a ? 1 : 2;
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── General Tests ──


class TestGeneral:
    def test_unsupported_extension(self) -> None:
        path = _write_tmp("x := a if b else c", ".go")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues == 0
            assert result.total_ternaries == 0
        finally:
            os.unlink(path)

    def test_empty_file(self) -> None:
        path = _write_tmp("", ".py")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_result_to_dict(self) -> None:
        code = """\
x = 1 if a else 2 if b else 3
"""
        path = _write_tmp(code, ".py")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            d = result.to_dict()
            assert "file_path" in d
            assert "issues" in d
            assert "total_ternaries" in d
            assert "total_issues" in d
            assert isinstance(d["issues"], list)
        finally:
            os.unlink(path)

    def test_issue_to_dict(self) -> None:
        code = """\
x = 1 if a else 2 if b else 3
"""
        path = _write_tmp(code, ".py")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            d = result.issues[0].to_dict()
            assert "issue_type" in d
            assert "line" in d
            assert "depth" in d
            assert "severity" in d
            assert "suggestion" in d
        finally:
            os.unlink(path)

    def test_custom_min_depth(self) -> None:
        code = """\
x = 1 if a else 2
"""
        path = _write_tmp(code, ".py")
        try:
            result = NestedTernaryAnalyzer(min_depth=1).analyze_file(path)
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_counts_multiple_nested_ternaries(self) -> None:
        code = """\
def f(a, b, c, d):
    x = 1 if a else 2 if b else 3
    y = 4 if c else 5 if d else 6
"""
        path = _write_tmp(code, ".py")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues >= 2
        finally:
            os.unlink(path)

    def test_severity_medium_for_depth_2(self) -> None:
        code = """\
x = 1 if a else 2 if b else 3
"""
        path = _write_tmp(code, ".py")
        try:
            result = NestedTernaryAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].severity == "medium"
        finally:
            os.unlink(path)
