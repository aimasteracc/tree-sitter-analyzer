"""#1696：``cache.backfill_scope`` 的决定、记录与传播分支（最小内存索引，不跑真实刷新）。"""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.cache import backfill_scope as bs
from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry


def _symbols(*symbols: dict) -> str:
    return json.dumps({"symbols": list(symbols), "syntax_error": False})


@pytest.fixture
def conn(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row  # 与 ASTCache 的连接相同
    connection.execute(
        "CREATE TABLE ast_index (file_path TEXT PRIMARY KEY, language TEXT, "
        "symbols_json TEXT, imports_json TEXT)"
    )
    connection.execute(
        "CREATE TABLE edges (id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "source_node_id TEXT, target_node_id TEXT, callee_name TEXT, "
        "callee_resolution TEXT, callee_resolved_file TEXT, callee_symbol_id INTEGER, "
        "metadata TEXT)"
    )
    connection.execute(
        "INSERT INTO ast_index VALUES ('a.py', 'python', ?, '[]')",
        (_symbols({"kind": "class", "name": "A", "line": 1}),),
    )
    connection.execute(
        "INSERT INTO ast_index VALUES ('c.py', 'python', ?, '[]')",
        (_symbols({"kind": "class", "name": "C", "line": 1, "parents": ["A"]}),),
    )
    connection.executemany(
        "INSERT INTO edges VALUES (?, 'calls', ?, '', '', ?, 'resolved', ?, NULL, '{}')",
        [(1, "c.py", "run", "a.py"), (2, "c.py", "other", "z.py")],
    )
    connection.execute(
        "INSERT INTO edges VALUES (3, 'extends', 'd.py', 'd.py:D:1', 'c.py:C:1', 'C', "
        "'', '', NULL, '{}')"
    )
    connection.execute(
        "INSERT INTO edges VALUES (4, 'extends', 'e.py', 'junk', 'class:C', 'C', "
        "'', '', NULL, '{}')"
    )
    from tree_sitter_analyzer.cache import callgraph_state

    monkeypatch.setattr(callgraph_state, "writer_marker_is_current", lambda _c: True)
    yield connection
    connection.close()


def _rewrite_a(conn: sqlite3.Connection, symbols: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO ast_index VALUES ('a.py', 'python', ?, '[]')",
        (symbols,),
    )
    bs.record_file_write(conn, "a.py", [1], [("c.py", "c.py:C:1", "a.py:A:1")])


def test_class_change_reaches_subclasses_and_records_why(conn, monkeypatch) -> None:
    monkeypatch.setattr(bs, "_importer_closure", lambda *_args: set())
    bs.begin(conn)
    _rewrite_a(
        conn, _symbols({"kind": "class", "name": "A", "line": 4, "parents": ["B"]})
    )

    decision = bs.decide(None, conn, 1)

    assert decision.reason == "DEPENDENCIES_BOUNDED"
    # c.py 继承 A（记录下的继承边），d.py 继承 C（传递），基类占位不命中 A。
    assert decision.stats["dependent_files"] == 2
    assert decision.scope is not None
    assert {"a.py", "c.py", "d.py"} <= decision.scope.files
    assert decision.scope.names == {"A"}


def test_body_only_rewrite_restores_name_reset_edges(conn) -> None:
    bs.begin(conn)
    _rewrite_a(conn, _symbols({"kind": "class", "name": "A", "line": 9}))
    conn.execute(
        "UPDATE edges SET callee_resolution = 'unknown', callee_resolved_file = '' "
        "WHERE id = 1"
    )

    decision = bs.decide(None, conn, 1)

    assert decision.stats["surface_changed_files"] == 0
    # 边 1 解析到改动文件，须重新解析：不恢复。
    assert decision.stats["restored_edges"] == 0
    assert decision.scope is not None
    assert decision.scope.edge_ids == {1}


def test_scope_too_large_and_unrecorded_writes_fall_back(conn, monkeypatch) -> None:
    monkeypatch.setattr(bs, "_MIN_EDGES_FOR_FRACTION", 0)
    monkeypatch.setattr(bs, "_MAX_SCOPE_FRACTION", 0.0)
    bs.begin(conn)
    _rewrite_a(conn, _symbols({"kind": "class", "name": "A", "line": 1}))
    assert bs.decide(None, conn, 2).reason == "CHANGED_FILE_NOT_RECORDED"
    assert bs.decide(None, conn, 1).reason == "SCOPE_TOO_LARGE"


def test_scope_computation_failure_falls_back(conn) -> None:
    bs.begin(conn)
    # 类变化需要解析上下文；没有缓存时计算失败，退回全量。
    _rewrite_a(
        conn, _symbols({"kind": "class", "name": "A", "line": 1, "parents": ["X"]})
    )
    assert bs.decide(None, conn, 1).reason == "SCOPE_COMPUTATION_FAILED"


def test_collector_errors_disarm_instead_of_raising(conn) -> None:
    bs.begin(conn)
    conn.execute("DROP TABLE edges")
    bs.record_file_write(conn, "a.py", [1], [])
    assert bs.decide(None, conn, 1).reason == "COLLECTOR_NOT_ARMED"

    closed = sqlite3.connect(":memory:")
    closed.close()
    bs.begin(closed)  # 关闭的连接：武装与撤销都失败，均不抛出。
    assert bs.decide(None, closed, 1).reason == "COLLECTOR_NOT_ARMED"


def test_importer_closure_follows_reexports_modules_and_typed_exports(
    conn, monkeypatch
) -> None:
    def entry(path: str, module: str, local: str, alias_of: str = "") -> ImportEntry:
        return ImportEntry(path, "python", module, local, False, False, alias_of)

    ctx = SimpleNamespace(
        name_to_source={
            "a.py": {"A": "a.py"},  # 自己导入自己：忽略
            "hub.py": {"Alias": "a.py", "Built": "a.py"},
            "far.py": {"Alias": "hub.py"},
            "starred.py": {"A": "a.py"},  # 星号展开：没有对应条目
        },
        import_alias_target={"mod.py": {"am": "a.py"}},
        imports_by_file={
            "a.py": [entry("a.py", "a", "A")],
            "hub.py": [
                entry("hub.py", "a", "Alias", "A"),
                entry("hub.py", "a", "Built"),
            ],
            "far.py": [entry("far.py", "hub", "Alias")],
            "starred.py": [ImportEntry("starred.py", "python", "a", "", False, True)],
            "mod.py": [entry("mod.py", "a", "am", "a")],
        },
    )
    from tree_sitter_analyzer import synapse_resolver

    monkeypatch.setattr(synapse_resolver, "build_resolver_context", lambda _cache: ctx)
    found = bs._importer_closure(None, conn, {"a.py": {"A"}}, {"a.py": {"A"}}, set())
    assert found == {"hub.py", "far.py", "starred.py", "mod.py"}
    # 整文件处理的文件：任何导入都命中。
    wide = bs._importer_closure(None, conn, {"a.py": {"zzz"}}, {}, {"a.py"})
    assert {"hub.py", "starred.py", "mod.py"} <= wide


def test_surface_and_node_helpers_handle_odd_inputs(conn) -> None:
    ruby = bs._surface(("ruby", _symbols(), json.dumps(["require 'x'"])))
    assert "require 'x'" in next(iter(ruby.items["@flags"]))
    assert bs._typed_exports(conn, "missing.py") == set()
    assert bs._node("junk") is None
    assert bs._node("class:Name:1") is None
    assert bs._node("a.py:A:1") == ("a.py", "A")


def test_changed_count_and_sync_result_report_the_scope() -> None:
    from tree_sitter_analyzer.incremental_sync_callgraph import _changed_count
    from tree_sitter_analyzer.incremental_sync_support import SyncResult

    assert _changed_count(None) is None
    assert _changed_count(SyncResult(changed_during_run=1)) is None
    assert _changed_count(SimpleNamespace(new_files=1, updated_files="x")) is None
    assert (
        _changed_count(SyncResult(new_files=1, updated_files=2, deleted_files=3)) == 6
    )
    result = SyncResult()
    assert "backfill_scope" not in result.to_dict()
    result.backfill_scope = {"mode": "full", "reason": "COLLECTOR_NOT_ARMED"}
    assert result.to_dict()["backfill_scope"] == result.backfill_scope


def test_subclass_walk_handles_placeholders_diamonds_and_bad_nodes(conn) -> None:
    conn.executemany(
        "INSERT INTO edges VALUES (?, 'extends', ?, ?, ?, '', '', '', NULL, '{}')",
        [
            (10, "f.py", "f.py:F:1", "class:pkg.A"),  # 占位命中（按末段名）
            (11, "g.py", "g.py:G:1", "junk"),  # 基类节点无法解析
            (12, "d.py", "d.py:D:1", "a.py:A:1"),  # D(C, A)：经两条路到达
            (13, "c.py", "c.py:C:1", "a.py:A:1"),  # C(A)
        ],
    )
    bs.begin(conn)
    files, subclasses = bs._subclass_files(conn, {"A"})
    assert {"f.py", "d.py"} <= files
    assert ("d.py", "D") in subclasses
    assert "g.py" not in files


def test_importer_closure_stops_after_the_hop_limit(conn, monkeypatch) -> None:
    chain = [f"m{index}.py" for index in range(bs._IMPORT_HOPS + 2)]
    ctx = SimpleNamespace(
        name_to_source={
            importer: {"N": target}
            for target, importer in zip(chain, chain[1:], strict=False)
        },
        import_alias_target={},
        imports_by_file={},
    )
    from tree_sitter_analyzer import synapse_resolver

    monkeypatch.setattr(synapse_resolver, "build_resolver_context", lambda _cache: ctx)
    found = bs._importer_closure(None, conn, {chain[0]: {"N"}}, {}, set())
    assert found == set(chain[1 : bs._IMPORT_HOPS + 1])


def test_pipelines_record_full_fallbacks(monkeypatch) -> None:
    from tree_sitter_analyzer import incremental_sync_callgraph as isc
    from tree_sitter_analyzer.cache import indexer

    memory = sqlite3.connect(":memory:")
    cache = SimpleNamespace(get_conn=lambda: memory, _get_conn=lambda: memory)
    monkeypatch.setattr(isc, "_run_stages", lambda _cache, _result: (True, 0))
    assert isc.run_call_graph_pipeline(cache, None) == (True, 0)
    monkeypatch.setattr(indexer, "_post_index_backfill", lambda *_a, **_k: None)
    stats: dict = {"changed_during_run": 1}
    indexer.post_index_backfill(cache, stats)
    assert stats["backfill_scope"] == {
        "mode": "full",
        "reason": "CHANGED_FILES_UNKNOWN",
    }
    memory.close()


def test_forced_rebuild_runs_the_full_backfill(tmp_path) -> None:
    from tree_sitter_analyzer.ast_cache import ASTCache

    (tmp_path / "a.py").write_text(
        "def f():\n    return g()\n\n\ndef g():\n    return 1\n"
    )
    cache = ASTCache(str(tmp_path))
    try:
        stats = cache.index_project(max_files=10, workers=0, force=True)
    finally:
        cache.close()
    assert stats["backfill_scope"]["mode"] == "full"
