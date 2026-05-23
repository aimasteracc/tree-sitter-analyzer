"""Schema-version table + post-init self-check tests.

Guards against the silent-migration-drop class of bug: a missing ALTER
TABLE in a parallel-edit conflict leaves the DB without an expected
column. The version table records every ``_SCHEMA_V*`` block as it
applies; the self-check raises ``SchemaIntegrityError`` if any expected
table or column is missing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import (
    _EXPECTED_SCHEMA_VERSIONS,
    ASTCache,
    SchemaIntegrityError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_db(cache: ASTCache) -> sqlite3.Connection:
    """Fresh SQLite handle separate from the WAL-mode cache connection."""
    conn = sqlite3.connect(cache.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _seed_healthy_db(db_path: str) -> None:
    """Build a complete, healthy cache DB at ``db_path`` and close it.

    Subsequent helpers operate via a raw SQLite handle (NOT via ASTCache)
    so we can simulate a damaged DB without triggering migrations.
    """
    cache = ASTCache(str(Path(db_path).parent.parent), db_path=db_path)
    cache.close()


def _seed_legacy_db_without_version_table(db_path: str) -> None:
    """Healthy DB then DELETE every ast_schema_version row — simulates a
    cache file produced before the version-table code shipped."""
    _seed_healthy_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM ast_schema_version")
        conn.commit()
    finally:
        conn.close()


def _drop_column_raw(db_path: str, table: str, column_to_drop: str) -> None:
    """Drop a column via raw connection (CREATE-AS-SELECT rename trick).

    SQLite < 3.35 lacks ``ALTER TABLE ... DROP COLUMN``. Never opens an
    ``ASTCache`` — that would trigger ``_init_db`` and either heal or
    raise before we can stage the damaged state.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cols = _column_names(conn, table)
        assert column_to_drop in cols, (
            f"Pre-seed sanity: expected {table}.{column_to_drop} to exist "
            f"(have: {sorted(cols)})"
        )
        keep_cols = [c for c in cols if c != column_to_drop]
        cols_csv = ", ".join(keep_cols)
        conn.executescript(
            f"""
            CREATE TABLE {table}__new AS SELECT {cols_csv} FROM {table};
            DROP TABLE {table};
            ALTER TABLE {table}__new RENAME TO {table};
            """
        )
        conn.commit()
    finally:
        conn.close()


def _drop_table_raw(db_path: str, table: str) -> None:
    """Drop ``table`` via a raw connection (no ASTCache open)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
    finally:
        conn.close()


def _make_proj(tmp_path: Path) -> tuple[Path, Path]:
    """Return (proj_root, db_path) with the .ast-cache dir pre-created."""
    proj_root = tmp_path / "proj"
    proj_root.mkdir()
    db_path = proj_root / ".ast-cache" / "index.db"
    db_path.parent.mkdir(parents=True)
    return proj_root, db_path


# ---------------------------------------------------------------------------
# Fresh DB — all expected versions land cleanly
# ---------------------------------------------------------------------------


class TestFreshDb:
    def test_fresh_db_applies_all_versions(self, tmp_path: Path) -> None:
        """A brand-new ASTCache stamps every expected version row."""
        cache = ASTCache(str(tmp_path))
        try:
            with _open_db(cache) as conn:
                rows = conn.execute(
                    "SELECT version, description FROM ast_schema_version "
                    "ORDER BY version"
                ).fetchall()
                versions = {row["version"]: row["description"] for row in rows}
            for expected_version, expected_desc, _ in _EXPECTED_SCHEMA_VERSIONS:
                assert expected_version in versions, (
                    f"Expected schema version {expected_version} "
                    f"({expected_desc}) (have: {sorted(versions.keys())})"
                )
                assert versions[expected_version] == expected_desc
        finally:
            cache.close()

    def test_fresh_db_self_check_passes(self, tmp_path: Path) -> None:
        """Constructing ASTCache on a fresh dir must not raise."""
        cache = ASTCache(str(tmp_path))
        try:
            with _open_db(cache) as conn:
                row = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='ast_schema_version'"
                ).fetchone()
                assert row is not None, "ast_schema_version table missing"
        finally:
            cache.close()


# ---------------------------------------------------------------------------
# Damaged DB — self-check raises
# ---------------------------------------------------------------------------


class TestSelfCheckDetection:
    def test_self_check_detects_missing_column(self, tmp_path: Path) -> None:
        """Drop callee_resolution from ast_call_edges → SchemaIntegrityError.

        The exact bug being closed: a missing ALTER TABLE leaves
        ast_call_edges without callee_resolution. The check must catch
        this on open instead of letting query-time fail downstream.
        """
        proj_root, db_path = _make_proj(tmp_path)
        _seed_healthy_db(str(db_path))
        _drop_column_raw(str(db_path), "ast_call_edges", "callee_resolution")

        with pytest.raises(SchemaIntegrityError) as exc_info:
            ASTCache(str(proj_root), db_path=str(db_path))

        err_msg = str(exc_info.value)
        assert "ast_call_edges.callee_resolution" in err_msg, (
            f"Expected error to name the missing column (got: {err_msg!r})"
        )
        assert str(db_path) in err_msg, (
            f"Expected error to include the cache DB path; got: {err_msg!r}"
        )

    def test_self_check_detects_missing_table(self, tmp_path: Path) -> None:
        """Drop ast_imports → SchemaIntegrityError."""
        proj_root, db_path = _make_proj(tmp_path)
        _seed_healthy_db(str(db_path))
        _drop_table_raw(str(db_path), "ast_imports")

        with pytest.raises(SchemaIntegrityError) as exc_info:
            ASTCache(str(proj_root), db_path=str(db_path))

        assert "ast_imports" in str(exc_info.value), (
            f"Expected error to mention ast_imports (got: {exc_info.value!r})"
        )

    def test_self_check_error_message_lists_all_problems(self, tmp_path: Path) -> None:
        """Multiple missing things → error lists ALL of them in one raise.

        Don't fail-fast on the first miss — agents need to see every
        problem so they can remediate in one pass.
        """
        proj_root, db_path = _make_proj(tmp_path)
        _seed_healthy_db(str(db_path))
        # Raw helpers so migrations never run between drops (which would
        # heal the first drop before we could stage the second).
        _drop_column_raw(str(db_path), "ast_call_edges", "callee_resolution")
        _drop_column_raw(str(db_path), "ast_call_edges", "callee_resolved_file")
        _drop_table_raw(str(db_path), "ast_symbol_activation")

        with pytest.raises(SchemaIntegrityError) as exc_info:
            ASTCache(str(proj_root), db_path=str(db_path))

        err_msg = str(exc_info.value)
        for needle in (
            "ast_call_edges.callee_resolution",
            "ast_call_edges.callee_resolved_file",
            "ast_symbol_activation",
        ):
            assert needle in err_msg, (
                f"Expected {needle!r} in error message; got: {err_msg!r}"
            )


# ---------------------------------------------------------------------------
# Legacy DB recovery
# ---------------------------------------------------------------------------


class TestLegacyRecovery:
    def test_legacy_db_without_version_table_is_recovered(self, tmp_path: Path) -> None:
        """All tables present + empty ast_schema_version → backfilled on
        re-open instead of raising. Simulates a cache file from the
        previous binary opened by code shipping the version table for
        the first time.
        """
        proj_root, db_path = _make_proj(tmp_path)
        _seed_legacy_db_without_version_table(str(db_path))

        # Pre-condition: registry is empty.
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM ast_schema_version"
            ).fetchone()["c"]
            assert count == 0, (
                f"Pre-seed sanity: expected empty registry, got {count} rows"
            )

        # Re-open: must NOT raise; must backfill the registry.
        cache = ASTCache(str(proj_root), db_path=str(db_path))
        try:
            with _open_db(cache) as conn:
                rows = conn.execute(
                    "SELECT version FROM ast_schema_version ORDER BY version"
                ).fetchall()
                versions = {row["version"] for row in rows}
            for expected_version, _desc, _exp in _EXPECTED_SCHEMA_VERSIONS:
                assert expected_version in versions, (
                    f"Recovery failed to backfill v{expected_version} "
                    f"(have: {sorted(versions)})"
                )
        finally:
            cache.close()
