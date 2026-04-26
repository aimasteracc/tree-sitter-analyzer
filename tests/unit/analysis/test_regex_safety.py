"""Tests for Regex Safety / ReDoS Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.regex_safety import (
    RegexSafetyAnalyzer,
    RegexSafetyResult,
    RegexVulnerability,
    analyze_regex_pattern,
)


@pytest.fixture
def analyzer() -> RegexSafetyAnalyzer:
    return RegexSafetyAnalyzer()


@pytest.fixture
def tmp_dir() -> Path:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _write_py(dir_path: Path, code: str, name: str = "test.py") -> Path:
    p = dir_path / name
    p.write_text(code)
    return p


def _write_js(dir_path: Path, code: str, name: str = "test.js") -> Path:
    p = dir_path / name
    p.write_text(code)
    return p


def _write_java(dir_path: Path, code: str, name: str = "Test.java") -> Path:
    p = dir_path / name
    p.write_text(code)
    return p


def _write_go(dir_path: Path, code: str, name: str = "test.go") -> Path:
    p = dir_path / name
    p.write_text(code)
    return p


# --- analyze_regex_pattern unit tests ---


class TestPatternAnalysis:
    def test_safe_pattern(self) -> None:
        issues = analyze_regex_pattern(r"\d+@\w+\.\w+")
        assert len(issues) == 0

    def test_simple_word(self) -> None:
        issues = analyze_regex_pattern(r"\w+")
        assert len(issues) == 0

    def test_nested_quantifier_group_plus(self) -> None:
        issues = analyze_regex_pattern(r"(\w+)+")
        assert any(v[0] == "nested_quantifier" for v in issues)

    def test_nested_quantifier_star_star(self) -> None:
        issues = analyze_regex_pattern(r"(a*)*")
        assert any(v[0] == "nested_quantifier" for v in issues)

    def test_nested_quantifier_plus_star(self) -> None:
        issues = analyze_regex_pattern(r"(a+)*")
        assert any(v[0] == "nested_quantifier" for v in issues)

    def test_nested_quantifier_star_plus(self) -> None:
        issues = analyze_regex_pattern(r"(a*)+")
        assert any(v[0] == "nested_quantifier" for v in issues)

    def test_no_nested_quantifier_single(self) -> None:
        issues = analyze_regex_pattern(r"\d+")
        assert len(issues) == 0

    def test_overlapping_alternation(self) -> None:
        issues = analyze_regex_pattern(r"(a|ab)")
        assert any(v[0] == "overlapping_alternation" for v in issues)

    def test_no_overlap_distinct(self) -> None:
        issues = analyze_regex_pattern(r"(cat|dog)")
        assert not any(v[0] == "overlapping_alternation" for v in issues)

    def test_quantified_alternation(self) -> None:
        issues = analyze_regex_pattern(r"(a+|b)+")
        assert len(issues) > 0

    def test_complex_safe_pattern(self) -> None:
        issues = analyze_regex_pattern(r"^[A-Z][a-z]+ \d{1,3}$")
        assert len(issues) == 0

    def test_escaped_parentheses(self) -> None:
        issues = analyze_regex_pattern(r"\(a\)")
        assert len(issues) == 0

    def test_character_class_not_quantified(self) -> None:
        issues = analyze_regex_pattern(r"[a-z]+")
        assert len(issues) == 0

    def test_email_pattern_safe(self) -> None:
        issues = analyze_regex_pattern(r"[\w.+-]+@[\w-]+\.[\w.]+")
        assert len(issues) == 0

    def test_classic_redos(self) -> None:
        issues = analyze_regex_pattern(r"(a+)+$")
        assert any(v[0] == "nested_quantifier" for v in issues)

    def test_curly_brace_quantifier(self) -> None:
        issues = analyze_regex_pattern(r"(a{1,3}){2,5}")
        assert any(v[0] == "nested_quantifier" for v in issues)


# --- Python file analysis ---


class TestPythonAnalysis:
    def test_re_compile_safe(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_py(tmp_dir, 'import re\npat = re.compile(r"\\d+")\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert result.is_safe

    def test_re_compile_vulnerable(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_py(tmp_dir, 'import re\npat = re.compile(r"(a+)+")\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert not result.is_safe
        assert any(v.vulnerability_type == "nested_quantifier" for v in result.vulnerabilities)

    def test_re_search(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_py(tmp_dir, 'import re\nre.search(r"(\\w+)+$", s)\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert not result.is_safe

    def test_re_match_safe(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_py(tmp_dir, 'import re\nre.match(r"^[a-z]+$", s)\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert result.is_safe

    def test_re_findall(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_py(tmp_dir, 'import re\nre.findall(r"(x*)+", s)\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert not result.is_safe

    def test_re_sub(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_py(tmp_dir, 'import re\nre.sub(r"(a|ab)+", "x", s)\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1

    def test_no_regex(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_py(tmp_dir, "x = 1\ny = 2\n")
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 0
        assert result.is_safe

    def test_non_regex_call(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_py(tmp_dir, 'print("hello")\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 0

    def test_multiple_patterns(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_py(tmp_dir, (
            'import re\n'
            're.compile(r"\\d+")\n'
            're.match(r"(a+)+", s)\n'
            're.search(r"[a-z]+", s)\n'
        ))
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 3
        assert result.vulnerable_count >= 1

    def test_file_not_found(self, analyzer: RegexSafetyAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_regex_patterns == 0


class TestJavaScriptAnalysis:
    def test_regex_literal_safe(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_js(tmp_dir, 'const pat = /\\d+/;\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert result.is_safe

    def test_regex_literal_vulnerable(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_js(tmp_dir, 'const pat = /(a+)+/;\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert not result.is_safe

    def test_new_regexp_safe(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_js(tmp_dir, 'const pat = new RegExp("\\\\d+");\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert result.is_safe

    def test_new_regexp_vulnerable(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_js(tmp_dir, 'const pat = new RegExp("(a+)+");\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert not result.is_safe

    def test_regex_with_flags(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_js(tmp_dir, 'const pat = /(\\w+)+$/gi;\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert not result.is_safe

    def test_typescript_file(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_js(tmp_dir, 'const pat = /(x+)+/;\n', name="test.ts")
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert not result.is_safe


# --- Java file analysis ---


class TestJavaAnalysis:
    def test_pattern_compile_safe(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_java(tmp_dir, (
            'import java.util.regex.Pattern;\n'
            'class T { Pattern p = Pattern.compile("\\\\d+"); }\n'
        ))
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert result.is_safe

    def test_pattern_compile_vulnerable(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_java(tmp_dir, (
            'import java.util.regex.Pattern;\n'
            'class T { Pattern p = Pattern.compile("(a+)+"); }\n'
        ))
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert not result.is_safe

    def test_no_pattern(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_java(tmp_dir, 'class T { int x = 1; }\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 0


# --- Go file analysis ---


class TestGoAnalysis:
    def test_must_compile_safe(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_go(tmp_dir, (
            'package main\n'
            'import "regexp"\n'
            'var pat = regexp.MustCompile(`\\d+`)\n'
        ))
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert result.is_safe

    def test_must_compile_vulnerable(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_go(tmp_dir, (
            'package main\n'
            'import "regexp"\n'
            'var pat = regexp.MustCompile(`(a+)+`)\n'
        ))
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert not result.is_safe

    def test_compile_func(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_go(tmp_dir, (
            'package main\n'
            'import "regexp"\n'
            'var pat, _ = regexp.Compile(`[a-z]+`)\n'
        ))
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 1
        assert result.is_safe

    def test_no_regex(self, analyzer: RegexSafetyAnalyzer, tmp_dir: Path) -> None:
        p = _write_go(tmp_dir, 'package main\nfunc main() {}\n')
        result = analyzer.analyze_file(p)
        assert result.total_regex_patterns == 0


# --- Result structure tests ---


class TestResultStructure:
    def test_result_dataclass(self) -> None:
        v = RegexVulnerability(
            line_number=5,
            pattern="(a+)+",
            vulnerability_type="nested_quantifier",
            severity="high",
            explanation="test",
        )
        r = RegexSafetyResult(
            total_regex_patterns=1,
            vulnerable_count=1,
            vulnerabilities=(v,),
            file_path="test.py",
        )
        assert not r.is_safe
        assert r.total_regex_patterns == 1

    def test_empty_result_is_safe(self) -> None:
        r = RegexSafetyResult(
            total_regex_patterns=0,
            vulnerable_count=0,
            vulnerabilities=(),
            file_path="test.py",
        )
        assert r.is_safe
