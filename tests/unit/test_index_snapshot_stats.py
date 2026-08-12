"""Tests for CodeGraph Status tool — index health at-a-glance."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
    CodeGraphStatusTool,
)

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


@pytest.fixture
def tool():
    return CodeGraphStatusTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphStatusTool(str(tmp_path))


def _certified_cache(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

    source = root / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(root))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(root))
    cache.close()


def test_status_rejects_non_read_existing_access_mode(tmp_path):
    with pytest.raises(ValueError, match="read_existing"):
        CodeGraphStatusTool(str(tmp_path)).validate_arguments({"access_mode": "write"})


@requires_posix_fd
@pytest.mark.asyncio
async def test_manifest_type_confusion_maps_to_stable_unknown(tmp_path):
    # PR #1253 review thread 1262: MCP never coerces hostile SQLite scalars.
    _certified_cache(tmp_path)
    conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
    conn.execute("UPDATE ast_index_snapshot_manifest SET file_count = 'not-an-integer'")
    conn.commit()
    conn.close()

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "unknown",
        "INDEX_MANIFEST_INVALID",
    )


def test_snapshot_stats_uses_ordinary_symbol_rows_without_fts(monkeypatch):
    # PR #1253 review threads 3755591655/59: ordinary rows are independent of FTS.
    import tree_sitter_analyzer.index_snapshot as owner
    import tree_sitter_analyzer.index_snapshot_stats as stats_owner
    import tree_sitter_analyzer.index_snapshot_symbols as symbols_owner

    conn = sqlite3.connect(":memory:")
    monkeypatch.setattr(
        stats_owner, "sqlite_compile_supports_fts5", lambda _conn: False
    )
    conn.execute(
        "CREATE TABLE ast_index(file_path TEXT, symbols_json TEXT, language TEXT, "
        "content_hash TEXT)"
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('sample.py', 'not-json', 'python', 'hash')"
    )
    conn.execute(
        "CREATE TABLE ast_symbol_rows(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, "
        "language TEXT, file_path TEXT, line INTEGER, end_line INTEGER)"
    )
    conn.executemany(
        "INSERT INTO ast_symbol_rows VALUES (?, ?, ?, ?, ?, 0, 0)",
        (
            (1, "Thing", "class", "python", "sample.py"),
            (2, "run", "function", "python", "sample.py"),
        ),
    )
    from tree_sitter_analyzer.index_symbol_projection import symbol_rows_digest

    digest = symbol_rows_digest(
        conn.execute(
            "SELECT id, name, kind, file_path, language, line, end_line "
            "FROM ast_symbol_rows ORDER BY id"
        )
    )
    conn.execute(
        "CREATE TABLE ast_symbol_projection_state("
        "file_path TEXT, content_hash TEXT, symbol_count INTEGER, "
        "projection_digest TEXT)"
    )
    conn.execute(
        "INSERT INTO ast_symbol_projection_state VALUES ('sample.py', 'hash', 2, ?)",
        (digest,),
    )
    conn.execute("CREATE TABLE ast_cache_metadata(key TEXT, value TEXT)")
    conn.execute(
        "INSERT INTO ast_cache_metadata VALUES "
        "('symbol_rows_projection_v1', 'complete')"
    )
    conn.execute("CREATE TABLE edges(kind TEXT)")
    monkeypatch.setattr(
        owner,
        "run_graph_snapshot_read",
        lambda _snapshot, _root, _generation, reader: reader(conn),
    )
    monkeypatch.setattr(
        symbols_owner.json,
        "loads",
        lambda _raw: (_ for _ in ()).throw(AssertionError("unexpected JSON fallback")),
    )

    result = owner.read_snapshot_stats("snapshot", "/project", "generation")

    assert result["fts5_available"] is False
    assert result["total_symbols"] == 2
    assert result["symbols_by_kind"] == {"class": 1, "function": 1}
    assert result["symbols_by_language"] == {"python": 2}
    conn.close()


def test_snapshot_stats_rejects_too_many_ordinary_groups():
    # PR #1253 review thread 3755842993: GROUP BY output has an absolute row cap.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols_owner

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_symbol_rows(kind TEXT, language TEXT)")
    conn.executemany(
        "INSERT INTO ast_symbol_rows VALUES (?, 'python')",
        ((f"kind-{index}",) for index in range(4097)),
    )

    with pytest.raises(RuntimeError, match="^SNAPSHOT_READ_FAILED$"):
        symbols_owner.ordinary_symbol_counts(conn)
    assert conn.execute("SELECT 1").fetchone() == (1,)
    conn.close()


def test_snapshot_stats_rejects_oversized_ordinary_cell():
    # PR #1253 review thread 3755842993: oversized group keys never enter output.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols_owner

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_symbol_rows(kind TEXT, language TEXT)")
    conn.execute(
        "INSERT INTO ast_symbol_rows VALUES (?, 'python')",
        ("x" * (1024 * 1024 + 1),),
    )

    with pytest.raises(RuntimeError, match="^SNAPSHOT_READ_FAILED$"):
        symbols_owner.ordinary_symbol_counts(conn)
    conn.close()


def test_snapshot_stats_ordinary_deadline_clears_progress_handler(monkeypatch):
    # PR #1253 review thread 3755842993: interrupted reads fail closed and clean up.
    import tree_sitter_analyzer.index_snapshot_symbols as symbols_owner

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_symbol_rows(kind TEXT, language TEXT)")
    conn.execute("INSERT INTO ast_symbol_rows VALUES ('function', 'python')")
    monkeypatch.setattr(symbols_owner, "_ORDINARY_DEADLINE_SECONDS", -1.0)

    with pytest.raises(RuntimeError, match="^SNAPSHOT_READ_FAILED$"):
        symbols_owner.ordinary_symbol_counts(conn)
    assert conn.execute("SELECT 1").fetchone() == (1,)
    conn.close()


def test_snapshot_stats_malformed_ordinary_rows_use_legacy_json(monkeypatch):
    # PR #1253 review thread 3755591659: incomplete projections fall back safely.
    import tree_sitter_analyzer.index_snapshot as owner

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index(file_path TEXT, symbols_json TEXT, language TEXT)"
    )
    conn.execute(
        "INSERT INTO ast_index VALUES (?, ?, ?)",
        (
            "sample.py",
            '{"symbols":[{"kind":"function"},{"kind":"class"}]}',
            "python",
        ),
    )
    conn.execute("CREATE TABLE ast_symbol_rows(name TEXT, kind TEXT, file_path TEXT)")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    monkeypatch.setattr(
        owner,
        "run_graph_snapshot_read",
        lambda _snapshot, _root, _generation, reader: reader(conn),
    )

    result = owner.read_snapshot_stats("snapshot", "/project", "generation")

    assert (result["total_symbols"], result["symbols_by_kind"]) == (
        2,
        {"class": 1, "function": 1},
    )
    conn.close()


def test_symbol_fallback_rejects_oversized_json_before_parsing(monkeypatch):
    # PR #1253 review thread 3755591659: preflight prevents huge json.loads calls.
    import tree_sitter_analyzer.index_snapshot as owner
    import tree_sitter_analyzer.index_snapshot_symbols as symbols_owner

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index(file_path TEXT, symbols_json TEXT, language TEXT)"
    )
    conn.execute(
        "INSERT INTO ast_index VALUES "
        "('huge.py', CAST(zeroblob(1048577) AS TEXT), 'python')"
    )
    monkeypatch.setattr(
        symbols_owner.json,
        "loads",
        lambda _raw: (_ for _ in ()).throw(AssertionError("oversized JSON parsed")),
    )

    with pytest.raises(RuntimeError, match="INDEX_SYMBOL_FALLBACK_BUDGET"):
        owner._fallback_symbol_counts(conn)
    conn.close()


def test_symbol_fallback_rejects_null_json_cell():
    # PR #1253 review thread 3755591659: NULL legacy cells fail closed.
    import tree_sitter_analyzer.index_snapshot as owner

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index(file_path TEXT, symbols_json TEXT, language TEXT)"
    )
    conn.execute("INSERT INTO ast_index VALUES ('bad.py', NULL, 'python')")

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        owner._fallback_symbol_counts(conn)
    conn.close()


def test_symbol_fallback_rejects_non_text_json_cell():
    # PR #1253 review thread 3755591659: typed legacy cells fail closed.
    import tree_sitter_analyzer.index_snapshot as owner

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index(file_path TEXT, symbols_json INTEGER, language TEXT)"
    )
    conn.execute("INSERT INTO ast_index VALUES ('bad.py', 123, 'python')")

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        owner._fallback_symbol_counts(conn)
    conn.close()


def test_symbol_fallback_deadline_interrupts_sql(monkeypatch):
    # PR #1253 review thread 3755591659: SQL progress enforces the deadline.
    import tree_sitter_analyzer.index_snapshot as owner
    import tree_sitter_analyzer.index_snapshot_symbols as symbols_owner

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index(file_path TEXT, symbols_json TEXT, language TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, '{}', 'python')",
        ((f"file-{index}.py",) for index in range(2_000)),
    )
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        return 0.0 if calls == 1 else 10.0

    monkeypatch.setattr(symbols_owner.time, "monotonic", clock)
    monkeypatch.setattr(symbols_owner, "_FALLBACK_DEADLINE_SECONDS", 5.0)

    with pytest.raises(RuntimeError, match="INDEX_SYMBOL_FALLBACK_BUDGET"):
        owner._fallback_symbol_counts(conn)
    conn.close()


def test_symbol_fallback_preserves_non_deadline_sql_errors():
    # PR #1253 review thread 3755591659: malformed schemas retain stable SQL errors.
    import tree_sitter_analyzer.index_snapshot as owner

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path TEXT)")

    with pytest.raises(sqlite3.OperationalError, match="symbols_json"):
        owner._fallback_symbol_counts(conn)
    conn.close()


def _minimal_stats_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path TEXT)")
    return conn


def test_snapshot_stats_default_deadline_allows_bounded_collection(monkeypatch):
    import tree_sitter_analyzer.index_snapshot_stats as stats_owner

    conn = _minimal_stats_connection()
    monkeypatch.setattr(stats_owner.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(stats_owner, "has_ordinary_symbol_projection", lambda *_: False)
    monkeypatch.setattr(
        stats_owner, "fallback_symbol_counts", lambda *_args, **_kwargs: (0, {}, {})
    )
    monkeypatch.setattr(
        stats_owner, "ordinary_edge_counts", lambda *_args, **_kwargs: (0, {})
    )

    result = stats_owner.collect_snapshot_stats(conn)

    assert (result["total_files"], result["total_symbols"], result["total_edges"]) == (
        0,
        0,
        0,
    )
    conn.close()


def test_snapshot_stats_rejects_already_expired_deadline() -> None:
    from tree_sitter_analyzer.index_snapshot_stats import collect_snapshot_stats

    conn = _minimal_stats_connection()
    with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_DEADLINE"):
        collect_snapshot_stats(conn, deadline=0.0)
    conn.close()


def test_snapshot_stats_rechecks_deadline_after_aggregate_queries(monkeypatch):
    import tree_sitter_analyzer.index_snapshot_stats as stats_owner

    conn = _minimal_stats_connection()
    ticks = [0.0]
    monkeypatch.setattr(
        stats_owner.time, "monotonic", lambda: ticks.pop() if ticks else 2.0
    )
    monkeypatch.setattr(stats_owner, "has_ordinary_symbol_projection", lambda *_: False)
    monkeypatch.setattr(
        stats_owner, "fallback_symbol_counts", lambda *_args, **_kwargs: (0, {}, {})
    )
    monkeypatch.setattr(
        stats_owner, "ordinary_edge_counts", lambda *_args, **_kwargs: (0, {})
    )

    with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_DEADLINE"):
        stats_owner.collect_snapshot_stats(conn, deadline=1.0)
    conn.close()


def test_snapshot_stats_reinstalls_handler_for_each_final_query(monkeypatch):
    # PR #1253 Codex review 3764611254: edge aggregation clears the handler.
    import tree_sitter_analyzer.index_snapshot_stats as stats_owner

    native = _minimal_stats_connection()

    class TrackingConnection:
        def __init__(self):
            self.handler_active = False
            self.final_queries: list[tuple[str, bool]] = []

        def set_progress_handler(self, handler, steps):
            self.handler_active = handler is not None
            native.set_progress_handler(handler, steps)

        def execute(self, query, parameters=()):
            if query in {"SELECT COUNT(*) FROM ast_index", "PRAGMA auto_vacuum"}:
                self.final_queries.append((query, self.handler_active))
            return native.execute(query, parameters)

    conn = TrackingConnection()
    monkeypatch.setattr(stats_owner.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(stats_owner, "sqlite_compile_supports_fts5", lambda *_: False)
    monkeypatch.setattr(stats_owner, "has_ordinary_symbol_projection", lambda *_: False)
    monkeypatch.setattr(
        stats_owner, "fallback_symbol_counts", lambda *_args, **_kwargs: (0, {}, {})
    )

    def edge_counts(connection, **_kwargs):
        connection.set_progress_handler(None, 0)
        return 0, {}

    monkeypatch.setattr(stats_owner, "ordinary_edge_counts", edge_counts)

    result = stats_owner.collect_snapshot_stats(conn, deadline=10.0)  # type: ignore[arg-type]

    assert (result["total_files"], result["db_auto_vacuum_mode"]) == (0, 0)
    assert conn.final_queries == [
        ("SELECT COUNT(*) FROM ast_index", True),
        ("PRAGMA auto_vacuum", True),
    ]
    assert conn.handler_active is False
    native.close()


def test_snapshot_stats_rejects_final_count_finishing_after_deadline(monkeypatch):
    # PR #1253 Codex review 3764611254: a completed final query cannot escape timeout.
    import tree_sitter_analyzer.index_snapshot_stats as stats_owner

    native = _minimal_stats_connection()
    now = [0.0]

    class DeadlineConnection:
        def __init__(self):
            self.handler_active = False
            self.final_queries: list[str] = []

        def set_progress_handler(self, handler, steps):
            self.handler_active = handler is not None
            native.set_progress_handler(handler, steps)

        def execute(self, query, parameters=()):
            cursor = native.execute(query, parameters)
            if query in {"SELECT COUNT(*) FROM ast_index", "PRAGMA auto_vacuum"}:
                self.final_queries.append(query)
            if query == "SELECT COUNT(*) FROM ast_index":
                now[0] = 2.0
            return cursor

    conn = DeadlineConnection()
    monkeypatch.setattr(stats_owner.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(stats_owner, "sqlite_compile_supports_fts5", lambda *_: False)
    monkeypatch.setattr(stats_owner, "has_ordinary_symbol_projection", lambda *_: False)
    monkeypatch.setattr(
        stats_owner, "fallback_symbol_counts", lambda *_args, **_kwargs: (0, {}, {})
    )

    def edge_counts(connection, **_kwargs):
        connection.set_progress_handler(None, 0)
        return 0, {}

    monkeypatch.setattr(stats_owner, "ordinary_edge_counts", edge_counts)

    with pytest.raises(RuntimeError, match="^INDEX_SNAPSHOT_DEADLINE$"):
        stats_owner.collect_snapshot_stats(conn, deadline=1.0)  # type: ignore[arg-type]
    assert conn.final_queries == ["SELECT COUNT(*) FROM ast_index"]
    assert conn.handler_active is False
    native.close()


def test_snapshot_stats_normalizes_sql_interrupt_to_deadline(monkeypatch):
    import tree_sitter_analyzer.index_snapshot_stats as stats_owner

    class InterruptedConnection:
        def __init__(self):
            self.handler = None
            self.cleared = False

        def set_progress_handler(self, handler, _steps):
            self.handler = handler
            if handler is None:
                self.cleared = True

        def execute(self, _query):
            assert self.handler is not None
            assert self.handler() == 1
            raise sqlite3.DatabaseError("interrupted")

    ticks = [0.0]
    monkeypatch.setattr(
        stats_owner.time, "monotonic", lambda: ticks.pop() if ticks else 2.0
    )
    conn = InterruptedConnection()

    with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_DEADLINE"):
        stats_owner.collect_snapshot_stats(conn, deadline=1.0)  # type: ignore[arg-type]
    assert conn.cleared is True


def test_snapshot_stats_preserves_non_deadline_database_error(monkeypatch):
    import tree_sitter_analyzer.index_snapshot_stats as stats_owner

    class CorruptConnection:
        def __init__(self):
            self.cleared = False

        def set_progress_handler(self, handler, _steps):
            if handler is None:
                self.cleared = True

        def execute(self, _query):
            raise sqlite3.DatabaseError("malformed database")

    monkeypatch.setattr(stats_owner.time, "monotonic", lambda: 0.0)
    conn = CorruptConnection()

    with pytest.raises(sqlite3.DatabaseError, match="malformed database"):
        stats_owner.collect_snapshot_stats(conn, deadline=1.0)  # type: ignore[arg-type]
    assert conn.cleared is True
