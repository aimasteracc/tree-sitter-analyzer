"""index_bound_graph：记忆化调用图与索引身份的绑定（#1611）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.mcp.tools.index_bound_graph as bound


@pytest.fixture
def identity(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """可变的假索引身份：修改 ``identity[0]`` 即模拟一次索引刷新。"""
    current = ["gen-1"]
    monkeypatch.setattr(bound, "index_identity", lambda root: (root, current[0]))
    return current


def _builder(built: list[str]):
    def build() -> str:
        built.append(f"graph-{len(built) + 1}")
        return built[-1]

    return build


def test_unchanged_identity_reuses_the_memoized_graph(identity) -> None:
    # Issue #1611：身份不变时不得每次调用都重建。
    owner = SimpleNamespace(_call_graph=None)
    built: list[str] = []
    first = bound.index_bound_graph(owner, "/p", _builder(built))
    second = bound.index_bound_graph(owner, "/p", _builder(built))
    assert (first, second, built) == ("graph-1", "graph-1", ["graph-1"])


def test_changed_identity_discards_and_rebuilds(identity) -> None:
    # Issue #1611：刷新索引（身份变化）后先通知共享缓存的持有者，再重建。
    owner = SimpleNamespace(_call_graph=None)
    built: list[str] = []
    discarded: list[str] = []
    bound.index_bound_graph(owner, "/p", _builder(built))
    identity[0] = "gen-2"
    graph = bound.index_bound_graph(
        owner, "/p", _builder(built), on_discard=lambda: discarded.append("x")
    )
    assert (graph, discarded) == ("graph-2", ["x"])
    assert owner._graph_index_identity == ("/p", "gen-2")


def test_graph_without_recorded_identity_is_kept(identity) -> None:
    # Issue #1611：未记录身份的注入图（测试替身）无从判定过期，原样保留。
    owner = SimpleNamespace(_call_graph="injected")
    graph = bound.index_bound_graph(owner, "/p", _builder([]))
    assert graph == "injected"


def test_unbound_root_returns_existing_graph_without_identity(identity) -> None:
    # Issue #1611：未绑定项目根时不计算身份，已有图直接返回。
    owner = SimpleNamespace(_call_graph="existing")
    assert bound.index_bound_graph(owner, None, _builder([])) == "existing"


def test_unbound_root_without_graph_delegates_to_build(identity) -> None:
    # Issue #1611：未绑定项目根且无图时交给 build（由它决定报错或返回 None）。
    owner = SimpleNamespace(_call_graph=None)
    built: list[str] = []
    assert bound.index_bound_graph(owner, "", _builder(built)) == "graph-1"


def test_reset_clears_graph_and_identity(identity) -> None:
    # Issue #1611：项目根切换时图与身份一并清空。
    owner = SimpleNamespace(_call_graph=None)
    bound.index_bound_graph(owner, "/p", _builder([]))
    bound.reset_index_bound_graph(owner)
    assert (owner._call_graph, owner._graph_index_identity) == (None, None)
