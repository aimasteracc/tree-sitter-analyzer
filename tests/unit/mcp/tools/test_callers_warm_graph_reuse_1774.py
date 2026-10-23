"""#1774：warm ``nav callers`` 每次查询至多构图一次，且同一认证快照上复用已建的图。

* 一次查询只取一次调用图：裸名的唯一方法改写（#1759）与 SQL 路径的并集（#1740）
  共用同一张图，认证快照上不再构图两次。
* 同一不可变认证快照上的后续查询不再读出全部调用边重算输入摘要。
* 编辑并刷新后，下一次查询看到改动（新快照、新输入摘要），绝不沿用旧图。
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import call_graph as call_graph_module
from tree_sitter_analyzer import call_graph_memo, call_graph_snapshot_inputs
from tree_sitter_analyzer.cache import graph_input_rows
from tree_sitter_analyzer.index_snapshot_query import CertifiedSnapshotCache
from tree_sitter_analyzer.mcp.tools import certification_timeouts
from tree_sitter_analyzer.mcp.tools.callers_tool import (
    CodeGraphCallersTool,
    _QueryGraph,
)

_AN_HOUR_NS = 3600 * 1_000_000_000

_WIDGET = (
    "class Widget:\n"
    "    def used(self):\n"
    "        return 1\n\n\n"
    "def run(w: Widget):\n"
    "    return w.used()\n"
)
_HELPER = "def helper():\n    return 3\n\n\ndef top():\n    return helper()\n"
_SECOND_CALLER = "\n\ndef again():\n    return helper()\n"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(certification_timeouts.DIR_ENV, str(tmp_path / "timeouts"))
    certification_timeouts.clear()
    call_graph_memo.clear()
    call_graph_snapshot_inputs.clear()
    yield
    certification_timeouts.clear()
    call_graph_memo.clear()
    call_graph_snapshot_inputs.clear()


def _backdate(root: Path) -> None:
    stamp = time.time_ns() - _AN_HOUR_NS
    for path in [*root.rglob("*.py"), root / "pkg", root]:
        os.utime(path, ns=(stamp, stamp))


async def _index(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    result = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert result["published"] is True


@pytest.fixture
async def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "widget.py").write_text(_WIDGET, encoding="utf-8")
    (root / "pkg" / "helper.py").write_text(_HELPER, encoding="utf-8")
    _backdate(root)
    await _index(root)
    return root


class _Spy:
    """Count graph builds and full edge reads, and remember which caches built."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.builds: list[Any] = []
        self.edge_reads = 0
        build = call_graph_module.CachedCallGraph._build_from_cache
        read = graph_input_rows.read_edge_source

        def counting_build(graph: Any) -> None:
            self.builds.append(graph._cache)
            build(graph)

        def counting_read(cache: Any) -> Any:
            self.edge_reads += 1
            return read(cache)

        monkeypatch.setattr(
            call_graph_module.CachedCallGraph, "_build_from_cache", counting_build
        )
        monkeypatch.setattr(graph_input_rows, "read_edge_source", counting_read)

    def reset(self) -> None:
        self.builds.clear()
        self.edge_reads = 0

    @property
    def certified(self) -> bool:
        return bool(self.builds) and all(
            isinstance(cache, CertifiedSnapshotCache) for cache in self.builds
        )


def _args(name: str, file_path: str) -> dict[str, Any]:
    return {"function_name": name, "file_path": file_path, "include_bodies": False}


def _answer(result: dict[str, Any]) -> tuple[Any, ...]:
    return (
        result.get("function"),
        result.get("completeness"),
        tuple(result.get("completeness_reasons") or ()),
        tuple(
            (c.get("name"), c.get("file"), c.get("line"))
            for c in result.get("callers") or ()
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name, file_path",
    [
        ("used", "widget.py"),  # bare, one method: rewritten to Widget.used (#1759)
        ("Widget.used", "widget.py"),  # qualified
        ("helper", "pkg/helper.py"),  # bare module function: SQL path + union
    ],
)
async def test_one_graph_build_per_query_and_reuse_across_warm_queries(
    project: Path, monkeypatch: pytest.MonkeyPatch, name: str, file_path: str
) -> None:
    spy = _Spy(monkeypatch)
    tool = CodeGraphCallersTool(str(project))

    first = await tool.execute(_args(name, file_path))
    assert spy.certified, "the query must take the certified snapshot path"
    assert len(spy.builds) == 1  # one graph per query, never two
    assert spy.edge_reads == 1

    spy.reset()
    warm = await tool.execute(_args(name, file_path))
    assert len(spy.builds) == 1
    # Same immutable snapshot: the build adopts the remembered graph without
    # reading every call edge again to recompute the input digest.
    assert spy.edge_reads == 0
    assert warm == first


@pytest.mark.asyncio
async def test_reuse_does_not_change_the_answer_of_a_fresh_process(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = CodeGraphCallersTool(str(project))
    queries = [("used", "widget.py"), ("Widget.used", "widget.py")]
    queries += [("helper", "pkg/helper.py"), ("top", "pkg/helper.py")]
    warm = [await tool.execute(_args(*q)) for q in queries]
    warm_again = [await tool.execute(_args(*q)) for q in queries]

    cold = []
    for query in queries:
        call_graph_memo.clear()
        call_graph_snapshot_inputs.clear()
        cold.append(await CodeGraphCallersTool(str(project)).execute(_args(*query)))

    assert warm == warm_again == cold


@pytest.mark.asyncio
async def test_an_edit_and_refresh_is_seen_by_the_next_warm_query(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _Spy(monkeypatch)
    tool = CodeGraphCallersTool(str(project))
    before = await tool.execute(_args("helper", "pkg/helper.py"))
    await tool.execute(_args("helper", "pkg/helper.py"))
    assert spy.certified
    assert {c["name"] for c in before["callers"]} == {"top"}

    helper = project / "pkg" / "helper.py"
    helper.write_text(_HELPER + _SECOND_CALLER, encoding="utf-8")
    _backdate(project)
    await _index(project)

    spy.reset()
    after = await tool.execute(_args("helper", "pkg/helper.py"))
    assert spy.certified
    assert spy.edge_reads == 1  # new snapshot: inputs re-read, never the old graph
    assert {c["name"] for c in after["callers"]} == {"top", "again"}
    assert after["caller_count"] == 2

    # And the refreshed answer equals a cold process on the refreshed index.
    call_graph_memo.clear()
    call_graph_snapshot_inputs.clear()
    cold = await CodeGraphCallersTool(str(project)).execute(
        _args("helper", "pkg/helper.py")
    )
    assert _answer(after) == _answer(cold)


# --------------------------------------------------------------------------- #
# Units
# --------------------------------------------------------------------------- #


def test_query_graph_builds_once_and_does_not_remember_a_failure() -> None:
    calls: list[int] = []

    def factory() -> tuple[Any, str]:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("unreadable")
        return object(), "cache"

    shared = _QueryGraph(factory)
    with pytest.raises(RuntimeError):
        shared.get()
    graph = shared.get()
    assert shared.get() is graph
    assert len(calls) == 2


class _Identified:
    def __init__(self, identity: Any) -> None:
        self._identity = identity

    def graph_input_identity(self) -> Any:
        if isinstance(self._identity, Exception):
            raise self._identity
        return self._identity


@pytest.mark.parametrize(
    "cache",
    [
        object(),  # live cache: no snapshot identity
        _Identified(None),
        _Identified(()),
        _Identified(("certified-snapshot", "")),
        _Identified(("certified-snapshot", None)),
        _Identified(RuntimeError("INDEX_SNAPSHOT_CLOSED")),
    ],
)
def test_snapshot_key_requires_a_complete_identity(cache: Any) -> None:
    assert call_graph_snapshot_inputs.snapshot_key(cache) is None


def test_snapshot_digests_are_bounded_and_keyed_exactly() -> None:
    key = ("certified-snapshot", "/r", "idxsnap_a", "fp", "gen")
    other = ("certified-snapshot", "/r", "idxsnap_b", "fp", "gen")
    call_graph_snapshot_inputs.remember(key, "d1")
    call_graph_snapshot_inputs.remember(None, "ignored")
    call_graph_snapshot_inputs.remember(other, None)
    assert call_graph_snapshot_inputs.digest_for(key) == "d1"
    assert call_graph_snapshot_inputs.digest_for(other) is None
    assert call_graph_snapshot_inputs.digest_for(None) is None
    for index in range(call_graph_snapshot_inputs._MAX_SNAPSHOTS):
        call_graph_snapshot_inputs.remember(("k", str(index)), "d")
    assert call_graph_snapshot_inputs.digest_for(key) is None


def test_a_remembered_digest_without_a_memo_state_falls_back_to_reading(
    tmp_path: Path,
) -> None:
    graph = call_graph_module.CachedCallGraph(str(tmp_path), cache=None)
    key = ("certified-snapshot", "/r", "idxsnap_a", "fp", "gen")
    call_graph_snapshot_inputs.remember(key, "digest-without-state")
    assert graph._adopt_snapshot_graph(key) is False
    assert graph._adopt_snapshot_graph(None) is False


class _Owner:
    def __init__(self, conn: sqlite3.Connection, built: bool) -> None:
        from tree_sitter_analyzer.index_snapshot_registry import IndexSnapshot

        self.connection = conn
        self.deadline = time.monotonic() + 60
        self.snapshot = IndexSnapshot(
            "idxsnap_test" + str(built),
            "src",
            "idx",
            "gen",
            "complete",
            None,
            "/root",
            0,
        )

    def require_active(self) -> None:
        return None


def test_call_graph_built_remembers_only_a_positive_verdict(monkeypatch) -> None:
    from tree_sitter_analyzer import index_snapshot_query

    verdicts = iter([False, True])
    calls: list[int] = []

    def fake_built(_conn: Any, **_kwargs: Any) -> bool:
        calls.append(1)
        return next(verdicts)

    monkeypatch.setattr(index_snapshot_query, "_call_graph_built", fake_built)
    monkeypatch.setattr(
        index_snapshot_query,
        "_BUILT_SNAPSHOTS",
        type(index_snapshot_query._BUILT_SNAPSHOTS)(),
    )
    conn = sqlite3.connect(":memory:")
    cache = CertifiedSnapshotCache(_Owner(conn, True))
    assert cache.call_graph_built() is False  # e.g. a deadline: not remembered
    assert cache.call_graph_built() is True
    assert cache.call_graph_built() is True
    assert len(calls) == 2
