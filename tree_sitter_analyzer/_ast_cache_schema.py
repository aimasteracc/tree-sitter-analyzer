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
