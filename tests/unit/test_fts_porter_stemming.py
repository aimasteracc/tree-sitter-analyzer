"""RED-first tests for #604 — FTS5 porter stemming (phase 0 of RFC-0016).

The default unicode61 tokenizer does not stem: ``"dispatching"`` returned
zero hits against ``dispatch_legacy`` / ``_dispatch``. After switching
``ast_symbols_fts`` to ``tokenize='porter unicode61'``:

* "dispatching" matches the dispatch family (stemmed recall),
* exact-identifier queries return byte-identical result sets vs the old
  tokenizer (stemming is applied symmetrically at index + query time),
* BM25 ranking still applies (normalized relevance_score, descending),
* migration v12 rebuilds an EXISTING cache in place from ast_symbol_rows
  (rowid join preserved) — no full reindex, no corruption.
"""

from __future__ import annotations

import sqlite3

import pytest

from tree_sitter_analyzer._ast_cache_query import fts_search_ranked
from tree_sitter_analyzer._ast_cache_schema import (
    SCHEMA_V1,
    SCHEMA_V2_FTS,
    SCHEMA_VERSIONS_DDL,
)
from tree_sitter_analyzer.ast_cache import ASTCache

# ---------------------------------------------------------------------------
# FTS5 availability guard (mirrors tests/unit/mcp/test_fts5_bm25_ranking.py)
# ---------------------------------------------------------------------------

_FTS5_AVAILABLE = True
try:
    _c = sqlite3.connect(":memory:")
    _c.execute("CREATE VIRTUAL TABLE _probe USING fts5(x, content='')")
    _c.close()
except sqlite3.OperationalError:
    _FTS5_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _FTS5_AVAILABLE,
    reason="SQLite FTS5 extension not available; tracked: optional sqlite build capability",
)

# The pre-#604 DDL (no tokenize= clause → default unicode61, no stemming).
# Kept as a literal so the before/after differential stays executable.
_OLD_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS ast_symbols_fts
    USING fts5(
        name,
        kind,
        file_path,
        language,
        content=''
    );

CREATE TABLE IF NOT EXISTS ast_symbol_rows (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    file_path  TEXT NOT NULL,
    language   TEXT NOT NULL,
    line       INTEGER NOT NULL DEFAULT 0,
    end_line   INTEGER NOT NULL DEFAULT 0
);
"""

# (name, kind, file_path, line) — all production paths, deterministic order.
_SYMBOLS = [
    ("dispatch_legacy", "function", "src/router.py", 10),
    ("_dispatch", "method", "src/server.py", 20),
    ("dispatch", "function", "src/core.py", 30),
    ("handle_call_tool", "method", "src/server.py", 40),
]


def _make_conn(ddl: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(ddl)
    for name, kind, file_path, line in _SYMBOLS:
        row_id = conn.execute(
            "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
            "VALUES (?, ?, ?, 'python', ?, ?)",
            (name, kind, file_path, line, line + 5),
        ).lastrowid
        conn.execute(
            "INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language) "
            "VALUES (?, ?, ?, ?, 'python')",
            (row_id, name, kind, file_path),
        )
    conn.commit()
    return conn


def _names(rows: list[dict]) -> list[str]:
    return sorted(r["name"] for r in rows)


# ---------------------------------------------------------------------------
# Recall: "dispatching" → dispatch family
# ---------------------------------------------------------------------------


class TestPorterStemmingRecall:
    def test_old_tokenizer_misses_dispatching(self):
        """Executable record of the pre-#604 gap: default tokenizer → 0 hits."""
        conn = _make_conn(_OLD_FTS_DDL)
        assert fts_search_ranked(conn, "dispatching") == []

    def test_dispatching_matches_dispatch_family(self):
        """Porter stems query + index: exactly the 3 dispatch symbols match."""
        conn = _make_conn(SCHEMA_V2_FTS)
        rows = fts_search_ranked(conn, "dispatching")
        assert _names(rows) == ["_dispatch", "dispatch", "dispatch_legacy"]

    def test_stemming_does_not_leak_unrelated_symbols(self):
        """handle_call_tool shares no stem with "dispatching" — excluded."""
        conn = _make_conn(SCHEMA_V2_FTS)
        rows = fts_search_ranked(conn, "dispatching")
        assert "handle_call_tool" not in _names(rows)


# ---------------------------------------------------------------------------
# Exact-identifier queries: unchanged result sets (old vs new differential)
# ---------------------------------------------------------------------------


class TestExactTokenQueriesUnchanged:
    @pytest.mark.parametrize(
        "query,expected_names",
        [
            ("dispatch_legacy", ["dispatch_legacy"]),
            ("handle_call_tool", ["handle_call_tool"]),
        ],
    )
    def test_exact_identifier_query_identical_old_vs_new(self, query, expected_names):
        old_conn = _make_conn(_OLD_FTS_DDL)
        new_conn = _make_conn(SCHEMA_V2_FTS)
        old_names = _names(fts_search_ranked(old_conn, query))
        new_names = _names(fts_search_ranked(new_conn, query))
        assert old_names == expected_names
        assert new_names == expected_names


# ---------------------------------------------------------------------------
# BM25 ranking still applies on stemmed queries
# ---------------------------------------------------------------------------


class TestBm25RankingStillApplies:
    def test_relevance_scores_normalized_and_descending(self):
        conn = _make_conn(SCHEMA_V2_FTS)
        rows = fts_search_ranked(conn, "dispatching")
        assert len(rows) == 3
        scores = [r["relevance_score"] for r in rows]
        assert scores[0] == 1.0
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Migration v12: existing caches rebuilt in place, never corrupted
# ---------------------------------------------------------------------------


class TestV12MigrationRebuild:
    def _build_legacy_db(self, tmp_path) -> str:
        """Hand-build a cache DB exactly as pre-#604 code would have left it."""
        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        db_path = str(cache_dir / "index.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_V1)
        conn.executescript(SCHEMA_VERSIONS_DDL)
        conn.executescript(_OLD_FTS_DDL)
        for name, kind, file_path, line in _SYMBOLS:
            row_id = conn.execute(
                "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
                "VALUES (?, ?, ?, 'python', ?, ?)",
                (name, kind, file_path, line, line + 5),
            ).lastrowid
            conn.execute(
                "INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language) "
                "VALUES (?, ?, ?, ?, 'python')",
                (row_id, name, kind, file_path),
            )
        conn.commit()
        # Pre-migration baseline: legacy tokenizer cannot stem.
        assert fts_search_ranked(conn, "dispatching") == []
        conn.close()
        return db_path

    def test_existing_cache_rebuilt_with_stemming(self, tmp_path):
        self._build_legacy_db(tmp_path)
        cache = ASTCache(str(tmp_path))
        try:
            rows = cache.fts_search_ranked("dispatching")
            assert _names(rows) == ["_dispatch", "dispatch", "dispatch_legacy"]
            conn = cache.get_conn()
            stamped = conn.execute(
                "SELECT COUNT(*) FROM ast_schema_version WHERE version = 12"
            ).fetchone()[0]
            assert stamped == 1
            joined = conn.execute(
                "SELECT COUNT(*) FROM ast_symbols_fts f "
                "JOIN ast_symbol_rows r ON f.rowid = r.id"
            ).fetchone()[0]
            assert joined == 4
        finally:
            cache.close()

    def test_migration_idempotent_on_second_open(self, tmp_path):
        self._build_legacy_db(tmp_path)
        first = ASTCache(str(tmp_path))
        first.close()
        second = ASTCache(str(tmp_path))
        try:
            rows = second.fts_search_ranked("dispatching")
            assert _names(rows) == ["_dispatch", "dispatch", "dispatch_legacy"]
            stamped = (
                second.get_conn()
                .execute("SELECT COUNT(*) FROM ast_schema_version WHERE version = 12")
                .fetchone()[0]
            )
            assert stamped == 1
        finally:
            second.close()

    def test_migration_degrades_silently_without_fts5(self):
        """FTS5-less builds: OperationalError is swallowed, version NOT stamped."""
        from tree_sitter_analyzer._ast_cache_schema import apply_migration_v12

        class _NoFts5Conn:
            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("no such module: fts5")

            def executescript(self, *args, **kwargs):
                raise sqlite3.OperationalError("no such module: fts5")

        recorded: list[int] = []
        apply_migration_v12(
            _NoFts5Conn(), lambda conn, version, desc: recorded.append(version)
        )
        assert recorded == []

    def test_fresh_cache_end_to_end(self, tmp_path):
        """Index a real file through ASTCache — stemmed recall on a fresh DB."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "router.py").write_text(
            "def dispatch_legacy():\n    pass\n\n"
            "def _dispatch():\n    pass\n\n"
            "class Dispatcher:\n    pass\n",
            newline="\n",
        )
        cache = ASTCache(str(tmp_path))
        try:
            cache.index_file(str(src / "router.py"))
            rows = cache.fts_search_ranked("dispatching")
            assert _names(rows) == ["Dispatcher", "_dispatch", "dispatch_legacy"]
        finally:
            cache.close()
