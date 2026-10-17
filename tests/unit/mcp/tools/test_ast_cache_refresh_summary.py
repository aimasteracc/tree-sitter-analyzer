"""#1635：刷新回复的 ``summary_line`` 计数必须是刷新之后活动索引的计数。

dogfood 第 6 轮：增删文件后，``index action=cache mode=index`` 的摘要仍是
``symbols=69316``。摘要计数在运行结束后读取活动索引；当运行有非稳定失败
（读写失败，第 6 轮机器只剩 1.25 GB 磁盘）时，私有副本被放弃、活动版本不变，
回复却既不带 ``published`` 也不在摘要中说明——旧计数看起来像是本次刷新的结果。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool


def _functions(prefix: str, count: int) -> str:
    return "".join(f"def {prefix}{n}():\n    return {n}\n\n\n" for n in range(count))


@pytest.fixture
async def indexed_root(tmp_path) -> Path:
    for module in range(3):
        (tmp_path / f"m{module}.py").write_text(
            _functions(f"f{module}_", 5), encoding="utf-8"
        )
    first = await ASTCacheTool(str(tmp_path)).execute({"mode": "index"})
    assert first["summary_line"].startswith("ast_cache index project files=3 ")
    return tmp_path


def _add_and_delete(root: Path) -> None:
    (root / "m0.py").unlink()
    (root / "added.py").write_text(_functions("n", 12), encoding="utf-8")


@pytest.mark.asyncio
async def test_refresh_summary_counts_the_refreshed_index(indexed_root) -> None:
    # 对照：发布成功时，摘要计数是刷新后的活动索引（15 - 5 + 12 = 22）。
    tool = ASTCacheTool(str(indexed_root))
    _add_and_delete(indexed_root)

    refreshed = await tool.execute({"mode": "index"})
    stats = await tool.execute({"mode": "stats"})

    assert refreshed["published"] is True
    assert "symbols=22 " in refreshed["summary_line"]
    assert "published=false" not in refreshed["summary_line"]
    assert stats["total_symbols"] == 22


@pytest.mark.asyncio
async def test_unpublished_refresh_says_the_count_is_the_previous_index(
    indexed_root, monkeypatch
) -> None:
    # #1635：运行有非稳定失败而未发布时，摘要必须说明未发布、计数属于旧版本。
    from tree_sitter_analyzer.cache import generation_indexing

    monkeypatch.setattr(generation_indexing, "publishable_result", lambda _r: False)
    tool = ASTCacheTool(str(indexed_root))
    _add_and_delete(indexed_root)

    refreshed = await tool.execute({"mode": "index"})

    assert refreshed["published"] is False
    assert refreshed["publication_reason"] == "INDEX_NOT_PUBLISHABLE"
    assert refreshed["summary_line"] == (
        "ast_cache index project files=1 symbols=15 force=False removed=1 "
        "published=false reason=INDEX_NOT_PUBLISHABLE"
    )
    assert refreshed["agent_summary"]["next_step"].startswith(
        "this refresh was not published: the active index was not replaced, so "
        "symbols=15 is the previous index."
    )
    stats = await tool.execute({"mode": "stats"})
    assert stats["total_symbols"] == 15


@pytest.mark.asyncio
async def test_unpublished_forced_rebuild_is_reported(
    indexed_root, monkeypatch
) -> None:
    # #1635：强制重建同样如实报告是否发布。
    from tree_sitter_analyzer.cache import generation_indexing

    monkeypatch.setattr(generation_indexing, "publishable_result", lambda _r: False)
    _add_and_delete(indexed_root)

    refreshed = await ASTCacheTool(str(indexed_root)).execute(
        {"mode": "index", "force": True}
    )

    assert refreshed["published"] is False
    assert "symbols=15 force=True" in refreshed["summary_line"]
    assert refreshed["summary_line"].endswith(
        "published=false reason=INDEX_NOT_PUBLISHABLE"
    )


@pytest.mark.asyncio
async def test_unchanged_refresh_summary_is_unchanged(indexed_root) -> None:
    # 负对照：零变化的刷新（#1631 不发布）计数本就准确，摘要不加未发布标记。
    refreshed = await ASTCacheTool(str(indexed_root)).execute({"mode": "index"})

    assert (refreshed["published"], refreshed["publication_reason"]) == (
        False,
        "INDEX_UNCHANGED",
    )
    assert refreshed["summary_line"] == (
        "ast_cache index project files=0 symbols=15 force=False removed=0"
    )
