"""RFC-0042 P3-lite: the rewritten edge-layer readers give the per-name answers, exactly.

The readers behind the RFC-0040 completeness checks were rewritten for speed:

* ``es_import_sites._RENAMED_SQL`` has a new query plan (and an explicit
  ``ORDER BY`` equal to the old plan's order);
* ``alias_edges`` reads the ES alias rows and the alias-import buckets from a
  whole-snapshot table when a certified snapshot binds one
  (:mod:`tree_sitter_analyzer.graph.snapshot_tables`);
* ``es_import_sites._import_statements`` keeps each file's import texts per
  snapshot.

A changed result here could turn into a wrong ``complete``, so the old
per-name path is the oracle: every reader is compared, in order, over every
name and file of real indexes. The fixture project covers the shapes the
readers exist for (renamed default and named imports, re-export chains,
namespace imports, Python ``import … as``, a non-ASCII name whose JSON escape
differs from its text). Set ``TSA_P3_DIFF_REPOS`` to a ``;``-separated list of
indexed project roots to run the same oracle on larger repos (the PR ran it on
hono, zod and rich).
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import index_snapshot
from tree_sitter_analyzer.cache.generation_routing import resolve_index_path
from tree_sitter_analyzer.graph import (
    alias_edges,
    edge_store,
    es_import_sites,
    snapshot_tables,
)
from tree_sitter_analyzer.graph.edge_store import EdgeStore
from tree_sitter_analyzer.query_scope import query_scope
from tree_sitter_analyzer.resident import snapshot_memo

_AN_HOUR_NS = 3600 * 1_000_000_000
_SOURCES = {
    "lib/jws.ts": (
        "export default function signer(x: number) {\n  return x;\n}\n"
        "export function verifying(k: string) {\n  return k;\n}\n"
        "export function pemToBinary(p: string) {\n  return p;\n}\n"
    ),
    "lib/index.ts": (
        "export { default as sign, verifying as verify } from './jws';\n"
        "export * from './jws';\n"
    ),
    "lib/use.ts": (
        "import makeSig from './jws';\n"
        "import { verifying as check, pemToBinary } from './jws';\n"
        "import * as jws from './jws';\n\n"
        "export function run() {\n"
        "  makeSig(1);\n  check('a');\n  pemToBinary('b');\n  return jws.signer(2);\n}\n"
    ),
    "lib/chain.ts": (
        "import { sign, verify } from './index';\n\n"
        "export function chained() {\n  sign(3);\n  return verify('c');\n}\n"
    ),
    "lib/unresolved.ts": (
        "import { pemToBinary as p2b } from './jws';\n"
        "import { missing } from './nowhere';\n\n"
        "export function later(fn: any) {\n"
        "  p2b(fn);\n  missing();\n  return fn.pemToBinary();\n}\n"
    ),
    "web/función.js": (
        "export function función(a) {\n  return a;\n}\n"
        "export default function anon() {\n  return función(1);\n}\n"
    ),
    "web/app.js": (
        "import f2 from './función.js';\n"
        "import { función as fx } from './función.js';\n\n"
        "export function main() {\n  f2();\n  return fx(2);\n}\n"
    ),
    "pkg/__init__.py": "from .helper import helper\n",
    "pkg/helper.py": "def helper():\n    return 3\n\n\ndef top():\n    return helper()\n",
    "router.py": (
        "from pkg.helper import helper as assist\n\n\ndef used():\n    return assist()\n"
    ),
}


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    root = tmp_path_factory.mktemp("p3lite") / "proj"
    for rel, text in _SOURCES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    stamp = time.time_ns() - _AN_HOUR_NS
    for path in [*root.rglob("*"), root]:
        os.utime(path, ns=(stamp, stamp))
    result = asyncio.run(
        CodeGraphFullIndexTool(str(root)).execute({"mode": "full", "max_files": 50})
    )
    assert result["published"] is True
    yield root
    index_snapshot.REGISTRY.close_all()


def _roots(fixture_root: Path) -> list[Path]:
    extra = [Path(p) for p in os.environ.get("TSA_P3_DIFF_REPOS", "").split(";") if p]
    return [fixture_root, *extra]


def _private_copy(root: Path) -> sqlite3.Connection:
    """A private in-memory copy of the published index, as a certified read holds."""
    source = sqlite3.connect(f"file:{resolve_index_path(str(root))}?mode=ro", uri=True)
    try:
        conn = sqlite3.connect(":memory:")
        source.backup(conn)
    finally:
        source.close()
    conn.row_factory = sqlite3.Row
    return conn


class _Tables:
    """A provider that keeps each table once, as the snapshot memo does."""

    def __init__(self) -> None:
        self.tables: dict[str, Any] = {}
        self.builds = 0

    def __call__(self, name: str, compute: Callable[[], Any]) -> Any:
        if name not in self.tables:
            self.builds += 1
            self.tables[name] = compute()
        return self.tables[name]


def _rows(rows: list[Any]) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in rows]


def _names(conn: sqlite3.Connection) -> list[str]:
    """Every name a reader can be asked: callees, symbols, import bindings, aliases."""
    names: set[str] = set()
    for sql in (
        "SELECT DISTINCT callee_name FROM edges WHERE kind = 'calls'",
        "SELECT DISTINCT name FROM ast_symbol_rows",
        "SELECT DISTINCT local_name FROM ast_imports",
        "SELECT DISTINCT alias_of FROM ast_imports",
    ):
        names.update(str(row[0]) for row in conn.execute(sql) if row[0])
    return sorted(names)


def _definitions(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT DISTINCT name, file_path FROM ast_symbol_rows "
        "WHERE kind IN ('function', 'method', 'class') ORDER BY file_path, name"
    )
    return [(str(name), str(path)) for name, path in rows if name and path]


@pytest.fixture
def cold_memos() -> Iterator[None]:
    snapshot_memo.clear()
    alias_edges._JOIN_MEMO.clear()
    yield
    snapshot_memo.clear()


def test_the_fixture_exercises_every_rewritten_reader(fixture_root: Path) -> None:
    """Guard: the oracle below compares non-empty results, not only ``[]``."""
    conn = _private_copy(fixture_root)
    files = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT callee_resolved_file FROM edges WHERE kind = 'imports' "
            "AND callee_resolved_file <> ''"
        )
    ]
    renamed = [
        row
        for file in files
        for row in conn.execute(es_import_sites._RENAMED_SQL, (file, "x"))
    ]
    assert renamed, "no renamed import binding in the fixture"
    alias_rows = [r for n in _names(conn) for r in alias_edges.alias_call_rows(conn, n)]
    assert alias_rows, "no alias call row in the fixture"
    es_rows = [r for n in _names(conn) for r in alias_edges._es_alias_rows(conn, n)]
    assert es_rows, "no ES alias row in the fixture"


@pytest.mark.parametrize("which", ["fixture", "extra"])
def test_renamed_import_plan_returns_the_old_rows_in_the_old_order(
    fixture_root: Path, which: str
) -> None:
    roots = _roots(fixture_root)
    roots = roots[:1] if which == "fixture" else roots[1:]
    if not roots:
        pytest.skip("TSA_P3_DIFF_REPOS not set")
    for root in roots:
        conn = _private_copy(root)
        files = [
            str(row[0])
            for row in conn.execute(
                "SELECT DISTINCT callee_resolved_file FROM edges "
                "WHERE kind = 'imports' AND callee_resolved_file <> ''"
            )
        ]
        names = ["", "x", *_names(conn)[:200]]
        for file in files:
            bindings = conn.execute(
                es_import_sites._RENAMED_SQL_PER_IMPORT, (file, "")
            ).fetchall()
            # Every local name bound to the file, plus names never bound there.
            asked = {*names[:20], *(str(b["local_name"]) for b in bindings)}
            for name in sorted(asked):
                old = conn.execute(
                    es_import_sites._RENAMED_SQL_PER_IMPORT, (file, name)
                ).fetchall()
                new = conn.execute(
                    es_import_sites._RENAMED_SQL, (file, name)
                ).fetchall()
                assert _rows(new) == _rows(old), (root.name, file, name)


@pytest.mark.parametrize("which", ["fixture", "extra"])
def test_tables_give_the_per_name_readers_results(
    fixture_root: Path, which: str
) -> None:
    roots = _roots(fixture_root)
    roots = roots[:1] if which == "fixture" else roots[1:]
    if not roots:
        pytest.skip("TSA_P3_DIFF_REPOS not set")
    for root in roots:
        conn = _private_copy(root)
        provider = _Tables()
        names = _names(conn)
        files = [str(r[0]) for r in conn.execute("SELECT file_path FROM ast_index")]
        for name in names:
            old_alias = _rows(alias_edges.alias_call_rows(conn, name))
            old_locals = alias_edges._alias_local_names(conn, name)
            with snapshot_tables.bound(conn, provider):
                new_alias = _rows(alias_edges.alias_call_rows(conn, name))
                new_locals = alias_edges._alias_local_names(conn, name)
            assert new_alias == old_alias, (root.name, name)
            assert new_locals == old_locals, (root.name, name)
        # Inside an RFC-0041 query scope the table stands in for the scope's own
        # buckets (an unscoped build per name here: an in-memory copy has no file
        # identity), so a sample of names suffices on large repos.
        for name in names[:300]:
            with query_scope():
                old_scoped = _rows(alias_edges.alias_call_rows(conn, name))
                with snapshot_tables.bound(conn, provider):
                    new_scoped = _rows(alias_edges.alias_call_rows(conn, name))
            assert new_scoped == old_scoped, (root.name, name)
        for file in files:
            old = es_import_sites._import_statements(conn, file)
            with snapshot_tables.bound(conn, provider):
                new = es_import_sites._import_statements(conn, file)
                again = es_import_sites._import_statements(conn, file)
            assert new == old == again, (root.name, file)
        # Two alias tables plus one import-text table per file, each built once.
        assert provider.builds == 2 + len(files)


@pytest.mark.parametrize("which", ["fixture", "extra"])
def test_edge_layer_answers_equal_the_per_name_path(
    fixture_root: Path, which: str
) -> None:
    """The check inputs themselves: unresolved inbound sites and the callers BFS."""
    roots = _roots(fixture_root)
    roots = roots[:1] if which == "fixture" else roots[1:]
    if not roots:
        pytest.skip("TSA_P3_DIFF_REPOS not set")
    for root in roots:
        conn = _private_copy(root)
        store = EdgeStore(conn, ensure_schema=False)
        provider = _Tables()
        for name, file in _definitions(conn):
            seen = es_import_sites.row_ids(edge_store._direct_callers(conn, name, file))
            args = (conn, name, file, seen)
            kwargs = {
                "is_resolved": edge_store._resolution_is_resolved,
                "source_file": edge_store._source_file,
            }
            with _old_renamed_statement():
                old_imported = _rows(
                    es_import_sites.imported_unresolved_rows(*args, **kwargs)
                )
                old_sites = store.unresolved_caller_sites(name, file)
                old_callers = store.query_callers(name, file)
            with snapshot_tables.bound(conn, provider):
                new_imported = _rows(
                    es_import_sites.imported_unresolved_rows(*args, **kwargs)
                )
                new_sites = store.unresolved_caller_sites(name, file)
                new_callers = store.query_callers(name, file)
            assert new_imported == old_imported, (root.name, name, file)
            assert new_sites == old_sites, (root.name, name, file)
            assert new_callers == old_callers, (root.name, name, file)


def test_tables_are_used_only_for_the_bound_connection(fixture_root: Path) -> None:
    conn = _private_copy(fixture_root)
    other = _private_copy(fixture_root)
    provider = _Tables()
    with snapshot_tables.bound(conn, provider):
        assert snapshot_tables.table(other, "t", lambda: 1) is None
        assert snapshot_tables.table(conn, "t", lambda: 2) == 2
    assert snapshot_tables.table(conn, "t", lambda: 3) is None


def test_certified_snapshot_keeps_the_tables_once(
    fixture_root: Path, cold_memos: None
) -> None:
    """The real certified adapter binds its tables; ``TSA_RESIDENT=off`` binds none."""
    with index_snapshot.certified_index_read(str(fixture_root)) as owner:
        assert owner is not None
        cache = owner.query_cache()
        first = cache.unresolved_caller_sites("signer", "lib/jws.ts")
        tables = [
            k for k in _memo_entries() if isinstance(k, tuple) and k[0] == "table"
        ]
        assert ("table", "es_alias_buckets") in tables
        assert cache.prefill_snapshot_tables() is True
        assert cache.query_callers("pemToBinary", "lib/jws.ts") is not None
        assert first is not None


def test_resident_off_keeps_no_tables(
    fixture_root: Path, cold_memos: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TSA_RESIDENT", "off")
    with index_snapshot.certified_index_read(str(fixture_root)) as owner:
        assert owner is not None
        cache = owner.query_cache()
        cache.unresolved_caller_sites("signer", "lib/jws.ts")
        assert cache.prefill_snapshot_tables() is False
    assert snapshot_memo.stats()["entries"] == 0


def test_an_interrupted_table_build_is_not_kept(
    fixture_root: Path, cold_memos: None
) -> None:
    from tree_sitter_analyzer.graph.read_interrupt import ReadInterrupted

    conn = _private_copy(fixture_root)
    provider = _Tables()
    conn.set_progress_handler(lambda: 1, 1)
    try:
        with snapshot_tables.bound(conn, provider), pytest.raises(ReadInterrupted):
            alias_edges._es_alias_rows(conn, "signer")
    finally:
        conn.set_progress_handler(None, 0)
    assert "es_alias_buckets" not in provider.tables


@contextmanager
def _old_renamed_statement() -> Iterator[None]:
    """The oracle reads the renamed bindings with the statement before P3-lite."""
    new = es_import_sites._RENAMED_SQL
    es_import_sites._RENAMED_SQL = es_import_sites._RENAMED_SQL_PER_IMPORT
    try:
        yield
    finally:
        es_import_sites._RENAMED_SQL = new


def _memo_entries() -> list[Any]:
    with snapshot_memo._lock:
        return [entry for memo in snapshot_memo._memos.values() for entry in memo]
