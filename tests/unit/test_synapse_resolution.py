"""RED tests for Feature 1 (Synapse): cross-file callee resolution.

Implementation (``tree_sitter_analyzer/synapse_resolver.py``) does NOT exist
yet — every test in this file is expected to FAIL today (the RED state).

Exercises: schema additions to ast_call_edges + new ast_imports table,
resolver priority (local → self/cls → import → stdlib → single match →
unknown), and the rule that stdlib calls are tagged but NOT entered.

Fixtures under ``tests/fixtures/synapse/`` are copied into a tmp_path
package per test so ASTCache.index_project() sees a realistic project.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "synapse"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _copy_fixture(name: str, dest_dir: Path) -> Path:
    """Copy a single fixture file into ``dest_dir``.

    Returns the absolute path of the copied file.
    """
    src = _FIXTURE_DIR / name
    if not src.is_file():
        raise FileNotFoundError(f"Synapse fixture missing: {src}")
    dst = dest_dir / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return dst


def _make_pkg(tmp_path: Path, files: list[str], pkg_name: str = "synapse_pkg") -> Path:
    """Build a fixture project at ``tmp_path/pkg_name`` with the given files.

    A package ``__init__.py`` is added so relative imports parse correctly.
    Returns the project root (the parent of the package directory) — that
    is the path you pass to ``ASTCache(project_root=...)``.
    """
    pkg = tmp_path / pkg_name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("# synapse test package\n")
    for fname in files:
        _copy_fixture(fname, pkg)
    return tmp_path


def _open_db(cache: ASTCache) -> sqlite3.Connection:
    """Fresh SQLite connection (separate from ASTCache's WAL handle)."""
    conn = sqlite3.connect(cache.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _edges_for_caller(
    conn: sqlite3.Connection, caller_name: str, pkg_name: str = "synapse_pkg"
) -> list[sqlite3.Row]:
    """ast_call_edges rows for ``caller_name``, scoped to the fixture pkg."""
    return conn.execute(
        "SELECT * FROM ast_call_edges "
        "WHERE caller_name = ? AND file_path LIKE ? "
        "ORDER BY caller_line, callee_line",
        (caller_name, f"{pkg_name}%"),
    ).fetchall()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchemaMigration:
    """The cache DB must surface the new columns / table on first init."""

    def test_schema_migration_adds_columns(self, tmp_path: Path) -> None:
        """ast_call_edges has callee_symbol_id / callee_resolution /
        callee_resolved_file, and ast_imports table exists."""
        cache = ASTCache(str(tmp_path))
        try:
            with _open_db(cache) as conn:
                # New columns on ast_call_edges.
                edge_cols = _column_names(conn, "ast_call_edges")
                assert "callee_symbol_id" in edge_cols, (
                    "Expected ast_call_edges.callee_symbol_id column "
                    f"(have: {sorted(edge_cols)})"
                )
                assert "callee_resolution" in edge_cols, (
                    "Expected ast_call_edges.callee_resolution column "
                    f"(have: {sorted(edge_cols)})"
                )
                assert "callee_resolved_file" in edge_cols, (
                    "Expected ast_call_edges.callee_resolved_file column "
                    f"(have: {sorted(edge_cols)})"
                )

                # New ast_imports table exists with the documented columns.
                assert _table_exists(conn, "ast_imports"), (
                    "Expected ast_imports table to be created on cache init"
                )
                import_cols = _column_names(conn, "ast_imports")
                for required in (
                    "file_path",
                    "language",
                    "module_path",
                    "local_name",
                    "is_relative",
                    "is_star",
                    "alias_of",
                ):
                    assert required in import_cols, (
                        f"Expected ast_imports.{required} (have: {sorted(import_cols)})"
                    )
        finally:
            cache.close()

    def test_callee_resolution_default_is_unknown(self, tmp_path: Path) -> None:
        """Pre-resolution rows default to callee_resolution='unknown'.

        This guards the backfill path: rows written before the resolver
        runs must look exactly like rows the resolver tagged as 'unknown'.
        """
        cache = ASTCache(str(tmp_path))
        try:
            with _open_db(cache) as conn:
                # Insert minimal row with only the legacy columns set.
                conn.execute(
                    "INSERT INTO ast_call_edges "
                    "(caller_name, caller_file, caller_line, callee_name, "
                    " callee_full, callee_line, file_path, language) "
                    "VALUES ('f', 'x.py', 1, 'g', '', 2, 'x.py', 'python')"
                )
                conn.commit()
                row = conn.execute(
                    "SELECT callee_resolution, callee_resolved_file, "
                    "callee_symbol_id FROM ast_call_edges"
                ).fetchone()
                assert row["callee_resolution"] == "unknown"
                assert row["callee_resolved_file"] == ""
                assert row["callee_symbol_id"] is None
        finally:
            cache.close()


# ---------------------------------------------------------------------------
# Resolver — happy paths
# ---------------------------------------------------------------------------


class TestResolveLocal:
    """Resolution priority 1: file-local symbol → 'local'."""

    def test_resolve_local_function_call_persists_symbol_id(
        self, tmp_path: Path
    ) -> None:
        """`foo` calling `bar` in the same file resolves to bar's row id."""
        proj = _make_pkg(tmp_path, ["local_calls.py"])
        cache = ASTCache(str(proj))
        try:
            cache.index_project()
            with _open_db(cache) as conn:
                # Look up bar's symbol_id so the edge can be compared.
                bar_row = conn.execute(
                    "SELECT id, file_path FROM ast_symbol_rows "
                    "WHERE name = 'bar' AND kind IN ('function','method')"
                ).fetchone()
                assert bar_row is not None, "expected `bar` to be indexed"

                edges = _edges_for_caller(conn, "foo")
                # Filter to the specific edge for `bar()`.
                bar_edges = [e for e in edges if e["callee_name"] == "bar"]
                assert bar_edges, (
                    f"expected an edge foo -> bar, got: {[dict(e) for e in edges]}"
                )
                edge = bar_edges[0]
                assert edge["callee_resolution"] == "local"
                assert edge["callee_symbol_id"] == bar_row["id"]
                assert edge["callee_resolved_file"].endswith("local_calls.py"), (
                    f"callee_resolved_file should end with local_calls.py, "
                    f"got {edge['callee_resolved_file']!r}"
                )
        finally:
            cache.close()

    def test_method_resolution_via_self(self, tmp_path: Path) -> None:
        """`self.m2()` inside m1 resolves to the m2 method on the same class."""
        proj = _make_pkg(tmp_path, ["inheritance.py"])
        cache = ASTCache(str(proj))
        try:
            cache.index_project()
            with _open_db(cache) as conn:
                m2_row = conn.execute(
                    "SELECT id FROM ast_symbol_rows "
                    "WHERE name = 'm2' AND kind IN ('function','method')"
                ).fetchone()
                assert m2_row is not None, "expected `m2` method to be indexed"

                edges = _edges_for_caller(conn, "m1")
                m2_edges = [e for e in edges if e["callee_name"] in ("m2", "self.m2")]
                assert m2_edges, (
                    f"expected an edge m1 -> m2 via self, got "
                    f"{[dict(e) for e in edges]}"
                )
                edge = m2_edges[0]
                assert edge["callee_resolution"] == "local"
                assert edge["callee_symbol_id"] == m2_row["id"]
                assert edge["callee_resolved_file"].endswith("inheritance.py")
        finally:
            cache.close()


class TestResolveCrossFile:
    """Resolution priority 3: imported name → 'project' with target file."""

    def test_resolve_cross_file_via_from_import(self, tmp_path: Path) -> None:
        """`from .b import baz` makes baz() resolve to b.py."""
        proj = _make_pkg(tmp_path, ["a.py", "b.py"])
        cache = ASTCache(str(proj))
        try:
            cache.index_project()
            with _open_db(cache) as conn:
                baz_row = conn.execute(
                    "SELECT id, file_path FROM ast_symbol_rows "
                    "WHERE name = 'baz' AND kind IN ('function','method')"
                ).fetchone()
                assert baz_row is not None, "expected `baz` to be indexed in b.py"

                edges = _edges_for_caller(conn, "caller")
                baz_edges = [e for e in edges if e["callee_name"] == "baz"]
                assert baz_edges, (
                    f"expected an edge caller -> baz, got {[dict(e) for e in edges]}"
                )
                edge = baz_edges[0]
                assert edge["callee_resolution"] == "project"
                assert edge["callee_symbol_id"] == baz_row["id"]
                assert edge["callee_resolved_file"].endswith("b.py")
                # Cross-file: resolved file must differ from the caller's file.
                assert edge["callee_resolved_file"] != edge["file_path"]
        finally:
            cache.close()

    def test_qualified_call_module_alias(self, tmp_path: Path) -> None:
        """`bb.baz()` after `from . import b as bb` resolves to b.py."""
        proj = _make_pkg(tmp_path, ["module_alias.py", "b.py"])
        cache = ASTCache(str(proj))
        try:
            cache.index_project()
            with _open_db(cache) as conn:
                baz_row = conn.execute(
                    "SELECT id FROM ast_symbol_rows WHERE name = 'baz'"
                ).fetchone()
                assert baz_row is not None

                edges = _edges_for_caller(conn, "use_alias")
                # Implementation may store the call as either "baz" or
                # "bb.baz" depending on whether qualifiers are stripped.
                baz_edges = [
                    e
                    for e in edges
                    if e["callee_name"] in ("baz", "bb.baz")
                    or (e["callee_full"] and "baz" in e["callee_full"])
                ]
                assert baz_edges, (
                    f"expected an edge use_alias -> baz via bb alias, "
                    f"got {[dict(e) for e in edges]}"
                )
                edge = baz_edges[0]
                assert edge["callee_resolution"] == "project"
                assert edge["callee_resolved_file"].endswith("b.py")
                assert edge["callee_symbol_id"] == baz_row["id"]
        finally:
            cache.close()

    def test_cross_file_edge_count_nonzero_after_index(self, tmp_path: Path) -> None:
        """After indexing a multi-file fixture, at least one 'project'
        edge exists where the caller file != callee_resolved_file."""
        proj = _make_pkg(tmp_path, ["a.py", "b.py"])
        cache = ASTCache(str(proj))
        try:
            cache.index_project()
            with _open_db(cache) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) AS c FROM ast_call_edges "
                    "WHERE callee_resolution = 'project' "
                    "AND callee_resolved_file != '' "
                    "AND callee_resolved_file != file_path"
                ).fetchone()["c"]
                assert count > 0, (
                    "expected at least one cross-file 'project' edge after "
                    "indexing a.py + b.py"
                )
        finally:
            cache.close()


# ---------------------------------------------------------------------------
# Resolver — stdlib and unknown
# ---------------------------------------------------------------------------


class TestResolveStdlib:
    """Resolution priority 4: stdlib allowlist → 'stdlib', not entered."""

    def test_resolve_stdlib_path_tagged_not_entered(self, tmp_path: Path) -> None:
        """`Path('x')` after `from pathlib import Path` is tagged stdlib;
        no `Path` row is inserted into ast_symbol_rows."""
        proj = _make_pkg(tmp_path, ["stdlib_use.py"])
        cache = ASTCache(str(proj))
        try:
            cache.index_project()
            with _open_db(cache) as conn:
                edges = _edges_for_caller(conn, "make_path")
                path_edges = [e for e in edges if e["callee_name"] == "Path"]
                assert path_edges, (
                    f"expected an edge make_path -> Path, got "
                    f"{[dict(e) for e in edges]}"
                )
                edge = path_edges[0]
                assert edge["callee_resolution"] == "stdlib"
                assert edge["callee_symbol_id"] is None, (
                    "stdlib callees should NOT have a symbol_id (we don't "
                    "index the stdlib)"
                )

                # And the stdlib symbol must NOT have been inserted into
                # ast_symbol_rows. We do not enter stdlib definitions.
                path_sym = conn.execute(
                    "SELECT id FROM ast_symbol_rows WHERE name = 'Path'"
                ).fetchone()
                assert path_sym is None, (
                    "stdlib name `Path` must not be indexed as a project symbol row"
                )
        finally:
            cache.close()


class TestResolveUnknown:
    """Resolution priority 6: nothing matched → 'unknown'."""

    def test_unknown_callee_fallback(self, tmp_path: Path) -> None:
        """A call to an undefined/non-imported name resolves to 'unknown'."""
        proj = _make_pkg(tmp_path, ["unknown_callee.py"])
        cache = ASTCache(str(proj))
        try:
            cache.index_project()
            with _open_db(cache) as conn:
                edges = _edges_for_caller(conn, "caller")
                mystery_edges = [e for e in edges if e["callee_name"] == "mystery_func"]
                assert mystery_edges, (
                    f"expected an edge caller -> mystery_func, got "
                    f"{[dict(e) for e in edges]}"
                )
                edge = mystery_edges[0]
                assert edge["callee_resolution"] == "unknown"
                assert edge["callee_symbol_id"] is None
                assert edge["callee_resolved_file"] == ""
        finally:
            cache.close()


# ---------------------------------------------------------------------------
# Resolver module surface (RED — module does not exist yet)
# ---------------------------------------------------------------------------


class TestResolverModuleSurface:
    """The new ``tree_sitter_analyzer.synapse_resolver`` module must export
    ``ResolverContext`` and ``resolve_callee``.

    NOTE: we deliberately do NOT use ``pytest.importorskip`` here — per the
    RED-test convention these MUST fail today with ImportError, not skip.
    They turn green once the resolver module ships.
    """

    @pytest.mark.parametrize("attr", ["ResolverContext", "resolve_callee"])
    def test_public_api_present(self, attr: str) -> None:
        from tree_sitter_analyzer import synapse_resolver  # noqa: F401

        assert hasattr(synapse_resolver, attr), f"synapse_resolver must export {attr!r}"

    def test_resolve_callee_returns_expected_tuple_shape(self, tmp_path: Path) -> None:
        """`resolve_callee` returns a value with the documented attributes."""
        from tree_sitter_analyzer import synapse_resolver

        proj = _make_pkg(tmp_path, ["local_calls.py"])
        cache = ASTCache(str(proj))
        try:
            cache.index_project()
            # The exact constructor is up to the impl; the test asserts only
            # what the spec requires: that we can build a context bound to
            # the project + cache and pass it to resolve_callee.
            ctx = synapse_resolver.ResolverContext(project_root=str(proj), cache=cache)
            caller_file = "synapse_pkg/local_calls.py"
            resolved = synapse_resolver.resolve_callee("bar", caller_file, ctx)
            # ResolvedCallee dataclass with these three attributes per spec.
            assert hasattr(resolved, "callee_symbol_id")
            assert hasattr(resolved, "resolution")
            assert hasattr(resolved, "resolved_file")
            assert resolved.resolution == "local"
            assert resolved.resolved_file.endswith("local_calls.py")
        finally:
            cache.close()


# ---------------------------------------------------------------------------
# Star imports — bookkeeping only
# ---------------------------------------------------------------------------


class TestStarImportBookkeeping:
    """Star imports MUST be recorded in ast_imports with is_star=1.

    Whether the resolver promotes `baz()` from 'unknown' to 'project' is an
    impl choice we do not pin here; that's a separate test/decision.
    """

    def test_star_import_recorded(self, tmp_path: Path) -> None:
        proj = _make_pkg(tmp_path, ["star_imports.py", "b.py"])
        cache = ASTCache(str(proj))
        try:
            cache.index_project()
            with _open_db(cache) as conn:
                row = conn.execute(
                    "SELECT is_star, module_path, is_relative FROM ast_imports "
                    "WHERE file_path LIKE ? AND is_star = 1",
                    ("synapse_pkg/star_imports.py",),
                ).fetchone()
                assert row is not None, (
                    "expected ast_imports to record the `from .b import *` "
                    "as a star import"
                )
                assert row["is_star"] == 1
                # Module path should reference the sibling module `b`. The
                # exact storage (`.b`, `b`, or `synapse_pkg.b`) is an impl
                # choice; we just require `b` appears somewhere.
                assert "b" in (row["module_path"] or ""), (
                    f"unexpected module_path: {row['module_path']!r}"
                )
                assert row["is_relative"] == 1, "from .b import * is a relative import"
        finally:
            cache.close()
