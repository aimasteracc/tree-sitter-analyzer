"""#1691（第 3 部分）：库文件事实按 stat 证据跨进程复用——构图不再为摘要读全部边。

“新进程”用清空进程内记忆来模拟。每个键成分都做过变异检验。
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat as stat_module
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.cache import index_file_facts as facts

_AN_HOUR_NS = 3600 * 1_000_000_000


def _backdate(path: Path, offset_ns: int = _AN_HOUR_NS) -> None:
    stamp = time.time_ns() - offset_ns
    os.utime(path, ns=(stamp, stamp))


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(facts.DIR_ENV, str(tmp_path / "facts"))
    # 回拨 mtime 也会把变更时间（ctime / NTFS ChangeTime）推到“现在”；竞争窗口
    # 另有专门测试，这里关闭它以便在写入后立即取得证据。
    monkeypatch.setattr(facts, "RACY_WINDOW_NS", 0)


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "index.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t(x)")
    conn.commit()
    conn.close()
    _backdate(path)
    return path


def test_a_recorded_fact_is_found_while_the_evidence_holds(database: Path) -> None:
    stamp = facts.evidence(str(database))
    assert stamp is not None

    facts.record(stamp, "f", [1, 2])

    assert facts.lookup(facts.evidence(str(database)), "f") == [1, 2]


def test_the_fact_name_is_part_of_the_key(database: Path) -> None:
    stamp = facts.evidence(str(database))
    facts.record(stamp, "f", 1)

    assert facts.lookup(stamp, "g") is None


def test_the_code_fingerprint_is_part_of_the_key(database: Path, monkeypatch) -> None:
    import tree_sitter_analyzer.source_fingerprint as fingerprint

    stamp = facts.evidence(str(database))
    facts.record(stamp, "f", 1)
    monkeypatch.setattr(fingerprint, "source_fingerprint", lambda: "other-code")

    assert facts.lookup(stamp, "f") is None


def test_a_stamp_that_no_longer_matches_the_file_is_a_miss(database: Path) -> None:
    stamp = facts.evidence(str(database))
    facts.record(stamp, "f", 1)
    conn = sqlite3.connect(database)
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    # 写入后证据处于竞争窗口（None）或已不同；旧证据不再被接受。
    assert facts.lookup(stamp, "f") is None


def test_a_racy_file_has_no_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(facts, "RACY_WINDOW_NS", 5_000_000_000)
    path = tmp_path / "fresh.db"
    path.write_bytes(b"x")

    assert facts.evidence(str(path)) is None


def test_missing_and_memory_databases_have_no_evidence(tmp_path: Path) -> None:
    assert facts.evidence(None) is None
    assert facts.evidence(":memory:") is None
    assert facts.evidence(str(tmp_path / "absent.db")) is None


def test_a_new_wal_sidecar_changes_the_evidence(database: Path) -> None:
    before = facts.evidence(str(database))
    wal = Path(str(database) + "-wal")
    wal.write_bytes(b"x")
    _backdate(wal)

    after = facts.evidence(str(database))
    assert after != before


def test_a_corrupt_or_foreign_store_is_a_miss(database: Path, tmp_path: Path) -> None:
    stamp = facts.evidence(str(database))
    facts.record(stamp, "f", 1)
    (stored,) = list((tmp_path / "facts").glob("*.json"))
    payload = json.loads(stored.read_text(encoding="utf-8"))
    for changed in ({**payload, "format": facts.FORMAT + 1}, {"format": facts.FORMAT}):
        stored.write_text(json.dumps(changed), encoding="utf-8")
        assert facts.lookup(stamp, "f") is None
    entry_key = next(iter(payload["facts"]))
    tampered = {
        **payload,
        "facts": {entry_key: {"stamp": ["other"], "value": 1}},
    }
    stored.write_text(json.dumps(tampered), encoding="utf-8")
    assert facts.lookup(stamp, "f") is None
    stored.write_text("not json", encoding="utf-8")
    assert facts.lookup(stamp, "f") is None


@pytest.mark.parametrize("env", [(facts.DIR_ENV, "off"), (facts.STORE_ENV, "off")])
def test_the_store_can_be_turned_off(database: Path, monkeypatch, env) -> None:
    monkeypatch.setenv(*env)
    stamp = facts.evidence(str(database))

    facts.record(stamp, "f", 1)

    assert facts.lookup(stamp, "f") is None


def test_the_default_store_is_under_the_user_home(monkeypatch) -> None:
    monkeypatch.delenv(facts.DIR_ENV)
    assert facts.store_dir() == Path.home() / ".tsa" / "cache" / "index-facts"


def test_a_write_failure_is_silent(database: Path, monkeypatch, tmp_path) -> None:
    def refuse(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(facts.os, "replace", refuse)
    stamp = facts.evidence(str(database))

    facts.record(stamp, "f", 1)

    assert facts.lookup(stamp, "f") is None


def test_database_of_reports_the_file_a_connection_reads(database: Path) -> None:
    conn = sqlite3.connect(database)
    try:
        assert os.path.samefile(facts.database_of(conn), database)
    finally:
        conn.close()
    memory = sqlite3.connect(":memory:")
    try:
        assert facts.database_of(memory) is None
    finally:
        memory.close()
    assert facts.database_of(object()) is None


# --------------------------------------------------------------------------- #
# 端到端：冷进程构图不再为摘要读边，图与现场构建逐项相同
# --------------------------------------------------------------------------- #

_SOURCE = (
    "class Widget:\n"
    "    def used(self):\n"
    "        return helper()\n\n\n"
    "def helper():\n"
    "    return 1\n\n\n"
    "def run(w):\n"
    "    return w.used()\n"
)


@pytest.fixture
async def project(tmp_path: Path) -> Path:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    root = tmp_path / "proj"
    root.mkdir()
    (root / "widget.py").write_text(_SOURCE, encoding="utf-8")
    result = await CodeGraphFullIndexTool(str(root)).execute({"mode": "full"})
    assert result["published"] is True
    database = Path(resolve_index_path(str(root)))
    for suffix in ("", "-wal", "-shm"):
        sidecar = Path(str(database) + suffix)
        if sidecar.exists():
            _backdate(sidecar)
    return root


def _new_process() -> None:
    from tree_sitter_analyzer import call_graph_memo
    from tree_sitter_analyzer.cache import call_graph_built_memo

    call_graph_memo.clear()
    call_graph_built_memo.clear()


def _graph(root: Path):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.call_graph import CachedCallGraph

    graph = CachedCallGraph(
        str(root), cache=ASTCache(str(root)), fallback=False, persist=True
    )
    graph.build()
    return graph


def _ref(ref) -> tuple:
    return (ref.file_path, ref.name, ref.start_line, ref.end_line, ref.receiver)


def _shape(graph) -> tuple:
    return (
        sorted(_ref(ref) for ref in graph.function_refs()),
        sorted((_ref(a), _ref(b), line) for a, b, line in graph.all_call_edges()),
        sorted(
            (_ref(callee), sorted(_ref(caller) for caller in callers))
            for callee, callers in graph.callers_map().items()
        ),
    )


@pytest.fixture
def edge_reads(monkeypatch) -> list[int]:
    from tree_sitter_analyzer.cache import graph_input_rows

    calls: list[int] = []
    original = graph_input_rows.read_edge_source

    def counting(cache):
        calls.append(1)
        return original(cache)

    monkeypatch.setattr(graph_input_rows, "read_edge_source", counting)
    return calls


@pytest.mark.asyncio
async def test_a_new_process_builds_the_same_graph_without_reading_edges(
    project: Path, edge_reads: list[int]
) -> None:
    _new_process()
    fresh = _graph(project)
    assert edge_reads == [1]

    _new_process()
    replayed = _graph(project)

    assert edge_reads == [1]
    assert _shape(replayed) == _shape(fresh)
    assert fresh.is_built and replayed.is_built


@pytest.mark.asyncio
async def test_an_index_write_reads_the_edges_again(
    project: Path, edge_reads: list[int]
) -> None:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path

    _new_process()
    _graph(project)
    database = Path(resolve_index_path(str(project)))
    os.chmod(database, stat_module.S_IREAD | stat_module.S_IWRITE)
    conn = sqlite3.connect(database)
    conn.execute("UPDATE ast_index SET indexed_at = indexed_at")
    conn.commit()
    conn.close()

    _new_process()
    _graph(project)

    assert edge_reads == [1, 1]


@pytest.mark.asyncio
async def test_a_missing_edge_store_falls_back_to_a_full_build(
    project: Path, edge_reads: list[int]
) -> None:
    import shutil

    _new_process()
    fresh = _graph(project)
    shutil.rmtree(project / ".ast-cache" / "graph-memo")

    _new_process()
    rebuilt = _graph(project)

    assert edge_reads == [1, 1]
    assert _shape(rebuilt) == _shape(fresh)


@pytest.mark.asyncio
async def test_call_graph_built_is_reused_by_a_new_process(
    project: Path, monkeypatch
) -> None:
    from tree_sitter_analyzer import _ast_cache_graph_mixin as mixin
    from tree_sitter_analyzer.ast_cache import ASTCache

    calls: list[int] = []
    original = mixin._call_graph_built

    def counting(conn):
        calls.append(1)
        return original(conn)

    monkeypatch.setattr(mixin, "_call_graph_built", counting)
    for _ in range(2):
        _new_process()
        cache = ASTCache(str(project))
        try:
            assert cache.call_graph_built() is True
        finally:
            cache.close()

    assert calls == [1]


def test_a_rewrite_with_the_mtime_restored_is_a_miss(database: Path) -> None:
    # 大小、mtime、inode 都不变，只有变更时间（ctime / NTFS ChangeTime）前进。
    stamp = facts.evidence(str(database))
    facts.record(stamp, "f", 1)
    info = os.stat(database)
    data = database.read_bytes()
    time.sleep(0.05)
    with open(database, "r+b") as handle:
        handle.write(data[:1])
    os.utime(database, ns=(info.st_atime_ns, info.st_mtime_ns))
    after = os.stat(database)
    assert (after.st_size, after.st_mtime_ns) == (info.st_size, info.st_mtime_ns)

    assert facts.lookup(facts.evidence(str(database)), "f") is None


def test_an_unstatable_database_has_no_evidence(database: Path, monkeypatch) -> None:
    def refuse(*_args, **_kwargs):
        raise PermissionError

    monkeypatch.setattr(facts.os, "stat", refuse)

    assert facts.evidence(str(database)) is None


def test_an_unknown_change_time_has_no_evidence(database: Path, monkeypatch) -> None:
    import tree_sitter_analyzer.file_change_time as change

    monkeypatch.setattr(change, "change_time_ns", lambda _path, _info: None)

    assert facts.evidence(str(database)) is None


def test_old_database_records_are_pruned(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(facts, "MAX_FILES", 2)
    for index in range(4):
        path = tmp_path / f"db{index}.db"
        path.write_bytes(b"x")
        stamp = facts.evidence(str(path))
        facts.record(stamp, "f", index)
        (record,) = [
            p
            for p in (tmp_path / "facts").glob("*.json")
            if p.stat().st_mtime_ns
            == max(q.stat().st_mtime_ns for q in (tmp_path / "facts").glob("*.json"))
        ]
        old = time.time_ns() - (10 - index) * 1_000_000_000
        os.utime(record, ns=(old, old))

    assert len(list((tmp_path / "facts").glob("*.json"))) == 2


def test_a_record_after_the_store_is_turned_off_is_ignored(
    database: Path, monkeypatch
) -> None:
    stamp = facts.evidence(str(database))
    monkeypatch.setenv(facts.DIR_ENV, "off")

    facts.record(stamp, "f", 1)

    assert facts.lookup(stamp, "f") is None


def test_the_graph_takes_no_evidence_from_a_cache_without_a_connection() -> None:
    from tree_sitter_analyzer.call_graph import _index_file_stamp

    class Broken:
        def get_conn(self):
            raise RuntimeError("closed")

    assert _index_file_stamp(object()) is None
    assert _index_file_stamp(Broken()) is None
