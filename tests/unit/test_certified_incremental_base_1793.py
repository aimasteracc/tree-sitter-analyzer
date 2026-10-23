"""#1793：认证快照上构建的调用图明确不作 #1723 增量基础（fail closed，带原因）。

认证快照只带 ``source_generation``（``idxsrc-v3:`` 源码树指纹），刷新范围记的是
generation id，两者从不相等；#1778 实测收益很小。因此这里钉住：

* 快照上的图不保留对齐依据与解析结果，只记下 ``CERTIFIED_SNAPSHOT_NOT_A_BASE``；
* ``update`` 与预构图调度都给出这个原因，不做增量；
* 退回的全量预构图与在新库上全新构图的结果逐项相同（不会给出旧图）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from tests.unit.test_incremental_call_graph_1723 import (
    _STATE_FIELDS,
    _fresh_state,
)
from tests.unit.test_scoped_backfill_1696 import _edit, _write_tree

_REFUSED = "CERTIFIED_SNAPSHOT_NOT_A_BASE"


@pytest.fixture(autouse=True)
def _warm_enabled():
    from tree_sitter_analyzer import call_graph_memo, call_graph_warm
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    auto_index_guard.reset()
    call_graph_memo.clear()
    call_graph_warm.enable()
    yield
    call_graph_warm.wait(timeout=60)
    call_graph_warm.disable()
    call_graph_memo.clear()
    call_graph_warm._ready.clear()
    auto_index_guard.reset()


def _certified_graph(root: str):
    """与认证查询相同的图：缓存带认证 owner 的快照（只用于判定身份）。"""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.call_graph import CachedCallGraph

    cache = ASTCache(root)
    cache._owner = SimpleNamespace(  # type: ignore[attr-defined]
        snapshot=SimpleNamespace(source_generation="idxsrc-v3:" + "0" * 64)
    )
    graph = CachedCallGraph(root, cache=cache, fallback=False, persist=False)
    graph.build()
    return graph


def _state(state: dict) -> dict:
    out: dict = {}
    for name in _STATE_FIELDS:
        value = state[name]
        if isinstance(value, dict):
            value = {key: item for key, item in value.items() if item not in ([], None)}
        out[name] = value
    return out


def test_update_refuses_a_certified_base_with_its_reason() -> None:
    from tree_sitter_analyzer.call_graph_incremental import RefreshPlan, update

    class _Graph:
        _cache = None

        def _reset_graph_state(self) -> None:
            pass

    plan = RefreshPlan(
        "g1", frozenset({"a.py"}), frozenset({"a.py"}), frozenset(), "OK", "g2"
    )
    previous = {"_incremental": {"refused": _REFUSED}}

    assert update(_Graph(), previous, plan) == _REFUSED  # type: ignore[arg-type]


@pytest.mark.slow_ok
def test_certified_graph_keeps_no_alignment_and_is_never_a_base(
    tmp_path, monkeypatch
) -> None:
    from tree_sitter_analyzer import call_graph_memo, call_graph_warm
    from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

    root = tmp_path / "project"
    _write_tree(root)
    tool = ASTCacheTool(str(root))
    asyncio.run(tool.execute({"mode": "index"}))
    asyncio.run(tool.execute({"mode": "index"}))
    graph = _certified_graph(str(root))
    assert graph._built
    assert graph._incremental == {"refused": _REFUSED}
    latest = call_graph_memo.latest(str(root.resolve()))
    assert latest is not None
    assert latest["_incremental"] == {"refused": _REFUSED}

    # 范围有界的显式刷新：基础是认证图，增量明确放弃；``always`` 退回全量预构图。
    monkeypatch.setenv(call_graph_warm.ENV_VAR, "always")
    _edit(root, "signature")
    reply = asyncio.run(tool.execute({"mode": "index"}))
    warm = reply.get("call_graph_warm") or {}

    assert (warm.get("incremental"), warm.get("incremental_reason")) == (
        False,
        _REFUSED,
    ), warm
    assert call_graph_warm.wait(str(root), timeout=60)
    outcome = call_graph_warm.last_outcome(str(root)) or {}
    assert outcome.get("warmed") is True and "incremental" not in outcome, outcome
    rebuilt = call_graph_memo.latest(str(root.resolve()))
    assert rebuilt is not None
    assert _state(rebuilt) == _state(_fresh_state(str(root)))
