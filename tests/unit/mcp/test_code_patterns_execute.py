"""Tests for CodePatternsTool.execute() — anti-patterns, filtering, response structure."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
    _SEVERITY_ORDER,
    CodePatternsTool,
)

# ---------------------------------------------------------------------------
# Shared file factories
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


# ---------------------------------------------------------------------------
# execute() — anti-pattern detection
# ---------------------------------------------------------------------------


class TestExecuteAntiPatterns:
    @pytest.mark.asyncio
    async def test_execute_detects_python_anti_patterns(self, tmp_path):
        fp = _make_python_with_anti_patterns(tmp_path)
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {"file_path": fp, "categories": ["anti_patterns"], "output_format": "json"}
        )
        assert result["success"] is True
        assert result["total_patterns"]
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


# ---------------------------------------------------------------------------
# execute() — category filtering
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# execute() — severity filtering
# ---------------------------------------------------------------------------


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
        assert result["total_patterns"]

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


# ---------------------------------------------------------------------------
# execute() — response structure
# ---------------------------------------------------------------------------


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
        result = await tool.execute(
            {"file_path": fp, "categories": ["anti_patterns"], "output_format": "json"}
        )
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


# ---------------------------------------------------------------------------
# execute() — workflow hint
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# execute() — edge cases
# ---------------------------------------------------------------------------


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
