"""Persisted "full rebuild in progress" marker (#578).

A ``--full-index --full-index-mode full`` rebuild does ``DELETE FROM ast_index``
+ ``commit`` up front, then re-populates in bounded 500-file batches (the "A4"
RSS guard in ``_commit_index_results``). Because the batched re-insert commits
incrementally over the ~70 s rebuild, a concurrent reader on another connection
(or process) sees the committed-but-empty / half-filled table and returns
``success: true`` with phantom-empty data (``caller_count: 0`` when the real
answer is 50).

The single-big-transaction "atomic swap" cannot be used here — it would revive
the exact OOM that A4's bounded-batch commit was added to prevent. So the fix is
a persisted, cross-connection marker: the rebuild stamps a single sqlite meta
row before the DELETE and clears it after re-population, and readers consult it
to warn instead of trusting the half-built table.

These tests pin the marker contract RED-first.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer import _ast_cache_build_state as bs
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool


def test_build_state_helpers_degrade_on_missing_table() -> None:
    """No ast_build_state table → safe defaults, no raise; mark creates it."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        # Absent table → not building, clear is a no-op, neither raises.
        assert bs.build_in_progress(conn) is False
        bs.clear_build_in_progress(conn)  # must not raise

        # mark creates the table and persists a building row.
        bs.mark_build_in_progress(conn)
        assert bs.build_in_progress(conn) is True

        # clear flips it back off.
        bs.clear_build_in_progress(conn)
        assert bs.build_in_progress(conn) is False
    finally:
        conn.close()


def test_build_state_helpers_degrade_on_readonly_db(tmp_path: Path) -> None:
    """Write failures (read-only DB) must be swallowed — the marker never raises.

    The whole point of the marker is to make reads *safer*; it must never become
    a new failure source. A read-only connection makes every write path
    (CREATE/INSERT in mark, UPDATE in clear) raise OperationalError.
    """
    db = tmp_path / "ro.db"
    sqlite3.connect(str(db)).close()  # materialise an empty db file
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        bs.mark_build_in_progress(conn)  # CREATE/INSERT on RO db → swallowed
        bs.clear_build_in_progress(conn)  # UPDATE on RO db → swallowed
        assert bs.build_in_progress(conn) is False
    finally:
        conn.close()


def test_build_in_progress_false_when_row_absent() -> None:
    """Table present but no id=1 row → not building (don't assume a row)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "CREATE TABLE ast_build_state "
            "(id INTEGER PRIMARY KEY, building INTEGER NOT NULL, "
            "started_at REAL NOT NULL, pid INTEGER NOT NULL)"
        )
        conn.commit()
        assert bs.build_in_progress(conn) is False
    finally:
        conn.close()


def test_build_in_progress_is_stale_after_ttl() -> None:
    """A crashed rebuild that never cleared must not wedge readers forever.

    An in-progress marker older than ``ttl_seconds`` is treated as stale
    (the process that set it died), so readers stop warning and trust the
    cache again.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        bs.mark_build_in_progress(conn)
        assert bs.build_in_progress(conn) is True

        # Backdate the marker far past any plausible rebuild duration.
        conn.execute("UPDATE ast_build_state SET started_at = 1.0 WHERE id = 1")
        conn.commit()

        assert bs.build_in_progress(conn) is False
        # A fresh short TTL also reports stale.
        assert bs.build_in_progress(conn, ttl_seconds=1) is False
    finally:
        conn.close()


def test_build_in_progress_stale_when_rebuilder_pid_is_dead() -> None:
    """Crashed rebuild (pid gone) is stale immediately, before the TTL backstop.

    pid 0 is never a live process, so _pid_alive(0) is False — the row is fresh
    (started_at = now, within TTL) yet still reported not-in-progress.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        bs.mark_build_in_progress(conn)
        assert bs.build_in_progress(conn) is True
        conn.execute("UPDATE ast_build_state SET pid = 0 WHERE id = 1")
        conn.commit()
        assert bs.build_in_progress(conn) is False
    finally:
        conn.close()


def test_pid_alive_branches(monkeypatch) -> None:
    """_pid_alive maps os.kill outcomes correctly: gone→False, EPERM→alive."""
    assert bs._pid_alive(0) is False  # non-positive pid is never alive

    monkeypatch.setattr(bs.os, "kill", lambda *a: None)
    assert bs._pid_alive(4321) is True  # signal 0 succeeded → running

    def _gone(*a):
        raise ProcessLookupError

    monkeypatch.setattr(bs.os, "kill", _gone)
    assert bs._pid_alive(4321) is False  # no such process → crashed

    def _eperm(*a):
        raise PermissionError

    monkeypatch.setattr(bs.os, "kill", _eperm)
    assert bs._pid_alive(4321) is True  # exists, owned by another user


def test_build_in_progress_stale_when_timestamp_is_in_the_future() -> None:
    """A clock that stepped backward (NTP) must not make a marker fresh forever."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        bs.mark_build_in_progress(conn)
        conn.execute(
            "UPDATE ast_build_state SET started_at = ? WHERE id = 1",
            (time.time() + 86_400,),
        )
        conn.commit()
        assert bs.build_in_progress(conn) is False
    finally:
        conn.close()


def _project(root: Path) -> None:
    (root / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "b.py").write_text(
        "from a import f\n\n\ndef g():\n    return f()\n", encoding="utf-8"
    )


def test_full_rebuild_sets_marker_during_empty_window_and_clears_after(
    tmp_path: Path, monkeypatch
) -> None:
    """force=True must mark building across the DELETE→repopulate window.

    The marker is asserted at the moment ``_commit_index_results`` runs — by
    then the up-front ``DELETE FROM ast_index`` has already committed an empty
    table, which is precisely the window a concurrent reader would observe.
    After ``index_project`` returns, the marker is cleared.
    """
    _project(tmp_path)
    cache = ASTCache(str(tmp_path))

    # Warm the cache so a subsequent force=True is a genuine rebuild.
    cache.index_project(max_files=10, workers=0)
    assert bs.build_in_progress(cache.get_conn()) is False

    import tree_sitter_analyzer.ast_cache as ast_cache_mod

    real_commit = ast_cache_mod._commit_index_results
    observed: dict[str, bool] = {}

    def _spy_commit(conn, *args, **kwargs):
        # Mid-rebuild: table was DELETE'd + committed empty, not yet refilled.
        observed["building_mid_rebuild"] = bs.build_in_progress(conn)
        observed["empty_mid_rebuild"] = (
            conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0] == 0
        )
        return real_commit(conn, *args, **kwargs)

    monkeypatch.setattr(ast_cache_mod, "_commit_index_results", _spy_commit)

    cache.index_project(max_files=10, workers=0, force=True)

    assert observed.get("empty_mid_rebuild") is True, "DELETE should empty the table"
    assert observed.get("building_mid_rebuild") is True, (
        "marker must be set during the empty rebuild window"
    )
    # Cleared on the way out.
    assert bs.build_in_progress(cache.get_conn()) is False


def test_marker_cleared_when_delete_phase_raises(tmp_path: Path, monkeypatch) -> None:
    """P2 regression: a failure in the DELETE/commit phase must not leak the marker.

    The MARK+DELETE+commit trio lives inside the try, so if the up-front DELETE
    raises (e.g. SQLITE_FULL), the finally still clears the marker. Otherwise a
    healthy cache would report ``index_rebuilding`` for the whole TTL window.
    """
    _project(tmp_path)
    cache = ASTCache(str(tmp_path))
    cache.index_project(max_files=10, workers=0)

    real_conn = cache.get_conn()

    class _RaiseOnDelete:
        """Proxy that fails the ast_index DELETE but delegates everything else."""

        def execute(self, sql, *args, **kwargs):
            if isinstance(sql, str) and "DELETE FROM ast_index" in sql:
                raise sqlite3.OperationalError("simulated SQLITE_FULL")
            return real_conn.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(real_conn, name)

    monkeypatch.setattr(cache, "_get_conn", lambda: _RaiseOnDelete())

    with pytest.raises(sqlite3.OperationalError):
        cache.index_project(max_files=10, workers=0, force=True)

    # The marker (written via the proxy → real db before the DELETE) must be
    # cleared by the finally, despite the abort. Check on the real connection.
    assert bs.build_in_progress(real_conn) is False


@pytest.mark.asyncio
async def test_status_warns_when_rebuilding_with_partial_index(tmp_path: Path) -> None:
    """A nonempty-but-rebuilding cache → status WARN + index_rebuilding flag.

    The marker is persisted, so the status tool's *separate* connection sees it
    — this is the cross-connection contract that makes phantom-empty reads
    detectable at all.
    """
    _project(tmp_path)
    cache = ASTCache(str(tmp_path))
    cache.index_project(max_files=10, workers=0)
    bs.mark_build_in_progress(cache.get_conn())

    tool = CodeGraphStatusTool(str(tmp_path))
    result = await tool.execute({"output_format": "json", "include_lag": False})

    assert result["index_rebuilding"] is True
    assert result["verdict"] == "WARN"
    assert "rebuild" in result["agent_summary"]["next_step"].lower()


@pytest.mark.asyncio
async def test_status_distinguishes_rebuild_from_missing_index(tmp_path: Path) -> None:
    """Mid-rebuild empty table must NOT read as 'index missing — run index'.

    Returning the generic missing-index hint here would make an agent kick off
    a *second* rebuild on top of the running one.
    """
    _project(tmp_path)
    cache = ASTCache(str(tmp_path))
    cache.index_project(max_files=10, workers=0)
    # Simulate the mid-rebuild empty window: rows gone, marker set.
    conn = cache.get_conn()
    conn.execute("DELETE FROM ast_index")
    conn.commit()
    bs.mark_build_in_progress(conn)

    tool = CodeGraphStatusTool(str(tmp_path))
    result = await tool.execute({"output_format": "json", "include_lag": False})

    assert result["index_rebuilding"] is True
    assert result["verdict"] == "WARN"
    hint = result["agent_summary"]["next_step"].lower()
    assert "rebuild in progress" in hint
    assert "missing or empty" not in hint
