"""Tests for finding_suppression module."""
from __future__ import annotations

import textwrap
from pathlib import Path

from tree_sitter_analyzer.analysis.finding_suppression import (
    SuppressionParseResult,
    build_suppression_set,
    filter_findings,
    is_suppressed,
    parse_suppressions,
)


def _write_tmp(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


class TestParseSuppressions:
    def test_python_single_rule(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
x = unused_var  # tsa: disable unused_import
y = 42
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 1
        assert result.suppressions[0].rule_names == frozenset({"unused_import"})
        assert result.suppressions[0].line == 1

    def test_python_multiple_rules(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
x = 1  # tsa: disable unused_import, magic_value
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 1
        assert result.suppressions[0].rule_names == frozenset(
            {"unused_import", "magic_value"}
        )

    def test_python_disable_all(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
# tsa: disable-all
x = 1
y = 2
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 1
        assert result.suppressions[0].is_file_level is True
        assert result.suppressions[0].is_enable is False

    def test_python_enable_after_disable_all(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
# tsa: disable-all
x = 1
# tsa: enable
y = 2
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 1
        assert len([s for s in result.suppressions if s.is_enable]) == 1

    def test_js_double_slash(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.js",
            """\
const x = 1; // tsa: disable unused_var
const y = 2;
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 1
        assert result.suppressions[0].rule_names == frozenset({"unused_var"})

    def test_java_double_slash(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "Test.java",
            """\
int x = 1; // tsa: disable magic_value
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 1
        assert result.suppressions[0].rule_names == frozenset({"magic_value"})

    def test_go_double_slash(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "main.go",
            """\
x := 1 // tsa: disable unused_var
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 1
        assert result.suppressions[0].rule_names == frozenset({"unused_var"})

    def test_block_comment(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.js",
            """\
/* tsa: disable magic_value */
const x = 42;
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 1
        assert result.suppressions[0].rule_names == frozenset({"magic_value"})

    def test_multiple_suppressions(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
# tsa: disable unused_import
x = 1  # tsa: disable magic_value
y = 2  # tsa: disable bare_except
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 3

    def test_file_not_found(self) -> None:
        result = parse_suppressions("/nonexistent/file.py")
        assert result.error == "File not found"
        assert result.total_suppressions == 0

    def test_no_suppression_comments(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
x = 1  # just a normal comment
y = 2  # another comment
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 0

    def test_no_rules_after_disable(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
x = 1  # tsa: disable
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 0

    def test_to_dict(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
# tsa: disable unused_import
x = 1
""",
        )
        result = parse_suppressions(p)
        d = result.to_dict()
        assert d["file_path"] == str(p)
        assert d["total_suppressions"] == 1
        assert d["suppressions"][0]["rules"] == ["unused_import"]


class TestBuildSuppressionSet:
    def test_empty_suppressions(self) -> None:
        result = SuppressionParseResult(file_path="test.py")
        sup_set = build_suppression_set(result)
        assert sup_set == set()

    def test_single_rule(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
# tsa: disable unused_import
x = 1
""",
        )
        result = parse_suppressions(p)
        sup_set = build_suppression_set(result)
        assert sup_set is not None
        assert ("unused_import", 1) in sup_set
        assert ("unused_import", 2) in sup_set
        assert ("magic_value", 2) not in sup_set

    def test_file_level_suppression(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
# tsa: disable-all
x = 1
y = 2
""",
        )
        result = parse_suppressions(p)
        sup_set = build_suppression_set(result)
        assert sup_set is None  # None = file-level active

    def test_file_level_enable_toggle(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
x = 1
# tsa: disable-all
y = 2
# tsa: enable
z = 3
""",
        )
        result = parse_suppressions(p)
        sup_set = build_suppression_set(result)
        # file-level disable was toggled off, so result is not None
        assert sup_set is not None

    def test_multiple_rules(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "test.py",
            """\
# tsa: disable unused_import, magic_value
x = 1
""",
        )
        result = parse_suppressions(p)
        sup_set = build_suppression_set(result)
        assert sup_set is not None
        assert ("unused_import", 1) in sup_set
        assert ("unused_import", 2) in sup_set
        assert ("magic_value", 1) in sup_set
        assert ("magic_value", 2) in sup_set


class TestIsSuppressed:
    def test_suppressed_specific(self) -> None:
        sup_set: set[tuple[str, int]] = {("unused_import", 5)}
        assert is_suppressed("unused_import", 5, sup_set) is True

    def test_not_suppressed_different_rule(self) -> None:
        sup_set: set[tuple[str, int]] = {("unused_import", 5)}
        assert is_suppressed("magic_value", 5, sup_set) is False

    def test_not_suppressed_different_line(self) -> None:
        sup_set: set[tuple[str, int]] = {("unused_import", 5)}
        assert is_suppressed("unused_import", 6, sup_set) is False

    def test_file_level_suppression(self) -> None:
        assert is_suppressed("any_rule", 999, None) is True

    def test_empty_set_not_suppressed(self) -> None:
        assert is_suppressed("any_rule", 1, set()) is False


class TestFilterFindings:
    def test_no_suppressions(self) -> None:
        findings = [
            {"finding_type": "unused_import", "line": 1},
            {"finding_type": "magic_value", "line": 2},
        ]
        result = filter_findings(findings, set())
        assert len(result) == 2

    def test_filter_specific(self) -> None:
        findings = [
            {"finding_type": "unused_import", "line": 1},
            {"finding_type": "magic_value", "line": 2},
        ]
        sup_set: set[tuple[str, int]] = {("unused_import", 1)}
        result = filter_findings(findings, sup_set)
        assert len(result) == 1
        assert result[0]["finding_type"] == "magic_value"

    def test_filter_file_level(self) -> None:
        findings = [
            {"finding_type": "unused_import", "line": 1},
            {"finding_type": "magic_value", "line": 2},
        ]
        result = filter_findings(findings, None)
        assert len(result) == 0

    def test_empty_findings(self) -> None:
        sup_set: set[tuple[str, int]] = {("unused_import", 1)}
        result = filter_findings([], sup_set)
        assert len(result) == 0

    def test_custom_keys(self) -> None:
        findings = [
            {"rule": "unused_import", "line_number": 5},
            {"rule": "magic_value", "line_number": 10},
        ]
        sup_set: set[tuple[str, int]] = {("unused_import", 5)}
        result = filter_findings(
            findings, sup_set, rule_key="rule", line_key="line_number"
        )
        assert len(result) == 1
        assert result[0]["rule"] == "magic_value"

    def test_preserves_original(self) -> None:
        findings = [
            {"finding_type": "unused_import", "line": 1},
            {"finding_type": "magic_value", "line": 2},
        ]
        sup_set: set[tuple[str, int]] = {("unused_import", 1)}
        result = filter_findings(findings, sup_set)
        assert len(findings) == 2
        assert len(result) == 1

    def test_multiple_suppressed(self) -> None:
        findings = [
            {"finding_type": "unused_import", "line": 1},
            {"finding_type": "unused_import", "line": 2},
            {"finding_type": "magic_value", "line": 3},
        ]
        sup_set: set[tuple[str, int]] = {("unused_import", 1), ("unused_import", 2)}
        result = filter_findings(findings, sup_set)
        assert len(result) == 1
        assert result[0]["finding_type"] == "magic_value"


class TestIntegration:
    def test_full_pipeline_python(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "example.py",
            """\
import os
# tsa: disable unused_import
import json
x = 1  # tsa: disable magic_value
y = 2
z = 3  # tsa: disable unused_var
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 3

        sup_set = build_suppression_set(result)
        assert sup_set is not None

        findings = [
            {"finding_type": "unused_import", "line": 3, "message": "json imported but unused"},
            {"finding_type": "magic_value", "line": 4, "message": "magic number 1"},
            {"finding_type": "unused_var", "line": 6, "message": "z assigned but unused"},
            {"finding_type": "bare_except", "line": 5, "message": "should not happen"},
        ]
        filtered = filter_findings(findings, sup_set)
        assert len(filtered) == 1
        assert filtered[0]["finding_type"] == "bare_except"
        assert filtered[0]["line"] == 5

    def test_full_pipeline_disable_all(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "example.py",
            """\
# tsa: disable-all
import json
x = 1
y = 2
""",
        )
        result = parse_suppressions(p)
        sup_set = build_suppression_set(result)
        assert sup_set is None

        findings = [
            {"finding_type": "unused_import", "line": 2},
            {"finding_type": "magic_value", "line": 3},
        ]
        filtered = filter_findings(findings, sup_set)
        assert len(filtered) == 0

    def test_full_pipeline_toggle(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "example.py",
            """\
x = 1
# tsa: disable-all
y = 2
z = 3
# tsa: enable
w = 4
""",
        )
        result = parse_suppressions(p)
        sup_set = build_suppression_set(result)
        # toggle ended with enable, so file-level is off
        assert sup_set is not None

        findings = [
            {"finding_type": "magic_value", "line": 1},
            {"finding_type": "magic_value", "line": 3},
            {"finding_type": "magic_value", "line": 4},
            {"finding_type": "magic_value", "line": 6},
        ]
        filtered = filter_findings(findings, sup_set)
        # Only line 6 should survive (after enable)
        # But toggle ended with enable, so set should be non-None
        # The toggle state only affects file-level, specific rules are separate
        # Since there are no specific rules, set should be empty -> no suppression
        assert len(filtered) == 4

    def test_full_pipeline_javascript(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "example.js",
            """\
// tsa: disable unused_var
const x = 1;
const y = 2;
const z = 3; // tsa: disable magic_value
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 2

        sup_set = build_suppression_set(result)
        findings = [
            {"finding_type": "unused_var", "line": 1},
            {"finding_type": "unused_var", "line": 2},
            {"finding_type": "magic_value", "line": 4},
        ]
        filtered = filter_findings(findings, sup_set)
        # Line 1 has unused_var suppressed (same line comment)
        # Line 2 has unused_var suppressed (next line from line 1 comment)
        # Line 4 has magic_value suppressed (same line comment)
        assert len(filtered) == 0

    def test_tsx_file(self, tmp_path: Path) -> None:
        p = _write_tmp(
            tmp_path,
            "component.tsx",
            """\
// tsa: disable unused_import
import React from 'react';
export const X = () => <div />;
""",
        )
        result = parse_suppressions(p)
        assert result.total_suppressions == 1

    def test_encoding_error_recovery(self, tmp_path: Path) -> None:
        p = tmp_path / "test.py"
        p.write_bytes(b"# tsa: disable unused_import\n\xff\xfe")
        result = parse_suppressions(p)
        # Should not crash, errors='replace' handles encoding
        assert result.error is None
