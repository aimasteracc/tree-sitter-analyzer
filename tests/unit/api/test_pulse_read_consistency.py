"""#1546：test_pulse 只读一致性与认证读取行为组；从 test_pulse.py 原样迁移，测试主体不变。"""

from __future__ import annotations

import pytest

from tests.unit.api._pulse_helpers import _seed_symbol
from tree_sitter_analyzer.api.pulse import query_pulse


@pytest.mark.parametrize("boundary", ["identity", "imports"])
@pytest.mark.parametrize("outer_transaction", [False, True])
def test_pulse_wal_reindex_keeps_one_read_version(
    tmp_path, boundary, outer_transaction
):
    """PR #1352 P2：另一真实 WAL 连接重索引换 ID 后，整次只读 Pulse 必须保持同一版本。"""
    import sqlite3

    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    importer = tmp_path / "consumer.py"
    source.write_text(
        'def target():\n    """old doc"""\n    # old comment\n    old_helper()\n\ndef old_helper():\n    pass\n',
        encoding="utf-8",
    )
    importer.write_text(
        "import sample\n" if boundary == "identity" else "import elsewhere\n",
        encoding="utf-8",
    )
    writer = ASTCache(str(tmp_path))
    writer.index_file(str(source))
    writer.index_file(str(importer))
    db = writer.get_conn()
    old_id = db.execute(
        "SELECT id FROM ast_symbol_rows WHERE name='target'"
    ).fetchone()[0]
    reader = sqlite3.connect(
        f"file:{writer.db_path}?mode=ro", uri=True, isolation_level=None
    )
    assert reader.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    reader.execute("PRAGMA query_only=ON")
    if outer_transaction:
        reader.execute("BEGIN")
    switched = []
    failures = []

    def reindex_between_reads(sql):
        marker = (
            "SELECT json_type(symbols_json"
            if boundary == "identity"
            else "SELECT file_path FROM ast_index WHERE language='python'"
        )
        if switched or not sql.lstrip().startswith(marker):
            return
        switched.append(True)
        try:
            source.write_text(
                'def target():\n    """new doc"""\n    # new comment\n    new_helper()\n\ndef new_helper():\n    pass\n',
                encoding="utf-8",
            )
            importer.write_text(
                "import elsewhere\n" if boundary == "identity" else "import sample\n",
                encoding="utf-8",
            )
            writer.index_file(str(source))
            writer.index_file(str(importer))
        except Exception as exc:
            failures.append(exc)

    reader.set_trace_callback(reindex_between_reads)
    try:
        result = query_pulse(reader, "sample.py", "target")
        assert switched == [True]
        assert failures == []
        assert (
            db.execute("SELECT id FROM ast_symbol_rows WHERE name='target'").fetchone()[
                0
            ]
            != old_id
        )
        assert result is not None
        assert result.symbol.docstring == "old doc"
        assert [c.name for c in result.callees] == ["old_helper"]
        assert [c.text for c in result.comments] == ["old comment"]
        assert result.imported_by == (
            ("consumer.py",) if boundary == "identity" else ()
        )
        assert reader.in_transaction is outer_transaction
        assert reader.total_changes == 0
        current = query_pulse(db, "sample.py", "target")
        assert current.symbol.docstring == "new doc"
        assert current.imported_by == (
            () if boundary == "identity" else ("consumer.py",)
        )
    finally:
        reader.close()
        writer.close()


@pytest.mark.parametrize("failure", [False, True])
def test_pulse_does_not_commit_or_rollback_caller_write_transaction(
    ast_cache_conn, failure
):
    """PR #1352 P2：Pulse 成功或报错均不得提交/回滚调用者已有写事务。"""
    _seed_symbol(ast_cache_conn, "target", "a.py")
    ast_cache_conn.execute("CREATE TABLE caller_state(value TEXT)")
    ast_cache_conn.commit()
    ast_cache_conn.execute("BEGIN")
    ast_cache_conn.execute("INSERT INTO caller_state VALUES ('pending')")
    if failure:
        ast_cache_conn.execute("DROP TABLE ast_symbol_activation")
        import sqlite3

        with pytest.raises(sqlite3.OperationalError, match="ast_symbol_activation"):
            query_pulse(ast_cache_conn, "a.py", "target", max_comments=0)
    else:
        assert (
            query_pulse(ast_cache_conn, "a.py", "target", max_comments=0).symbol.name
            == "target"
        )
    assert ast_cache_conn.in_transaction is True
    assert (
        ast_cache_conn.execute("SELECT value FROM caller_state").fetchone()[0]
        == "pending"
    )
    ast_cache_conn.rollback()
    assert ast_cache_conn.execute("SELECT * FROM caller_state").fetchall() == []


def test_target_removed_between_identity_and_context_returns_missing(ast_cache_conn):
    """PR #1352：连接上并发删除已识别目标后，不能从其他同名目标拼出上下文。"""
    _seed_symbol(ast_cache_conn, "vanish", "a.py")

    def delete_before_context(sql):
        if sql.lstrip().startswith("WITH"):
            ast_cache_conn.execute("DELETE FROM ast_symbol_rows WHERE name='vanish'")

    ast_cache_conn.set_trace_callback(delete_before_context)
    try:
        assert query_pulse(ast_cache_conn, "a.py", "vanish", max_comments=0) is None
    finally:
        ast_cache_conn.set_trace_callback(None)


def test_certified_pulse_missing_index_is_read_only(tmp_path):
    # 2026-09-08：查询不能创建空索引后把无索引误报成不存在。
    from tree_sitter_analyzer.api.pulse_evidence import (
        PulseSourceError,
        certified_pulse_connection,
    )

    with pytest.raises(PulseSourceError) as error:
        with certified_pulse_connection(str(tmp_path)):
            pytest.fail("缺失索引不能发布读取连接")
    assert (error.value.reason, error.value.freshness) == ("MISSING_INDEX", "missing")
    assert list(tmp_path.iterdir()) == []
