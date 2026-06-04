"""Cross-file second-pass resolution tests (B1.3 — unified ``edges`` table).

The ``unresolved_refs`` work-queue table was dropped in B1.3. The second pass
now recomputes its pending work set in-memory per Python file (the same
``_parent_refs`` / ``_call_refs`` filtering) and writes results directly onto
the ``edges`` table: a resolved EXTENDS reference becomes a real EXTENDS edge,
and a resolved CALLS reference UPDATEs the resolution columns of its existing
CALLS edge. These tests pin that Python resolution behaviour so it cannot
regress.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import _ast_cache_unresolved as unresolved
from tree_sitter_analyzer import ast_cache as ast_cache_module
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.class_hierarchy import ClassHierarchy
from tree_sitter_analyzer.graph.edge_store import EdgeKind, symbol_node
from tree_sitter_analyzer.mcp.utils import auto_index_guard


def _write_project(root: Path) -> None:
    pkg = root / "pkg"
    other = pkg / "other"
    other.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (other / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "base.py").write_text(
        "class LanguagePlugin:\n    pass\n",
        encoding="utf-8",
    )
    (other / "base.py").write_text(
        "class LanguagePlugin:\n    pass\n",
        encoding="utf-8",
    )
    (pkg / "python_plugin.py").write_text(
        "from .base import LanguagePlugin\n\n"
        "class PythonPlugin(LanguagePlugin):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "alias_plugin.py").write_text(
        "from .base import LanguagePlugin as LP\n\nclass AliasPlugin(LP):\n    pass\n",
        encoding="utf-8",
    )
    (pkg / "helper.py").write_text(
        "def helper():\n    return 'ok'\n",
        encoding="utf-8",
    )
    (pkg / "service.py").write_text(
        "from .helper import helper\n\ndef build():\n    return helper()\n",
        encoding="utf-8",
    )
    (pkg / "missing.py").write_text(
        "class Orphan(MissingBase):\n    pass\n",
        encoding="utf-8",
    )


def _rows(
    cache: ASTCache, sql: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    return [dict(row) for row in cache.get_conn().execute(sql, params).fetchall()]


def _pending_extends(cache: ASTCache) -> set[tuple[str, str]]:
    """EXTENDS edges still pointing at an unresolved ``class:`` synthetic node."""
    return {
        (row["file_path"], row["target_node_id"].removeprefix("class:"))
        for row in cache.get_conn().execute(
            "SELECT file_path, target_node_id FROM edges "
            "WHERE kind = 'extends' AND target_node_id LIKE 'class:%'"
        )
    }


def test_index_project_resolves_cross_file_extends_and_calls(tmp_path: Path) -> None:
    _write_project(tmp_path)
    cache = ASTCache(str(tmp_path))
    try:
        stats = cache.index_project(max_files=20, workers=0)
        assert stats["indexed"] >= 7
        # The second pass resolves the cross-file EXTENDS references (alias_plugin
        # + python_plugin). Cross-file CALLS resolution is handled earlier by the
        # cross-file backfill, so it no longer flows through this counter (the
        # resolved edge data is asserted directly below).
        assert stats["unresolved_refs_backfill"]["resolved"] >= 2

        conn = cache.get_conn()
        # The cross-file EXTENDS references resolved into real edges pointing at
        # the resolved base class (provenance unresolved_refs).
        alias_edge = conn.execute(
            """SELECT target_node_id, metadata
               FROM edges
               WHERE source_node_id = ?
                 AND target_node_id = ?
                 AND kind = ?
                 AND provenance = 'unresolved_refs'""",
            (
                symbol_node("pkg/alias_plugin.py", "AliasPlugin", 3),
                symbol_node("pkg/base.py", "LanguagePlugin", 1),
                EdgeKind.EXTENDS.value,
            ),
        ).fetchone()
        assert alias_edge is not None
        metadata = json.loads(alias_edge["metadata"])
        assert metadata["parent"] == "LanguagePlugin"
        assert metadata["parent_reference"] == "LP"

        python_plugin_edge = conn.execute(
            """SELECT 1 FROM edges
               WHERE source_node_id = ? AND target_node_id = ?
                 AND kind = ? AND provenance = 'unresolved_refs'""",
            (
                symbol_node("pkg/python_plugin.py", "PythonPlugin", 3),
                symbol_node("pkg/base.py", "LanguagePlugin", 1),
                EdgeKind.EXTENDS.value,
            ),
        ).fetchone()
        assert python_plugin_edge is not None

        # The cross-file CALLS reference resolved in place on the edge's columns.
        call_row = conn.execute(
            "SELECT callee_resolution, callee_resolved_file FROM edges "
            "WHERE kind = 'calls' AND caller_name = 'build' AND callee_name = 'helper'"
        ).fetchone()
        assert call_row is not None
        assert call_row["callee_resolved_file"] == "pkg/helper.py"

        hierarchy = ClassHierarchy(cache)
        subclass_names = {
            item["name"] for item in hierarchy.subclasses_of("LanguagePlugin")
        }
        assert {"AliasPlugin", "PythonPlugin"}.issubset(subclass_names)
        assert hierarchy.superclasses_of("AliasPlugin")[0]["file"] == "pkg/base.py"

        callees = cache.query_callees("build", "pkg/service.py")
        assert any(
            item["callee_name"] == "helper"
            and item["callee_resolved_file"] == "pkg/helper.py"
            for item in callees
        )
        callers = cache.query_callers("helper", "pkg/helper.py")
        assert any(
            item["caller_name"] == "build" and item["caller_file"] == "pkg/service.py"
            for item in callers
        )
    finally:
        cache.close()


def test_resolve_only_does_not_reparse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A warm cache resolves pending cross-file refs without re-parsing."""
    _write_project(tmp_path)
    cache = ASTCache(str(tmp_path))
    try:
        assert (
            cache.index_file(str(tmp_path / "pkg" / "base.py"))["status"] == "indexed"
        )
        assert (
            cache.index_file(str(tmp_path / "pkg" / "alias_plugin.py"))["status"]
            == "indexed"
        )
        # AliasPlugin's parent (LP) is cross-file and not yet resolved.
        assert ("pkg/alias_plugin.py", "LP") in _pending_extends(cache)

        calls: list[str] = []
        real_parse = ast_cache_module.Parser.parse_file

        def counting_parse(self: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append(str(args[0]) if args else "")
            return real_parse(self, *args, **kwargs)

        monkeypatch.setattr(ast_cache_module.Parser, "parse_file", counting_parse)

        stats = cache.index_project(resolve_only=True)
        assert stats["mode_used"] == "resolve_only"
        assert calls == []

        # After the resolve-only pass a real resolved EXTENDS edge exists.
        resolved = (
            cache.get_conn()
            .execute(
                "SELECT 1 FROM edges WHERE kind = 'extends' "
                "AND provenance = 'unresolved_refs' AND source_node_id = ?",
                (symbol_node("pkg/alias_plugin.py", "AliasPlugin", 3),),
            )
            .fetchone()
        )
        assert resolved is not None
    finally:
        cache.close()


def test_unknown_parent_stays_unresolved(tmp_path: Path) -> None:
    (tmp_path / "missing.py").write_text(
        "class Orphan(MissingBase):\n    pass\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=5, workers=0)
        # No project class named MissingBase → the EXTENDS edge stays pointing
        # at the unresolved ``class:`` synthetic target.
        assert ("missing.py", "MissingBase") in _pending_extends(cache)
        resolved = (
            cache.get_conn()
            .execute(
                "SELECT 1 FROM edges WHERE kind = 'extends' "
                "AND provenance = 'unresolved_refs' "
                "AND target_node_id LIKE '%MissingBase%'"
            )
            .fetchone()
        )
        assert resolved is None
    finally:
        cache.close()


def test_autoindex_resolves_pending_refs_when_cache_is_already_warm(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    cache = ASTCache(str(tmp_path))
    try:
        assert (
            cache.index_file(str(tmp_path / "pkg" / "base.py"))["status"] == "indexed"
        )
        assert (
            cache.index_file(str(tmp_path / "pkg" / "python_plugin.py"))["status"]
            == "indexed"
        )
        # python_plugin's cross-file parent is unresolved before warming.
        assert ("pkg/python_plugin.py", "LanguagePlugin") in _pending_extends(cache)
    finally:
        cache.close()

    auto_index_guard.reset()
    warmed = auto_index_guard.ensure_indexed(str(tmp_path), max_files=20)
    try:
        assert warmed is not None
        resolved = (
            warmed.get_conn()
            .execute(
                "SELECT 1 FROM edges WHERE kind = 'extends' "
                "AND provenance = 'unresolved_refs' AND source_node_id = ?",
                (symbol_node("pkg/python_plugin.py", "PythonPlugin", 3),),
            )
            .fetchone()
        )
        assert resolved is not None
    finally:
        if warmed is not None:
            warmed.close()
        auto_index_guard.reset()


def test_class_hierarchy_cli_reads_resolved_cross_file_edge(tmp_path: Path) -> None:
    _write_project(tmp_path)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=20, workers=0)
    finally:
        cache.close()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tree_sitter_analyzer",
            "--project-root",
            str(tmp_path),
            "--class-hierarchy",
            "--class-hierarchy-mode",
            "subclasses",
            "--class-hierarchy-class",
            "LanguagePlugin",
            "--format",
            "json",
        ],
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert {item["name"] for item in payload["subclasses"]}.issuperset(
        {"AliasPlugin", "PythonPlugin"}
    )


def test_call_does_not_bind_across_languages(tmp_path: Path) -> None:
    """A Python call must not resolve to a same-named symbol in another language.

    Regression: ``_choose_candidate`` scored candidates by import/path/name only,
    with no language gate. A Python ``config.get(...)`` (bare name ``get``) with no
    Python ``get`` definition in the tree fell through to *any* repo symbol named
    ``get`` ordered by file path — binding to a JavaScript ``get`` and inlining its
    JS body into the Python callee list (wrong AND token-bloat). The call must stay
    unresolved rather than cross the language boundary.
    """
    (tmp_path / "service.py").write_text(
        "def use_config(config):\n    return config.get('key')\n",
        encoding="utf-8",
    )
    # Only definition of ``get`` anywhere in the tree is this JS method.
    (tmp_path / "widget.js").write_text(
        "class Api {\n    get(endpoint) {\n        return fetch(endpoint);\n    }\n}\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=10, workers=0)
        callees = cache.query_callees("use_config", "service.py")
        get_callees = [c for c in callees if c.get("callee_name") == "get"]
        # The ``get`` call may stay unresolved, but it must NEVER resolve to a
        # JavaScript file.
        for callee in get_callees:
            resolved = str(callee.get("callee_resolved_file") or "")
            assert not resolved.endswith(".js"), (
                f"Python call bound across languages to {resolved!r}: {callee}"
            )
    finally:
        cache.close()


def _choose_candidate_conn() -> sqlite3.Connection:
    """Minimal conn for ``_choose_candidate`` (ast_index + ast_imports only)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE ast_index (file_path TEXT PRIMARY KEY, language TEXT);
        CREATE TABLE ast_imports (
            file_path TEXT, module_path TEXT, local_name TEXT, alias_of TEXT
        );
        INSERT INTO ast_index VALUES ('app/main.py', 'python');
        INSERT INTO ast_index VALUES ('zsrc/real.py', 'python');
        INSERT INTO ast_index VALUES ('tests/test_cache.py', 'python');
        """
    )
    return conn


def test_choose_candidate_prefers_source_over_test_shadow() -> None:
    """A non-test caller must bind to the source def, not the test mock.

    Regression: ``_choose_candidate`` broke ties on ``file_path`` alphabetically,
    so ``tests/...`` sorted before the source tree and a real method
    (``fts_search``) bound to its test mock. The test def is now demoted when the
    caller is not itself a test file.
    """
    conn = _choose_candidate_conn()
    try:
        row = {
            "file_path": "app/main.py",
            "from_node_id": "app/main.py:use_cache:5",
            "reference_name": "fts_search",
        }
        # Test def sorts first alphabetically ('tests/' < 'zsrc/'); source must
        # still win via the test-demotion tier.
        candidates = [
            {
                "node_id": "tests/test_cache.py:fts_search:2",
                "id": 1,
                "name": "fts_search",
                "file_path": "tests/test_cache.py",
                "line": 2,
                "language": "python",
            },
            {
                "node_id": "zsrc/real.py:fts_search:9",
                "id": 2,
                "name": "fts_search",
                "file_path": "zsrc/real.py",
                "line": 9,
                "language": "python",
            },
        ]
        chosen = unresolved._choose_candidate(conn, row, candidates)
        assert chosen is not None
        assert chosen["file_path"] == "zsrc/real.py", chosen
    finally:
        conn.close()


def test_choose_candidate_allows_test_target_for_test_caller() -> None:
    """A test caller may still bind to a test definition (no demotion)."""
    conn = _choose_candidate_conn()
    try:
        row = {
            "file_path": "tests/test_cache.py",
            "from_node_id": "tests/test_cache.py:test_fetch:1",
            "reference_name": "helper",
        }
        candidates = [
            {
                "node_id": "tests/test_cache.py:helper:2",
                "id": 1,
                "name": "helper",
                "file_path": "tests/test_cache.py",
                "line": 2,
                "language": "python",
            },
        ]
        chosen = unresolved._choose_candidate(conn, row, candidates)
        assert chosen is not None
        assert chosen["file_path"] == "tests/test_cache.py"
    finally:
        conn.close()


def test_resolve_unresolved_refs_sqlite_error_paths_are_nonfatal() -> None:
    """Missing schema / broken connections must degrade, not crash."""
    no_schema = sqlite3.connect(":memory:")
    no_schema.row_factory = sqlite3.Row
    try:
        assert unresolved.resolve_unresolved_refs(no_schema) is None
        assert unresolved.pending_unresolved_count(no_schema) == 0
        assert unresolved._call_rows(
            no_schema,
            "broken.py",
            [{"caller_name": "caller", "callee_name": "target"}],
        ) == [{"caller_name": "caller", "callee_name": "target"}]
        assert (
            unresolved._candidate_symbols(
                no_schema, "broken.py", "Missing", EdgeKind.CALLS.value
            )
            == []
        )
        assert unresolved._reference_names(no_schema, "broken.py", "Alias") == ["Alias"]
        assert unresolved._import_target_hints(no_schema, "broken.py", "Alias") == set()
        assert unresolved._file_language(no_schema, "broken.py") == ""
    finally:
        no_schema.close()


def test_resolve_unresolved_refs_row_and_commit_error_paths() -> None:
    """A resolvable ref whose UPDATE/upsert fails counts as an error, not a crash."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        # ast_index drives the per-file loop; the EXTENDS upsert then fails
        # because the ``edges`` table is intentionally absent.
        conn.executescript(
            """
            CREATE TABLE ast_index (
                file_path TEXT NOT NULL,
                language TEXT NOT NULL,
                symbols_json TEXT NOT NULL
            );
            CREATE TABLE ast_symbol_rows (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                file_path TEXT NOT NULL,
                language TEXT NOT NULL,
                line INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO ast_index (file_path, language, symbols_json) VALUES (?, ?, ?)",
            (
                "child.py",
                "python",
                json.dumps(
                    {
                        "symbols": [
                            {
                                "kind": "class",
                                "name": "Child",
                                "line": 1,
                                "parents": ["Base"],
                            }
                        ]
                    }
                ),
            ),
        )
        conn.execute(
            """INSERT INTO ast_symbol_rows (id, name, kind, file_path, language, line)
               VALUES (10, 'Base', 'class', 'base.py', 'python', 1)"""
        )
        stats = unresolved.resolve_unresolved_refs(conn)
        assert stats == {"total": 1, "resolved": 0, "unchanged": 0, "errors": 1}
    finally:
        conn.close()

    class EmptyRows:
        def fetchall(self) -> list[Any]:
            return []

    class CommitFails:
        def execute(self, *_args: Any, **_kwargs: Any) -> EmptyRows:
            return EmptyRows()

        def commit(self) -> None:
            raise sqlite3.OperationalError("commit failed")

    assert unresolved.resolve_unresolved_refs(CommitFails()) == {
        "total": 0,
        "resolved": 0,
        "unchanged": 0,
        "errors": 0,
    }


def test_non_python_skips_second_pass_refs() -> None:
    """A2/B1.3: non-Python languages emit no second-pass refs.

    They have no structured import parsing, so cross-file resolution is pure
    waste (and the dominant stall/OOM cost on large Java repos). Python keeps
    producing refs.
    """
    assert unresolved._refs_supported("python") is True
    for lang in ("java", "go", "cobol", "csharp", "javascript"):
        assert unresolved._refs_supported(lang) is False

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        java_class = {
            "symbols": [{"kind": "class", "name": "Foo", "line": 1, "parents": ["Bar"]}]
        }
        assert (
            unresolved._pending_refs_for_file(conn, "Foo.java", "java", java_class)
            == []
        )
        # Python on the same shape DOES produce a pending EXTENDS ref.
        py_refs = unresolved._pending_refs_for_file(
            conn, "foo.py", "python", java_class
        )
        assert any(r["reference_kind"] == EdgeKind.EXTENDS.value for r in py_refs)
    finally:
        conn.close()


def test_pending_refs_and_helper_branches() -> None:
    # Local / already-resolved / obvious-external refs are filtered out.
    assert (
        unresolved._parent_refs(
            "child.py",
            [
                {"kind": "class", "parents": ["Base"]},
                {"kind": "class", "name": "LocalChild", "line": 2, "parents": ["Base"]},
            ],
            {"Base"},
        )
        == []
    )
    assert (
        unresolved._call_refs(
            sqlite3.connect(":memory:"),
            "caller.py",
            "python",
            [
                {
                    "caller_name": "caller",
                    "caller_line": 1,
                    "callee_name": "target",
                    "callee_line": 2,
                    "callee_resolution": "project",
                    "callee_resolved_file": "target.py",
                },
                {
                    "caller_name": "caller",
                    "caller_line": 1,
                    "callee_name": "local_target",
                    "callee_line": 3,
                },
                {
                    "caller_name": "caller",
                    "caller_line": 1,
                    "callee_name": "print",
                    "callee_line": 4,
                },
            ],
            {"local_target"},
        )
        == []
    )
    candidate = {"node_id": "same.py:Only:1", "file_path": "same.py", "line": 1}
    assert (
        unresolved._choose_candidate(
            sqlite3.connect(":memory:"),
            {
                "file_path": "same.py",
                "from_node_id": "same.py:Only:1",
                "reference_name": "Only",
            },
            [candidate],
        )
        is None
    )
    # _update_call_edge_resolution tolerates a file: node id and a missing edges
    # table without raising.
    unresolved._update_call_edge_resolution(
        sqlite3.connect(":memory:"),
        {
            "from_node_id": "file:caller.py",
            "reference_kind": EdgeKind.CALLS.value,
            "file_path": "caller.py",
            "reference_name": "target",
            "line": 0,
        },
        {"id": 1, "file_path": "target.py"},
    )
    unresolved._update_call_edge_resolution(
        sqlite3.connect(":memory:"),
        {
            "from_node_id": "caller.py:caller:1",
            "reference_kind": EdgeKind.CALLS.value,
            "file_path": "caller.py",
            "reference_name": "target",
            "line": 2,
        },
        {"id": 1, "file_path": "target.py"},
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """CREATE TABLE ast_imports (
                file_path TEXT,
                module_path TEXT,
                local_name TEXT,
                alias_of TEXT
            )"""
        )
        conn.execute(
            """INSERT INTO ast_imports
               (file_path, module_path, local_name, alias_of)
               VALUES ('caller.py', '.base', 'Other', '')"""
        )
        assert unresolved._import_target_hints(conn, "caller.py", "Base") == set()
    finally:
        conn.close()

    assert unresolved._module_path_candidates("") == set()
    assert unresolved._matches_import_hint("pkg/base.py", set()) is False
    assert unresolved._file_language(sqlite3.connect(":memory:"), "missing.py") == ""
    assert unresolved._call_is_resolved({"callee_resolution": "stdlib"}) is True
    assert unresolved._is_obvious_external("javascript", "console.log") is False

    assert unresolved._line("not-an-int") == 0
    assert unresolved._row_to_dict(("value",), ("name",)) == {"name": "value"}


def test_orchestration_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = ASTCache(str(tmp_path))
    try:
        monkeypatch.setattr(cache, "backfill_cross_file_edges", lambda: {})
        monkeypatch.setattr(cache, "_run_synapse_backfill", lambda: None)
        monkeypatch.setattr(cache, "_refresh_graph_edges_from_cache", lambda _files: {})

        def fail_unresolved() -> dict[str, int]:
            raise RuntimeError("nope")

        monkeypatch.setattr(cache, "_run_unresolved_refs_backfill", fail_unresolved)
        stats: dict[str, Any] = {"files": []}
        cache._post_index_backfill(stats)
        assert "unresolved_refs_backfill" not in stats

        monkeypatch.setattr(cache, "_run_unresolved_refs_backfill", lambda: None)
        stats = {"files": []}
        cache._post_index_backfill(stats)
        assert "unresolved_refs_backfill" not in stats
    finally:
        cache.close()

    clean_cache = ASTCache(str(tmp_path))
    try:
        auto_index_guard._resolve_pending_unresolved_refs(clean_cache)
    finally:
        clean_cache.close()

    class BrokenCache:
        def get_conn(self) -> None:
            raise RuntimeError("connection failed")

    auto_index_guard._resolve_pending_unresolved_refs(BrokenCache())
