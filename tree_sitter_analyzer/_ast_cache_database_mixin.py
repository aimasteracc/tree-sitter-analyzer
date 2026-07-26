"""Database lifecycle and schema integrity for :mod:`ast_cache`."""

from __future__ import annotations

import sqlite3
from typing import Any, cast

from .cache.schema import (
    EXPECTED_SCHEMA_VERSIONS as _EXPECTED_SCHEMA_VERSIONS,
)
from .cache.schema import (
    SQL_GET_SCHEMA_VERSION as _SQL_GET_SCHEMA_VERSION,
)
from .cache.schema import (
    apply_large_repo_indexes as _apply_large_repo_indexes,
)
from .cache.schema import (
    apply_migration_v3 as _apply_migration_v3,
)
from .cache.schema import (
    apply_migration_v4 as _apply_migration_v4,
)
from .cache.schema import (
    apply_migration_v5 as _apply_migration_v5,
)
from .cache.schema import (
    apply_migration_v6 as _apply_migration_v6,
)
from .cache.schema import (
    apply_migration_v7 as _apply_migration_v7,
)
from .cache.schema import (
    apply_migration_v8 as _apply_migration_v8,
)
from .cache.schema import (
    apply_migration_v9 as _apply_migration_v9,
)
from .cache.schema import (
    apply_migration_v10 as _apply_migration_v10,
)
from .cache.schema import (
    apply_migration_v11 as _apply_migration_v11,
)
from .cache.schema import (
    apply_migration_v12 as _apply_migration_v12,
)
from .cache.schema import (
    backfill_schema_version_row as _backfill_schema_version_row,
)
from .cache.schema import (
    check_schema_expectations as _check_schema_expectations,
)
from .cache.schema import (
    init_db as _schema_init_db,
)
from .core.parser import Parser


class SchemaIntegrityError(RuntimeError):
    """Raised when the cache cannot prove its expected schema is complete."""


def _schema_version_row(
    conn: sqlite3.Connection,
    version: int,
) -> sqlite3.Row | tuple[Any, ...] | None:
    try:
        return cast(
            sqlite3.Row | tuple[Any, ...] | None,
            conn.execute(_SQL_GET_SCHEMA_VERSION, (version,)).fetchone(),
        )
    except sqlite3.OperationalError:
        return None


def _verify_schema_version(
    conn: sqlite3.Connection,
    version: int,
    description: str,
    expectations: Any,
    missing: list[str],
) -> None:
    payload_ok = _check_schema_expectations(conn, expectations, missing)
    row = _schema_version_row(conn, version)
    if row is None and payload_ok:
        _backfill_schema_version_row(conn, version, description, missing)


class ASTCacheSurface:
    """Typed cross-mixin surface implemented by the concrete cache."""

    project_root: str
    db_path: str
    _local: Any
    _parser: Parser
    _fts5_available: bool | None
    _extractor_version: int

    def _get_conn(self) -> sqlite3.Connection:
        raise NotImplementedError

    def call_graph_built(self) -> bool:
        raise NotImplementedError

    def backfill_cross_file_edges(self) -> dict[str, Any]:
        raise NotImplementedError


class ASTCacheDatabaseMixin(ASTCacheSurface):
    """Thread-local connections, migrations, and schema verification."""

    def get_conn(self) -> sqlite3.Connection:
        """Return the lazily configured thread-local SQLite connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-65536")
            conn.execute("PRAGMA mmap_size=268435456")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        """Backward-compatible private alias for :meth:`get_conn`."""
        return self.get_conn()

    @property
    def fts5_available(self) -> bool:
        """Return whether this SQLite build supports FTS5."""
        return bool(self._fts5_available)

    @property
    def parser(self) -> Parser:
        """Return the reusable tree-sitter parser."""
        return self._parser

    def _init_db(self) -> None:
        from . import ast_cache as ast_cache_facade

        conn = self._get_conn()
        migrations = [
            (3, _apply_migration_v3),
            (4, _apply_migration_v4),
            (5, _apply_migration_v5),
            (6, _apply_migration_v6),
            (7, _apply_migration_v7),
            (8, _apply_migration_v8),
            (9, _apply_migration_v9),
            (10, _apply_migration_v10),
            (11, _apply_migration_v11),
            (12, _apply_migration_v12),
        ]
        self._fts5_available = _schema_init_db(
            conn,
            self._fts5_available,
            ast_cache_facade._has_fts5,
            migrations,
        )
        self._verify_schema_integrity(conn)

    @staticmethod
    def _ensure_large_repo_indexes(conn: sqlite3.Connection) -> None:
        """Create non-shape-changing indexes for large-repo query paths."""
        _apply_large_repo_indexes(conn)

    def _verify_schema_integrity(self, conn: sqlite3.Connection) -> None:
        missing: list[str] = []
        for version, description, expectations in _EXPECTED_SCHEMA_VERSIONS:
            _verify_schema_version(
                conn,
                version,
                description,
                expectations,
                missing,
            )
        if not missing:
            return
        remediation = (
            f"Remove the cache DB at {self.db_path!r} and re-index "
            "(e.g. ``rm -rf .ast-cache && uv run python -m "
            "tree_sitter_analyzer --index``)."
        )
        missing_text = "; ".join(missing)
        raise SchemaIntegrityError(
            f"AST cache schema is incomplete. Missing: {missing_text}. {remediation}"
        )

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
