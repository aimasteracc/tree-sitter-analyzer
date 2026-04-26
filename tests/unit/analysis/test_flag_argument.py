"""Tests for Flag Argument Detector."""
from __future__ import annotations

import os
import tempfile

from tree_sitter_analyzer.analysis.flag_argument import (
    ISSUE_FLAG_ARGUMENT,
    FlagArgumentAnalyzer,
    FlagArgumentResult,
)


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


# ── Python Tests ──


class TestPythonTypedBool:
    def test_detects_bool_type_annotation(self) -> None:
        code = """\
def process(data: str, verbose: bool) -> None:
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert isinstance(result, FlagArgumentResult)
            assert result.functions_analyzed == 1
            assert result.total_issues >= 1
            issue = result.issues[0]
            assert issue.issue_type == ISSUE_FLAG_ARGUMENT
            assert issue.param_name == "verbose"
        finally:
            os.unlink(path)

    def test_detects_multiple_bool_params(self) -> None:
        code = """\
def process(data: str, verbose: bool, dry_run: bool) -> None:
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues >= 2
            names = {i.param_name for i in result.issues}
            assert "verbose" in names
            assert "dry_run" in names
        finally:
            os.unlink(path)


class TestPythonDefaultBool:
    def test_detects_default_true(self) -> None:
        code = """\
def process(data, verbose=True):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].param_name == "verbose"
        finally:
            os.unlink(path)

    def test_detects_default_false(self) -> None:
        code = """\
def process(data, dry_run=False):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].param_name == "dry_run"
        finally:
            os.unlink(path)


class TestPythonTypedDefaultBool:
    def test_detects_typed_default_bool(self) -> None:
        code = """\
def process(data: str, verbose: bool = True) -> None:
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].param_name == "verbose"
        finally:
            os.unlink(path)


class TestPythonNegative:
    def test_no_issue_non_bool_param(self) -> None:
        code = """\
def process(data: str, count: int) -> None:
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_no_issue_no_params(self) -> None:
        code = """\
def process():
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── JavaScript Tests ──


class TestJSDefaultBool:
    def test_detects_default_true_js(self) -> None:
        code = """\
function process(data, verbose = true) {
    console.log(data);
}
"""
        path = _write_tmp(code, ".js")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.functions_analyzed == 1
            assert result.total_issues >= 1
            assert result.issues[0].param_name == "verbose"
        finally:
            os.unlink(path)

    def test_no_issue_non_bool_default_js(self) -> None:
        code = """\
function process(data, count = 10) {
    return data;
}
"""
        path = _write_tmp(code, ".js")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── TypeScript Tests ──


class TestTSBoolParam:
    def test_detects_boolean_type_ts(self) -> None:
        code = """\
function process(data: string, verbose: boolean): void {
    console.log(data);
}
"""
        path = _write_tmp(code, ".ts")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.functions_analyzed == 1
            assert result.total_issues >= 1
            assert result.issues[0].param_name == "verbose"
        finally:
            os.unlink(path)

    def test_detects_optional_bool_ts(self) -> None:
        code = """\
function process(data: string, verbose?: boolean): void {
    console.log(data);
}
"""
        path = _write_tmp(code, ".ts")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].param_name == "verbose"
        finally:
            os.unlink(path)

    def test_no_issue_non_bool_ts(self) -> None:
        code = """\
function process(data: string, count: number): void {
    console.log(data);
}
"""
        path = _write_tmp(code, ".ts")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── Java Tests ──


class TestJavaBoolParam:
    def test_detects_boolean_java(self) -> None:
        code = """\
public class Foo {
    public void process(boolean verbose, String data) {
        System.out.println(data);
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.functions_analyzed >= 1
            assert result.total_issues >= 1
            assert result.issues[0].param_name == "verbose"
        finally:
            os.unlink(path)

    def test_no_issue_non_bool_java(self) -> None:
        code = """\
public class Foo {
    public void process(String data, int count) {
        System.out.println(data);
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── Go Tests ──


class TestGoBoolParam:
    def test_detects_bool_go(self) -> None:
        code = """\
package main

func process(verbose bool, data string) {
    fmt.Println(data)
}
"""
        path = _write_tmp(code, ".go")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.functions_analyzed >= 1
            assert result.total_issues >= 1
            assert result.issues[0].param_name == "verbose"
        finally:
            os.unlink(path)

    def test_no_issue_non_bool_go(self) -> None:
        code = """\
package main

func process(count int, data string) {
    fmt.Println(data)
}
"""
        path = _write_tmp(code, ".go")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── General Tests ──


class TestGeneral:
    def test_result_to_dict(self) -> None:
        code = """\
def process(data: str, verbose: bool) -> None:
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
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
def process(data: str, verbose: bool) -> None:
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            d = result.issues[0].to_dict()
            assert "issue_type" in d
            assert "line" in d
            assert "severity" in d
            assert "param_name" in d
            assert "suggestion" in d
        finally:
            os.unlink(path)

    def test_severity_is_medium_for_typed(self) -> None:
        code = """\
def process(verbose: bool) -> None:
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            result = FlagArgumentAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].severity == "medium"
        finally:
            os.unlink(path)
