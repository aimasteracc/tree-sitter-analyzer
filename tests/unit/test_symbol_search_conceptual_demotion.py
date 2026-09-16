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

import os
import sqlite3
from typing import Any

import pytest

from tests.unit._navigation_test_support import published_search
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


def test_source_demotion_preserves_non_body_guidance() -> None:
    result = {
        "results": [{"name": "target", "code": "x", "body": {"content": "x"}}],
        "next_step": "Raise limit to inspect more coordinates.",
    }

    CodeGraphSymbolSearchTool._remove_unbound_source(result)

    assert result["results"] == [{"name": "target"}]
    assert result["next_step"] == "Raise limit to inspect more coordinates."


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="tracked:C1 certified source owner is POSIX-only",
)
@pytest.mark.parametrize(
    ("failure_stage", "query"),
    [("fts", "absent term"), ("like", "arget"), ("fuzzy", "targte")],
)
async def test_public_search_sql_failure_falls_back_without_source(
    tmp_path, monkeypatch, failure_stage: str, query: str
) -> None:
    """认证查询失败必须重试普通坐标路径，不能伪装成认证空集。"""
    from tree_sitter_analyzer.cache import query as cache_query
    from tree_sitter_analyzer.cache import search as cache_search

    _source, facade, symbol = await published_search(tmp_path)
    legacy_cache = symbol._get_cache()
    legacy_calls = 0
    original_cascade = legacy_cache.search_symbols_cascade

    def observe_legacy(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        nonlocal legacy_calls
        legacy_calls += 1
        return original_cascade(*args, **kwargs)

    monkeypatch.setattr(legacy_cache, "search_symbols_cascade", observe_legacy)

    if failure_stage == "fts":
        original_ranked = cache_query.fts_search_ranked

        def fail_ranked(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            if kwargs.get("suppress_sql_errors") is False:
                raise sqlite3.OperationalError("injected certified FTS failure")
            return original_ranked(*args, **kwargs)

        monkeypatch.setattr(cache_query, "fts_search_ranked", fail_ranked)
        monkeypatch.setattr(cache_search, "fts_search_ranked", fail_ranked)
    else:
        helper_name = "_like_rows" if failure_stage == "like" else "_fuzzy_rows"
        original_helper = getattr(cache_search, helper_name)

        def fail_late(*args: Any, **kwargs: Any) -> Any:
            if kwargs.get("suppress_sql_errors") is False:
                raise sqlite3.OperationalError(
                    f"injected certified {failure_stage} failure"
                )
            return original_helper(*args, **kwargs)

        monkeypatch.setattr(cache_search, helper_name, fail_late)

    try:
        result = await facade.execute(
            {"action": "symbol", "query": query, "output_format": "json"}
        )
        assert result["success"] is True
        assert legacy_calls == 1
        assert all("code" not in row and "body" not in row for row in result["results"])
        assert "no Read needed" not in result.get("next_step", "")
    finally:
        legacy_cache.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="tracked:C1 certified source owner is POSIX-only",
)
@pytest.mark.parametrize("query", ["foo-bar", "foo.bar", "foo:bar", 'foo"bar'])
async def test_certified_plain_fts_special_characters_remain_compatible(
    tmp_path, query: str
) -> None:
    """用户特殊字符由 FTS 查询构造器引用，不应被当成数据库故障。"""
    _source, facade, symbol = await published_search(tmp_path)
    try:
        result = await facade.execute(
            {"action": "symbol", "query": query, "output_format": "json"}
        )
        assert result["success"] is True
    finally:
        symbol._cache.close()
