"""#1684：全量索引在负载高的机器上不再整份丢弃、无界重试。

* 其余一切干净、只有认证盖戳因期限中断（``SOURCE_SCAN_DEADLINE`` 等）时，索引
  如实发布为未认证（``completeness: incomplete``、``verdict: WARN``）；随后一次
  刷新即可认证并复用它。内容不一致的盖戳失败仍不发布。
* ``ensure_indexed`` 的自动预热在上次预热未使调用图标记当前后退避，而不是
  每次查询都重建一份完整版本。
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

_DEADLINE = (
    "SOURCE_CHANGED:state=unknown:reason=SOURCE_SCAN_DEADLINE:"
    "rows_current=0:rows_recorded=2"
)


@pytest.fixture
def project(tmp_path):
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    (tmp_path / "a.py").write_text(
        "from b import beta\n\n\ndef alpha():\n    return beta()\n", encoding="utf-8"
    )
    (tmp_path / "b.py").write_text("def beta():\n    return 1\n", encoding="utf-8")
    auto_index_guard.reset()
    yield tmp_path
    auto_index_guard.reset()


def _full(root):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    return asyncio.run(CodeGraphFullIndexTool(str(root)).execute({"mode": "full"}))


def _manifests(root) -> int:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    location = resolve_index_location(str(root))
    if not location.published:
        return -1
    conn = sqlite3.connect(location.path.as_uri() + "?mode=ro", uri=True)
    try:
        return int(
            conn.execute("SELECT COUNT(*) FROM ast_index_snapshot_manifest").fetchone()[
                0
            ]
        )
    finally:
        conn.close()


def _refuse_stamp(monkeypatch, message):
    from tree_sitter_analyzer import index_snapshot_schema

    original = index_snapshot_schema.stamp_full_index_manifest

    def refuse(*_args, **_kwargs):
        raise sqlite3.OperationalError(message)

    monkeypatch.setattr(index_snapshot_schema, "stamp_full_index_manifest", refuse)
    return original


def test_certification_deadline_publishes_an_uncertified_index(project, monkeypatch):
    from tree_sitter_analyzer import index_snapshot_schema
    from tree_sitter_analyzer.ast_cache import ASTCache

    original = _refuse_stamp(monkeypatch, _DEADLINE)
    result = _full(project)
    monkeypatch.setattr(index_snapshot_schema, "stamp_full_index_manifest", original)

    assert (
        result["published"],
        result["success"],
        result["completeness"],
        result["verdict"],
        result["manifest_warning"],
        _manifests(project),
    ) == (True, True, "incomplete", "WARN", "INDEX_CERTIFICATION_DEADLINE", 0)
    assert "index action=cache mode=index" in result["agent_summary"]["next_step"]

    # 之后一次刷新即认证（发布带清单的版本）。
    cache = ASTCache(str(project))
    try:
        refreshed = cache.index_project(workers=0)
    finally:
        cache.close()
    assert (refreshed["published"], _manifests(project)) == (True, 1)


def test_an_inconsistent_stamp_still_publishes_nothing(project, monkeypatch):
    _refuse_stamp(monkeypatch, "SOURCE_CHANGED:state=exact:reason=None:rows_current=3")
    result = _full(project)

    assert (result["published"], result["success"], _manifests(project)) == (
        False,
        False,
        -1,
    )


def test_certification_timed_out_classifies_only_deadlines() -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_outcome import (
        certification_timed_out,
    )

    assert (
        certification_timed_out(sqlite3.OperationalError(_DEADLINE)),
        certification_timed_out(RuntimeError("INDEX_FINGERPRINT_DEADLINE")),
        certification_timed_out(TimeoutError()),
        certification_timed_out(sqlite3.OperationalError("CALL_GRAPH_INCOMPLETE")),
        certification_timed_out(RuntimeError("INDEX_FINGERPRINT_BUDGET")),
    ) == (True, True, True, False, False)


def test_auto_warm_backs_off_after_a_non_converging_warm(project, monkeypatch):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    cache = ASTCache(str(project))
    try:
        cache.index_project(workers=0)
    finally:
        cache.close()
    warms: list[str] = []
    original = ASTCache.index_project

    def counted(self, *args, **kwargs):
        warms.append("warm")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ASTCache, "index_project", counted)
    monkeypatch.setattr(
        auto_index_guard, "_call_graph_marker_is_current", lambda _cache: False
    )

    def ensure():
        opened = auto_index_guard.ensure_indexed(str(project))
        if opened is not None:
            opened.close()

    ensure()
    ensure()
    first = list(warms)
    auto_index_guard.mark_dirty(str(project))
    ensure()

    assert (first, warms) == (["warm"], ["warm", "warm"])


def _consistent_graph(tmp_path):
    from tree_sitter_analyzer.ast_cache import ASTCache

    database = tmp_path / "custom" / "index.db"
    database.parent.mkdir()
    cache = ASTCache(str(tmp_path), str(database))
    cache.index_project(workers=0)
    return cache


def test_a_slow_consistency_check_is_not_reported_as_dangling(project, monkeypatch):
    # 根因（本仓库在负载下实测）：悬空解析核验沿用读者的 5 秒期限，两条遍历全部
    # 调用边的查询被中断后返回 False，一致的图被报告为
    # CALL_GRAPH_DANGLING_RESOLUTION，整份全量索引不发布。写入方用自己的期限。
    from tree_sitter_analyzer.cache import callgraph_state

    cache = _consistent_graph(project)
    try:
        monkeypatch.setattr(callgraph_state, "_CALL_GRAPH_MARKER_DEADLINE_SECONDS", 0.0)
        conn = cache._get_conn()
        callgraph_state.clear_call_graph_built_strict(conn)
        callgraph_state.mark_call_graph_built_strict(conn)
        built = callgraph_state.writer_marker_is_current(conn)
    finally:
        cache.close()

    assert built is True


def test_real_dangling_resolution_is_still_rejected(project) -> None:
    from tree_sitter_analyzer.cache import callgraph_state

    cache = _consistent_graph(project)
    try:
        conn = cache._get_conn()
        conn.execute(
            "UPDATE edges SET callee_resolved_file = 'gone.py' WHERE kind = 'calls'"
        )
        conn.commit()
        with pytest.raises(sqlite3.OperationalError) as caught:
            callgraph_state.mark_call_graph_built_strict(conn)
    finally:
        cache.close()

    assert str(caught.value) == "CALL_GRAPH_DANGLING_RESOLUTION"


def test_a_check_that_runs_out_of_writer_time_is_named(project, monkeypatch) -> None:
    from tree_sitter_analyzer.cache import callgraph_state

    cache = _consistent_graph(project)
    try:
        monkeypatch.setattr(callgraph_state, "_WRITER_CHECK_DEADLINE_SECONDS", -1.0)
        with pytest.raises(sqlite3.OperationalError) as caught:
            callgraph_state.mark_call_graph_built_strict(cache._get_conn())
    finally:
        cache.close()

    assert str(caught.value) == "CALL_GRAPH_CHECK_DEADLINE"
