"""Unit rules of ``callers_cross_file`` (#1936) on a hand-built index."""

from __future__ import annotations

import sqlite3

from tree_sitter_analyzer.mcp.tools.callers_cross_file import (
    cross_file_unresolved_sites,
)


class _Cache:
    def __init__(self, conn: sqlite3.Connection | None) -> None:
        self._conn = conn

    def get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise sqlite3.OperationalError("closed")
        return self._conn


def _cache(language: str, edges: list[tuple]) -> _Cache:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_symbol_rows (name TEXT, kind TEXT, file_path TEXT, "
        "language TEXT, line INTEGER, end_line INTEGER)"
    )
    conn.execute(
        "INSERT INTO ast_symbol_rows VALUES ('make', 'method', 'a/Base.x', ?, 2, 2)",
        (language,),
    )
    conn.execute(
        "CREATE TABLE edges (id INTEGER PRIMARY KEY, source_node_id TEXT, "
        "target_node_id TEXT, kind TEXT, line INTEGER, provenance TEXT, "
        "metadata TEXT, caller_name TEXT, callee_name TEXT, file_path TEXT, "
        "caller_line INTEGER, callee_full TEXT, callee_line INTEGER, "
        "language TEXT, callee_resolution TEXT, callee_resolved_file TEXT, "
        "callee_symbol_id INTEGER)"
    )
    for file_path, line, caller, caller_line, resolution, edge_language in edges:
        conn.execute(
            "INSERT INTO edges (source_node_id, target_node_id, kind, line, "
            "provenance, metadata, caller_name, callee_name, file_path, "
            "caller_line, callee_full, callee_line, language, callee_resolution, "
            "callee_resolved_file) VALUES (?, ?, 'calls', ?, 'tree-sitter', '{}', "
            "?, 'make', ?, ?, 'make', ?, ?, ?, '')",
            (
                f"{file_path}:{caller}:{caller_line}",
                f"{file_path}:make:{line}",
                line,
                caller,
                file_path,
                caller_line,
                line,
                edge_language,
                resolution,
            ),
        )
    return _Cache(conn)


def _sites(cache: _Cache, **kwargs) -> list[dict] | None:
    return cross_file_unresolved_sites(
        cache,
        "make",
        kwargs.pop("file_path", "a/Base.x"),
        listed=kwargs.pop("listed", []),
        known=kwargs.pop("known", []),
    )


def test_unresolved_call_in_another_file_is_an_open_site() -> None:
    cache = _cache("swift", [("a/Sub.x", 5, "run", 3, "unknown", "swift")])

    assert _sites(cache) == [
        {"file": "a/Sub.x", "line": 5, "caller": "run", "callee": "make"}
    ]


def test_resolved_known_listed_and_other_language_sites_are_skipped() -> None:
    cache = _cache(
        "csharp",
        [
            ("a/Resolved.x", 4, "run", 1, "project", "csharp"),
            ("a/Known.x", 7, "run", 1, "unknown", "csharp"),
            ("a/Listed.x", 9, "go", 8, "unknown", "csharp"),
            ("a/Other.x", 2, "run", 1, "unknown", "php"),
            ("a/Base.x", 6, "own", 5, "unknown", "csharp"),
            ("a/Module.x", 1, "", 0, "unknown", "csharp"),
        ],
    )

    sites = _sites(
        cache,
        known=[{"file": "a/Known.x", "line": 7}],
        listed=[{"file": "a/Listed.x", "line": 8}],
    )

    assert sites == [
        {"file": "a/Module.x", "line": 1, "caller": "<module>", "callee": "make"}
    ]


def test_gated_languages_are_left_to_their_resolvers() -> None:
    for language in ("python", "typescript", "java", "kotlin"):
        cache = _cache(language, [("a/Sub.x", 5, "run", 3, "unknown", language)])

        assert _sites(cache) == [], language


def test_no_file_path_adds_nothing() -> None:
    cache = _cache("swift", [("a/Sub.x", 5, "run", 3, "unknown", "swift")])

    assert _sites(cache, file_path=None) == []
    assert (
        cross_file_unresolved_sites(None, "make", "a/Base.x", listed=[], known=[]) == []
    )


def test_unreadable_index_is_not_evidence() -> None:
    assert _sites(_Cache(None)) is None
