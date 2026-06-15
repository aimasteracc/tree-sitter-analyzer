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
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.callee_resolution import CalleeResolver

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
    """CALLS edges for ``caller_name`` (unified ``edges`` table), scoped to pkg.

    B1.3: CALLS rows + their resolution columns live in ``edges``; ``file_path``
    is the caller's file (== legacy ``ast_call_edges.caller_file``).
    """
    return conn.execute(
        "SELECT * FROM edges "
        "WHERE kind = 'calls' AND caller_name = ? AND file_path LIKE ? "
        "ORDER BY caller_line, callee_line",
        (caller_name, f"{pkg_name}%"),
    ).fetchall()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchemaMigration:
    """The cache DB must surface the new columns / table on first init."""

    def test_schema_migration_adds_columns(self, tmp_path: Path) -> None:
        """The unified ``edges`` table carries callee_symbol_id /
        callee_resolution / callee_resolved_file (B1.3), and ast_imports exists."""
        cache = ASTCache(str(tmp_path))
        try:
            with _open_db(cache) as conn:
                # Resolution columns now live on the unified ``edges`` table.
                edge_cols = _column_names(conn, "edges")
                assert "callee_symbol_id" in edge_cols, (
                    "Expected edges.callee_symbol_id column "
                    f"(have: {sorted(edge_cols)})"
                )
                assert "callee_resolution" in edge_cols, (
                    "Expected edges.callee_resolution column "
                    f"(have: {sorted(edge_cols)})"
                )
                assert "callee_resolved_file" in edge_cols, (
                    "Expected edges.callee_resolved_file column "
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
                # Insert a CALLS edge with only the structural columns set; the
                # resolution columns must default exactly as the resolver's
                # "unknown" verdict (B1.3 — edges, not ast_call_edges).
                conn.execute(
                    "INSERT INTO edges "
                    "(source_node_id, target_node_id, kind, line, caller_name, "
                    " callee_name, file_path, caller_line, callee_line, language) "
                    "VALUES ('x.py:f:1', 'x.py:g:2', 'calls', 2, 'f', 'g', "
                    " 'x.py', 1, 2, 'python')"
                )
                conn.commit()
                row = conn.execute(
                    "SELECT callee_resolution, callee_resolved_file, "
                    "callee_symbol_id FROM edges WHERE kind = 'calls'"
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
                    "SELECT COUNT(*) AS c FROM edges "
                    "WHERE kind = 'calls' AND callee_resolution = 'project' "
                    "AND callee_resolved_file != '' "
                    "AND callee_resolved_file != file_path"
                ).fetchone()["c"]
                assert count == 1, (
                    "expected exactly one cross-file 'project' edge after "
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

    def test_resolve_callee_uses_shared_resolver_for_local_and_import(self) -> None:
        """Synapse keeps its cascade while sharing local/import resolution."""
        from tree_sitter_analyzer import synapse_resolver

        ctx = synapse_resolver.ResolverContext(
            project_root="",
            cache=None,  # type: ignore[arg-type]
            builtins={"python": frozenset()},
            stdlib_modules={"python": frozenset()},
            callee_resolver=CalleeResolver(
                functions_by_name={
                    "bar": [{"name": "bar", "file": "a.py", "id": 1}],
                    "baz": [
                        {"name": "baz", "file": "a.py", "id": 2},
                        {"name": "baz", "file": "b.py", "id": 3},
                    ],
                },
                functions_by_file={
                    "a.py": [
                        {"name": "bar", "file": "a.py", "id": 1},
                        {"name": "baz", "file": "a.py", "id": 2},
                    ],
                    "b.py": [{"name": "baz", "file": "b.py", "id": 3}],
                },
                name_to_source={"a.py": {"bb": "b.py"}},
            ),
        )

        local = synapse_resolver.resolve_callee("bar", "a.py", ctx)
        imported = synapse_resolver.resolve_callee("bb.baz", "a.py", ctx)

        assert local.resolution == "local"
        assert local.callee_symbol_id == 1
        assert imported.resolution == "project"
        assert imported.callee_symbol_id == 3
        assert imported.resolved_file == "b.py"

    def test_convenience_context_loads_lazily_and_reuses_lru_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Constructing ResolverContext should be cheap; first use loads maps."""
        from tree_sitter_analyzer.synapse_resolver import _context

        cache = MagicMock()
        cache.project_root = "/repo"
        cache.db_path = "/repo/.ast-cache/index.db"
        monkeypatch.setattr(
            _context,
            "_cache_identity",
            lambda _cache: ("/repo/.ast-cache/index.db", 1, 2),
        )

        built = _context.ResolverContext(
            project_root="/repo",
            cache=cache,
            file_symbols={"a.py": [("run", "function", 1)]},
            builtins={"python": frozenset()},
            stdlib_modules={"python": frozenset()},
        )
        build = MagicMock(return_value=built)
        monkeypatch.setattr(_context, "_build_resolver_context_uncached", build)
        _context.clear_resolver_context_cache()

        ctx = _context.ResolverContext(project_root="/repo", cache=cache)
        assert build.call_count == 0

        assert ctx.file_symbols == {"a.py": [("run", "function", 1)]}
        assert build.call_count == 1

        ctx2 = _context.ResolverContext(project_root="/repo", cache=cache)
        assert ctx2.file_symbols == {"a.py": [("run", "function", 1)]}
        assert build.call_count == 1


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


# ---------------------------------------------------------------------------
# RFC-0002 — builtin classifier + shadowing contract
# ---------------------------------------------------------------------------


class TestRFC0002BuiltinClassifier:
    """RFC-0002 criterion 1+2: builtins get ``"builtin"`` (not ``"stdlib"``),
    applied AFTER local/import bindings so shadowing is preserved."""

    def _make_ctx(
        self,
        builtins: frozenset[str],
        stdlib: frozenset[str] = frozenset(),
        functions_by_name: dict | None = None,
    ):
        from tree_sitter_analyzer.callee_resolution import CalleeResolver
        from tree_sitter_analyzer.synapse_resolver import ResolverContext

        return ResolverContext(
            project_root="",
            cache=None,  # type: ignore[arg-type]
            builtins={"python": builtins},
            stdlib_modules={"python": stdlib},
            callee_resolver=CalleeResolver(
                functions_by_name=functions_by_name or {},
                functions_by_file={},
                name_to_source={},
            ),
        )

    def test_builtin_name_resolves_to_builtin(self) -> None:
        """``len()`` with no local shadow → resolution="builtin" (RFC-0002 criterion 1)."""
        from tree_sitter_analyzer.synapse_resolver import resolve_callee

        ctx = self._make_ctx(builtins=frozenset({"len", "print", "range"}))
        result = resolve_callee("len", "module.py", ctx, caller_name="f")
        assert result.resolution == "builtin", (
            f"expected 'builtin', got {result.resolution!r} — "
            "RFC-0002 criterion 1: builtins classified as 'builtin', not 'stdlib'"
        )
        assert result.callee_symbol_id is None

    def test_project_binding_shadows_builtin(self) -> None:
        """A project function named ``len`` shadows the builtin (RFC-0002 criterion 2)."""
        from tree_sitter_analyzer.synapse_resolver import resolve_callee

        ctx = self._make_ctx(
            builtins=frozenset({"len"}),
            functions_by_name={
                "len": [
                    {"name": "len", "file": "utils.py", "id": 42, "language": "python"}
                ]
            },
        )
        result = resolve_callee("len", "utils.py", ctx, caller_name="f")
        assert result.resolution in ("local", "project"), (
            f"expected local/project (shadowing), got {result.resolution!r} — "
            "RFC-0002 criterion 2: project binding shadows builtin"
        )

    def test_stdlib_import_wins_over_builtin_name_collision(self) -> None:
        """When a name is both a known builtin and stdlib-imported, stdlib wins (runs earlier)."""
        from tree_sitter_analyzer.synapse_resolver import (
            ResolverContext,
            resolve_callee,
        )
        from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry

        # ``path`` treated as a builtin AND imported from stdlib ``os`` module.
        # ``_try_stdlib`` must fire before ``_try_builtin`` per cascade order.
        imp = ImportEntry(
            file_path="module.py",
            language="python",
            module_path="os",
            local_name="path",
        )
        ctx = ResolverContext(
            project_root="",
            cache=None,  # type: ignore[arg-type]
            builtins={"python": frozenset({"path"})},
            stdlib_modules={"python": frozenset({"os"})},
            imports_by_file={"module.py": [imp]},
            callee_resolver=None,
        )
        result = resolve_callee("path", "module.py", ctx, caller_name="f")
        assert result.resolution == "stdlib", (
            f"expected 'stdlib' (stdlib fires before builtin), got {result.resolution!r}"
        )


# ---------------------------------------------------------------------------
# RFC-0002 criterion 7 — monotonicity: no resolved→unknown regression
# ---------------------------------------------------------------------------


class TestRFC0002Monotonicity:
    """RFC-0002 criterion 7: a re-index must not regress resolved edges back to unknown.

    Uses a two-file project where the callee is defined in b.py and called from a.py.
    After two index passes, the edge must still be resolved (or at worst stay at
    its original resolution — not degrade).
    """

    def test_reindex_does_not_regress_resolved_edges(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text(
            "from b import helper\n\ndef caller():\n    return helper()\n",
            encoding="utf-8",
        )
        (tmp_path / "b.py").write_text(
            "def helper():\n    return 42\n",
            encoding="utf-8",
        )
        cache = ASTCache(str(tmp_path))
        try:
            cache.index_project(max_files=10, workers=0)
            # Collect resolution after first index
            conn = cache.get_conn()
            rows_pass1 = {
                (r["callee_name"], r["callee_resolution"])
                for r in conn.execute(
                    "SELECT callee_name, callee_resolution FROM edges WHERE kind='calls'"
                ).fetchall()
                if r["callee_resolution"] not in (None, "unknown")
            }

            # Re-index (simulates file modification triggering a second pass)
            (tmp_path / "a.py").write_text(
                "from b import helper\n\ndef caller():\n    x = 1\n    return helper()\n",
                encoding="utf-8",
            )
            cache.index_project(max_files=10, workers=0)

            rows_pass2 = {
                (r["callee_name"], r["callee_resolution"])
                for r in conn.execute(
                    "SELECT callee_name, callee_resolution FROM edges WHERE kind='calls'"
                ).fetchall()
                if r["callee_resolution"] not in (None, "unknown")
            }

            # Any edge resolved in pass1 must still be resolved in pass2 (or better)
            regressions = rows_pass1 - rows_pass2
            assert not regressions, (
                f"RFC-0002 monotonicity violated: these edges regressed to unknown "
                f"after reindex: {regressions}"
            )
        finally:
            cache.close()


# ---------------------------------------------------------------------------
# RFC-0002 criterion 4 — same-named functions → distinct callee_symbol_ids
# ---------------------------------------------------------------------------


class TestRFC0002DistinctSymbolIds:
    """RFC-0002 criterion 4: similarly-named functions in different files must
    resolve to distinct callee_symbol_ids, not collapse to one bare name."""

    def test_same_named_functions_in_different_files_get_distinct_ids(
        self, tmp_path: Path
    ) -> None:
        """Two local ``helper()`` functions each called from their own file
        must resolve to different callee_symbol_ids."""
        (tmp_path / "a.py").write_text(
            "def helper():\n    return 'a'\n\ndef caller_a():\n    return helper()\n",
            encoding="utf-8",
        )
        (tmp_path / "b.py").write_text(
            "def helper():\n    return 'b'\n\ndef caller_b():\n    return helper()\n",
            encoding="utf-8",
        )
        cache = ASTCache(str(tmp_path))
        try:
            cache.index_project(max_files=10, workers=0)
            conn = cache.get_conn()
            rows = conn.execute(
                "SELECT callee_name, callee_symbol_id, callee_resolved_file "
                "FROM edges WHERE kind='calls' AND callee_name='helper' "
                "AND callee_symbol_id IS NOT NULL"
            ).fetchall()
            symbol_ids = {r["callee_symbol_id"] for r in rows}
            resolved_files = {
                r["callee_resolved_file"] for r in rows if r["callee_resolved_file"]
            }
            assert len(rows) == 2, (
                f"expected exactly 2 resolved 'helper' call edges, got {len(rows)}"
            )
            assert len(symbol_ids) == 2, (
                "RFC-0002 criterion 4: same-named functions in different files "
                f"must have distinct callee_symbol_ids — got single id: {symbol_ids}"
            )
            assert len(resolved_files) == 2, (
                f"expected exactly 2 distinct resolved files, got: {resolved_files}"
            )
        finally:
            cache.close()


# ---------------------------------------------------------------------------
# RFC-0002 criterion 6 — Hyphae false-positive rate measurably lower
# ---------------------------------------------------------------------------


class TestRFC0002HyphaeCalleeFalsePositive:
    """RFC-0002 criterion 6: resolution rate on a small project must be
    measurably above 0% after the cascade fix."""

    def test_resolution_rate_above_zero_for_simple_project(
        self, tmp_path: Path
    ) -> None:
        """After indexing, at least one call edge must be resolved (not bare-name).
        Pins the RFC-0002 criterion 6 goal: unknown rate measurably < 100%."""
        (tmp_path / "engine_a.py").write_text(
            "class EngineA:\n    def run(self):\n        return 'a'\n",
            encoding="utf-8",
        )
        (tmp_path / "caller_a.py").write_text(
            "from engine_a import EngineA\n\ndef main():\n    EngineA().run()\n",
            encoding="utf-8",
        )
        cache = ASTCache(str(tmp_path))
        try:
            cache.index_project(max_files=10, workers=0)
            conn = cache.get_conn()
            rows = conn.execute(
                "SELECT callee_name, callee_resolution FROM edges WHERE kind='calls'"
            ).fetchall()
            total = len(rows)
            unknown = sum(
                1 for r in rows if r["callee_resolution"] in (None, "unknown")
            )
            if total > 0:
                unknown_rate = unknown / total
                assert unknown_rate < 1.0, (
                    f"RFC-0002 criterion 6: all {total} call edges are unknown — "
                    "Hyphae :callees false-positive rate not reduced vs baseline"
                )
        finally:
            cache.close()
