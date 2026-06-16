#!/usr/bin/env python3
"""Issue #607 — conceptual queries through CodeGraphSymbolSearchTool.

Reproduces the RFC-0016 pilot Q3 failure shape end-to-end: long descriptive
``test_*`` names share more conceptual-query tokens than any production
symbol, so they win the raw BM25 race. ``fts_search_ranked`` demotes test
files, but ``search_symbols_cascade`` re-sorted purely by relevance_score and
truncated, so the tool's own ``_demote_test_files`` received an all-test
window with nothing left to promote.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.symbol_search_tool import CodeGraphSymbolSearchTool

_Q3_STYLE_QUERY = "where are stop words filtered out of search queries"

_PROD_SOURCE = "def filter_stop_words(query):\n    return query\n"

_TEST_SOURCE = (
    "def test_stop_words_filtered_out_of_search_queries():\n    pass\n\n"
    "def test_stop_word_filter_applies_to_search_query():\n    pass\n\n"
    "def test_filtered_stop_words_removed_from_search_queries():\n    pass\n\n"
    "def test_search_query_stop_words_filtered():\n    pass\n\n"
    "def test_stop_words_are_filtered_from_queries():\n    pass\n\n"
    "def test_query_search_filters_out_stop_words():\n    pass\n"
)


@pytest.fixture
def q3_shaped_project(tmp_path):
    """1 production symbol + 6 token-richer test symbols (pilot Q3 shape)."""
    project = tmp_path / "proj"
    test_dir = project / "tests" / "unit"
    test_dir.mkdir(parents=True)

    (project / "search_filters.py").write_text(_PROD_SOURCE, newline="\n")
    (test_dir / "test_search_filters.py").write_text(_TEST_SOURCE, newline="\n")

    cache = ASTCache(str(project))
    cache.index_project(max_files=100)
    cache.close()
    return project


class TestConceptualQueryTestDemotion:
    @pytest.mark.asyncio
    async def test_production_symbol_tops_conceptual_query(self, q3_shaped_project):
        """#607 RED: top-5 was all test functions; production must rank first."""
        tool = CodeGraphSymbolSearchTool(str(q3_shaped_project))
        result = await tool.execute(
            {"query": _Q3_STYLE_QUERY, "limit": 5, "output_format": "json"}
        )

        assert result["success"] is True
        assert result["match_count"] == 5
        names = [r["name"] for r in result["results"]]
        assert names[0] == "filter_stop_words"
        assert [n.startswith("test_") for n in names] == [
            False,
            True,
            True,
            True,
            True,
        ]

    @pytest.mark.asyncio
    async def test_test_intent_query_still_surfaces_test_symbols(
        self, q3_shaped_project
    ):
        """Counter-direction pin: explicit test-seeking queries keep tests on top."""
        tool = CodeGraphSymbolSearchTool(str(q3_shaped_project))
        result = await tool.execute(
            {
                "query": "tests for stop words filtered out of search queries",
                "limit": 5,
                "output_format": "json",
            }
        )

        assert result["success"] is True
        assert result["match_count"] == 5
        names = [r["name"] for r in result["results"]]
        assert [n.startswith("test_") for n in names] == [
            True,
            True,
            True,
            True,
            True,
        ]
