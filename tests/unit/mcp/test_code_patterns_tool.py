"""Tests for CodePatternsTool — smell/security/anti-pattern detection."""

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
# Tool execute() — integration-level tests
# ---------------------------------------------------------------------------


def _make_python_with_anti_patterns(tmp_path) -> str:
    p = tmp_path / "sample.py"
    p.write_text(
        "def foo(x=[]):\n    try:\n        pass\n    except:\n        print('bad')\n",
        encoding="utf-8",
    )
    return str(p)


def _make_clean_python(tmp_path) -> str:
    p = tmp_path / "clean.py"
    p.write_text(
        "import logging\n\nlogger = logging.getLogger(__name__)\n\ndef bar(x=None):\n    if x is None:\n        x = []\n    return x\n",
        encoding="utf-8",
    )
    return str(p)


def _make_js_with_anti_patterns(tmp_path) -> str:
    p = tmp_path / "sample.js"
    p.write_text(
        "var x = 1;\nif (x == 2) { console.log(x); }\n",
        encoding="utf-8",
    )
    return str(p)


def _make_java_with_anti_patterns(tmp_path) -> str:
    p = tmp_path / "Sample.java"
    p.write_text(
        "public class Sample {\n"
        "  void run() {\n"
        '    System.out.println("hi");\n'
        "    try { bad(); } catch (Exception e) { e.printStackTrace(); }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    return str(p)


class TestExecuteAntiPatterns:
    @pytest.mark.asyncio
    async def test_execute_detects_python_anti_patterns(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "categories": ["anti_patterns"], "output_format": "json"}
        )
        assert result["success"] is True
        assert result["total_patterns"] > 0
        types = [p["type"] for p in result["results"]]
        assert "mutable_default_argument" in types
        assert "bare_except" in types
        assert "print_in_production" in types

    @pytest.mark.asyncio
    async def test_execute_detects_js_anti_patterns(self, tmp_path):
        fp = _make_js_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "categories": ["anti_patterns"], "output_format": "json"}
        )
        assert result["success"] is True
        types = [p["type"] for p in result["results"]]
        assert "var_usage" in types
        assert "loose_equality" in types

    @pytest.mark.asyncio
    async def test_execute_detects_java_anti_patterns(self, tmp_path):
        fp = _make_java_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "categories": ["anti_patterns"], "output_format": "json"}
        )
        assert result["success"] is True
        types = [p["type"] for p in result["results"]]
        assert "system_out_println" in types
        assert "print_stacktrace" in types

    @pytest.mark.asyncio
    async def test_execute_clean_file_no_anti_patterns(self, tmp_path):
        fp = _make_clean_python(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute({"file_path": fp, "categories": ["anti_patterns"]})
        assert result["success"] is True
        assert result["total_patterns"] == 0


class TestExecuteCategoryFiltering:
    @pytest.mark.asyncio
    async def test_category_smells_only(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "categories": ["smells"], "output_format": "json"}
        )
        assert result["success"] is True
        for p in result["results"]:
            assert p["category"] == "smells"

    @pytest.mark.asyncio
    async def test_category_security_only(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "categories": ["security"], "output_format": "json"}
        )
        assert result["success"] is True
        for p in result["results"]:
            assert p["category"] == "security"

    @pytest.mark.asyncio
    async def test_category_all_includes_everything(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "categories": ["all"], "output_format": "json"}
        )
        assert result["success"] is True
        cats = {p["category"] for p in result["results"]}
        assert "anti_patterns" in cats

    @pytest.mark.asyncio
    async def test_default_categories_is_all(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute({"file_path": fp})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_multiple_categories(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": fp,
                "categories": ["smells", "anti_patterns"],
                "output_format": "json",
            }
        )
        assert result["success"] is True
        cats = {p["category"] for p in result["results"]}
        assert cats <= {"smells", "anti_patterns"}


class TestExecuteSeverityFiltering:
    @pytest.mark.asyncio
    async def test_severity_threshold_critical(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": fp,
                "categories": ["anti_patterns"],
                "severity_threshold": "critical",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        for p in result["results"]:
            assert p["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_severity_threshold_warning(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": fp,
                "categories": ["anti_patterns"],
                "severity_threshold": "warning",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        for p in result["results"]:
            assert p["severity"] in ("warning", "critical")

    @pytest.mark.asyncio
    async def test_severity_threshold_info_includes_all(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": fp,
                "categories": ["anti_patterns"],
                "severity_threshold": "info",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        sevs = {p["severity"] for p in result["results"]}
        assert sevs >= {"critical", "warning", "info"}

    @pytest.mark.asyncio
    async def test_default_severity_is_info(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute({"file_path": fp, "categories": ["anti_patterns"]})
        assert result["success"] is True
        assert result["total_patterns"] > 0

    @pytest.mark.asyncio
    async def test_patterns_sorted_by_severity_desc(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "categories": ["anti_patterns"], "output_format": "json"}
        )
        sevs = [p["severity"] for p in result["results"]]
        order = [_SEVERITY_ORDER.get(s, 0) for s in sevs]
        assert order == sorted(order, reverse=True)


class TestExecuteResponseStructure:
    @pytest.mark.asyncio
    async def test_response_has_required_fields(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        # J13 (round-22): switch to JSON output so we can inspect the
        # ``results`` field directly (TOON drops it into ``toon_content``).
        result = await tool.execute({"file_path": fp, "output_format": "json"})
        assert "success" in result
        assert "file_path" in result
        assert "language" in result
        assert "total_patterns" in result
        # J13 (round-22): ``patterns`` was a byte-identical duplicate of
        # ``results``. The canonical alias is ``results`` (matches every
        # other search/scan tool).
        assert "results" in result
        assert "by_category" in result
        assert "summary" in result
        assert "smart_workflow_hint" in result

    @pytest.mark.asyncio
    async def test_language_detected(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute({"file_path": fp})
        assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_by_category_counts(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute({"file_path": fp, "categories": ["anti_patterns"]})
        by_cat = result["by_category"]
        total_from_cats = sum(by_cat.values())
        assert total_from_cats == result["total_patterns"]

    @pytest.mark.asyncio
    async def test_patterns_capped_at_50(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute({"file_path": fp, "output_format": "json"})
        assert len(result["results"]) <= 50

    @pytest.mark.asyncio
    async def test_each_pattern_has_required_keys(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "categories": ["anti_patterns"], "output_format": "json"}
        )
        for p in result["results"]:
            assert "id" in p
            assert "category" in p
            assert "type" in p
            assert "severity" in p
            assert "message" in p


class TestExecuteWorkflowHint:
    @pytest.mark.asyncio
    async def test_hint_mentions_critical_when_present(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "categories": ["anti_patterns"], "output_format": "json"}
        )
        hint = result["smart_workflow_hint"]
        has_critical = any(p["severity"] == "critical" for p in result["results"])
        if has_critical:
            assert "Critical issues found" in hint

    @pytest.mark.asyncio
    async def test_hint_mentions_refactoring_suggestions(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute({"file_path": fp})
        assert "refactoring_suggestions" in result["smart_workflow_hint"]

    @pytest.mark.asyncio
    async def test_hint_warns_when_no_critical(self, tmp_path):
        fp = _make_clean_python(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute({"file_path": fp})
        hint = result["smart_workflow_hint"]
        assert "Found 0 pattern" in hint


class TestExecuteEdgeCases:
    @pytest.mark.asyncio
    async def test_nonexistent_file_raises(self, tmp_path):
        tool = CodePatternsTool(str(tmp_path))
        with pytest.raises(ValueError, match="Not a file"):
            await tool.execute({"file_path": str(tmp_path / "nope.py")})

    @pytest.mark.asyncio
    async def test_directory_path_raises(self, tmp_path):
        tool = CodePatternsTool(str(tmp_path))
        with pytest.raises(ValueError, match="Not a file"):
            await tool.execute({"file_path": str(tmp_path)})

    @pytest.mark.asyncio
    async def test_toon_format_requested(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "output_format": "toon", "categories": ["anti_patterns"]}
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_json_format_requested(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "output_format": "json", "categories": ["anti_patterns"]}
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_typescript_uses_js_detector(self, tmp_path):
        p = tmp_path / "sample.ts"
        p.write_text("var x = 1;\nif (x == 2) {}\n", encoding="utf-8")
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(p),
                "categories": ["anti_patterns"],
                "output_format": "json",
            }
        )
        assert result["success"] is True
        types = [pt["type"] for pt in result["results"]]
        assert "var_usage" in types


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


class TestDetectAntiPatternsTypescript:
    def test_typescript_uses_js_patterns(self, tmp_path):
        f = tmp_path / "code.ts"
        f.write_text("var y = 2;\nif (y != 3) {}\n")
        result = _detect_anti_patterns(str(f), "typescript")
        assert any(p["type"] == "var_usage" for p in result)
        assert any(p["type"] == "loose_equality" for p in result)


class TestDetectSecurityWithRealFile:
    def test_detect_security_returns_list_for_valid_file(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("x = 1\n")
        result = _detect_security(str(f), "python")
        assert isinstance(result, list)

    def test_detect_security_handles_unreadable_gracefully(self):
        result = _detect_security("/nonexistent/path/code.py", "python")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Cross-language smell detection (regression for bugs H1 + M5)
#
# Before the fix, code_patterns called detect_code_smells with analysis=None,
# which fell back to a Python-only heuristic. JS / TS / Java long functions
# and god-classes were silently ignored even though file_health flagged them.
# ---------------------------------------------------------------------------


class TestCrossLanguageSmellDetection:
    @pytest.mark.asyncio
    async def test_code_patterns_long_method_js(self, tmp_path):
        """Bug H1 regression: a 100+ line JS function MUST surface as long_method."""
        body = "\n".join(f"  const var{i} = input + {i};" for i in range(1, 121))
        source = (
            "function longJSFunction(input) {\n"
            "  // Auto-generated long function for testing\n"
            f"{body}\n"
            "  return var100;\n"
            "}\n"
        )
        target = tmp_path / "long.js"
        target.write_text(source, encoding="utf-8")

        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["smells"],
                "output_format": "json",
            }
        )

        smells = [p for p in result["results"] if p["category"] == "smells"]
        long_methods = [p for p in smells if p["type"] == "long_method"]
        assert long_methods, (
            "expected at least one long_method smell from cross-language AST "
            f"detection, got: {smells}"
        )
        assert long_methods[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_code_patterns_god_class_js(self, tmp_path):
        """Bug M5 regression: a single 300+ line JS class MUST surface as god_class."""
        method_chunks: list[str] = []
        for i in range(1, 30):
            body = "\n".join(f"    const x{j} = {i} + {j};" for j in range(10))
            method_chunks.append(f"  method{i}() {{\n{body}\n    return x9;\n  }}")
        source = "class BigJS {\n" + "\n".join(method_chunks) + "\n}\n"

        target = tmp_path / "big_class.js"
        target.write_text(source, encoding="utf-8")

        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["smells"],
                "output_format": "json",
            }
        )

        smells = [p for p in result["results"] if p["category"] == "smells"]
        god_classes = [p for p in smells if p["type"] == "god_class"]
        assert god_classes, (
            "expected a god_class smell once the AST path is wired up; got "
            f"smells={smells}"
        )


# ---------------------------------------------------------------------------
# G3 regression — SQL-injection regex must not flag benign diagnostic f-strings.
#
# Pre-fix the regex was ``f['\"].*?(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s``,
# which matched any f-string containing the keyword anywhere followed by
# whitespace. English text like ``f"Please update {n} call sites"`` and
# ``f"DROP this approach, use {alternative} instead"`` were reported as
# ``critical: sql_injection``. The fix tightens the body so a clause
# indicator (``FROM``, ``INTO``, ``WHERE``, ``TABLE``, ``VALUES``, ``SET``)
# must follow the SQL keyword inside the same f-string.
# ---------------------------------------------------------------------------


class TestG3SqlInjectionFalsePositives:
    @pytest.mark.asyncio
    async def test_g3_fp_please_update_call_sites(self, tmp_path):
        """``Please update {n} call sites`` is English, not SQL."""
        target = tmp_path / "msg.py"
        target.write_text(
            "def msg(n, name):\n"
            '    return f"Please update {n} call sites for {name}."\n',
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["security"],
                "output_format": "json",
            }
        )
        sql_findings = [
            p
            for p in result["results"]
            if str(p.get("type") or p.get("id") or "").endswith("sql_injection")
        ]
        assert sql_findings == [], (
            f"benign English f-string was flagged as sql_injection: {sql_findings}"
        )

    @pytest.mark.asyncio
    async def test_g3_fp_drop_this_approach(self, tmp_path):
        """``DROP this approach`` is figurative, not a DROP TABLE."""
        target = tmp_path / "comment.py"
        target.write_text(
            "def note(alternative):\n"
            '    return f"DROP this approach, use {alternative} instead"\n',
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["security"],
                "output_format": "json",
            }
        )
        sql_findings = [
            p
            for p in result["results"]
            if str(p.get("type") or p.get("id") or "").endswith("sql_injection")
        ]
        assert sql_findings == [], (
            f"figurative ``DROP this approach`` was flagged: {sql_findings}"
        )

    @pytest.mark.asyncio
    async def test_g3_tp_select_from_users(self, tmp_path):
        """Real SQL with FROM clause MUST be flagged."""
        target = tmp_path / "real_sqli.py"
        target.write_text(
            "def lookup(user_input):\n"
            "    return f\"SELECT * FROM users WHERE name = '{user_input}'\"\n",
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["security"],
                "output_format": "json",
            }
        )
        sql_findings = [
            p
            for p in result["results"]
            if str(p.get("type") or p.get("id") or "").endswith("sql_injection")
        ]
        assert len(sql_findings) == 1, (
            "expected exactly one sql_injection finding for a SELECT-FROM-WHERE "
            f"f-string; got {sql_findings}"
        )
        assert sql_findings[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_g3_tp_insert_into_logs(self, tmp_path):
        """Real INSERT with INTO clause MUST be flagged."""
        target = tmp_path / "real_insert.py"
        target.write_text(
            'def log(val):\n    return f"INSERT INTO logs VALUES ({val})"\n',
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["security"],
                "output_format": "json",
            }
        )
        sql_findings = [
            p
            for p in result["results"]
            if str(p.get("type") or p.get("id") or "").endswith("sql_injection")
        ]
        assert len(sql_findings) == 1, (
            "expected exactly one sql_injection finding for an INSERT-INTO "
            f"f-string; got {sql_findings}"
        )


# ---------------------------------------------------------------------------
# G4 regression — code_patterns must not report the same finding twice.
#
# Pre-fix, ``_detect_smells`` re-emitted security issues as ``smell``
# entries (category=smells, id=security:<name>), AND ``_detect_security``
# emitted the canonical entry (category=security, id=<name>). The same
# underlying SQL-injection ended up listed twice in ``results`` and double-
# counted in ``critical_count``. The fix drops the smell-namespaced mirror
# when a matching security entry exists.
# ---------------------------------------------------------------------------


class TestG4NoDuplicateFindings:
    @pytest.mark.asyncio
    async def test_g4_sql_injection_appears_once(self, tmp_path):
        """A single SQL-injection line yields exactly one ``results`` entry."""
        target = tmp_path / "sqli.py"
        target.write_text(
            "def get_user(user_id):\n"
            '    return f"SELECT * FROM users WHERE id = {user_id}"\n',
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["all"],
                "output_format": "json",
            }
        )
        sql_findings = [
            p
            for p in result["results"]
            if str(p.get("type") or p.get("id") or "").endswith("sql_injection")
        ]
        assert len(sql_findings) == 1, (
            "expected exactly one sql_injection entry in results; got "
            f"{len(sql_findings)}: {sql_findings}"
        )
        # The canonical entry under ``security`` namespace must survive;
        # the smell-namespaced mirror must be dropped.
        assert sql_findings[0]["category"] == "security"

    @pytest.mark.asyncio
    async def test_g4_count_matches_results_length(self, tmp_path):
        """``count`` must equal ``len(results)`` after dedup."""
        target = tmp_path / "sqli.py"
        target.write_text(
            "def get_user(user_id):\n"
            '    return f"SELECT * FROM users WHERE id = {user_id}"\n',
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["all"],
                "output_format": "json",
            }
        )
        assert result["count"] == len(result["results"])
        # critical_count should reflect ONE underlying problem, not two.
        assert result["critical_count"] == 1

    @pytest.mark.asyncio
    async def test_g4_dedup_does_not_swallow_non_security_smells(self, tmp_path):
        """Dedup must only target the security mirror, not real smells."""
        # An oversized file produces ``oversized_file`` (a real smell) plus
        # a security finding. The smell must survive even after dedup runs.
        lines = ["def f():"] + ["    x = 1"] * 1200
        lines.append('    return f"SELECT * FROM users WHERE id = {x}"')
        target = tmp_path / "big.py"
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")

        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["all"],
                "output_format": "json",
            }
        )
        types = {str(p.get("type") or p.get("id") or "") for p in result["results"]}
        assert "oversized_file" in types
        # sql_injection still appears exactly once
        sql_count = sum(
            1 for p in result["results"] if p.get("type") == "sql_injection"
        )
        assert sql_count == 1
