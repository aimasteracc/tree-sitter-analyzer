"""Unit tests for query_symbol_search wildcard and fuzzy matching."""

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.query_symbol_search import (
    _build_match_fn,
    _build_type_filter,
    execute_find_references,
    execute_symbol_search,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class TestBuildMatchFn:
    def test_exact_match(self):
        fn = _build_match_fn("HealthScorer")
        assert fn("HealthScorer")
        assert not fn("health_scorer")
        assert not fn("OtherClass")

    def test_exact_match_case_sensitive(self):
        fn = _build_match_fn("analyze_file")
        assert fn("analyze_file")
        assert not fn("Analyze_File")

    def test_wildcard_prefix(self):
        fn = _build_match_fn("*Tool")
        assert fn("QueryTool")
        assert fn("SearchContentTool")
        assert fn("query_tool")  # case-insensitive
        assert not fn("ToolFactory")  # doesn't end with Tool

    def test_wildcard_suffix(self):
        fn = _build_match_fn("handle_*")
        assert fn("handle_request")
        assert fn("handle_response")
        assert fn("Handle_Request")  # case-insensitive

    def test_wildcard_both_ends(self):
        fn = _build_match_fn("*_test_*")
        assert fn("unit_test_helper")
        assert fn("Unit_Test_Helper")  # case-insensitive

    def test_wildcard_case_insensitive(self):
        fn = _build_match_fn("*tool")
        assert fn("QueryTool")
        assert fn("querytool")
        assert not fn("QueryToolX")

    def test_fuzzy_match(self):
        fn = _build_match_fn("~analyz")
        assert fn("analyze_file")
        assert fn("AnalyzeCode")
        assert fn("re_analyze")
        assert not fn("health_scorer")
        assert not fn("analysis_engine")  # "analyz" not in "analysis"

    def test_fuzzy_case_insensitive(self):
        fn = _build_match_fn("~SCORE")
        assert fn("score_file")
        assert fn("HealthScore")

    def test_empty_symbol_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            asyncio.run(execute_symbol_search(".", {"symbol": ""}))


class TestBuildTypeFilter:
    def test_none_returns_none(self):
        assert _build_type_filter(None) is None

    def test_class_filter(self):
        fn = _build_type_filter("class")
        assert fn("class")
        assert fn("class_definition")
        assert not fn("function")
        assert not fn("function_definition")

    def test_function_filter(self):
        fn = _build_type_filter("function")
        assert fn("function")
        assert fn("function_definition")
        assert not fn("class")

    def test_method_filter(self):
        fn = _build_type_filter("method")
        assert fn("method")
        assert fn("method_definition")
        assert not fn("class")

    def test_unknown_type_returns_none(self):
        assert _build_type_filter("unknown_type") is None


class TestSymbolSearchIntegration:
    @pytest.fixture
    def tool_with_project(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

        sample = tmp_path / "symbols.py"
        sample.write_text(
            """
class HealthScorer:
    def score_file(self):
        return 100


class QueryTool:
    pass


class SearchContentTool:
    pass


class RefactoringTool:
    pass


def analyze_file():
    return HealthScorer()
""".strip()
        )

        tool = QueryTool(str(tmp_path))
        return tool

    def test_exact_search_finds_symbol(self, tool_with_project):
        result = asyncio.run(tool_with_project.execute({"symbol": "HealthScorer"}))
        assert result["success"] is True
        assert result["matches_found"] >= 1
        defs = result.get("definitions", [])
        names = [d["name"] for d in defs]
        assert "HealthScorer" in names

    def test_wildcard_search_finds_multiple(self, tool_with_project):
        result = asyncio.run(tool_with_project.execute({"symbol": "*Tool"}))
        assert result["success"] is True
        assert result["matches_found"] >= 3
        defs = result.get("definitions", [])
        names = [d["name"] for d in defs]
        assert any("Tool" in n for n in names)

    def test_fuzzy_search_finds_matches(self, tool_with_project):
        result = asyncio.run(tool_with_project.execute({"symbol": "~scorer"}))
        assert result["success"] is True
        assert result["matches_found"] >= 1

    def test_type_filter_classes_only(self, tool_with_project):
        result = asyncio.run(
            tool_with_project.execute({"symbol": "*Tool", "symbol_type": "class"})
        )
        assert result["success"] is True
        defs = result.get("definitions", [])
        for d in defs:
            assert "class" in d.get("type", "").lower()

    def test_symbol_type_in_schema(self):
        from tree_sitter_analyzer.mcp.tools.query_helpers import TOOL_SCHEMA

        props = TOOL_SCHEMA["properties"]
        assert "symbol_type" in props
        assert props["symbol_type"]["type"] == "string"
        assert "enum" in props["symbol_type"]


class TestFindReferences:
    @pytest.fixture
    def ref_project(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

        main_py = tmp_path / "main.py"
        main_py.write_text(
            """
from scorer import HealthScorer

def run():
    s = HealthScorer()
    score = s.score_file()
    return score
""".strip()
        )

        scorer_py = tmp_path / "scorer.py"
        scorer_py.write_text(
            """
class HealthScorer:
    def score_file(self):
        return 100
""".strip()
        )

        tool = QueryTool(str(tmp_path))
        return tool

    def test_find_references_returns_definitions_and_refs(self, ref_project):
        result = asyncio.run(
            ref_project.execute(
                {"symbol": "HealthScorer", "find_references": True}
            )
        )
        assert result["success"] is True
        assert "definitions" in result
        assert "references" in result

    def test_find_references_counts_callers(self, ref_project):
        result = asyncio.run(
            ref_project.execute(
                {"symbol": "HealthScorer", "find_references": True}
            )
        )
        assert result["success"] is True
        assert result.get("callers_count", 0) >= 0
        assert "total_usages" in result

    def test_find_references_empty_symbol_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            asyncio.run(
                execute_find_references(".", {"symbol": ""})
            )

    def test_find_references_flag_in_schema(self):
        from tree_sitter_analyzer.mcp.tools.query_helpers import TOOL_SCHEMA

        props = TOOL_SCHEMA["properties"]
        assert "find_references" in props
        assert props["find_references"]["type"] == "boolean"
