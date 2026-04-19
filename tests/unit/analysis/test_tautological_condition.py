"""Tests for Tautological Condition Detector."""
from __future__ import annotations

import os
import tempfile

from tree_sitter_analyzer.analysis.tautological_condition import (
    ISSUE_CONTRADICTORY,
    ISSUE_SUBSUMED,
    ISSUE_TAUTOLOGICAL,
    TautologicalConditionAnalyzer,
    TautologicalResult,
)


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


# ── Python Tests ──


class TestPythonSelfComparison:
    def test_detects_x_eq_x(self) -> None:
        code = """\
def check(x):
    if x == x:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert isinstance(result, TautologicalResult)
            assert result.functions_analyzed == 1
            assert result.total_issues >= 1
            issue = result.issues[0]
            assert issue.issue_type == ISSUE_TAUTOLOGICAL
            assert "x" in issue.message
        finally:
            os.unlink(path)

    def test_detects_x_ne_x(self) -> None:
        code = """\
def check(x):
    if x != x:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].issue_type == ISSUE_TAUTOLOGICAL
        finally:
            os.unlink(path)

    def test_no_issue_normal_comparison(self) -> None:
        code = """\
def check(x, y):
    if x == y:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            taut_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_TAUTOLOGICAL
            ]
            assert len(taut_issues) == 0
        finally:
            os.unlink(path)


class TestPythonContradictory:
    def test_detects_x_eq_5_and_x_eq_10(self) -> None:
        code = """\
def check(x):
    if x == 5 and x == 10:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            contra = [
                i for i in result.issues
                if i.issue_type == ISSUE_CONTRADICTORY
            ]
            assert len(contra) >= 1
        finally:
            os.unlink(path)

    def test_detects_x_gt_5_and_x_lt_3(self) -> None:
        code = """\
def check(x):
    if x > 5 and x < 3:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            contra = [
                i for i in result.issues
                if i.issue_type == ISSUE_CONTRADICTORY
            ]
            assert len(contra) >= 1
        finally:
            os.unlink(path)

    def test_no_issue_non_contradictory(self) -> None:
        code = """\
def check(x):
    if x > 3 and x < 10:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            contra = [
                i for i in result.issues
                if i.issue_type == ISSUE_CONTRADICTORY
            ]
            assert len(contra) == 0
        finally:
            os.unlink(path)


class TestPythonSubsumed:
    def test_detects_x_gt_3_and_x_gt_5(self) -> None:
        code = """\
def check(x):
    if x > 3 and x > 5:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            subsumed = [
                i for i in result.issues
                if i.issue_type == ISSUE_SUBSUMED
            ]
            assert len(subsumed) >= 1
        finally:
            os.unlink(path)

    def test_detects_x_lt_10_and_x_lt_5(self) -> None:
        code = """\
def check(x):
    if x < 10 and x < 5:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            subsumed = [
                i for i in result.issues
                if i.issue_type == ISSUE_SUBSUMED
            ]
            assert len(subsumed) >= 1
        finally:
            os.unlink(path)

    def test_no_issue_non_subsumed(self) -> None:
        code = """\
def check(x):
    if x > 3 and x > 2:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            subsumed = [
                i for i in result.issues
                if i.issue_type == ISSUE_SUBSUMED
            ]
            assert len(subsumed) == 0
        finally:
            os.unlink(path)


class TestPythonBooleanLiteral:
    def test_detects_if_true(self) -> None:
        code = """\
def check():
    if True:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].issue_type == ISSUE_TAUTOLOGICAL
        finally:
            os.unlink(path)

    def test_detects_if_false(self) -> None:
        code = """\
def check():
    if False:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            os.unlink(path)


# ── JavaScript/TypeScript Tests ──


class TestJSSelfComparison:
    def test_detects_x_eq_x_js(self) -> None:
        code = """\
function check(x) {
    if (x === x) {
        console.log("always true");
    }
}
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed == 1
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_no_issue_normal_js(self) -> None:
        code = """\
function check(x, y) {
    if (x === y) {
        return true;
    }
}
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            taut_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_TAUTOLOGICAL
            ]
            assert len(taut_issues) == 0
        finally:
            os.unlink(path)


class TestJSContradictory:
    def test_detects_contradictory_js(self) -> None:
        code = """\
function check(x) {
    if (x === 5 && x === 10) {
        return true;
    }
}
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            contra = [
                i for i in result.issues
                if i.issue_type == ISSUE_CONTRADICTORY
            ]
            assert len(contra) >= 1
        finally:
            os.unlink(path)


class TestJSSubsumed:
    def test_detects_subsumed_js(self) -> None:
        code = """\
function check(x) {
    if (x > 3 && x > 5) {
        return true;
    }
}
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            subsumed = [
                i for i in result.issues
                if i.issue_type == ISSUE_SUBSUMED
            ]
            assert len(subsumed) >= 1
        finally:
            os.unlink(path)


class TestTypeScriptSelfComparison:
    def test_detects_x_ne_x_ts(self) -> None:
        code = """\
function check(x: number): boolean {
    return x !== x;
}
"""
        path = _write_tmp(code, ".ts")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            os.unlink(path)


# ── Java Tests ──


class TestJavaContradictory:
    def test_detects_contradictory_java(self) -> None:
        code = """\
public class Check {
    public boolean test(int x) {
        if (x == 5 && x == 10) {
            return true;
        }
        return false;
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed >= 1
            contra = [
                i for i in result.issues
                if i.issue_type == ISSUE_CONTRADICTORY
            ]
            assert len(contra) >= 1
        finally:
            os.unlink(path)

    def test_no_issue_non_contradictory_java(self) -> None:
        code = """\
public class Check {
    public boolean test(int x) {
        if (x > 3 && x < 10) {
            return true;
        }
        return false;
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            contra = [
                i for i in result.issues
                if i.issue_type == ISSUE_CONTRADICTORY
            ]
            assert len(contra) == 0
        finally:
            os.unlink(path)


class TestJavaSubsumed:
    def test_detects_subsumed_java(self) -> None:
        code = """\
public class Check {
    public boolean test(int x) {
        if (x > 3 && x > 5) {
            return true;
        }
        return false;
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            subsumed = [
                i for i in result.issues
                if i.issue_type == ISSUE_SUBSUMED
            ]
            assert len(subsumed) >= 1
        finally:
            os.unlink(path)


# ── Go Tests ──


class TestGoSelfComparison:
    def test_detects_x_eq_x_go(self) -> None:
        code = """\
package main

func check(x int) bool {
    if x == x {
        return true
    }
    return false
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed >= 1
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_no_issue_normal_go(self) -> None:
        code = """\
package main

func check(x int, y int) bool {
    if x == y {
        return true
    }
    return false
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            taut_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_TAUTOLOGICAL
            ]
            assert len(taut_issues) == 0
        finally:
            os.unlink(path)


class TestGoContradictory:
    def test_detects_contradictory_go(self) -> None:
        code = """\
package main

func check(x int) bool {
    if x == 5 && x == 10 {
        return true
    }
    return false
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            contra = [
                i for i in result.issues
                if i.issue_type == ISSUE_CONTRADICTORY
            ]
            assert len(contra) >= 1
        finally:
            os.unlink(path)


class TestGoSubsumed:
    def test_detects_subsumed_go(self) -> None:
        code = """\
package main

func check(x int) bool {
    if x > 3 && x > 5 {
        return true
    }
    return false
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            subsumed = [
                i for i in result.issues
                if i.issue_type == ISSUE_SUBSUMED
            ]
            assert len(subsumed) >= 1
        finally:
            os.unlink(path)


# ── General Tests ──


class TestGeneral:
    def test_unsupported_extension(self) -> None:
        code = "some ruby code"
        path = _write_tmp(code, ".rb")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
            assert result.functions_analyzed == 0
        finally:
            os.unlink(path)

    def test_empty_file(self) -> None:
        path = _write_tmp("", ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_result_to_dict(self) -> None:
        code = """\
def check(x):
    if x == x:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            d = result.to_dict()
            assert "file_path" in d
            assert "issues" in d
            assert "total_issues" in d
            assert "functions_analyzed" in d
            assert isinstance(d["issues"], list)
        finally:
            os.unlink(path)

    def test_issue_to_dict(self) -> None:
        code = """\
def check(x):
    if x == x:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
            d = result.issues[0].to_dict()
            assert "issue_type" in d
            assert "line" in d
            assert "severity" in d
            assert "suggestion" in d
        finally:
            os.unlink(path)

    def test_get_issues_by_severity(self) -> None:
        code = """\
def check(x):
    if x == x:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = TautologicalConditionAnalyzer()
            result = analyzer.analyze_file(path)
            high = result.get_issues_by_severity("high")
            assert len(high) >= 1
            low = result.get_issues_by_severity("low")
            assert isinstance(low, list)
        finally:
            os.unlink(path)
