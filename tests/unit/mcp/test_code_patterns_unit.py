"""Tests for CodePatternsTool — schema, private helpers, and severity ordering."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
    _SEVERITY_ORDER,
    CodePatternsTool,
    _build_summary,
    _check_java_anti_patterns,
    _check_js_anti_patterns,
    _check_python_anti_patterns,
    _detect_anti_patterns,
    _detect_security,
    _detect_smells,
)

# ---------------------------------------------------------------------------
# Tool schema / definition
# ---------------------------------------------------------------------------


class TestCodePatternsToolSchema:
    def test_get_tool_schema_returns_required_fields(self):
        schema = CodePatternsTool().get_tool_schema()
        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "categories" in schema["properties"]
        assert "file_path" in schema["required"]

    def test_get_tool_definition_has_name(self):
        defn = CodePatternsTool().get_tool_definition()
        assert defn["name"] == "code_patterns"
        assert "inputSchema" in defn

    def test_validate_arguments_missing_file_path_raises(self):
        with pytest.raises(ValueError, match="file_path is required"):
            CodePatternsTool().validate_arguments({})

    def test_validate_arguments_invalid_category_raises(self):
        with pytest.raises(ValueError, match="Unknown category"):
            CodePatternsTool().validate_arguments(
                {"file_path": "/tmp/x.py", "categories": ["bogus"]}
            )

    def test_validate_arguments_valid(self):
        assert CodePatternsTool().validate_arguments({"file_path": "/tmp/x.py"})
        assert CodePatternsTool().validate_arguments(
            {"file_path": "/tmp/x.py", "categories": ["smells", "security"]}
        )


# ---------------------------------------------------------------------------
# _check_python_anti_patterns
# ---------------------------------------------------------------------------


class TestCheckPythonAntiPatterns:
    def test_mutable_default_list(self):
        lines = [
            "def foo(items=[]):",
            "    pass",
        ]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        assert any(p["type"] == "mutable_default_argument" for p in patterns)

    def test_bare_except(self):
        lines = ["try:", "    pass", "except:", "    pass"]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        assert any(p["type"] == "bare_except" for p in patterns)

    def test_print_in_function(self):
        lines = [
            "def do_thing():",
            "    print('debug')",
        ]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        assert any(p["type"] == "print_in_production" for p in patterns)

    def test_clean_code_no_patterns(self):
        lines = [
            "import os",
            "",
            "def foo():",
            "    return 42",
        ]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        assert patterns == []

    def test_print_at_module_level_ignored(self):
        lines = ["print('hello')"]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        assert not any(p["type"] == "print_in_production" for p in patterns)

    def test_print_in_multiline_docstring_ignored(self):
        """Dogfood regression: --code-patterns previously flagged docstring
        example `print()` calls as production smells. The fix is to skip lines
        that fall inside a triple-quoted string."""
        lines = [
            "def example():",
            '    """Show how to use this thing.',
            "",
            "    Example:",
            "        result = thing.run()",
            "        print(result)",
            '    """',
            "    return 42",
        ]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        assert not any(p["type"] == "print_in_production" for p in patterns)

    def test_print_in_single_line_docstring_ignored(self):
        lines = [
            "def f():",
            '    """Like: print("ok")."""',
            "    return 1",
        ]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        assert not any(p["type"] == "print_in_production" for p in patterns)

    def test_print_outside_docstring_still_flagged(self):
        """Don't over-correct: real print() in a function body must still flag."""
        lines = [
            "def do_thing():",
            '    """Doc."""',
            "    print('still bad')",
        ]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        assert any(p["type"] == "print_in_production" for p in patterns)

    def test_bare_except_in_docstring_ignored(self):
        lines = [
            "def f():",
            '    """Bad pattern example:',
            "",
            "        try:",
            "            x()",
            "        except:",
            "            pass",
            '    """',
            "    return 1",
        ]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        assert not any(p["type"] == "bare_except" for p in patterns)


# ---------------------------------------------------------------------------
# _check_js_anti_patterns
# ---------------------------------------------------------------------------


class TestCheckJsAntiPatterns:
    def test_var_usage(self):
        lines = ["var x = 1;"]
        patterns: list[dict] = []
        _check_js_anti_patterns(lines, patterns)
        assert any(p["type"] == "var_usage" for p in patterns)

    def test_loose_equality(self):
        lines = ["if (x == 1) {`"]
        patterns: list[dict] = []
        _check_js_anti_patterns(lines, patterns)
        assert any(p["type"] == "loose_equality" for p in patterns)

    def test_strict_equality_not_flagged(self):
        lines = ["if (x === 1) {`"]
        patterns: list[dict] = []
        _check_js_anti_patterns(lines, patterns)
        assert not any(p["type"] == "loose_equality" for p in patterns)

    def test_commented_var_ignored(self):
        lines = ["// var legacy = true;"]
        patterns: list[dict] = []
        _check_js_anti_patterns(lines, patterns)
        assert patterns == []


# ---------------------------------------------------------------------------
# _check_java_anti_patterns
# ---------------------------------------------------------------------------


class TestCheckJavaAntiPatterns:
    def test_system_out_println(self):
        lines = ['System.out.println("hi");']
        patterns: list[dict] = []
        _check_java_anti_patterns(lines, patterns)
        assert any(p["type"] == "system_out_println" for p in patterns)

    def test_print_stacktrace(self):
        lines = ["e.printStackTrace();"]
        patterns: list[dict] = []
        _check_java_anti_patterns(lines, patterns)
        assert any(p["type"] == "print_stacktrace" for p in patterns)

    def test_commented_println_ignored(self):
        lines = ['// System.out.println("debug");']
        patterns: list[dict] = []
        _check_java_anti_patterns(lines, patterns)
        assert patterns == []


# ---------------------------------------------------------------------------
# _detect_anti_patterns
# ---------------------------------------------------------------------------


class TestDetectAntiPatterns:
    def test_nonexistent_file_returns_empty(self, tmp_path):
        result = _detect_anti_patterns(str(tmp_path / "nope.py"), "python")
        assert result == []

    def test_detects_python_patterns(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def foo(x=[]):\n    except:\n    print('x')\n")
        result = _detect_anti_patterns(str(f), "python")
        assert len(result) > 0

    def test_detects_js_patterns(self, tmp_path):
        f = tmp_path / "bad.js"
        f.write_text("var x = 1;\nif (x == 2) {}\n")
        result = _detect_anti_patterns(str(f), "javascript")
        assert any(p["type"] == "var_usage" for p in result)

    def test_unsupported_language_returns_empty(self, tmp_path):
        f = tmp_path / "code.rs"
        f.write_text("fn main() {}")
        result = _detect_anti_patterns(str(f), "rust")
        assert result == []


# ---------------------------------------------------------------------------
# _detect_smells / _detect_security (graceful error handling)
# ---------------------------------------------------------------------------


class TestDetectSmellsAndSecurity:
    def test_detect_smells_nonexistent_file_returns_empty(self):
        result = _detect_smells("/nonexistent/file.py", "python")
        assert result == []

    def test_detect_security_nonexistent_file_returns_empty(self):
        result = _detect_security("/nonexistent/file.py", "python")
        assert result == []

    def test_detect_smells_valid_file(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        result = _detect_smells(str(f), "python")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_empty_patterns(self):
        assert _build_summary([]) == "No patterns detected."

    def test_mixed_severity(self):
        patterns = [
            {"severity": "critical"},
            {"severity": "warning"},
            {"severity": "warning"},
            {"severity": "info"},
        ]
        summary = _build_summary(patterns)
        assert "1 critical" in summary
        assert "2 warning" in summary
        assert "1 info" in summary
        assert "Total: 4" in summary

    def test_only_critical(self):
        patterns = [{"severity": "critical"}]
        assert "1 critical" in _build_summary(patterns)
        assert "warning" not in _build_summary(patterns)


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------


class TestSeverityOrder:
    def test_info_is_lowest(self):
        assert _SEVERITY_ORDER["info"] < _SEVERITY_ORDER["warning"]

    def test_warning_below_critical(self):
        assert _SEVERITY_ORDER["warning"] < _SEVERITY_ORDER["critical"]

    def test_three_levels(self):
        assert set(_SEVERITY_ORDER.keys()) == {"info", "warning", "critical"}


# ---------------------------------------------------------------------------
# Anti-pattern line numbers
# ---------------------------------------------------------------------------


class TestAntiPatternLineNumbers:
    def test_python_anti_patterns_have_line_numbers(self):
        lines = [
            "def foo(x=[]):",
            "    try:",
            "        pass",
            "    except:",
            "        print('bad')",
        ]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        for p in patterns:
            assert "line" in p
            assert isinstance(p["line"], int)
            assert p["line"] >= 1

    def test_js_anti_patterns_have_line_numbers(self):
        lines = ["var x = 1;", "if (x == 2) {}"]
        patterns: list[dict] = []
        _check_js_anti_patterns(lines, patterns)
        for p in patterns:
            assert "line" in p

    def test_java_anti_patterns_have_line_numbers(self):
        lines = ['System.out.println("hi");', "e.printStackTrace();"]
        patterns: list[dict] = []
        _check_java_anti_patterns(lines, patterns)
        for p in patterns:
            assert "line" in p


# ---------------------------------------------------------------------------
# Anti-pattern IDs
# ---------------------------------------------------------------------------


class TestAntiPatternIds:
    def test_python_anti_patterns_have_ids(self):
        # r37au: AP001 now uses AST-based detection (was line-text regex
        # with too-loose "def in nearby lines" heuristic). The input must
        # therefore be parseable Python — the previous fixture had a bare
        # ``except:`` without an enclosing ``try:`` which broke AST parsing.
        # Real-world input is always parseable, so this matches usage.
        lines = [
            "def foo(x=[]):",
            "    pass",
            "",
            "def bar():",
            "    try:",
            "        pass",
            "    except:",
            "        pass",
            "    print('x')",
        ]
        patterns: list[dict] = []
        _check_python_anti_patterns(lines, patterns)
        ids = {p["id"] for p in patterns}
        assert "AP001" in ids
        assert "AP002" in ids
        assert "AP003" in ids

    def test_js_anti_patterns_have_ids(self):
        lines = ["var x = 1;", "if (x == 2) {}"]
        patterns: list[dict] = []
        _check_js_anti_patterns(lines, patterns)
        ids = {p["id"] for p in patterns}
        assert "AP010" in ids
        assert "AP011" in ids

    def test_java_anti_patterns_have_ids(self):
        lines = ['System.out.println("hi");', "e.printStackTrace();"]
        patterns: list[dict] = []
        _check_java_anti_patterns(lines, patterns)
        ids = {p["id"] for p in patterns}
        assert "AP020" in ids
        assert "AP021" in ids


# ---------------------------------------------------------------------------
# Detect anti-patterns — TypeScript
# ---------------------------------------------------------------------------


class TestDetectAntiPatternsTypescript:
    def test_typescript_uses_js_patterns(self, tmp_path):
        f = tmp_path / "code.ts"
        f.write_text("var y = 2;\nif (y != 3) {}\n")
        result = _detect_anti_patterns(str(f), "typescript")
        assert any(p["type"] == "var_usage" for p in result)
        assert any(p["type"] == "loose_equality" for p in result)


# ---------------------------------------------------------------------------
# Detect security — real file
# ---------------------------------------------------------------------------


class TestDetectSecurityWithRealFile:
    def test_detect_security_returns_list_for_valid_file(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("x = 1\n")
        result = _detect_security(str(f), "python")
        assert isinstance(result, list)

    def test_detect_security_handles_unreadable_gracefully(self):
        result = _detect_security("/nonexistent/path/code.py", "python")
        assert isinstance(result, list)
