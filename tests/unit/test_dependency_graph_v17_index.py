"""RFC-0032 follow-up (#1664 item 5): the cached dependency graph reads v17 indexes.

Schema 18 only adds the ``ast_writer_state`` control table (RFC-0032 slice 5);
readers never use it. Both change-impact loaders nevertheless required schema 18,
so an already-published v17 index (read-only, never migrated by a reader) fell
back to parsing every source file until its next write. The reader requirement
is ``SNAPSHOT_SCHEMA_VERSION`` (17), the same as snapshot validation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.unit._ast_cache_helpers import legacy_cache, requires_posix_fd
from tree_sitter_analyzer.cache.schema import CURRENT_SCHEMA_VERSION
from tree_sitter_analyzer.index_snapshot_schema import SNAPSHOT_SCHEMA_VERSION
from tree_sitter_analyzer.mcp.tools.utils import change_impact_cached_graph as cached
from tree_sitter_analyzer.mcp.tools.utils import change_impact_index_graph as ig

_FIXTURE = {
    "pkg/__init__.py": "",
    "pkg/sub.py": "VALUE = 1\n",
    "pkg/b.py": "def helper():\n    return 1\n",
    "pkg/a.py": (
        "from .b import helper\nfrom . import sub\n\n\n"
        "def run():\n    return helper() + sub.VALUE\n"
    ),
    "web/util.js": "export const x = 1;\n",
    "web/app.js": "import { x } from './util';\n",
    "tests/test_b.py": "from pkg.b import helper\n",
}


def _indexed(root: Path) -> Path:
    for rel, text in _FIXTURE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    cache = legacy_cache(str(root))
    try:
        cache.index_project(max_files=50)
    finally:
        cache.close()
    db = root / ".ast-cache" / "index.db"
    assert db.is_file()
    return db


def _versions(db: Path) -> set[int]:
    connection = sqlite3.connect(db)
    try:
        return {r[0] for r in connection.execute("SELECT version FROM ast_schema_version")}
    finally:
        connection.close()


def _downgrade_to_v17(db: Path) -> None:
    """A v17 index as published before slice 5: no writer-state table, no v18 row."""
    connection = sqlite3.connect(db)
    try:
        connection.execute("DROP TABLE ast_writer_state")
        connection.execute("DELETE FROM ast_schema_version WHERE version = 18")
        connection.commit()
    finally:
        connection.close()


def _dump(db: Path) -> tuple[str, ...]:
    connection = sqlite3.connect(db)
    try:
        return tuple(connection.iterdump())
    finally:
        connection.close()


def _no_source_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args, **_kwargs):
        raise AssertionError("parsed source instead of reading the index")

    monkeypatch.setattr(ig, "extract_imports_from_file", refuse)


def _shape(graph) -> tuple:
    return (
        graph.nodes(),
        graph.edges(),
        {node: graph.dependents_of(node) for node in graph.nodes()},
    )


def test_reader_version_is_17_and_writer_version_is_18():
    assert (SNAPSHOT_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION) == (17, 18)


def test_verified_graph_serves_v17_index_without_parse_fallback(tmp_path, monkeypatch):
    db = _indexed(tmp_path)
    assert CURRENT_SCHEMA_VERSION in _versions(db)
    v18 = ig.load_verified_index_graph(str(tmp_path))
    assert v18 is not None
    _downgrade_to_v17(db)
    assert max(_versions(db)) == 17
    before = _dump(db)
    _no_source_parse(monkeypatch)

    v17 = ig.load_verified_index_graph(str(tmp_path))

    assert v17 is not None
    assert (v17.index_files, v17.source_files) == (len(_FIXTURE), 0)
    assert ig.dependency_graph_provenance(v17)["source"] == "index"
    assert _shape(v17) == _shape(v18)
    assert ("pkg/a.py", "pkg/b.py") in v17.edges()
    # Reading does not migrate: the v17 index is byte-for-byte unchanged.
    assert _dump(db) == before


@pytest.mark.parametrize("version", [1, 16, CURRENT_SCHEMA_VERSION + 1])
def test_verified_graph_still_rejects_versions_outside_the_reader_range(
    tmp_path, version
):
    db = _indexed(tmp_path)
    connection = sqlite3.connect(db)
    try:
        connection.execute("DELETE FROM ast_schema_version")
        connection.execute(
            "INSERT INTO ast_schema_version(version, applied_at, description) "
            "VALUES (?, 0, 'test')",
            (version,),
        )
        connection.commit()
    finally:
        connection.close()
    assert ig.load_verified_index_graph(str(tmp_path)) is None


@requires_posix_fd
def test_certified_graph_serves_v17_index(tmp_path):
    # The whole-graph certifier needs POSIX dir_fd traversal (see its module).
    db = _indexed(tmp_path)
    v18 = cached.load_cached_dependency_graph(str(tmp_path))
    assert v18 is not None
    _downgrade_to_v17(db)
    before = _dump(db)

    v17 = cached.load_cached_dependency_graph(str(tmp_path))

    assert isinstance(v17, cached.CachedDependencyGraph)
    assert ig.dependency_graph_provenance(v17)["source"] == "certified_index"
    assert _shape(v17) == _shape(v18)
    assert _dump(db) == before
