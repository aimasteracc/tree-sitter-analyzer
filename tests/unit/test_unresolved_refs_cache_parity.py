"""B4 perf: per-run candidate cache for the second-pass resolver.

``resolve_unresolved_refs`` used to issue one ``ast_symbol_rows`` SELECT per
(name, kind) per ref. Hot names (``get`` / ``run`` / ``build`` …) recur across
thousands of refs, so the same SELECT ran thousands of times. B4 adds a per-run
``(name, kind)`` candidate cache so each distinct lookup hits SQLite once.

These tests are the parity gate: the cached pass must produce **byte-for-byte
identical** ``edges`` rows + identical aggregate stats as the uncached pass, and
must collapse the duplicate SELECTs (proven by a query counter). If parity ever
breaks, the cache changed resolution semantics — which is forbidden.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from tree_sitter_analyzer import _ast_cache_unresolved as unresolved
from tree_sitter_analyzer.ast_cache import ASTCache


def _write_repeated_name_project(root: Path) -> None:
    """A project where one callee/base name recurs across many files.

    The shared name ``helper`` (function) + shared base ``Base`` (class) are
    referenced cross-file from many call sites, which is exactly the shape that
    makes the uncached path re-run the same SELECT over and over.
    """
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "helper.py").write_text(
        "def helper():\n    return 1\n",
        encoding="utf-8",
    )
    (pkg / "base.py").write_text(
        "class Base:\n    pass\n",
        encoding="utf-8",
    )
    # Many caller files all importing + calling the same helper and extending
    # the same base — each produces a pending CALLS ref for ``helper`` and a
    # pending EXTENDS ref for ``Base``.
    for i in range(12):
        (pkg / f"caller_{i}.py").write_text(
            "from .helper import helper\n"
            "from .base import Base\n\n"
            f"class Widget{i}(Base):\n"
            "    def run(self):\n"
            "        return helper()\n",
            encoding="utf-8",
        )


def _snapshot_edges(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    """Full, deterministic snapshot of every edge row (resolution columns incl.)."""
    rows = conn.execute(
        "SELECT source_node_id, target_node_id, kind, line, provenance, "
        "callee_name, callee_full, callee_resolution, callee_resolved_file, "
        "callee_symbol_id, metadata "
        "FROM edges ORDER BY source_node_id, target_node_id, kind, line, provenance"
    ).fetchall()
    return [tuple(r) for r in rows]


class _CountingConn:
    """Wrap a sqlite3 connection and count candidate-table SELECTs."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.candidate_selects = 0

    def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        if "FROM ast_symbol_rows" in sql and "name = ? AND kind = ?" in sql:
            self.candidate_selects += 1
        return self._conn.execute(sql, *args, **kwargs)

    def commit(self) -> None:
        self._conn.commit()

    def __getattr__(self, item: str) -> Any:
        return getattr(self._conn, item)


def _reset_resolution(conn: sqlite3.Connection) -> None:
    """Reset CALLS resolution + drop second-pass EXTENDS edges so the pass re-runs."""
    conn.execute(
        "UPDATE edges SET callee_resolution = 'unknown', "
        "callee_resolved_file = '', callee_symbol_id = NULL WHERE kind = 'calls'"
    )
    conn.execute("DELETE FROM edges WHERE provenance = 'unresolved_refs'")
    conn.commit()


def test_cached_candidate_lookup_matches_uncached_byte_for_byte(
    tmp_path: Path,
) -> None:
    """Cached pass == uncached pass: identical edge snapshot + identical stats."""
    # Two identical projects: a/ runs the legacy uncached path, b/ the cached
    # path. Project-relative file_path is identical, so edge snapshots compare
    # byte-for-byte.
    _write_repeated_name_project(tmp_path / "a")
    _write_repeated_name_project(tmp_path / "b")

    cache_a = ASTCache(str(tmp_path / "a"))
    cache_b = ASTCache(str(tmp_path / "b"))
    try:
        cache_a.index_project(workers=0)
        cache_b.index_project(workers=0)

        conn_a = cache_a.get_conn()
        conn_b = cache_b.get_conn()
        _reset_resolution(conn_a)
        _reset_resolution(conn_b)

        # Run A with the candidate cache forcibly disabled (legacy behaviour):
        orig = unresolved._candidate_symbols

        def uncached(c: Any, sf: str, rn: str, rk: str, _cache: Any = None) -> Any:
            return orig(c, sf, rn, rk, None)

        unresolved._candidate_symbols = uncached  # type: ignore[assignment]
        try:
            stats_a = unresolved.resolve_unresolved_refs(conn_a)
        finally:
            unresolved._candidate_symbols = orig  # type: ignore[assignment]

        # Run B with the cache enabled (default code path):
        stats_b = unresolved.resolve_unresolved_refs(conn_b)

        assert stats_a == stats_b, (stats_a, stats_b)
        assert stats_b is not None and stats_b["resolved"] > 0

        # Byte-for-byte edge parity (rewrite b/ paths is unnecessary — both
        # snapshots use project-relative file_path which is identical).
        snap_a = _snapshot_edges(conn_a)
        snap_b = _snapshot_edges(conn_b)
        assert snap_a == snap_b
    finally:
        cache_a.close()
        cache_b.close()


def test_candidate_cache_collapses_duplicate_selects(tmp_path: Path) -> None:
    """The cache must issue far fewer candidate SELECTs than the uncached path."""
    _write_repeated_name_project(tmp_path)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(workers=0)
        conn = cache.get_conn()

        _reset_resolution(conn)
        uncached_conn = _CountingConn(conn)
        orig = unresolved._candidate_symbols

        def uncached(c: Any, sf: str, rn: str, rk: str, _cache: Any = None) -> Any:
            return orig(c, sf, rn, rk, None)

        unresolved._candidate_symbols = uncached  # type: ignore[assignment]
        try:
            unresolved.resolve_unresolved_refs(uncached_conn)
        finally:
            unresolved._candidate_symbols = orig  # type: ignore[assignment]

        _reset_resolution(conn)
        cached_conn = _CountingConn(conn)
        unresolved.resolve_unresolved_refs(cached_conn)

        # Many refs share the names ``helper`` / ``Base`` / ``run`` → the cache
        # collapses thousands of repeats to one SELECT per distinct (name, kind).
        assert cached_conn.candidate_selects < uncached_conn.candidate_selects
        assert uncached_conn.candidate_selects > 0
    finally:
        cache.close()


def test_candidate_cache_returns_empty_on_broken_connection() -> None:
    """A failing candidate SELECT still yields [] and is cached as the abort."""
    no_schema = sqlite3.connect(":memory:")
    no_schema.row_factory = sqlite3.Row
    try:
        cache: dict[tuple[str, str], Any] = {}
        assert (
            unresolved._candidate_symbols(no_schema, "x.py", "Foo", "calls", cache)
            == []
        )
        # The abort sentinel is cached so a repeat lookup does not re-hit SQLite.
        assert ("Foo", "function") in cache or ("Foo", "calls") in cache
        assert (
            unresolved._candidate_symbols(no_schema, "x.py", "Foo", "calls", cache)
            == []
        )
    finally:
        no_schema.close()
