"""RFC-0032 follow-up (#1664 item 4): commits SQLite makes on its own are fenced.

Two kinds of commit bypassed ``FencedConnection.commit()`` and so never checked or
advanced the ``ast_writer_state`` revision (schema 18):

* releasing the outermost ``SAVEPOINT`` when no transaction was open (used by the
  projection repair in ``index_symbol_migration``, the call-graph marker
  certification and the activation flush);
* ``executescript``, which first commits any pending transaction and then runs
  its statements in autocommit mode.

A writer that had already lost the race could therefore publish through one of
these paths. Each interleaving below is deterministic: the loser binds its
operation, the winner then commits, and only after that does the loser write.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.admission import (
    INDEX_CANDIDATE_SUPERSEDED,
    Superseded,
    admission_failure_of,
)
from tree_sitter_analyzer.cache.callgraph_state import mark_call_graph_built_strict
from tree_sitter_analyzer.cache.writer_state import (
    REVISION_SUPERSEDED,
    writer_operation,
)
from tree_sitter_analyzer.incremental_sync import IncrementalSync

_A = "def alpha():\n    return 1\n"
_A_CHANGED = "def alpha():\n    return 2\n"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text(_A, encoding="utf-8")
    db = tmp_path / "custom" / "index.db"
    cache = ASTCache(str(root), str(db))
    try:
        _sync(cache)
    finally:
        cache.close()
    return root, db


def _sync(cache: ASTCache):
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    return IncrementalSync(cache).sync(
        max_files=scope.certification_max_files,
        exclude_patterns=scope.effective_excludes,
        source_scope=scope,
    )


def _dump(db: Path) -> tuple[str, ...]:
    connection = sqlite3.connect(db)
    try:
        return tuple(connection.iterdump())
    finally:
        connection.close()


def _revision(db: Path) -> int:
    connection = sqlite3.connect(db)
    try:
        return int(
            connection.execute("SELECT revision FROM ast_writer_state").fetchone()[0]
        )
    finally:
        connection.close()


def _assert_no_writer_holds_lock(db: Path) -> None:
    connection = sqlite3.connect(db, timeout=0)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.rollback()
    finally:
        connection.close()


def _savepoint_delete(conn: sqlite3.Connection) -> None:
    conn.execute("SAVEPOINT loser_write")
    conn.execute("DELETE FROM ast_index")
    conn.execute("RELEASE loser_write")


def _script_delete(conn: sqlite3.Connection) -> None:
    conn.executescript("DELETE FROM ast_index;")


def _pending_then_script(conn: sqlite3.Connection) -> None:
    # executescript's own implicit COMMIT of the pending DELETE, then DDL.
    conn.execute("DELETE FROM ast_index")
    conn.executescript("CREATE TABLE IF NOT EXISTS loser_probe (x INTEGER);")


def _marker_certification(conn: sqlite3.Connection) -> None:
    # A real production writer whose only commit is the outermost RELEASE.
    mark_call_graph_built_strict(conn)


@pytest.mark.parametrize(
    "implicit_write",
    [_savepoint_delete, _script_delete, _pending_then_script, _marker_certification],
    ids=["outer-savepoint", "executescript", "pending-then-script", "graph-marker"],
)
def test_loser_committing_only_implicitly_does_not_publish(project, implicit_write):
    root, db = project
    loser = ASTCache(str(root), str(db))
    winner = ASTCache(str(root), str(db))
    try:
        with pytest.raises(Superseded) as raised:
            with writer_operation(loser):
                (root / "a.py").write_text(_A_CHANGED, encoding="utf-8")
                _sync(winner)  # the winner commits after the loser bound its revision
                winner_dump = _dump(db)
                implicit_write(loser.get_conn())
        assert loser.get_conn().in_transaction is False
    finally:
        winner.close()
        loser.close()
    failure = admission_failure_of(raised.value)
    assert failure is not None
    assert (failure.code, failure.cause_code) == (
        INDEX_CANDIDATE_SUPERSEDED,
        REVISION_SUPERSEDED,
    )
    assert _dump(db) == winner_dump
    _assert_no_writer_holds_lock(db)


def test_outer_savepoint_commit_advances_the_revision(project):
    # Outside an operation the implicit commit still goes through the CAS, so a
    # candidate bound before it is superseded (no ABA through the implicit path).
    root, db = project
    cache = ASTCache(str(root), str(db))
    try:
        bound = cache.writer_revision()
        conn = cache.get_conn()
        conn.execute("SAVEPOINT outer_write")
        conn.execute("SAVEPOINT inner_write")
        conn.execute("DELETE FROM ast_symbol_activation")
        conn.execute("RELEASE inner_write")
        assert conn.in_transaction is True  # inner release never commits
        conn.execute("RELEASE SAVEPOINT outer_write")
        assert conn.in_transaction is False
        assert cache.writer_revision().revision == bound.revision + 1
    finally:
        cache.close()


def test_executescript_rows_advance_the_revision(project):
    root, db = project
    cache = ASTCache(str(root), str(db))
    try:
        before = _revision(db)
        cache.get_conn().executescript(
            "CREATE TABLE IF NOT EXISTS probe (x INTEGER); INSERT INTO probe VALUES (1);"
        )
        assert cache.get_conn().in_transaction is False
    finally:
        cache.close()
    assert _revision(db) == before + 1


def test_read_only_and_rolled_back_savepoints_do_not_advance_the_revision(project):
    # Pulse reads and the FTS integrity check end in RELEASE without publishing
    # anything: they must not take the write lock or supersede bound candidates.
    root, db = project
    cache = ASTCache(str(root), str(db))
    try:
        before = _revision(db)
        conn = cache.get_conn()
        conn.execute("SAVEPOINT read_only")
        conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()
        conn.execute("RELEASE SAVEPOINT read_only")
        conn.execute("SAVEPOINT undone")
        conn.execute("DELETE FROM ast_index")
        conn.execute("ROLLBACK TO undone")
        conn.execute("RELEASE undone")
        cache.get_conn().executescript("CREATE TABLE IF NOT EXISTS probe (x INTEGER);")
        assert conn.in_transaction is False
        files = [r[0] for r in conn.execute("SELECT file_path FROM ast_index")]
    finally:
        cache.close()
    assert files == ["a.py"]
    assert _revision(db) == before


def test_commit_inside_an_auto_opened_savepoint_still_ends_the_transaction(project):
    # The activation flush commits from inside its savepoint; that must keep
    # working and must not leave stale savepoint bookkeeping behind.
    root, db = project
    cache = ASTCache(str(root), str(db))
    try:
        before = _revision(db)
        conn = cache.get_conn()
        conn.execute("SAVEPOINT flush")
        conn.execute("DELETE FROM ast_symbol_activation")
        conn.commit()
        assert conn.in_transaction is False
        conn.execute("SAVEPOINT again")
        conn.execute("DELETE FROM ast_symbol_activation")
        conn.execute("RELEASE again")
        assert conn.in_transaction is False
    finally:
        cache.close()
    assert _revision(db) == before + 2
