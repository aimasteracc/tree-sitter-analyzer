"""#1657：按构图输入的内容摘要复用内存调用图。

复用只能以证明输入未变的证据为键：同内容的新 generation 必须命中，任何一类
构图输入（调用边、函数定义、import、包再导出、类定义、继承边）改变都必须未命中，
且未命中后重建的图与清空记忆后的全新构建完全相同。
"""

from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import call_graph_memo
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cached_reexport_binding import PackageReexportBinder
from tree_sitter_analyzer.call_graph import CachedCallGraph

_SOURCES = {
    "widget.py": (
        "class Widget:\n"
        "    def unused(self):\n"
        "        return 0\n\n"
        "    def used(self):\n"
        "        return 1\n\n\n"
        # #1669：接收者须被证明（这里经注解）才是确定调用方。
        "def run(w: Widget):\n"
        "    return w.used()\n"
    ),
    "base.py": (
        "class Base:\n"
        "    def run(self):\n"
        "        return self.hook()\n\n"
        "    def hook(self):\n"
        "        return 0\n"
    ),
    "sub.py": (
        "from base import Base\n\n\n"
        "class Sub(Base):\n"
        "    def hook(self):\n"
        "        return 1\n"
    ),
    "pkg/__init__.py": "from .impl import Impl\n",
    "pkg/impl.py": ("class Impl:\n    def go(self):\n        return 2\n"),
    "main.py": (
        "from pkg import Impl\n"
        "from widget import run\n\n\n"
        "def start():\n"
        "    impl = Impl()\n"
        "    impl.go()\n"
        "    return run(None)\n"
    ),
    # RFC-0038：参数注解把接收者绑定到 Widget（annotated_receiver 边）。
    "annotated.py": (
        "from widget import Widget\n\n\n"
        "def poke(w: Widget) -> int:\n"
        "    return w.unused()\n"
    ),
}


@pytest.fixture(autouse=True)
def _clean_memo():
    call_graph_memo.clear()
    yield
    call_graph_memo.clear()


def _write_sources(root: Path) -> None:
    for rel, text in _SOURCES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _index(root: Path, *, force: bool = False) -> None:
    cache = ASTCache(str(root))
    try:
        cache.index_project(force=force)
    finally:
        cache.close()


@pytest.fixture
def indexed(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    _write_sources(root)
    _index(root)
    return root


def _database(root: Path) -> Path:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path

    return Path(resolve_index_path(str(root)))


def _generation(root: Path) -> Any:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    return getattr(resolve_index_location(str(root)).selector, "generation_id", None)


def _write_index(root: Path, statement: str) -> None:
    """在已发布（封存为只读）的索引上执行一条写语句。"""
    database = _database(root)
    os.chmod(database, stat.S_IREAD | stat.S_IWRITE)
    conn = sqlite3.connect(database)
    try:
        changed = conn.execute(statement).rowcount
        conn.commit()
    finally:
        conn.close()
    if not changed:
        # 前提失效（夹具里没有被改写的行）时，下面的“未命中”断言什么也证明不了。
        pytest.fail(f"mutation changed no rows: {statement}")


def _write_index_script(root: Path, statement: str) -> None:
    """执行一条不返回行数的语句（DDL）。"""
    database = _database(root)
    os.chmod(database, stat.S_IREAD | stat.S_IWRITE)
    conn = sqlite3.connect(database)
    try:
        conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


class _Conn:
    """只提供 ``get_conn`` 的只读连接（直接读已发布的库，不经 ASTCache 迁移）。"""

    def __init__(self, root: Path) -> None:
        self._path = _database(root)

    def get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path.absolute().as_uri() + "?mode=ro", uri=True)


def _built(root: Path) -> CachedCallGraph:
    cache = ASTCache(str(root))
    graph = CachedCallGraph(str(root), cache=cache, fallback=False)
    graph.build()
    graph.close()
    return graph


def _fresh(root: Path) -> CachedCallGraph:
    """清空记忆后的全新构建（未加记忆时的计算）。"""
    call_graph_memo.clear()
    return _built(root)


def _view(graph: CachedCallGraph) -> dict[str, Any]:
    """图对外可观察的全部内容：每个函数的调用方 / 被调方 / 可能调用方与边列表。"""
    per_function = {}
    for ref in graph.function_refs():
        key = f"{ref.qualified_name()}:{ref.start_line}"
        per_function[key] = (
            [c.to_dict() for c in graph.caller_refs_of(ref)],
            [c.to_dict() for c in graph.callee_refs_of(ref)],
            [c.to_dict() for c in graph.possible_caller_refs_of(ref)],
            [c.to_dict() for c in graph.reachable_callee_refs_of(ref)],
        )
    edges = [(a.to_dict(), b.to_dict(), line) for a, b, line in graph.call_edges()]
    return {
        "functions": [ref.to_dict() for ref in graph.function_refs()],
        "per_function": per_function,
        "edges": edges,
        "by_name": {
            name: [r.to_dict() for r in refs]
            for name, refs in graph._func_by_name.items()
        },
    }


def _shares_state(a: CachedCallGraph, b: CachedCallGraph) -> bool:
    return a._callers is b._callers and a._possible_callers is b._possible_callers


# --------------------------------------------------------------------------- #
# 命中：内容相同
# --------------------------------------------------------------------------- #


def test_identical_content_reuses_the_built_graph(indexed: Path) -> None:
    first = _built(indexed)
    second = _built(indexed)

    assert _shares_state(first, second)
    assert _view(second) == _view(_fresh(indexed))


def test_reused_graph_answers_exactly_like_a_fresh_build(indexed: Path) -> None:
    first = _built(indexed)
    reused = _built(indexed)
    fresh = _fresh(indexed)

    assert not _shares_state(first, fresh)
    assert _view(reused) == _view(fresh)
    for name in ("Widget.used", "hook", "Base.hook", "Sub.hook", "go", "run"):
        assert reused.callers_of(name) == fresh.callers_of(name), name
        assert reused.possible_callers_of(name) == fresh.possible_callers_of(name)


def test_noop_refresh_with_a_new_generation_reuses_the_graph(indexed: Path) -> None:
    # #1657：无变化的强制刷新发布新 generation；generation 不是证据，内容才是。
    before = _generation(indexed)
    first = _built(indexed)

    _index(indexed, force=True)

    assert _generation(indexed) != before
    second = _built(indexed)
    assert _shares_state(first, second)
    assert _view(second) == _view(_fresh(indexed))


# --------------------------------------------------------------------------- #
# 未命中：任何一类构图输入变化
# --------------------------------------------------------------------------- #

_MUTATIONS = {
    "call_edge_resolution": (
        "UPDATE edges SET callee_resolved_file = 'elsewhere.py' "
        "WHERE kind = 'calls' AND callee_name = 'used'"
    ),
    "call_edge_line": (
        "UPDATE edges SET callee_line = callee_line + 100 WHERE kind = 'calls'"
    ),
    "function_definition": (
        "UPDATE ast_index SET symbols_json = "
        "replace(symbols_json, '\"unused\"', '\"renamed\"') "
        "WHERE file_path = 'widget.py'"
    ),
    "imports": "UPDATE ast_index SET imports_json = '[]' WHERE file_path = 'main.py'",
    "package_reexport": (
        "UPDATE ast_imports SET alias_of = 'Other' WHERE file_path = 'pkg/__init__.py'"
    ),
    "class_definition": (
        "UPDATE ast_symbol_rows SET name = 'Gone' "
        "WHERE kind = 'class' AND name = 'Impl'"
    ),
    "extends_edge": "DELETE FROM edges WHERE kind = 'extends'",
    # RFC-0038：只改注解绑定的来源（metadata.receiver_binding），其余列不变。
    "receiver_binding": (
        "UPDATE edges SET metadata = "
        "json_set(metadata, '$.receiver_binding.owner', 'Gone') "
        "WHERE kind = 'calls' AND callee_resolution = 'annotated_receiver'"
    ),
}


@pytest.mark.parametrize("mutation", sorted(_MUTATIONS))
def test_changed_input_rebuilds_exactly_like_a_fresh_build(
    indexed: Path, mutation: str
) -> None:
    first = _built(indexed)

    _write_index(indexed, _MUTATIONS[mutation])
    second = _built(indexed)

    assert not _shares_state(first, second)
    assert _view(second) == _view(_fresh(indexed))


def test_extends_change_is_evidence_even_without_binding_evidence(
    indexed: Path,
) -> None:
    # 包再导出证据读不到（旧索引缺 ast_imports）时，子类索引仍读取 extends 边；
    # 继承关系的变化必须单独使记忆失效。
    _write_index_script(indexed, "DROP TABLE ast_imports")
    first = _built(indexed)
    assert PackageReexportBinder(_Conn(indexed)).evidence() is None

    _write_index(indexed, "DELETE FROM edges WHERE kind = 'extends'")
    second = _built(indexed)

    assert not _shares_state(first, second)
    assert _view(second) == _view(_fresh(indexed))


def test_edit_and_refresh_rebuilds_with_the_new_answer(indexed: Path) -> None:
    first = _built(indexed)
    assert [c["name"] for c in first.callers_of("Widget.unused")] == ["poke"]

    (indexed / "caller.py").write_text(
        "from widget import Widget\n\n\ndef go_unused():\n    Widget().unused()\n",
        encoding="utf-8",
    )
    _index(indexed)
    second = _built(indexed)

    assert not _shares_state(first, second)
    assert _view(second) == _view(_fresh(indexed))


def test_deleted_file_and_refresh_rebuilds(indexed: Path) -> None:
    first = _built(indexed)

    (indexed / "sub.py").unlink()
    _index(indexed)
    second = _built(indexed)

    assert not _shares_state(first, second)
    assert "Sub" not in {r.receiver for r in second.function_refs()}
    assert _view(second) == _view(_fresh(indexed))


# --------------------------------------------------------------------------- #
# 摘要与存取
# --------------------------------------------------------------------------- #


def test_digest_is_order_sensitive_and_part_delimited() -> None:
    a, b = {"x": 1}, {"x": 2}
    assert call_graph_memo.input_digest([a, b]) != call_graph_memo.input_digest([b, a])
    assert call_graph_memo.input_digest([a], [b]) != call_graph_memo.input_digest(
        [a, b]
    )
    assert call_graph_memo.input_digest([1]) != call_graph_memo.input_digest([True])
    assert call_graph_memo.input_digest([a, b]) == call_graph_memo.input_digest(
        [{"x": 1}, {"x": 2}]
    )


def test_unserializable_input_has_no_digest() -> None:
    assert call_graph_memo.input_digest([lambda: None]) is None


def test_memo_keys_on_the_digest_and_keeps_one_graph_per_root() -> None:
    call_graph_memo.store("/p", "d1", {"g": 1})
    assert call_graph_memo.lookup("/p", "d1") == {"g": 1}
    assert call_graph_memo.lookup("/p", "d2") is None
    assert call_graph_memo.lookup("/q", "d1") is None

    call_graph_memo.store("/p", "d2", {"g": 2})
    assert call_graph_memo.lookup("/p", "d1") is None
    assert call_graph_memo.lookup("/p", "d2") == {"g": 2}


def test_memo_is_bounded_by_root_count() -> None:
    for index in range(call_graph_memo._MAX_ROOTS + 2):
        call_graph_memo.store(f"/r{index}", "d", {"g": index})
    assert call_graph_memo.lookup("/r0", "d") is None
    assert call_graph_memo.lookup(f"/r{call_graph_memo._MAX_ROOTS + 1}", "d") == {
        "g": call_graph_memo._MAX_ROOTS + 1
    }
    assert len(call_graph_memo._MEMO) == call_graph_memo._MAX_ROOTS


def test_unserializable_rows_build_normally_without_memo(indexed: Path) -> None:
    class _OddCache:
        # 不提供原始行读取：构图退回 get_call_edges，其中含不可序列化的值。
        get_call_edge_rows = None

        def __init__(self, inner: ASTCache) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

        def get_call_edges(self) -> list[dict[str, Any]]:
            return [
                {**row, "odd": lambda: None} for row in self._inner.get_call_edges()
            ]

    inner = ASTCache(str(indexed))
    graph = CachedCallGraph(str(indexed), cache=_OddCache(inner), fallback=False)
    graph.build()
    inner.close()

    assert call_graph_memo._MEMO == {}
    assert _view(graph) == _view(_fresh(indexed))


def test_resolver_memos_do_not_change_the_built_graph(
    indexed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #1657：构图内的解析记忆（静态目标、全局兜底）只省重复计算，不改变任何边。
    from tree_sitter_analyzer import call_graph

    memoized = _fresh(indexed)
    original = call_graph.CachedEdgeResolver

    class _Plain(original):  # type: ignore[misc, valid-type]
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**{**kwargs, "memoize": False})

    monkeypatch.setattr(call_graph, "CachedEdgeResolver", _Plain)
    plain = _fresh(indexed)

    assert not _shares_state(memoized, plain)
    assert _view(plain) == _view(memoized)


def _without_timing(response: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in response.items() if "elapsed" not in key}


@pytest.mark.asyncio
async def test_callers_after_noop_refresh_reuse_the_graph_and_answer_identically(
    indexed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #1657：刷新发布新 generation 后，身份绑定照旧丢弃旧图对象；新对象从记忆
    # 采用内容相同的状态而不重新解析，答案与清空记忆后的计算完全相同。
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    builds: list[str] = []
    original = CachedCallGraph._build_from_inputs

    def counting(self: CachedCallGraph, *args: Any, **kwargs: Any) -> None:
        builds.append(str(self.project_root))
        original(self, *args, **kwargs)

    monkeypatch.setattr(CachedCallGraph, "_build_from_inputs", counting)
    query = {"function_name": "Widget.used", "include_bodies": False}
    tool = CodeGraphCallersTool(str(indexed))
    before = await tool.execute(dict(query))
    assert len(builds) == 1

    _index(indexed, force=True)
    after = await tool.execute(dict(query))
    assert len(builds) == 1

    call_graph_memo.clear()
    fresh = await CodeGraphCallersTool(str(indexed)).execute(dict(query))
    assert len(builds) == 2
    assert [c["name"] for c in after["callers"]] == ["run"]
    assert _without_timing(after) == _without_timing(fresh)
    assert _without_timing(after) == _without_timing(before)


def test_discard_releases_only_that_root() -> None:
    call_graph_memo.store("/p", "d", {"g": 1})
    call_graph_memo.store("/q", "d", {"g": 2})
    call_graph_memo.discard("/p")
    assert call_graph_memo.lookup("/p", "d") is None
    assert call_graph_memo.lookup("/q", "d") == {"g": 2}


def test_changed_input_releases_the_old_state_before_rebuilding(
    indexed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #1657：输入变化时旧状态先被释放，构图期间不同时持有两张图。
    _built(indexed)
    _write_index(indexed, _MUTATIONS["call_edge_line"])
    seen: list[int] = []
    original = CachedCallGraph._build_from_inputs

    def spy(self: CachedCallGraph, *args: Any, **kwargs: Any) -> None:
        seen.append(len(call_graph_memo._MEMO))
        original(self, *args, **kwargs)

    monkeypatch.setattr(CachedCallGraph, "_build_from_inputs", spy)
    _built(indexed)

    assert seen == [0]
    assert len(call_graph_memo._MEMO) == 1


def test_chunked_digest_of_large_lists_is_exact() -> None:
    # 大列表分块摘要：内容相同则相同；跨块边界交换、截断、拆成两部分都不同。
    size = call_graph_memo._CHUNK_ROWS * 2 + 5
    rows = [(index, f"f{index}.py") for index in range(size)]
    boundary = call_graph_memo._CHUNK_ROWS
    swapped = list(rows)
    swapped[boundary - 1], swapped[boundary] = swapped[boundary], swapped[boundary - 1]
    digest = call_graph_memo.input_digest(rows)

    assert digest == call_graph_memo.input_digest([tuple(row) for row in rows])
    assert digest != call_graph_memo.input_digest(swapped)
    assert digest != call_graph_memo.input_digest(rows[:-1])
    assert digest != call_graph_memo.input_digest(rows[:boundary], rows[boundary:])
    assert digest != call_graph_memo.input_digest(rows + [(size, "x")])


def test_build_pauses_cyclic_gc_and_restores_it(
    indexed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #1657：构图期间暂停循环 GC；结束（含异常）后恢复进入时的状态。
    import gc

    states: list[bool] = []
    original = CachedCallGraph._build_from_inputs

    def spy(self: CachedCallGraph, *args: Any, **kwargs: Any) -> None:
        states.append(gc.isenabled())
        original(self, *args, **kwargs)

    monkeypatch.setattr(CachedCallGraph, "_build_from_inputs", spy)
    assert gc.isenabled()
    _built(indexed)
    assert (states, gc.isenabled()) == ([False], True)

    def boom(self: CachedCallGraph, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(CachedCallGraph, "_build_from_inputs", boom)
    call_graph_memo.clear()
    with pytest.raises(RuntimeError):
        _built(indexed)
    assert gc.isenabled()

    gc.disable()
    try:
        monkeypatch.setattr(CachedCallGraph, "_build_from_inputs", original)
        call_graph_memo.clear()
        _built(indexed)
        assert not gc.isenabled()  # 进入时已关闭：不擅自开启。
    finally:
        gc.enable()


def test_build_releases_its_resolution_memos(indexed: Path) -> None:
    # #1657：构图内记忆只服务一次构建；保留下来的解析器不再记忆、也不持有列表。
    graph = _fresh(indexed)
    resolver = graph._callee_resolver
    assert resolver is not None
    assert resolver._global_memo is None
    assert [c["name"] for c in graph.callers_of("Widget.used")] == ["run"]
