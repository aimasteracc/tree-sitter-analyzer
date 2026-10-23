"""#1723：增量调用图的放弃路径与辅助函数（每条放弃路径都必须退回全量构图）。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import pytest

from tests.unit.test_scoped_backfill_1696 import _sync, _write_tree
from tree_sitter_analyzer import call_graph_incremental as inc
from tree_sitter_analyzer import call_graph_memo, call_graph_warm


@pytest.fixture(autouse=True)
def _clean():
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    auto_index_guard.reset()
    call_graph_memo.clear()
    yield
    call_graph_warm.disable()
    call_graph_memo.clear()
    auto_index_guard.reset()


class _Broken:
    db_path = None

    def get_conn(self):
        raise sqlite3.OperationalError("locked")


def _edges_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE edges (id INTEGER PRIMARY KEY, kind TEXT, callee_name TEXT, "
        "file_path TEXT)"
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, 'calls', ?, ?)",
        [(3, "g", "b.py"), (1, "f", "a.py")],
    )
    return conn


def test_alignment_from_index_reads_only_in_a_long_lived_process() -> None:
    class _Cache:
        def __init__(self) -> None:
            self.conn = _edges_conn()

        def get_conn(self):
            return self.conn

    assert inc.alignment_from_index(_Cache()) is None  # 预构图未启用
    call_graph_warm.enable()
    aligned = inc.alignment_from_index(_Cache())
    assert aligned == inc.Alignment([1, 3], ["f", "g"], ["a.py", "b.py"])
    assert inc.alignment_from_index(_Broken()) is None
    assert inc.alignment_from_index(None) is None


def test_alignment_requires_rowids_in_increasing_order() -> None:
    from tree_sitter_analyzer.cache.graph_input_rows import CallEdgeRows

    names = ("callee_name", "caller_file")
    assert inc.alignment(CallEdgeRows(names, [("f", "a.py")], [1])) == inc.Alignment(
        [1], ["f"], ["a.py"]
    )
    rows = [("f", "a.py"), ("g", "b.py")]
    assert inc.alignment(CallEdgeRows(names, rows, [2, 1])) is None
    assert inc.alignment(CallEdgeRows(names, rows, [])) is None
    assert inc.alignment(None) is None


@dataclass
class _Binder:
    module_to_file: dict = field(default_factory=dict)
    reexports: dict = field(default_factory=dict)
    classes: set = field(default_factory=set)
    bases: dict = field(default_factory=dict)


class _Ref:
    def __init__(self, name: str, receiver: str | None) -> None:
        self.name = name
        self.receiver = receiver


def test_binder_method_names_cover_changed_classes_and_their_ancestors() -> None:
    base = ("a.py", "Base")
    sub = ("b.py", "Sub")
    old = _Binder(classes={base, sub}, bases={sub: [base]})
    new = _Binder(classes={base, sub}, bases={})
    files = {"a.py": [_Ref("shared", "Base")], "b.py": [_Ref("run", "Sub")]}

    assert inc.binder_method_names(old, new, files, files) == frozenset(
        {"shared", "run"}
    )
    assert inc.binder_method_names(old, old, files, files) == frozenset()
    assert inc.binder_method_names(None, None, files, files) == frozenset()
    assert inc.binder_method_names(None, new, files, files) is None
    moved = _Binder(module_to_file={"m": "x.py"})
    assert inc.binder_method_names(new, moved, files, files) is None


def test_changed_classes_include_every_ancestor() -> None:
    old = {"Base": frozenset({"Mid"}), "Mid": frozenset({"Leaf"})}
    new = {"Base": frozenset({"Mid"}), "Mid": frozenset({"Leaf", "Other"})}

    assert inc.changed_classes(old, new) == frozenset({"Mid", "Base"})
    assert inc.changed_classes(old, old) == frozenset()


def test_update_refuses_a_plan_for_another_generation() -> None:
    class _Graph:
        _cache = _Broken()

    plan = inc.RefreshPlan(
        "g1", frozenset({"a.py"}), frozenset({"a.py"}), frozenset(), "OK", "g2"
    )
    previous = {"_incremental": {"generation": "g1"}}

    assert inc.update(_Graph(), previous, plan) == "PLAN_FOR_ANOTHER_GENERATION"  # type: ignore[arg-type]


def test_generation_of_reads_only_the_generation_directory() -> None:
    class _Snapshot:
        source_generation = "idxsrc-v3:gen-7"

    class _Owner:
        snapshot = _Snapshot()

    class _SnapshotCache:
        _owner = _Owner()
        db_path = "/r/.ast-cache/index-generations/generations/abc/index.db"

    class _Published:
        db_path = "/r/.ast-cache/index-generations/generations/abc/index.db"

    class _Loose:
        db_path = "/r/.ast-cache/index.db"

    # #1793：认证快照的 source_generation 不是 generation id，不参与比较。
    assert inc.generation_of(_SnapshotCache()) is None
    assert inc.base_refusal(_SnapshotCache()) == inc.CERTIFIED_SNAPSHOT_NOT_A_BASE
    assert inc.base_refusal(_Published()) is None
    assert inc.generation_of(_Published()) == "abc"
    assert inc.generation_of(_Loose()) is None
    assert inc.generation_of(_Broken()) is None


def _built_project(tmp_path):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.call_graph import CachedCallGraph

    root = tmp_path / "project"
    _write_tree(root)
    _sync(root)
    _sync(root)
    call_graph_warm.enable()
    graph = CachedCallGraph(str(root), cache=ASTCache(str(root)), fallback=False)
    graph.build()
    previous = graph._export_state()
    generation = inc.generation_of(graph._cache)
    plan = inc.RefreshPlan(
        generation,
        frozenset({"pkg/base.py"}),
        frozenset({"pkg/base.py"}),
        frozenset(),
        "DEPENDENCIES_BOUNDED",
        generation or "",
    )
    return root, previous, plan


def _fresh_graph(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.call_graph import CachedCallGraph

    return CachedCallGraph(str(root), cache=ASTCache(str(root)), fallback=False)


@pytest.mark.slow_ok
def test_each_unbounded_input_change_falls_back(tmp_path) -> None:
    root, previous, plan = _built_project(tmp_path)
    memo = previous["_incremental"]

    def run(**changes) -> str | None:
        doctored = {**previous, "_incremental": {**memo, **changes}}
        graph = _fresh_graph(root)
        reason = inc.update(graph, doctored, plan)
        if reason is not None:
            assert (graph._built, graph._incremental, graph._functions) == (
                False,
                None,
                [],
            )
        return reason

    assert run(function_files=frozenset()) == "FUNCTION_FILES_CHANGED"
    assert run(binder=_Binder(module_to_file={"x": "y.py"})) == (
        "REEXPORT_EVIDENCE_CHANGED"
    )
    shorter = inc.Alignment(
        memo["alignment"].ids[1:],
        memo["alignment"].callee_names[1:],
        memo["alignment"].caller_files[1:],
    )
    assert run(alignment=shorter, records=memo["records"][1:]) == "EDGE_COUNT_MISMATCH"
    assert run(alignment=None) == "INCREMENTAL_UPDATE_FAILED"
    # 子类关系变化：调用方属于变化类的行重新解析，结果仍与全新构图相同。
    assert run(children={}) is None


@pytest.mark.slow_ok
def test_finalize_declines_when_it_cannot_confirm_the_digest(tmp_path) -> None:
    root, previous, plan = _built_project(tmp_path)
    graph = _fresh_graph(root)
    assert inc.update(graph, previous, plan) is None
    state = graph._export_state()

    # 状态不是当前记忆：不登记。
    assert inc.finalize(graph, state) is False
    call_graph_memo.store(str(graph.project_root), "k", state)
    graph._incremental = {**graph._incremental, "alignment": inc.Alignment([], [], [])}
    assert inc.finalize(graph, state) is False
    graph._incremental = None
    assert inc.finalize(graph, state) is False

    class _Raising:
        _incremental = {"alignment": inc.Alignment([], [], [])}
        _cache = _Broken()

    assert inc.finalize(_Raising(), state) is False  # type: ignore[arg-type]


def test_read_rows_with_an_empty_scope_still_knows_the_columns() -> None:
    conn = sqlite3.connect(":memory:")
    from tree_sitter_analyzer.graph.edge_store import ensure_edge_schema

    ensure_edge_schema(conn)
    plan = inc.RefreshPlan("g", frozenset(), frozenset(), frozenset(), "OK", "g")

    rows = inc._read_rows(conn, plan, [])

    assert (rows.rows, rows.ids) == ([], [])
    assert "callee_name" in rows.names


def test_memo_extra_keys_follow_the_current_state() -> None:
    state: dict = {}
    call_graph_memo.store("r", "a", state)
    assert call_graph_memo.add_key("r", {}, "b") is False
    assert call_graph_memo.add_key("r", state, "b") is True
    assert call_graph_memo.lookup("r", "b") is state
    for index in range(call_graph_memo._MAX_ROOTS):
        call_graph_memo.store(f"other{index}", "x", {})
    assert call_graph_memo.lookup("r", "b") is None
    assert "r" not in call_graph_memo._EXTRA_KEYS


def test_hierarchy_update_without_files_or_on_a_read_error() -> None:
    from tree_sitter_analyzer.class_mro import Hierarchy, load_hierarchy_update

    base = Hierarchy()

    class _Conn:
        def execute(self, *_args):
            raise sqlite3.OperationalError("no such table")

    assert load_hierarchy_update(_Conn(), base, []) is base  # type: ignore[arg-type]
    assert load_hierarchy_update(_Conn(), base, ["a.py"]) == Hierarchy()  # type: ignore[arg-type]


@pytest.mark.slow_ok
def test_warm_job_falls_back_to_a_full_build_when_allowed(tmp_path) -> None:
    root, _previous, plan = _built_project(tmp_path)
    call_graph_memo.clear()  # 没有上一张图：增量放弃

    explicit = call_graph_warm._build(str(root), call_graph_warm._Job(plan, False))
    watcher = call_graph_warm._build(str(root), call_graph_warm._Job(plan, True))

    assert explicit["incremental"]["reason"] == "NO_PREVIOUS_GRAPH"
    assert explicit["warmed"] is False
    assert (watcher["incremental"]["applied"], watcher["warmed"]) == (False, True)
