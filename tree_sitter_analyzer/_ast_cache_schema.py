"""Schema DDL constants and migration functions for ASTCache.

Each ``apply_migration_vN(conn, record_fn)`` function:
- receives the SQLite connection and a ``record_fn(conn, version, description)``
  callback (``ASTCache._record_schema_version``)
- applies its migration block idempotently via PRAGMA/ALTER detection
- calls ``record_fn`` then commits before returning
- silently passes on ``sqlite3.OperationalError`` (legacy DB degradation)

Having these here keeps ``ast_cache.py`` focused on orchestration and
reduces its line count / nesting depth.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Schema DDL constants
# ---------------------------------------------------------------------------

SCHEMA_V3_CALL_EDGES = """
CREATE TABLE IF NOT EXISTS ast_call_edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_name TEXT NOT NULL,
    caller_file TEXT NOT NULL,
    caller_line INTEGER NOT NULL,
    callee_name TEXT NOT NULL,
    callee_full TEXT NOT NULL DEFAULT '',
    callee_line INTEGER NOT NULL DEFAULT 0,
    file_path   TEXT NOT NULL,
    language    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ce_callee_name
    ON ast_call_edges(callee_name);

CREATE INDEX IF NOT EXISTS idx_ce_caller_name
    ON ast_call_edges(caller_name);

CREATE INDEX IF NOT EXISTS idx_ce_file_path
    ON ast_call_edges(file_path);
"""

# Feature 1 (Synapse) — V4 schema additions.
#
# Adds three resolution columns to ``ast_call_edges`` plus a new
# ``ast_imports`` table that records every imported name binding.
#
# The three new edge columns:
#
# * ``callee_symbol_id``    — points to the row in ``ast_symbol_rows`` the
#   resolver believes is the called definition, or NULL when the callee
#   isn't a project symbol (stdlib / builtin / unknown).
# * ``callee_resolution``   — one of {local, project, stdlib, unknown}.
#   Default ``'unknown'`` so legacy rows look identical to rows the
#   resolver could not place.
# * ``callee_resolved_file`` — relative path of the file containing the
#   resolved definition, empty when ``resolution`` is stdlib / unknown.
#
# The ALTER statements live in ``apply_migration_v4`` (Python-side PRAGMA
# detection) rather than a single executescript: ALTER lacks IF NOT EXISTS
# in SQLite, so re-opening a DB that already has the columns would raise.
# The imports table is plain CREATE TABLE IF NOT EXISTS, so the executescript
# form is safe for it.
SCHEMA_V4_IMPORTS = """
CREATE TABLE IF NOT EXISTS ast_imports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path   TEXT NOT NULL,
    language    TEXT NOT NULL,
    module_path TEXT NOT NULL,
    local_name  TEXT NOT NULL DEFAULT '',
    is_relative INTEGER NOT NULL DEFAULT 0,
    is_star     INTEGER NOT NULL DEFAULT 0,
    alias_of    TEXT NOT NULL DEFAULT '',
    line        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_imp_file
    ON ast_imports(file_path);

CREATE INDEX IF NOT EXISTS idx_imp_local
    ON ast_imports(local_name);

CREATE INDEX IF NOT EXISTS idx_imp_star
    ON ast_imports(is_star);
"""


# Feature 2 (Temporal Activation) — per-symbol git modification frequency.
# Populated as a side-effect of ``index_file`` via ``git_activation``.
# Consumers: change-impact verdict bump, callees/callers ``include_activation``,
# homeostasis health scoring (Phase 3b).
#
# One row per symbol_id; the (file_path) index lets re-index deletes scope
# by file without touching ast_symbol_rows joins.
SCHEMA_V5_ACTIVATION = """
CREATE TABLE IF NOT EXISTS ast_symbol_activation (
    symbol_id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL,
    last_modified_commit TEXT,
    last_modified_at INTEGER,
    mod_count_30d INTEGER NOT NULL DEFAULT 0,
    mod_count_90d INTEGER NOT NULL DEFAULT 0,
    mod_count_all INTEGER NOT NULL DEFAULT 0,
    computed_at INTEGER NOT NULL,
    git_state TEXT NOT NULL DEFAULT 'tracked'
);

CREATE INDEX IF NOT EXISTS idx_act_file
    ON ast_symbol_activation(file_path);

CREATE INDEX IF NOT EXISTS idx_act_hot_30d
    ON ast_symbol_activation(mod_count_30d DESC);

CREATE INDEX IF NOT EXISTS idx_act_last_at
    ON ast_symbol_activation(last_modified_at DESC);
"""


# Feature 3 (Inhibition / Constraint DSL) — persistent violation cache.
# ``check_constraints`` writes detected violations here; ``safe_to_edit``
# and ``analyze_change_impact`` read them on every gate-tool call.
#
# Composite primary key (rule_id, caller_file, caller_line, callee_name)
# is intentionally tight: a single rule can fire from many lines, and a
# single line can violate many rules, but the same (rule, line, callee)
# combination should dedupe into one row across re-evaluations.
SCHEMA_V6_VIOLATIONS = """
CREATE TABLE IF NOT EXISTS ast_constraint_violations (
    rule_id      TEXT NOT NULL,
    caller_file  TEXT NOT NULL,
    caller_name  TEXT NOT NULL,
    caller_line  INTEGER NOT NULL,
    callee_name  TEXT NOT NULL,
    callee_file  TEXT NOT NULL DEFAULT '',
    severity     TEXT NOT NULL,
    detected_at  INTEGER NOT NULL,
    PRIMARY KEY (rule_id, caller_file, caller_line, callee_name)
);

CREATE INDEX IF NOT EXISTS idx_cv_caller_file
    ON ast_constraint_violations(caller_file);

CREATE INDEX IF NOT EXISTS idx_cv_severity
    ON ast_constraint_violations(severity);
"""

# ---------------------------------------------------------------------------
# RecordFn type alias
# ---------------------------------------------------------------------------

RecordFn = Callable[[sqlite3.Connection, int, str], None]

# ---------------------------------------------------------------------------
# Migration functions (one per version)
# ---------------------------------------------------------------------------


def apply_migration_v3(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """Create ``ast_call_edges`` table and its indexes (v3).

    Idempotent via ``CREATE TABLE IF NOT EXISTS`` / ``CREATE INDEX IF NOT EXISTS``.
    """
    try:
        conn.executescript(SCHEMA_V3_CALL_EDGES)
        record_fn(conn, 3, "ast_call_edges + indices")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def apply_migration_v4(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """Add Synapse resolution columns + ``ast_imports`` table (v4).

    ALTER TABLE has no IF NOT EXISTS form in SQLite, so each column is
    added only when PRAGMA table_info confirms it is missing.
    """
    try:
        edge_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(ast_call_edges)").fetchall()
        }
        if "callee_symbol_id" not in edge_cols:
            conn.execute(
                "ALTER TABLE ast_call_edges ADD COLUMN callee_symbol_id INTEGER"
            )
        if "callee_resolution" not in edge_cols:
            conn.execute(
                "ALTER TABLE ast_call_edges "
                "ADD COLUMN callee_resolution TEXT NOT NULL "
                "DEFAULT 'unknown'"
            )
        if "callee_resolved_file" not in edge_cols:
            conn.execute(
                "ALTER TABLE ast_call_edges "
                "ADD COLUMN callee_resolved_file TEXT NOT NULL "
                "DEFAULT ''"
            )
        conn.executescript(SCHEMA_V4_IMPORTS)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ce_callee_symbol_id "
            "ON ast_call_edges(callee_symbol_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ce_callee_resolved "
            "ON ast_call_edges(callee_resolved_file)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ce_resolution "
            "ON ast_call_edges(callee_resolution)"
        )
        record_fn(conn, 4, "Synapse: callee_resolution + ast_imports")
        conn.commit()
    except sqlite3.OperationalError:
        # Legacy DB with incompatible ast_call_edges shape — degrade
        # silently. The post-init self-check will fire if columns we
        # require are still missing.
        pass


def apply_migration_v5(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """Create ``ast_symbol_activation`` table (v5 — Temporal Activation).

    Idempotent via ``CREATE TABLE IF NOT EXISTS``.
    """
    try:
        conn.executescript(SCHEMA_V5_ACTIVATION)
        record_fn(conn, 5, "Temporal activation")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def apply_migration_v6(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """Create ``ast_constraint_violations`` table (v6 — Constraint DSL).

    The DDL must stay in sync with ``ast_cache._SCHEMA_V6_VIOLATIONS``.
    Idempotent via ``CREATE TABLE IF NOT EXISTS``.
    """
    try:
        conn.executescript(SCHEMA_V6_VIOLATIONS)
        record_fn(conn, 6, "Constraint violations")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def apply_migration_v7(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """Add ``extractor_version`` column to ``ast_index`` (v7).

    ALTER TABLE has no IF NOT EXISTS form — column added only when PRAGMA
    table_info confirms it is missing.
    """
    try:
        index_cols = {r[1] for r in conn.execute("PRAGMA table_info(ast_index)")}
        if "extractor_version" not in index_cols:
            conn.execute(
                "ALTER TABLE ast_index "
                "ADD COLUMN extractor_version INTEGER NOT NULL DEFAULT 0"
            )
        record_fn(conn, 7, "Extractor version invalidation")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def apply_migration_v8(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """Create unified ``edges`` table (v8 — EdgeStore)."""
    try:
        from .graph.edge_store import EDGE_STORE_SCHEMA

        conn.executescript(EDGE_STORE_SCHEMA)
        record_fn(conn, 8, "Unified edge store")
        conn.commit()
    except sqlite3.OperationalError:
        pass


SCHEMA_V9_UNRESOLVED_REFS = """
CREATE TABLE IF NOT EXISTS unresolved_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id TEXT NOT NULL,
    reference_name TEXT NOT NULL,
    reference_kind TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line INTEGER,
    candidates TEXT,
    resolved INTEGER DEFAULT 0,
    UNIQUE(from_node_id, reference_name, reference_kind, line)
);

CREATE INDEX IF NOT EXISTS idx_unresolved_name
    ON unresolved_refs(reference_name);

CREATE INDEX IF NOT EXISTS idx_unresolved_resolved
    ON unresolved_refs(resolved);
"""


def apply_migration_v9(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """Create ``unresolved_refs`` table (v9 — cross-file second pass)."""
    try:
        conn.executescript(SCHEMA_V9_UNRESOLVED_REFS)
        record_fn(conn, 9, "Unresolved reference backfill")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def apply_migration_v10(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """Promote caller/callee/file scalars to real ``edges`` columns (v10 — B1.1).

    Non-breaking first step of the single edge-table consolidation: the CALLS
    scalars that previously only lived in the JSON ``metadata`` blob become
    indexed real columns so callers/callees/call_path can push the name filter
    down to SQL instead of full-scanning ``kind='calls'`` in Python.

    Uses the EdgeStore schema/backfill helpers directly (not the ``EdgeStore``
    class) so it is unaffected by tests that monkeypatch ``EdgeStore``. It
    idempotently adds the ``caller_name`` / ``callee_name`` / ``file_path``
    columns (ALTER for legacy v8/v9 tables) plus the supporting indexes, then
    backfills the new columns from the existing node ids.
    """
    try:
        from .graph.edge_store import (
            backfill_edge_name_columns,
            ensure_edge_schema,
        )

        ensure_edge_schema(conn)
        backfill_edge_name_columns(conn)
        record_fn(conn, 10, "Edge name columns + pushdown indexes")
        conn.commit()
    except sqlite3.OperationalError:
        pass


# ---------------------------------------------------------------------------
# Schema DDL constants V1 and V2 (moved from ast_cache.py)
# ---------------------------------------------------------------------------

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS ast_index (
    file_path    TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    language     TEXT NOT NULL,
    mtime_ns     INTEGER NOT NULL,
    file_size    INTEGER NOT NULL,
    extractor_version INTEGER NOT NULL DEFAULT 0,
    symbols_json TEXT NOT NULL DEFAULT '{}',
    imports_json TEXT NOT NULL DEFAULT '[]',
    structure_json TEXT NOT NULL DEFAULT '{}',
    indexed_at   TEXT NOT NULL,
    PRIMARY KEY (file_path)
);

CREATE INDEX IF NOT EXISTS idx_ast_content_hash
    ON ast_index(content_hash);

CREATE INDEX IF NOT EXISTS idx_ast_language
    ON ast_index(language);
"""

SCHEMA_V2_FTS = """
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
        name      TEXT NOT NULL,
        kind      TEXT NOT NULL,
        file_path TEXT NOT NULL,
        language  TEXT NOT NULL,
        line      INTEGER NOT NULL DEFAULT 0,
        end_line  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sym_rows_file_path
    ON ast_symbol_rows(file_path);
"""

LARGE_REPO_INDEXES: tuple[tuple[str, str], ...] = (
    (
        "ast_symbol_rows",
        "CREATE INDEX IF NOT EXISTS idx_sym_rows_name_kind_path_line "
        "ON ast_symbol_rows(name, kind, file_path, line)",
    ),
    (
        "ast_symbol_rows",
        "CREATE INDEX IF NOT EXISTS idx_sym_rows_file_name_kind_line "
        "ON ast_symbol_rows(file_path, name, kind, line)",
    ),
    (
        "ast_call_edges",
        "CREATE INDEX IF NOT EXISTS idx_ce_callee_name_resolved_file "
        "ON ast_call_edges(callee_name, callee_resolved_file)",
    ),
    (
        "ast_call_edges",
        "CREATE INDEX IF NOT EXISTS idx_ce_callee_name_file_path "
        "ON ast_call_edges(callee_name, file_path)",
    ),
    (
        "ast_call_edges",
        "CREATE INDEX IF NOT EXISTS idx_ce_caller_name_file "
        "ON ast_call_edges(caller_name, caller_file)",
    ),
)

SCHEMA_VERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS ast_schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at INTEGER NOT NULL,
    description TEXT NOT NULL
);
"""

EXPECTED_SCHEMA_VERSIONS: list[Any] = [
    (
        3,
        "ast_call_edges + indices",
        {
            "tables": ["ast_call_edges"],
            "ast_call_edges_columns": [
                "caller_name",
                "caller_file",
                "caller_line",
                "callee_name",
                "callee_full",
                "callee_line",
                "file_path",
                "language",
            ],
        },
    ),
    (
        4,
        "Synapse: callee_resolution + ast_imports",
        {
            "tables": ["ast_imports"],
            "ast_call_edges_columns": [
                "callee_symbol_id",
                "callee_resolution",
                "callee_resolved_file",
            ],
        },
    ),
    (
        5,
        "Temporal activation",
        {
            "tables": ["ast_symbol_activation"],
        },
    ),
    (
        6,
        "Constraint violations",
        {
            "tables": ["ast_constraint_violations"],
        },
    ),
    (
        7,
        "Extractor version invalidation",
        {
            "ast_index_columns": ["extractor_version"],
        },
    ),
    (
        8,
        "Unified edge store",
        {
            "tables": ["edges"],
            "edges_columns": [
                "source_node_id",
                "target_node_id",
                "kind",
                "line",
                "provenance",
                "metadata",
            ],
        },
    ),
    (
        9,
        "Unresolved reference backfill",
        {
            "tables": ["unresolved_refs"],
            "unresolved_refs_columns": [
                "from_node_id",
                "reference_name",
                "reference_kind",
                "file_path",
                "line",
                "candidates",
                "resolved",
            ],
        },
    ),
    (
        10,
        "Edge name columns + pushdown indexes",
        {
            "tables": ["edges"],
            "edges_columns": [
                "caller_name",
                "callee_name",
                "file_path",
            ],
        },
    ),
]

# ---------------------------------------------------------------------------
# SQL helper constants (moved from ast_cache.py)
# ---------------------------------------------------------------------------

SQL_TABLE_EXISTS = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?"
SQL_GET_SCHEMA_VERSION = "SELECT version FROM ast_schema_version WHERE version = ?"
SQL_UPDATE_CALLEE_RESOLVED = (
    "UPDATE ast_call_edges SET callee_resolved_file = ? "
    "WHERE caller_file = ? AND caller_line = ? "
    "AND callee_name = ? AND callee_line = ?"
)
SQL_COUNT_SYMBOL_ROWS = "SELECT COUNT(*) as c FROM ast_symbol_rows"
SQL_COUNT_RESOLVED_EDGES = (
    "SELECT COUNT(*) as c FROM ast_call_edges WHERE callee_resolved_file != ''"
)
SQL_COUNT_CROSS_FILE_EDGES = (
    "SELECT COUNT(*) as c FROM ast_call_edges "
    "WHERE callee_resolved_file != '' "
    "AND callee_resolved_file != file_path"
)

# ---------------------------------------------------------------------------
# Pure schema helper functions (moved from ASTCache static methods)
# ---------------------------------------------------------------------------


def get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the column names of ``table``, or empty set when absent."""
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {r[1] for r in rows}


def check_schema_expectations(
    conn: sqlite3.Connection,
    expectations: dict[str, list[str]],
    missing: list[str],
) -> bool:
    """Confirm every expected table + column from one version block exists."""
    all_ok = True
    for table in expectations.get("tables", []):
        cols = get_table_columns(conn, table)
        if not cols:
            missing.append(f"table {table!r}")
            all_ok = False
    for key, required_cols in expectations.items():
        if key == "tables":
            continue
        if not key.endswith("_columns"):
            continue
        table = key[: -len("_columns")]
        cols = get_table_columns(conn, table)
        if not cols:
            if table not in expectations.get("tables", []):
                missing.append(f"table {table!r} (needed for columns)")
            all_ok = False
            continue
        for col in required_cols:
            if col not in cols:
                missing.append(f"column {table}.{col}")
                all_ok = False
    return all_ok


def apply_large_repo_indexes(conn: sqlite3.Connection) -> None:
    """Create non-shape-changing indexes for large-repo query hot paths."""
    import logging as _logging

    _log = _logging.getLogger(__name__)
    for table_name, sql in LARGE_REPO_INDEXES:
        try:
            exists = conn.execute(SQL_TABLE_EXISTS, (table_name,)).fetchone()
            if exists:
                conn.execute(sql)
        except sqlite3.OperationalError:
            _log.debug("Skipping optional index for table %s", table_name)


def already_applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of schema versions already recorded in ast_schema_version."""
    try:
        rows = conn.execute("SELECT version FROM ast_schema_version").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {int(r[0]) for r in rows}


def record_schema_version(
    conn: sqlite3.Connection, version: int, description: str
) -> None:
    """Stamp a row in ast_schema_version after a migration block applies."""
    import time as _time

    ts = int(_time.time())
    try:
        conn.execute(
            "INSERT OR IGNORE INTO ast_schema_version "
            "(version, applied_at, description) VALUES (?, ?, ?)",
            (version, ts, description),
        )
    except sqlite3.OperationalError:
        pass


def backfill_schema_version_row(
    conn: sqlite3.Connection,
    version: int,
    description: str,
    missing: list[str],
) -> None:
    """INSERT OR IGNORE a version row for a legacy DB that predates the registry."""
    import time as _time

    ts = int(_time.time())
    try:
        conn.execute(
            "INSERT OR IGNORE INTO ast_schema_version "
            "(version, applied_at, description) VALUES (?, ?, ?)",
            (version, ts, description),
        )
        conn.commit()
    except sqlite3.OperationalError:
        missing.append(
            f"ast_schema_version row for v{version} ({description}) could not be inserted"
        )


def clear_activation_for_file(conn: sqlite3.Connection, rel_path: str) -> None:
    """Drop stale activation rows when project indexing runs in fast mode."""
    try:
        conn.execute(
            "DELETE FROM ast_symbol_activation WHERE file_path = ?",
            (rel_path,),
        )
    except sqlite3.OperationalError:
        pass


def init_db(
    conn: sqlite3.Connection,
    fts5_available: bool | None,
    has_fts5_fn: Any,
    migrations: list[tuple[int, Any]],
) -> bool:
    """Apply schema DDL and migrations. Returns updated fts5_available flag."""
    conn.executescript(SCHEMA_V1)
    conn.executescript(SCHEMA_VERSIONS_DDL)
    conn.commit()
    if fts5_available is None:
        fts5_available = has_fts5_fn(conn)
    if fts5_available:
        try:
            conn.executescript(SCHEMA_V2_FTS)
            conn.commit()
        except sqlite3.OperationalError:
            fts5_available = False
    applied = already_applied_versions(conn)
    for version, migration_fn in migrations:
        if version not in applied:
            migration_fn(conn, record_schema_version)
    apply_large_repo_indexes(conn)
    conn.commit()
    return bool(fts5_available)
