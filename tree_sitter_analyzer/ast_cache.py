#!/usr/bin/env python3
"""
Pre-indexed AST Cache — SQLite-backed persistent parse result storage.

Stores serialized AST metadata (symbols, imports, structure) keyed by
content SHA-256 hash so re-analysis is instant without re-parsing.

CodeGraph parity: equivalent to CodeGraph's pre-indexed code intelligence.
Like CodeGraph, a one-time index step makes subsequent queries O(1).
"""

import json
import logging
import os
import sqlite3
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from .core.parser import Parser, ParseResult
from .project_graph import _language_from_ext

logger = logging.getLogger(__name__)

_AST_CACHE_EXTRACTOR_VERSION = 2

_SCHEMA_V1 = """
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

_SCHEMA_V2_FTS = """
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

_SCHEMA_V3_CALL_EDGES = """
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
# The ALTER statements live in ``_init_db`` (Python-side PRAGMA detection)
# rather than a single executescript: ALTER lacks IF NOT EXISTS in SQLite,
# so re-opening a DB that already has the columns would raise. The
# imports table is plain CREATE TABLE IF NOT EXISTS, so the executescript
# form is safe for it.
_SCHEMA_V4_IMPORTS = """
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
_SCHEMA_V5_ACTIVATION = """
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
_SCHEMA_V6_VIOLATIONS = """
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


# Large-repo hot-path indexes. These are deliberately versionless and
# idempotent: adding an index does not change row shape, but existing caches
# still need to pick it up when opened after an upgrade.
_LARGE_REPO_INDEXES: tuple[tuple[str, str], ...] = (
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


# Schema-version registry — the "did every migration block actually apply?"
# self-check. Earlier this sprint a parallel agent edit clobbered V4's two
# ALTER TABLE statements down to one, and nothing detected it until a
# downstream test happened to query ``callee_resolution`` and got a
# ``no such column`` error. The version table + ``_verify_schema_integrity``
# below close that class of bug: each migration block records its version
# after it applies, and ``_init_db`` raises ``SchemaIntegrityError`` if the
# expected versions or columns are missing on completion.
_SCHEMA_VERSIONS = """
CREATE TABLE IF NOT EXISTS ast_schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at INTEGER NOT NULL,
    description TEXT NOT NULL
);
"""

# Expected versions + the columns / tables they bring. Keep in sync with the
# _SCHEMA_V* constants above. Update this when adding a new V*.
_EXPECTED_SCHEMA_VERSIONS: list[tuple[int, str, dict[str, list[str]]]] = [
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
]


class SchemaIntegrityError(RuntimeError):
    """Raised when ``_init_db`` cannot prove all expected schema versions
    are present. Usually caused by a parallel-edit conflict that silently
    dropped ALTER TABLE statements, or a corrupted cache file."""


# ---------------------------------------------------------------------------
# Extraction helpers — moved to _ast_extraction.py to keep this file lean.
# Re-exported here so existing internal call-sites continue to work without
# any changes.
# ---------------------------------------------------------------------------
from ._ast_extraction import (  # noqa: E402
    _EXCLUDE_DIRS,
    _content_hash,
    _extract_call_edges,
    _extract_imports,
    _extract_structure,
    _extract_symbols,
    _has_fts5,
    _node_text,  # noqa: F401 - public back-compat re-export
    _worker_index_file,
)

# Back-compat alias imported by file_watcher.py and incremental_sync.py.
from ._lang_extension_map import EXT_TO_LANG as _EXT_TO_LANG  # noqa: E402


def _project_index_activation_enabled(include_activation: bool | None) -> bool:
    """Return whether project-wide indexing should compute git activation.

    Full-project indexing is the warm-cache path used by agents. It must be
    fast and predictable on large repos, so activation is opt-in there. The
    existing ``TSA_INDEX_ACTIVATION=1`` escape hatch keeps the richer path
    available without adding per-file git subprocess cost by default.
    """
    if include_activation is not None:
        return bool(include_activation)
    value = os.environ.get("TSA_INDEX_ACTIVATION", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ASTCache:
    """
    SQLite-backed persistent AST cache.

    Stores per-file parse metadata (symbols, imports, structure) keyed by
    content hash. Re-analysis of unchanged files is a simple DB lookup.
    """

    def __init__(self, project_root: str, db_path: str | None = None) -> None:
        self.project_root = os.path.abspath(project_root)
        if db_path is None:
            db_path = os.path.join(self.project_root, ".ast-cache", "index.db")
        self.db_path = db_path
        self._local = threading.local()
        self._parser = Parser()
        self._index_lock = threading.Lock()
        self._fts5_available: bool | None = None
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA_V1)
        # Create the version registry up-front so each migration block can
        # stamp its row as it applies. Idempotent CREATE TABLE IF NOT EXISTS.
        conn.executescript(_SCHEMA_VERSIONS)
        conn.commit()
        if self._fts5_available is None:
            self._fts5_available = _has_fts5(conn)
        if self._fts5_available:
            try:
                conn.executescript(_SCHEMA_V2_FTS)
                conn.commit()
            except sqlite3.OperationalError:
                self._fts5_available = False
        # Snapshot which versions are already recorded. Each migration
        # block consults this snapshot: if its version is recorded we
        # skip the migration body (the version row is the source of
        # truth for "this block already applied"). This lets the
        # post-init self-check detect schema tampering: if the registry
        # says v4 applied but the column is missing, somebody has
        # corrupted the DB or a parallel-edit clobbered an ALTER
        # statement, and the self-check raises rather than silently
        # re-applying the migration and masking the problem.
        applied_versions = self._already_applied_versions(conn)
        if 3 not in applied_versions:
            try:
                conn.executescript(_SCHEMA_V3_CALL_EDGES)
                self._record_schema_version(conn, 3, "ast_call_edges + indices")
                conn.commit()
            except sqlite3.OperationalError:
                pass
        # Feature 1 (Synapse) — V4 schema. ALTER TABLE has no
        # IF NOT EXISTS form in SQLite, so we add the columns only when
        # PRAGMA table_info confirms they are missing. Defaults match
        # what a never-resolved row would look like, so the backfill
        # path can detect "fresh" rows by ``callee_resolution = 'unknown'
        # AND callee_resolved_file = ''``.
        #
        # Migration runs only when v4 is not in the registry. Once
        # recorded, this block is skipped and the self-check below is
        # the only thing that touches the schema — that's how we catch
        # tampering / silently-dropped ALTER statements.
        if 4 not in applied_versions:
            try:
                edge_cols = {
                    r[1]
                    for r in conn.execute(
                        "PRAGMA table_info(ast_call_edges)"
                    ).fetchall()
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
                conn.executescript(_SCHEMA_V4_IMPORTS)
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
                self._record_schema_version(
                    conn, 4, "Synapse: callee_resolution + ast_imports"
                )
                conn.commit()
            except sqlite3.OperationalError:
                # Legacy DB with incompatible ast_call_edges shape —
                # degrade silently rather than wedge open. The
                # post-init self-check will fire if the legacy shape
                # is missing columns we require.
                pass
        # Feature 2 (Temporal Activation) — V5 schema. Idempotent
        # CREATE TABLE IF NOT EXISTS so the migration is safe to re-run.
        if 5 not in applied_versions:
            try:
                conn.executescript(_SCHEMA_V5_ACTIVATION)
                self._record_schema_version(conn, 5, "Temporal activation")
                conn.commit()
            except sqlite3.OperationalError:
                pass
        # Feature 3 (Constraint DSL) — V6 schema. Same idempotency.
        if 6 not in applied_versions:
            try:
                conn.executescript(_SCHEMA_V6_VIOLATIONS)
                self._record_schema_version(conn, 6, "Constraint violations")
                conn.commit()
            except sqlite3.OperationalError:
                pass
        # V7 records which extraction algorithm produced the serialized
        # per-file rows. Bump ``_AST_CACHE_EXTRACTOR_VERSION`` whenever
        # symbols/imports/structure/call_edges change semantics so existing
        # caches are re-parsed instead of serving stale graph answers.
        if 7 not in applied_versions:
            try:
                index_cols = {
                    r[1] for r in conn.execute("PRAGMA table_info(ast_index)")
                }
                if "extractor_version" not in index_cols:
                    conn.execute(
                        "ALTER TABLE ast_index "
                        "ADD COLUMN extractor_version INTEGER NOT NULL DEFAULT 0"
                    )
                self._record_schema_version(conn, 7, "Extractor version invalidation")
                conn.commit()
            except sqlite3.OperationalError:
                pass
        self._ensure_large_repo_indexes(conn)
        conn.commit()
        # Post-init self-check — raise SchemaIntegrityError if any
        # expected table / column is missing. Backfills the version
        # registry for legacy DBs that pre-date this code.
        self._verify_schema_integrity(conn)

    @staticmethod
    def _ensure_large_repo_indexes(conn: sqlite3.Connection) -> None:
        """Create non-shape-changing indexes for large-repo query hot paths."""
        for table_name, sql in _LARGE_REPO_INDEXES:
            try:
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone()
                if exists:
                    conn.execute(sql)
            except sqlite3.OperationalError:
                logger.debug("Skipping optional index for table %s", table_name)

    @staticmethod
    def _already_applied_versions(conn: sqlite3.Connection) -> set[int]:
        """Return the set of schema versions already recorded in
        ``ast_schema_version``. Empty when the table is fresh."""
        try:
            rows = conn.execute("SELECT version FROM ast_schema_version").fetchall()
        except sqlite3.OperationalError:
            return set()
        return {int(r[0]) for r in rows}

    @staticmethod
    def _record_schema_version(
        conn: sqlite3.Connection, version: int, description: str
    ) -> None:
        """Stamp a row in ``ast_schema_version`` after a migration block
        applies. INSERT OR IGNORE so re-opens are idempotent."""
        import time as _time

        try:
            conn.execute(
                "INSERT OR IGNORE INTO ast_schema_version "
                "(version, applied_at, description) VALUES (?, ?, ?)",
                (version, int(_time.time()), description),
            )
        except sqlite3.OperationalError:
            # Version table missing — degrade silently. The self-check
            # will surface this as a SchemaIntegrityError downstream.
            pass

    def _verify_schema_integrity(self, conn: sqlite3.Connection) -> None:
        """Walk ``_EXPECTED_SCHEMA_VERSIONS`` and prove every entry exists.

        Two responsibilities:

        1. **Recovery**: for fresh DBs created before the version table
           shipped, INSERT OR IGNORE the version rows so the cache looks
           healthy on the next open.
        2. **Detection**: confirm every expected table + column exists via
           ``PRAGMA table_info``. Collect ALL missing things first then
           raise once — don't fail-fast on the first miss so the
           remediation message lists every problem.

        Raises ``SchemaIntegrityError`` with file path + missing-thing list
        + remediation (``rm .ast-cache/index.db and re-index``) when the
        schema is incomplete.
        """
        import time as _time

        missing: list[str] = []
        for version, description, expectations in _EXPECTED_SCHEMA_VERSIONS:
            # Recovery: backfill the version row if it's absent but the
            # tables/columns it gates DO exist. ``_check_expectations``
            # decides whether the version's payload is actually present.
            payload_ok = self._check_expectations(conn, expectations, missing)
            try:
                row = conn.execute(
                    "SELECT version FROM ast_schema_version WHERE version = ?",
                    (version,),
                ).fetchone()
            except sqlite3.OperationalError:
                row = None
            if row is None and payload_ok:
                # Legacy DB: tables exist but the registry row never got
                # written. Backfill so future opens look clean.
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO ast_schema_version "
                        "(version, applied_at, description) VALUES (?, ?, ?)",
                        (version, int(_time.time()), description),
                    )
                    conn.commit()
                except sqlite3.OperationalError:
                    # If we can't even backfill, the version table itself
                    # is missing — surface it as a missing payload.
                    missing.append(
                        f"ast_schema_version row for v{version} "
                        f"({description}) could not be inserted"
                    )
        if missing:
            remediation = (
                f"Remove the cache DB at {self.db_path!r} and re-index "
                "(e.g. ``rm -rf .ast-cache && uv run python -m "
                "tree_sitter_analyzer --index``)."
            )
            raise SchemaIntegrityError(
                "AST cache schema is incomplete. Missing: "
                + "; ".join(missing)
                + ". "
                + remediation
            )

    @staticmethod
    def _check_expectations(
        conn: sqlite3.Connection,
        expectations: dict[str, list[str]],
        missing: list[str],
    ) -> bool:
        """Confirm every expected table + column from one version block
        exists. Appends descriptive entries to ``missing`` for anything
        absent. Returns ``True`` when every check passed."""
        # ``expectations`` is keyed by either ``tables`` (a list of table
        # names that must exist) or ``<table>_columns`` (a list of column
        # names that must exist on ``<table>``). We iterate both.
        all_ok = True
        for table in expectations.get("tables", []):
            cols = ASTCache._table_columns(conn, table)
            if not cols:
                missing.append(f"table {table!r}")
                all_ok = False
        for key, required_cols in expectations.items():
            if key == "tables":
                continue
            if not key.endswith("_columns"):
                continue
            table = key[: -len("_columns")]
            cols = ASTCache._table_columns(conn, table)
            if not cols:
                # The table itself is missing — already reported via the
                # ``tables`` check if it was listed there. Add it now for
                # the column-only case (table not declared in ``tables``).
                if table not in expectations.get("tables", []):
                    missing.append(f"table {table!r} (needed for columns)")
                all_ok = False
                continue
            for col in required_cols:
                if col not in cols:
                    missing.append(f"column {table}.{col}")
                    all_ok = False
        return all_ok

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        """Return the column names of ``table``, or empty set when absent."""
        try:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        except sqlite3.OperationalError:
            return set()
        return {r[1] for r in rows}

    def index_file(self, file_path: str, language: str | None = None) -> dict[str, Any]:
        abs_path = os.path.abspath(file_path)
        rel_path = os.path.relpath(abs_path, self.project_root).replace("\\", "/")
        if language is None:
            language = _language_from_ext(abs_path)
        if language is None:
            return {
                "file": rel_path,
                "status": "skipped",
                "reason": "unsupported language",
            }

        try:
            stat = os.stat(abs_path)
        except OSError as e:
            return {"file": rel_path, "status": "error", "reason": str(e)}

        source_code: str | None = None
        conn = self._get_conn()
        row = conn.execute(
            "SELECT content_hash, mtime_ns, file_size, extractor_version "
            "FROM ast_index WHERE file_path = ?",
            (rel_path,),
        ).fetchone()
        if row is not None:
            if (
                row["mtime_ns"] == int(stat.st_mtime_ns)
                and row["file_size"] == stat.st_size
                and row["extractor_version"] >= _AST_CACHE_EXTRACTOR_VERSION
            ):
                return {"file": rel_path, "status": "cached", "reason": "unchanged"}

        try:
            with open(abs_path, encoding="utf-8", errors="replace") as f:
                source_code = f.read()
        except OSError as e:
            return {"file": rel_path, "status": "error", "reason": str(e)}

        content_hash = _content_hash(source_code)

        if (
            row is not None
            and row["content_hash"] == content_hash
            and row["extractor_version"] >= _AST_CACHE_EXTRACTOR_VERSION
        ):
            conn.execute(
                "UPDATE ast_index SET mtime_ns = ?, file_size = ? WHERE file_path = ?",
                (int(stat.st_mtime_ns), stat.st_size, rel_path),
            )
            conn.commit()
            return {"file": rel_path, "status": "cached", "reason": "content unchanged"}

        result: ParseResult = self._parser.parse_file(abs_path, language)
        if not result.success:
            return {
                "file": rel_path,
                "status": "error",
                "reason": result.error_message or "parse failed",
            }

        symbols = _extract_symbols(result.tree, source_code, language)
        imports = _extract_imports(symbols)
        structure = _extract_structure(symbols)
        call_edges = _extract_call_edges(result.tree, source_code, language, symbols)
        indexed_at = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """INSERT OR REPLACE INTO ast_index
               (file_path, content_hash, language, mtime_ns, file_size,
                extractor_version, symbols_json, imports_json, structure_json,
                indexed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rel_path,
                content_hash,
                language,
                int(stat.st_mtime_ns),
                stat.st_size,
                _AST_CACHE_EXTRACTOR_VERSION,
                json.dumps(symbols, ensure_ascii=False),
                json.dumps(imports, ensure_ascii=False),
                json.dumps(structure, ensure_ascii=False),
                indexed_at,
            ),
        )

        inserted_symbol_rows: list[dict[str, Any]] = []
        if self._fts5_available:
            conn.execute(
                "DELETE FROM ast_symbol_rows WHERE file_path = ?",
                (rel_path,),
            )
            conn.execute(
                "DELETE FROM ast_symbols_fts WHERE file_path = ?",
                (rel_path,),
            )
            for sym in symbols.get("symbols", []):
                sym_name = sym.get("name", sym.get("text", ""))
                sym_kind = sym.get("kind", "unknown")
                sym_line = sym.get("line", 0)
                sym_end = sym.get("end_line", 0)
                row_id = conn.execute(
                    """INSERT INTO ast_symbol_rows
                       (name, kind, file_path, language, line, end_line)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (sym_name, sym_kind, rel_path, language, sym_line, sym_end),
                ).lastrowid
                conn.execute(
                    """INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language)
                       VALUES (?, ?, ?, ?, ?)""",
                    (row_id, sym_name, sym_kind, rel_path, language),
                )
                inserted_symbol_rows.append(
                    {
                        "id": int(row_id) if row_id is not None else 0,
                        "line": sym_line,
                        "end_line": sym_end,
                    }
                )

        conn.execute(
            "DELETE FROM ast_call_edges WHERE file_path = ?",
            (rel_path,),
        )
        for edge in call_edges:
            conn.execute(
                """INSERT INTO ast_call_edges
                   (caller_name, caller_file, caller_line,
                    callee_name, callee_full, callee_line,
                    file_path, language)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge["caller_name"],
                    rel_path,
                    edge["caller_line"],
                    edge["callee_name"],
                    edge["callee_full"],
                    edge["callee_line"],
                    rel_path,
                    language,
                ),
            )

        # Feature 1 (Synapse) — replace ast_imports rows for this file.
        # Done here (not in workers) because parse_imports is a small
        # regex pass on text we already have; cheaper than shipping the
        # structured entries through the worker IPC envelope.
        self._write_imports_for_file(conn, rel_path, language, imports)

        # Feature 2 (Temporal Activation) — refresh per-symbol git heat
        # rows for this file using the symbol_ids we just inserted.
        # Honours TSA_INDEX_ACTIVATION=0 via the helper below.
        self._write_activation_for_file(conn, rel_path, inserted_symbol_rows)

        # Feature 1 (Synapse) — resolve the call edges we just wrote.
        # ``index_file`` is a single-file path so cross-file resolution
        # is best-effort: it sees whatever already lives in
        # ast_symbol_rows / ast_imports. ``index_project`` runs a final
        # resolver pass after all files are indexed; this per-file pass
        # is here so direct ``index_file`` callers still see local /
        # stdlib resolution work without a separate backfill call.
        self._resolve_call_edges_for_file(conn, rel_path)

        conn.commit()
        return {
            "file": rel_path,
            "status": "indexed",
            "symbols": len(symbols.get("symbols", [])),
            "call_edges": len(call_edges),
            "content_hash": content_hash[:16],
        }

    def _write_activation_for_file(
        self,
        conn: sqlite3.Connection,
        rel_path: str,
        inserted_symbol_rows: list[dict[str, Any]],
    ) -> None:
        """Refresh ``ast_symbol_activation`` rows for a single file.

        Replaces all existing rows for ``rel_path`` with fresh
        ``ActivationRow`` entries computed from git history. Skipped when
        ``TSA_INDEX_ACTIVATION=0`` so callers can opt out without paying
        the subprocess cost.

        Never raises — git failures degrade to zero-row writes (or no
        writes when the feature is disabled). The indexing pipeline
        cannot afford to fail on git oddities.
        """
        if not inserted_symbol_rows:
            # No symbols → clear any stale rows for this file in case a
            # previous index pass had symbols here.
            try:
                conn.execute(
                    "DELETE FROM ast_symbol_activation WHERE file_path = ?",
                    (rel_path,),
                )
            except sqlite3.OperationalError:
                pass
            return
        try:
            from . import git_activation
        except Exception as exc:  # pragma: no cover — import path defensive
            logger.debug("git_activation import failed: %s", exc)
            return
        if git_activation._activation_disabled():
            # Honour the kill switch BEFORE invoking subprocess. Tests
            # patch ``ga.subprocess`` to detect any escape.
            return
        try:
            rows = git_activation.compute_symbol_activation(
                file_path=os.path.join(self.project_root, rel_path),
                symbols=inserted_symbol_rows,
                repo_root=self.project_root,
            )
        except Exception as exc:  # pragma: no cover — git_activation never raises
            logger.debug("compute_symbol_activation failed for %s: %s", rel_path, exc)
            return
        try:
            conn.execute(
                "DELETE FROM ast_symbol_activation WHERE file_path = ?",
                (rel_path,),
            )
            for r in rows:
                conn.execute(
                    """INSERT OR REPLACE INTO ast_symbol_activation (
                        symbol_id, file_path,
                        last_modified_commit, last_modified_at,
                        mod_count_30d, mod_count_90d, mod_count_all,
                        computed_at, git_state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        int(r.symbol_id),
                        rel_path,
                        r.last_modified_commit,
                        r.last_modified_at,
                        int(r.mod_count_30d),
                        int(r.mod_count_90d),
                        int(r.mod_count_all),
                        int(r.computed_at),
                        r.git_state,
                    ),
                )
        except sqlite3.OperationalError as exc:
            # Table missing on legacy DB — degrade silently rather than
            # failing the whole index pass.
            logger.debug("activation write failed for %s: %s", rel_path, exc)

    def _write_imports_for_file(
        self,
        conn: sqlite3.Connection,
        rel_path: str,
        language: str,
        imports: list[str] | list[dict[str, Any]],
    ) -> None:
        """Refresh ``ast_imports`` rows for ``rel_path``.

        ``imports`` is the list produced by ``_extract_imports`` — either
        raw statement strings or structured dicts with a ``text`` field.
        Parses via :func:`synapse_resolver.parse_imports` and writes one
        row per bound name. Non-Python languages return empty in Phase 3a.
        """
        try:
            from .synapse_resolver import parse_imports
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("synapse_resolver import failed: %s", exc)
            return
        try:
            conn.execute("DELETE FROM ast_imports WHERE file_path = ?", (rel_path,))
        except sqlite3.OperationalError:
            # Table missing on legacy DB — skip.
            return
        for raw in imports or []:
            if isinstance(raw, dict):
                text = raw.get("text") or raw.get("statement") or ""
                line = int(raw.get("line", 0) or 0)
            else:
                text = str(raw)
                line = 0
            if not text:
                continue
            for entry in parse_imports(text, language, rel_path, line):
                try:
                    conn.execute(
                        """INSERT INTO ast_imports
                           (file_path, language, module_path, local_name,
                            is_relative, is_star, alias_of)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            rel_path,
                            language,
                            entry.module_path,
                            entry.local_name,
                            1 if entry.is_relative else 0,
                            1 if entry.is_star else 0,
                            entry.alias_of,
                        ),
                    )
                except sqlite3.OperationalError as exc:
                    logger.debug("ast_imports write failed for %s: %s", rel_path, exc)
                    return

    def _resolve_call_edges_for_file(
        self,
        conn: sqlite3.Connection,
        rel_path: str,
    ) -> None:
        """Resolve every call edge for ``rel_path`` and persist the result.

        Reads the ``ast_call_edges`` rows we just wrote with default
        ``unknown`` resolution, builds a :class:`ResolverContext` from the
        live cache state, and updates each row in-place with the three
        Synapse columns (``callee_symbol_id``, ``callee_resolution``,
        ``callee_resolved_file``). Skipped when ``TSA_SYNAPSE=0`` so the
        index-time cost is opt-out.
        """
        try:
            from .synapse_resolver import (
                build_resolver_context,
                is_enabled,
                resolve_callee,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("synapse_resolver import failed: %s", exc)
            return
        if not is_enabled():
            return
        try:
            ctx = build_resolver_context(self)
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("build_resolver_context failed: %s", exc)
            return
        try:
            rows = conn.execute(
                """SELECT id, caller_name, caller_file, callee_name
                   FROM ast_call_edges WHERE file_path = ?""",
                (rel_path,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.debug("call_edge select failed for %s: %s", rel_path, exc)
            return
        for row in rows:
            try:
                resolved = resolve_callee(row["callee_name"], row["caller_file"], ctx)
            except Exception as exc:  # pragma: no cover — defensive
                logger.debug(
                    "resolve_callee crashed on %s: %s", row["callee_name"], exc
                )
                continue
            try:
                conn.execute(
                    """UPDATE ast_call_edges
                       SET callee_symbol_id = ?,
                           callee_resolution = ?,
                           callee_resolved_file = ?
                       WHERE id = ?""",
                    (
                        resolved.callee_symbol_id,
                        resolved.resolution,
                        resolved.resolved_file,
                        row["id"],
                    ),
                )
            except sqlite3.OperationalError as exc:
                logger.debug("call_edge update failed for id=%s: %s", row["id"], exc)
                return

    def _run_synapse_backfill(self) -> dict[str, int] | None:
        """Re-resolve every unresolved call edge in the cache.

        Scans ``ast_call_edges`` for rows where ``callee_resolution =
        'unknown'`` (or ``callee_resolved_file = ''``) and runs each
        through the Synapse resolver.  Cheaper than a full re-index
        because it reads existing ``ast_symbol_rows`` / ``ast_imports``
        data — no tree-sitter, no IO, just SQL + in-memory maps.

        Returns ``{total, resolved, unchanged, errors}`` or ``None``
        when Synapse is disabled or no unresolved edges remain.
        """
        try:
            from .synapse_resolver import (
                build_resolver_context,
                is_enabled,
                resolve_callee,
            )
        except Exception as exc:
            logger.debug("synapse_resolver import failed: %s", exc)
            return None
        if not is_enabled():
            return None
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, caller_name, caller_file, callee_name "
                "FROM ast_call_edges "
                "WHERE callee_resolution = 'unknown' "
                "OR callee_resolved_file = ''"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.debug("synapse backfill select failed: %s", exc)
            return None
        if not rows:
            return None
        try:
            ctx = build_resolver_context(self)
        except Exception as exc:
            logger.debug("build_resolver_context failed in backfill: %s", exc)
            return None
        total = len(rows)
        resolved = 0
        unchanged = 0
        errors = 0
        for row in rows:
            try:
                result = resolve_callee(row["callee_name"], row["caller_file"], ctx)
            except Exception as exc:
                logger.debug("resolve_callee failed in backfill: %s", exc)
                errors += 1
                continue
            if result.resolution == "unknown" and not result.resolved_file:
                unchanged += 1
                continue
            try:
                conn.execute(
                    "UPDATE ast_call_edges "
                    "SET callee_symbol_id = ?, callee_resolution = ?, "
                    "    callee_resolved_file = ? "
                    "WHERE id = ?",
                    (
                        result.callee_symbol_id,
                        result.resolution,
                        result.resolved_file,
                        row["id"],
                    ),
                )
                resolved += 1
            except sqlite3.OperationalError as exc:
                logger.debug("synapse backfill update failed: %s", exc)
                errors += 1
        try:
            conn.commit()
        except sqlite3.OperationalError:
            pass
        return {
            "total": total,
            "resolved": resolved,
            "unchanged": unchanged,
            "errors": errors,
        }

    def index_project(
        self,
        max_files: int = 20_000,
        force: bool = False,
        *,
        workers: int | None = None,
        resolve_only: bool = False,
        include_activation: bool | None = None,
    ) -> dict[str, Any]:
        """Index every source file under ``self.project_root``.

        PERF-4: when there are enough files to amortise the spawn cost,
        we farm parse + extract out to a process pool. Workers return
        already-serialised JSON; this thread does the SQLite write.
        Workers never return tree-sitter ``Tree`` objects (C objects,
        not picklable).

        ``workers``:
          * ``None`` (default): pick a sensible value — 0 if files < 64
            (serial path, no spawn cost), otherwise
            ``max(2, (os.cpu_count() or 4) - 1)``.
          * ``0`` or ``1``: force serial path.
          * ``>=2``: use that many worker processes.
          Configurable per-call; overridden by ``TSA_INDEX_WORKERS`` env var.

        ``resolve_only``:
          When ``True`` skip parse + symbol insert entirely and only
          refresh the Synapse resolution columns from data already in
          ``ast_index`` / ``ast_symbol_rows`` / ``ast_imports``. This is
          the cheap path agents call after a schema bump or policy
          change — no tree-sitter, no IO, just a SQL pass.

        ``include_activation``:
          Project-wide indexing defaults to the fast warm-cache path:
          temporal git activation is skipped unless this is explicitly
          ``True`` or ``TSA_INDEX_ACTIVATION=1`` is set. Single-file
          ``index_file`` keeps the historical default because its cost is
          bounded to one file.
        """
        activation_enabled = _project_index_activation_enabled(include_activation)
        if resolve_only:
            # Cheap path: re-run the resolver against the data already
            # in the cache. No walk, no parse, no FTS5 rewrite. The
            # integration test ``test_backfill_no_reparse`` asserts
            # Parser.parse_file is never called from this branch.
            updated = self._run_synapse_backfill()
            return {
                "mode_used": "resolve_only",
                "resolve_only": True,
                "indexed": 0,
                "cached": 0,
                "errors": 0,
                "skipped": 0,
                "files": [],
                "synapse_backfill": updated,
                "activation_enabled": activation_enabled,
            }

        if force:
            conn = self._get_conn()
            conn.execute("DELETE FROM ast_index")
            conn.commit()

        # Pass 1: enumerate candidate files and partition into
        # (already-cached, needs-parse). The "already-cached" partition
        # is handled inline because it is one SQL lookup per file with
        # no parsing — cheaper than dispatching to workers.
        candidates: list[tuple[str, str]] = []  # (abs_path, language)
        already_cached: list[dict[str, Any]] = []
        stats: dict[str, Any] = {
            # ``mode_used`` makes the incremental-vs-full distinction
            # explicit in the response. Without this an agent that
            # calls ``index_project()`` thinks it ran a full index, but
            # only files with stale mtime / new content get re-indexed —
            # files added since the last call are picked up here too
            # (the walker re-enumerates), but files removed from disk
            # stay in the DB until ``force=True`` clears them. The
            # honest summary lets agents decide whether to retry with
            # force. See TRUST_BUT_VERIFY_2026-05-23.md for context.
            "mode_used": "full" if force else "incremental",
            "indexed": 0,
            "cached": 0,
            "errors": 0,
            "skipped": 0,
            "files": [],
            "activation_enabled": activation_enabled,
        }
        count = 0
        conn = self._get_conn()
        for abs_path in _walk_source_files(self.project_root):
            if count >= max_files:
                break
            count += 1
            lang = _language_from_ext(abs_path)
            if lang is None:
                stats["skipped"] += 1
                continue
            rel_path = os.path.relpath(abs_path, self.project_root).replace("\\", "/")
            try:
                stat = os.stat(abs_path)
            except OSError as e:
                stats["errors"] += 1
                stats["files"].append(
                    {"file": rel_path, "status": "error", "reason": str(e)}
                )
                continue
            row = conn.execute(
                "SELECT mtime_ns, file_size, extractor_version "
                "FROM ast_index WHERE file_path = ?",
                (rel_path,),
            ).fetchone()
            if (
                row is not None
                and row["mtime_ns"] == int(stat.st_mtime_ns)
                and row["file_size"] == stat.st_size
                and row["extractor_version"] >= _AST_CACHE_EXTRACTOR_VERSION
            ):
                already_cached.append(
                    {"file": rel_path, "status": "cached", "reason": "unchanged"}
                )
                continue
            candidates.append((abs_path, lang))

        stats["cached"] += len(already_cached)
        stats["files"].extend(already_cached)

        # Pass 2: process the parse-needed list. Decide serial vs parallel.
        env_workers = os.environ.get("TSA_INDEX_WORKERS")
        if env_workers is not None:
            try:
                workers = int(env_workers)
            except ValueError:
                pass
        if workers is None:
            if len(candidates) < 64:
                workers = 0  # serial — spawn overhead not worth it on tiny sets
            else:
                workers = max(2, (os.cpu_count() or 4) - 1)

        if workers and workers >= 2 and len(candidates) >= 2:
            results = self._index_parallel(candidates, workers)
        else:
            results = [
                _worker_index_file((p, self.project_root, lang))
                for p, lang in candidates
            ]

        # Pass 3: single-writer SQLite insert wrapped in one transaction.
        # Batching avoids the per-insert fsync/commit cost that dominated
        # the post-parallel timing on medium projects (~1 ms per file).
        indexed_at = datetime.now(timezone.utc).isoformat()
        conn.execute("BEGIN")
        try:
            for r in results:
                if r["status"] == "io_error":
                    stats["errors"] += 1
                    stats["files"].append(
                        {
                            "file": r["rel_path"],
                            "status": "error",
                            "reason": r["reason"],
                        }
                    )
                    continue
                if r["status"] == "parse_failed":
                    stats["errors"] += 1
                    stats["files"].append(
                        {
                            "file": r["rel_path"],
                            "status": "error",
                            "reason": r["reason"],
                        }
                    )
                    continue
                self._insert_index_row(
                    r,
                    indexed_at,
                    include_activation=activation_enabled,
                )
                stats["indexed"] += 1
                stats["files"].append(
                    {
                        "file": r["rel_path"],
                        "status": "indexed",
                        "symbols": r["symbols_count"],
                        "content_hash": r["content_hash"][:16],
                    }
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        stats["total_files"] = count
        stats["workers"] = workers
        if stats["indexed"] > 0:
            try:
                bf = self.backfill_cross_file_edges()
                stats["cross_file_backfill"] = bf
            except Exception:
                logger.debug("cross-file backfill failed", exc_info=True)
            # Feature 1 (Synapse) — resolve every call edge now that all
            # symbols + imports for the project are on disk. Runs even
            # when ``stats["indexed"]`` is zero would be wasted work, so
            # we gate it here. Disabled by ``TSA_SYNAPSE=0``.
            try:
                synapse = self._run_synapse_backfill()
                if synapse is not None:
                    stats["synapse_backfill"] = synapse
            except Exception:
                logger.debug("synapse backfill failed", exc_info=True)
        return stats

    def _index_parallel(
        self, candidates: list[tuple[str, str]], workers: int
    ) -> list[dict[str, Any]]:
        """Dispatch parse+extract to a process pool. Spawn context so the
        behaviour is identical on macOS and Linux (fork inherits SQLite
        handles in a way SQLite does not like)."""
        from multiprocessing import get_context

        ctx = get_context("spawn")
        args_iter = [(p, self.project_root, lang) for p, lang in candidates]
        results: list[dict[str, Any]] = []
        with ctx.Pool(processes=workers) as pool:
            for r in pool.imap_unordered(_worker_index_file, args_iter, chunksize=8):
                results.append(r)
        return results

    def _insert_index_row(
        self,
        r: dict[str, Any],
        indexed_at: str,
        *,
        include_activation: bool = True,
    ) -> None:
        """Write one worker result to SQLite (main table + optional FTS5).

        Workers DO NOT run git themselves — only this writer thread does,
        via ``_write_activation_for_file`` below. Subprocess in a worker
        pool deadlocks against git's index lock and gains us nothing.
        """
        conn = self._get_conn()
        rel_path = r["rel_path"]
        conn.execute(
            """INSERT OR REPLACE INTO ast_index
               (file_path, content_hash, language, mtime_ns, file_size,
                extractor_version, symbols_json, imports_json, structure_json,
                indexed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rel_path,
                r["content_hash"],
                r["language"],
                r["mtime_ns"],
                r["file_size"],
                _AST_CACHE_EXTRACTOR_VERSION,
                r["symbols_json"],
                r["imports_json"],
                r["structure_json"],
                indexed_at,
            ),
        )
        if not self._fts5_available:
            # Without FTS5 we have no symbol_ids to attach activation to.
            return
        conn.execute(
            "DELETE FROM ast_symbol_rows WHERE file_path = ?",
            (rel_path,),
        )
        conn.execute(
            "DELETE FROM ast_symbols_fts WHERE file_path = ?",
            (rel_path,),
        )
        inserted_symbol_rows: list[dict[str, Any]] = []
        for sym_name, sym_kind, sym_line, sym_end in r["symbol_rows"]:
            row_id = conn.execute(
                """INSERT INTO ast_symbol_rows
                   (name, kind, file_path, language, line, end_line)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sym_name, sym_kind, rel_path, r["language"], sym_line, sym_end),
            ).lastrowid
            conn.execute(
                """INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language)
                   VALUES (?, ?, ?, ?, ?)""",
                (row_id, sym_name, sym_kind, rel_path, r["language"]),
            )
            inserted_symbol_rows.append(
                {
                    "id": int(row_id) if row_id is not None else 0,
                    "line": sym_line,
                    "end_line": sym_end,
                }
            )

        conn.execute(
            "DELETE FROM ast_call_edges WHERE file_path = ?",
            (rel_path,),
        )
        call_edges = json.loads(r.get("call_edges_json", "[]"))
        for edge in call_edges:
            conn.execute(
                """INSERT INTO ast_call_edges
                   (caller_name, caller_file, caller_line,
                    callee_name, callee_full, callee_line,
                    file_path, language)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge["caller_name"],
                    rel_path,
                    edge["caller_line"],
                    edge["callee_name"],
                    edge["callee_full"],
                    edge["callee_line"],
                    rel_path,
                    r["language"],
                ),
            )

        # Feature 1 (Synapse) — write imports rows for this file. Done
        # on the writer thread so the worker IPC envelope stays small.
        imports_list = json.loads(r.get("imports_json", "[]"))
        self._write_imports_for_file(conn, rel_path, r["language"], imports_list)

        # Feature 2 (Temporal Activation): only this writer thread runs
        # git. Workers stay focused on parse + extract; subprocess in a
        # multiprocess pool would deadlock against git's index lock.
        if include_activation:
            self._write_activation_for_file(conn, rel_path, inserted_symbol_rows)
        else:
            self._clear_activation_for_file(conn, rel_path)

        # NOTE: Synapse resolver pass is NOT run per-file in the parallel
        # writer. The whole-project resolver pass at the end of
        # ``index_project`` does it once with the full context, which is
        # both correct (sees every file's symbols + imports) and cheap.

    @staticmethod
    def _clear_activation_for_file(conn: sqlite3.Connection, rel_path: str) -> None:
        """Drop stale activation rows when project indexing runs in fast mode."""
        try:
            conn.execute(
                "DELETE FROM ast_symbol_activation WHERE file_path = ?",
                (rel_path,),
            )
        except sqlite3.OperationalError:
            pass

    def lookup(self, file_path: str) -> dict[str, Any] | None:
        try:
            rel = os.path.relpath(
                os.path.abspath(file_path), self.project_root
            ).replace("\\", "/")
        except ValueError:
            # Windows: path on a different drive than project_root.
            return None
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM ast_index WHERE file_path = ?",
            (rel,),
        ).fetchone()
        if row is None:
            return None
        return {
            "file": row["file_path"],
            "content_hash": row["content_hash"],
            "language": row["language"],
            "symbols": json.loads(row["symbols_json"]),
            "imports": json.loads(row["imports_json"]),
            "structure": json.loads(row["structure_json"]),
            "indexed_at": row["indexed_at"],
        }

    def search_symbols(
        self, query: str, language: str | None = None
    ) -> list[dict[str, Any]]:
        if self._fts5_available:
            return self.fts_search(query, language=language)
        return self._search_symbols_linear(query, language)

    def fts_search(
        self,
        query: str,
        language: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self._fts5_available:
            return self._search_symbols_linear(query, language)

        conn = self._get_conn()
        fts_query = " OR ".join(f'"{term}"' for term in query.split() if term)
        if not fts_query:
            fts_query = f'"{query}"'

        if language:
            sql = """
                SELECT r.name, r.kind, r.file_path, r.language, r.line, r.end_line
                FROM ast_symbols_fts f
                JOIN ast_symbol_rows r ON f.rowid = r.id
                WHERE ast_symbols_fts MATCH ? AND r.language = ?
                ORDER BY rank
                LIMIT ?
            """
            rows = conn.execute(sql, (fts_query, language, limit)).fetchall()
        else:
            sql = """
                SELECT r.name, r.kind, r.file_path, r.language, r.line, r.end_line
                FROM ast_symbols_fts f
                JOIN ast_symbol_rows r ON f.rowid = r.id
                WHERE ast_symbols_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            rows = conn.execute(sql, (fts_query, limit)).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "name": row["name"],
                    "kind": row["kind"],
                    "file": row["file_path"],
                    "language": row["language"],
                    "line": row["line"],
                    "end_line": row["end_line"],
                }
            )
        return results

    def _search_symbols_linear(
        self, query: str, language: str | None = None
    ) -> list[dict[str, Any]]:
        conn = self._get_conn()
        if language:
            rows = conn.execute(
                "SELECT file_path, symbols_json, language FROM ast_index WHERE language = ?",
                (language,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT file_path, symbols_json, language FROM ast_index"
            ).fetchall()

        results: list[dict[str, Any]] = []
        query_lower = query.lower()
        for row in rows:
            symbols = json.loads(row["symbols_json"])
            for sym in symbols.get("symbols", []):
                name = sym.get("name", sym.get("text", ""))
                if query_lower in name.lower():
                    results.append(
                        {
                            "file": row["file_path"],
                            "language": row["language"],
                            **sym,
                        }
                    )
        return results

    def get_stats(self) -> dict[str, Any]:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as c FROM ast_index").fetchone()["c"]
        by_lang = conn.execute(
            "SELECT language, COUNT(*) as c FROM ast_index GROUP BY language ORDER BY c DESC"
        ).fetchall()
        total_symbols: int | None = None
        if self._fts5_available:
            try:
                total_symbols = conn.execute(
                    "SELECT COUNT(*) as c FROM ast_symbol_rows"
                ).fetchone()["c"]
            except sqlite3.OperationalError:
                total_symbols = None
        if total_symbols is None:
            total_symbols = 0
            for row in conn.execute("SELECT symbols_json FROM ast_index").fetchall():
                syms = json.loads(row["symbols_json"])
                total_symbols += len(syms.get("symbols", []))
        stats: dict[str, Any] = {
            "total_files": total,
            "total_symbols": total_symbols,
            "by_language": {r["language"]: r["c"] for r in by_lang},
            "db_path": self.db_path,
            "fts5_available": bool(self._fts5_available),
        }
        if self._fts5_available:
            try:
                stats["fts_indexed_symbols"] = total_symbols
            except sqlite3.OperationalError:
                pass
        return stats

    def invalidate(self, file_path: str) -> bool:
        try:
            rel = os.path.relpath(
                os.path.abspath(file_path), self.project_root
            ).replace("\\", "/")
        except ValueError:
            # Windows: path on a different drive than project_root.
            return False
        conn = self._get_conn()
        if self._fts5_available:
            conn.execute("DELETE FROM ast_symbols_fts WHERE file_path = ?", (rel,))
            conn.execute("DELETE FROM ast_symbol_rows WHERE file_path = ?", (rel,))
        conn.execute("DELETE FROM ast_call_edges WHERE file_path = ?", (rel,))
        cursor = conn.execute("DELETE FROM ast_index WHERE file_path = ?", (rel,))
        conn.commit()
        return cursor.rowcount > 0

    def get_call_edges(self) -> list[dict[str, Any]]:
        """Return all stored call edges from the cache."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT caller_name, caller_file, caller_line, "
                "callee_name, callee_full, callee_line, file_path, language "
                "FROM ast_call_edges"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]

    def get_functions(self) -> list[dict[str, Any]]:
        """Return all indexed function definitions."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, symbols_json, language FROM ast_index"
        ).fetchall()
        functions: list[dict[str, Any]] = []
        for row in rows:
            symbols = json.loads(row["symbols_json"])
            for sym in symbols.get("symbols", []):
                if sym.get("kind") == "function":
                    functions.append(
                        {
                            "name": sym["name"],
                            "file": row["file_path"],
                            "line": sym.get("line", 0),
                            "end_line": sym.get("end_line", 0),
                            "language": row["language"],
                            "params": sym.get("params", ""),
                        }
                    )
        return functions

    def get_functions_by_file(self, file_path: str) -> list[dict[str, Any]]:
        """Return indexed function definitions for a specific file."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT symbols_json, language FROM ast_index WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        if row is None:
            return []
        symbols = json.loads(row["symbols_json"])
        return [
            {
                "name": sym["name"],
                "file": file_path,
                "line": sym.get("line", 0),
                "end_line": sym.get("end_line", 0),
                "language": row["language"],
                "params": sym.get("params", ""),
            }
            for sym in symbols.get("symbols", [])
            if sym.get("kind") == "function"
        ]

    def get_imports(self) -> dict[str, Any]:
        """Return per-file import lists from the cache.

        Returns dict mapping relative file path -> list of import entries.
        Entries are typically strings, but historical caches may contain
        dicts; callers must defensively check ``isinstance(item, str)``.
        Used by CachedCallGraph for import-aware cross-file call resolution.
        """
        conn = self._get_conn()
        rows = conn.execute("SELECT file_path, imports_json FROM ast_index").fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            result[row["file_path"]] = json.loads(row["imports_json"])
        return result

    def query_callers(
        self,
        callee_name: str,
        callee_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """SQL-native callers lookup — instant O(k) query, no graph build.

        Finds functions that call ``callee_name`` by querying the
        ``ast_call_edges`` table directly.  Supports transitive lookups
        via BFS when ``max_depth > 1``.

        Returns list of dicts with keys: caller_name, caller_file,
        caller_line, callee_name, callee_file, callee_line, depth.
        """
        conn = self._get_conn()
        # Normalise Windows backslash paths so callers can pass
        # ``src/a.py`` regardless of host OS.
        if callee_file:
            callee_file = callee_file.replace("\\", "/")
        try:
            return self._bfs_callers(conn, callee_name, callee_file, max_depth)
        except sqlite3.OperationalError:
            return []

    def _bfs_callers(
        self,
        conn: sqlite3.Connection,
        callee_name: str,
        callee_file: str | None,
        max_depth: int,
    ) -> list[dict[str, Any]]:
        visited: set[str] = set()
        result: list[dict[str, Any]] = []
        queue: list[tuple[str, str | None, int]] = [(callee_name, callee_file, 0)]
        while queue:
            current_name, current_file, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            if current_file:
                rows = conn.execute(
                    "SELECT caller_name, caller_file, caller_line, "
                    "callee_name, callee_full, file_path, callee_line, "
                    "callee_resolved_file "
                    "FROM ast_call_edges "
                    "WHERE (callee_name = ? OR callee_full = ?) "
                    "AND callee_resolved_file = ?",
                    (current_name, current_name, current_file),
                ).fetchall()
                if not rows:
                    rows = conn.execute(
                        "SELECT caller_name, caller_file, caller_line, "
                        "callee_name, callee_full, file_path, callee_line, "
                        "callee_resolved_file "
                        "FROM ast_call_edges "
                        "WHERE (callee_name = ? OR callee_full = ?) "
                        "AND file_path = ?",
                        (current_name, current_name, current_file),
                    ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT caller_name, caller_file, caller_line, "
                    "callee_name, callee_full, file_path, callee_line, "
                    "callee_resolved_file "
                    "FROM ast_call_edges WHERE callee_name = ? OR callee_full = ?",
                    (current_name, current_name),
                ).fetchall()
            for row in rows:
                key = f"{row['caller_file']}:{row['caller_name']}:{row['caller_line']}"
                if key in visited:
                    continue
                visited.add(key)
                callee_file_val = row["callee_resolved_file"] or row["file_path"]
                entry: dict[str, Any] = {
                    "caller_name": row["caller_name"],
                    "caller_file": row["caller_file"],
                    "caller_line": row["caller_line"],
                    "callee_name": row["callee_name"],
                    "callee_full": row["callee_full"],
                    "callee_file": callee_file_val,
                    "callee_line": row["callee_line"],
                    "depth": depth + 1,
                }
                result.append(entry)
                if max_depth > 1:
                    queue.append((row["caller_name"], row["caller_file"], depth + 1))
        return result

    def query_callees(
        self,
        caller_name: str,
        caller_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """SQL-native callees lookup — instant O(k) query, no graph build.

        Finds functions called by ``caller_name`` by querying the
        ``ast_call_edges`` table directly.  Supports transitive lookups
        via BFS when ``max_depth > 1``.

        Returns list of dicts with keys: caller_name, caller_file,
        caller_line, callee_name, callee_file, callee_line, depth.
        """
        conn = self._get_conn()
        if caller_file:
            caller_file = caller_file.replace("\\", "/")
        try:
            return self._bfs_callees(conn, caller_name, caller_file, max_depth)
        except sqlite3.OperationalError:
            return []

    def _bfs_callees(
        self,
        conn: sqlite3.Connection,
        caller_name: str,
        caller_file: str | None,
        max_depth: int,
    ) -> list[dict[str, Any]]:
        visited: set[str] = set()
        result: list[dict[str, Any]] = []
        queue: list[tuple[str, str | None, int]] = [(caller_name, caller_file, 0)]
        while queue:
            current_name, current_file, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            if current_file:
                rows = conn.execute(
                    "SELECT caller_name, caller_file, caller_line, "
                    "callee_name, callee_full, file_path, callee_line, callee_resolved_file "
                    "FROM ast_call_edges "
                    "WHERE caller_name = ? AND caller_file = ?",
                    (current_name, current_file),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT caller_name, caller_file, caller_line, "
                    "callee_name, callee_full, file_path, callee_line, callee_resolved_file "
                    "FROM ast_call_edges WHERE caller_name = ?",
                    (current_name,),
                ).fetchall()
            for row in rows:
                key = f"{row['callee_name']}:{row['file_path']}:{row['callee_line']}"
                if key in visited:
                    continue
                visited.add(key)
                callee_file_val = row["callee_resolved_file"] or row["file_path"]
                entry: dict[str, Any] = {
                    "caller_name": row["caller_name"],
                    "caller_file": row["caller_file"],
                    "caller_line": row["caller_line"],
                    "callee_name": row["callee_name"],
                    "callee_full": row["callee_full"],
                    "callee_file": callee_file_val,
                    "callee_line": row["callee_line"],
                    "depth": depth + 1,
                }
                result.append(entry)
                if max_depth > 1:
                    queue.append((row["callee_name"], None, depth + 1))
        return result

    def has_call_edges(self) -> bool:
        """Check whether the cache contains any call edge data."""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT COUNT(*) as c FROM ast_call_edges").fetchone()
            return bool(row["c"] > 0)
        except sqlite3.OperationalError:
            return False

    def get_cross_file_resolver(self) -> Any:
        """Get (or build) the CrossFileResolver for import-aware resolution."""
        resolver = getattr(self, "_cross_file_resolver", None)
        if resolver is None:
            from .cross_file_resolver import CrossFileResolver

            resolver = CrossFileResolver(self)
            self._cross_file_resolver = resolver
        return resolver

    def query_callers_enhanced(
        self,
        callee_name: str,
        callee_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Enhanced callers lookup with cross-file import resolution.

        Like query_callers but fixes empty caller names by finding the
        enclosing function, and adds callee_resolved_file for cross-file
        calls resolved through import chains.
        """
        raw = self.query_callers(callee_name, callee_file, max_depth)
        if not raw:
            return raw
        resolver = self.get_cross_file_resolver()
        for entry in raw:
            if not entry.get("caller_name"):
                name, line = resolver.find_caller_function(
                    entry.get("callee_line", 0), entry.get("caller_file", "")
                )
                if name:
                    entry["caller_name"] = name
                    entry["caller_line"] = line
        return raw

    def query_callees_enhanced(
        self,
        caller_name: str,
        caller_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Enhanced callees lookup with cross-file import resolution.

        Like query_callees but adds callee_resolved_file showing where
        the callee is actually defined (resolved through import chains).
        """
        raw = self.query_callees(caller_name, caller_file, max_depth)
        if not raw:
            return raw
        resolver = self.get_cross_file_resolver()
        for entry in raw:
            callee_name = entry.get("callee_name", "")
            source_file = entry.get("caller_file", "")
            candidates = resolver.resolve_callee(callee_name, source_file)
            if candidates:
                entry["callee_resolved_file"] = candidates[0][0]
                entry["confidence"] = candidates[0][1]
        return raw

    def backfill_cross_file_edges(self) -> dict[str, Any]:
        """Resolve cross-file call edges and persist callee_resolved_file.

        Uses CrossFileResolver to re-resolve all call edges with import-aware
        symbol resolution, then writes the resolved callee file back to the
        ``ast_call_edges`` table. After backfill, cross-file callers/callees
        queries return accurate results instead of bare names.

        Returns dict with ``total``, ``resolved``, ``unchanged``, ``errors``.
        """
        from .cross_file_resolver import CrossFileResolver

        resolver = CrossFileResolver(self)
        resolver.build()
        resolved_edges = resolver.resolve_call_edges()

        conn = self._get_conn()
        total = len(resolved_edges)
        resolved = 0
        unchanged = 0
        errors = 0

        try:
            for edge in resolved_edges:
                callee_resolved = edge.callee_resolved_file
                if not callee_resolved:
                    unchanged += 1
                    continue
                try:
                    cursor = conn.execute(
                        "UPDATE ast_call_edges SET callee_resolved_file = ? "
                        "WHERE caller_file = ? AND caller_line = ? "
                        "AND callee_name = ? AND callee_line = ?",
                        (
                            callee_resolved,
                            edge.caller_file,
                            edge.caller_line,
                            edge.caller_name,
                            edge.caller_line,
                        ),
                    )
                    if cursor.rowcount > 0:
                        resolved += 1
                    else:
                        unchanged += 1
                except Exception:
                    errors += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return {
            "total": total,
            "resolved": resolved,
            "unchanged": unchanged,
            "errors": errors,
        }

    def get_cross_file_stats(self) -> dict[str, Any]:
        """Return cross-file edge resolution statistics."""
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) as c FROM ast_call_edges").fetchone()[
                "c"
            ]
            resolved = conn.execute(
                "SELECT COUNT(*) as c FROM ast_call_edges "
                "WHERE callee_resolved_file != ''"
            ).fetchone()["c"]
            cross_file = conn.execute(
                "SELECT COUNT(*) as c FROM ast_call_edges "
                "WHERE callee_resolved_file != '' "
                "AND callee_resolved_file != file_path"
            ).fetchone()["c"]
        except sqlite3.OperationalError:
            return {"total": 0, "resolved": 0, "cross_file": 0, "pct": 0.0}
        pct = (cross_file / total * 100) if total > 0 else 0.0
        return {
            "total": total,
            "resolved": resolved,
            "cross_file": cross_file,
            "pct": round(pct, 2),
        }

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


def _walk_source_files(project_root: str) -> Iterator[str]:
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [
            d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in _EXT_TO_LANG:
                yield os.path.join(dirpath, fname)
