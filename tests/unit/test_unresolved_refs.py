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
from tree_sitter_analyzer._ast_cache_schema import apply_migration_v9
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


def test_unresolved_refs_schema_created(tmp_path: Path) -> None:
    cache = ASTCache(str(tmp_path))
    try:
        conn = cache.get_conn()
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(unresolved_refs)").fetchall()
        }
        assert {
            "from_node_id",
            "reference_name",
            "reference_kind",
            "file_path",
            "line",
            "candidates",
            "resolved",
        }.issubset(columns)
        indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list(unresolved_refs)").fetchall()
        }
        assert {"idx_unresolved_name", "idx_unresolved_resolved"}.issubset(indexes)
        version = conn.execute(
            "SELECT description FROM ast_schema_version WHERE version = 9"
        ).fetchone()
        assert version["description"] == "Unresolved reference backfill"
    finally:
        cache.close()


def test_index_file_records_unresolved_refs_before_second_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        row = (
            cache.get_conn()
            .execute(
                """SELECT reference_name, reference_kind, resolved
               FROM unresolved_refs
               WHERE file_path = 'pkg/alias_plugin.py'"""
            )
            .fetchone()
        )
        assert dict(row) == {
            "reference_name": "LP",
            "reference_kind": EdgeKind.EXTENDS.value,
            "resolved": 0,
        }

        calls: list[str] = []
        real_parse = ast_cache_module.Parser.parse_file

        def counting_parse(self: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append(str(args[0]) if args else "")
            return real_parse(self, *args, **kwargs)

        monkeypatch.setattr(ast_cache_module.Parser, "parse_file", counting_parse)

        stats = cache.index_project(resolve_only=True)
        assert stats["mode_used"] == "resolve_only"
        assert calls == []
        resolved = (
            cache.get_conn()
            .execute(
                """SELECT resolved
               FROM unresolved_refs
               WHERE file_path = 'pkg/alias_plugin.py'"""
            )
            .fetchone()
        )
        assert resolved["resolved"] == 1
    finally:
        cache.close()


def test_index_project_resolves_cross_file_extends_and_calls(tmp_path: Path) -> None:
    _write_project(tmp_path)
    cache = ASTCache(str(tmp_path))
    try:
        stats = cache.index_project(max_files=20, workers=0)
        assert stats["indexed"] >= 7
        assert stats["unresolved_refs_backfill"]["resolved"] >= 3

        resolved_refs = _rows(
            cache,
            """SELECT reference_name, reference_kind, file_path, resolved
               FROM unresolved_refs
               WHERE resolved = 1
               ORDER BY file_path, reference_name""",
        )
        assert {
            (row["file_path"], row["reference_name"], row["reference_kind"])
            for row in resolved_refs
        }.issuperset(
            {
                ("pkg/alias_plugin.py", "LP", EdgeKind.EXTENDS.value),
                ("pkg/python_plugin.py", "LanguagePlugin", EdgeKind.EXTENDS.value),
                ("pkg/service.py", "helper", EdgeKind.CALLS.value),
            }
        )

        conn = cache.get_conn()
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


def test_unknown_parent_stays_unresolved(tmp_path: Path) -> None:
    (tmp_path / "missing.py").write_text(
        "class Orphan(MissingBase):\n    pass\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=5, workers=0)
        row = (
            cache.get_conn()
            .execute(
                """SELECT resolved, candidates
               FROM unresolved_refs
               WHERE reference_name = 'MissingBase'"""
            )
            .fetchone()
        )
        assert row["resolved"] == 0
        assert json.loads(row["candidates"]) == []
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
    finally:
        cache.close()

    auto_index_guard.reset()
    warmed = auto_index_guard.ensure_indexed(str(tmp_path), max_files=20)
    try:
        assert warmed is not None
        row = (
            warmed.get_conn()
            .execute(
                """SELECT resolved
               FROM unresolved_refs
               WHERE file_path = 'pkg/python_plugin.py'"""
            )
            .fetchone()
        )
        assert row["resolved"] == 1
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


def test_unresolved_refs_sqlite_error_paths_are_nonfatal(
    tmp_path: Path,
) -> None:
    no_schema = sqlite3.connect(":memory:")
    no_schema.row_factory = sqlite3.Row
    try:
        unresolved.write_unresolved_refs_for_file(
            no_schema,
            "broken.py",
            "python",
            {"symbols": []},
            [],
        )
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

    bad_insert = sqlite3.connect(":memory:")
    bad_insert.row_factory = sqlite3.Row
    try:
        bad_insert.execute("CREATE TABLE unresolved_refs (file_path TEXT)")
        unresolved.write_unresolved_refs_for_file(
            bad_insert,
            "child.py",
            "python",
            {
                "symbols": [
                    {
                        "kind": "class",
                        "name": "Child",
                        "line": 1,
                        "parents": ["Base"],
                    }
                ]
            },
            [],
        )
    finally:
        bad_insert.close()


def test_unresolved_refs_row_and_commit_error_paths() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE unresolved_refs (
                id INTEGER PRIMARY KEY,
                from_node_id TEXT NOT NULL,
                reference_name TEXT NOT NULL,
                reference_kind TEXT NOT NULL,
                file_path TEXT NOT NULL,
                line INTEGER,
                candidates TEXT,
                resolved INTEGER DEFAULT 0
            );
            CREATE TABLE ast_symbol_rows (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                file_path TEXT NOT NULL,
                language TEXT NOT NULL,
                line INTEGER NOT NULL
            );
            CREATE TABLE ast_index (
                file_path TEXT NOT NULL,
                language TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """INSERT INTO unresolved_refs
               (id, from_node_id, reference_name, reference_kind, file_path, line)
               VALUES (1, 'caller.py:caller:1', 'target', 'calls', 'caller.py', 2)"""
        )
        conn.execute(
            """INSERT INTO ast_symbol_rows
               (id, name, kind, file_path, language, line)
               VALUES (10, 'target', 'function', 'target.py', 'python', 1)"""
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


def test_non_python_skips_unresolved_refs_rows() -> None:
    """A2: non-Python languages must not emit unresolved_refs rows.

    They have no structured import parsing, so second-pass resolution is pure
    waste (and the dominant stall/OOM cost on large Java repos). Python keeps
    writing rows.
    """
    assert unresolved._refs_supported("python") is True
    for lang in ("java", "go", "cobol", "csharp", "javascript"):
        assert unresolved._refs_supported(lang) is False

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE unresolved_refs (
                id INTEGER PRIMARY KEY,
                from_node_id TEXT NOT NULL,
                reference_name TEXT NOT NULL,
                reference_kind TEXT NOT NULL,
                file_path TEXT NOT NULL,
                line INTEGER,
                candidates TEXT,
                resolved INTEGER DEFAULT 0
            );
            CREATE TABLE ast_call_edges (
                id INTEGER PRIMARY KEY,
                caller_name TEXT, caller_file TEXT, caller_line INTEGER,
                callee_name TEXT, callee_full TEXT, callee_line INTEGER,
                file_path TEXT, language TEXT,
                callee_resolution TEXT, callee_resolved_file TEXT
            );
            """
        )
        java_class = {
            "symbols": [{"kind": "class", "name": "Foo", "line": 1, "parents": ["Bar"]}]
        }
        java_calls = [
            {
                "caller_name": "Foo",
                "caller_line": 5,
                "callee_name": "doThing",
                "callee_line": 6,
            }
        ]
        unresolved.write_unresolved_refs_for_file(
            conn, "Foo.java", "java", java_class, java_calls
        )
        rows = conn.execute("SELECT COUNT(*) AS c FROM unresolved_refs").fetchone()
        assert rows["c"] == 0

        # Python on the same shape DOES write rows.
        unresolved.write_unresolved_refs_for_file(
            conn, "foo.py", "python", java_class, java_calls
        )
        rows = conn.execute("SELECT COUNT(*) AS c FROM unresolved_refs").fetchone()
        assert rows["c"] > 0
    finally:
        conn.close()


def test_unresolved_refs_helper_branches(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_unresolved_refs_migration_and_orchestration_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken_schema = sqlite3.connect(":memory:")
    try:
        broken_schema.execute("CREATE TABLE unresolved_refs (id INTEGER)")
        recorded: list[int] = []
        apply_migration_v9(
            broken_schema,
            lambda _conn, version, _description: recorded.append(version),
        )
        assert recorded == []
    finally:
        broken_schema.close()

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
