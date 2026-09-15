"""认证 symbol search 公共路径的 SQL 失败语义。"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

import pytest

from tests.unit._navigation_test_support import published_search

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.name != "posix",
        reason="tracked:C1 certified source owner is POSIX-only",
    ),
]


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
