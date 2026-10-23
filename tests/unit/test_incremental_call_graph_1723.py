"""#1723：发布后按刷新的解析范围增量更新内存调用图，结果等于新库上的全新构图。

长驻进程（MCP 服务器）里：全量构图 → 编辑 1 个文件 → 显式刷新（范围回填）。
发布后的预构图按同一范围增量更新上一张图；``nav`` 的第一次调用采用它。等价门：
增量得到的图状态与在同一新库上全新构图的状态逐项相同（含边的应用顺序），覆盖
#1696 的 8 种编辑与 #1721 的 ``global`` 重新绑定；范围回填退回全量时图也全量构建。
"""

from __future__ import annotations

import asyncio

import pytest

from tests.unit.test_scoped_backfill_1696 import _EDITS, _edit, _sync, _write_tree

_REBIND_FILES = {
    "pkg/hub.py": (
        "from .base import make as _make\nfrom .base import factory\n\n\n"
        "def install(value):\n    return value\n",
        "from .base import make as _make\nfrom .base import factory\n\n\n"
        "def install(value):\n    global _make\n    _make = value\n",
    )
}
_STATE_FIELDS = (
    "_functions",
    "_func_by_name",
    "_func_by_file",
    "_func_by_qualified",
    "_callers",
    "_callees",
    "_possible_callers",
    "_possible_callees",
    "_call_edges",
    "_edge_bindings",
    "_plain_edges",
)


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


def _graph(root: str, *, persist: bool = True):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.call_graph import CachedCallGraph

    graph = CachedCallGraph(root, cache=ASTCache(root), fallback=False, persist=persist)
    graph.build()
    return graph


def _normalised(state: dict) -> dict:
    out: dict = {}
    for name in _STATE_FIELDS:
        value = state[name]
        if isinstance(value, dict):
            value = {key: item for key, item in value.items() if item not in ([], None)}
        out[name] = value
    out["records"] = state["_incremental"]["records"]
    out["ids"] = state["_incremental"]["alignment"].ids
    return out


def _fresh_state(root: str) -> dict:
    from tree_sitter_analyzer import call_graph_memo, call_graph_warm

    call_graph_memo.clear()
    call_graph_warm._ready.clear()
    return _graph(root, persist=False)._export_state()


def _refresh_and_take_increment(root) -> tuple[dict, dict]:
    from tree_sitter_analyzer import call_graph_memo, call_graph_warm

    _sync(root)
    assert call_graph_warm.wait(str(root), timeout=60)
    outcome = call_graph_warm.last_outcome(str(root)) or {}
    state = call_graph_memo.latest(str(root.resolve())) or call_graph_memo.latest(
        str(root)
    )
    return outcome, state or {}


def _established(root) -> None:
    _sync(root)
    _sync(root)
    _graph(str(root))


@pytest.mark.slow_ok
@pytest.mark.parametrize("edit", sorted(_EDITS))
def test_incremental_graph_equals_a_fresh_build(tmp_path, edit: str) -> None:
    root = tmp_path / "project"
    _write_tree(root)
    _established(root)
    _edit(root, edit)

    outcome, incremental = _refresh_and_take_increment(root)

    assert outcome.get("incremental", {}).get("applied") is True, outcome
    assert _normalised(incremental) == _normalised(_fresh_state(str(root)))


@pytest.mark.slow_ok
@pytest.mark.parametrize("direction", ["add", "remove"])
def test_global_rebinding_updates_the_graph_like_a_fresh_build(
    tmp_path, direction: str
) -> None:
    root = tmp_path / "project"
    _write_tree(root)
    plain, rebinding = _REBIND_FILES["pkg/hub.py"]
    before, after = (plain, rebinding) if direction == "add" else (rebinding, plain)
    (root / "pkg" / "hub.py").write_text(before, encoding="utf-8")
    _established(root)
    (root / "pkg" / "hub.py").write_text(after, encoding="utf-8")
    import os

    info = os.stat(root / "pkg" / "hub.py")
    os.utime(root / "pkg" / "hub.py", ns=(info.st_atime_ns, info.st_mtime_ns + 2**31))

    outcome, incremental = _refresh_and_take_increment(root)

    assert outcome.get("incremental", {}).get("applied") is True, outcome
    assert _normalised(incremental) == _normalised(_fresh_state(str(root)))


@pytest.mark.slow_ok
def test_nav_adopts_the_incremental_graph(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    root = tmp_path / "project"
    _write_tree(root)
    _established(root)
    _edit(root, "add_method")
    _sync(root)

    reply = asyncio.run(
        CodeGraphCallersTool(str(root)).execute(
            {"function_name": "Mixin.shared", "file_path": "pkg/base.py"}
        )
    )
    expected = {entry["name"] for entry in reply["callers"]}
    _fresh_state(str(root))
    fresh = asyncio.run(
        CodeGraphCallersTool(str(root)).execute(
            {"function_name": "Mixin.shared", "file_path": "pkg/base.py"}
        )
    )
    assert expected == {entry["name"] for entry in fresh["callers"]}
    assert expected


def test_incremental_refuses_without_a_matching_previous_graph(tmp_path) -> None:
    from tree_sitter_analyzer.call_graph_incremental import RefreshPlan, update

    class _Graph:
        _cache = None

        def _reset_graph_state(self) -> None:
            pass

    empty = RefreshPlan(None, frozenset(), frozenset(), frozenset(), "SCOPE_TOO_LARGE")
    scoped = RefreshPlan(
        "g1", frozenset({"a.py"}), frozenset({"a.py"}), frozenset(), "OK", "x"
    )

    assert update(_Graph(), {}, empty) == "BACKFILL_NOT_SCOPED:SCOPE_TOO_LARGE"  # type: ignore[arg-type]
    assert update(_Graph(), {}, scoped) == "PREVIOUS_GRAPH_NOT_ALIGNED"  # type: ignore[arg-type]
    other = {"_incremental": {"generation": "g2"}}
    assert update(_Graph(), other, scoped) == "PREVIOUS_GRAPH_OTHER_GENERATION"  # type: ignore[arg-type]


@pytest.mark.slow_ok
def test_explicit_index_refresh_updates_the_graph_incrementally(tmp_path) -> None:
    from tree_sitter_analyzer import call_graph_incremental, call_graph_memo
    from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

    root = tmp_path / "project"
    _write_tree(root)
    tool = ASTCacheTool(str(root))
    asyncio.run(tool.execute({"mode": "index"}))
    asyncio.run(tool.execute({"mode": "index"}))
    _graph(str(root))
    _edit(root, "signature")

    reply = asyncio.run(tool.execute({"mode": "index"}))

    assert reply.get("call_graph_warm", {}).get("incremental") is True, (
        reply.get("call_graph_warm"),
        call_graph_incremental._plans,
    )
    from tree_sitter_analyzer import call_graph_warm

    assert call_graph_warm.wait(str(root), timeout=60)
    incremental = call_graph_memo.latest(str(root.resolve()))
    assert _normalised(incremental) == _normalised(_fresh_state(str(root)))
