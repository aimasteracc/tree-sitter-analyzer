"""#1942: definition-to-definition call paths over a hand-built index."""

from __future__ import annotations

import json
import sqlite3

from tree_sitter_analyzer.call_path_pinned import (
    DEPTH_REASON,
    NAME_ONLY,
    OPEN_SITES_REASON,
    Definition,
    SymbolBook,
    callee_of,
    find_pinned_paths,
    incoming,
    outgoing,
)
from tree_sitter_analyzer.mcp.tools import call_path_endpoints as endpoints

_SYMBOLS = {
    "a.py": [
        {"kind": "function", "name": "top", "line": 1, "end_line": 3},
        {"kind": "method", "name": "mid", "line": 5, "end_line": 7, "class": "M"},
        {"kind": "method", "name": "mid", "line": 9, "end_line": 11, "class": "N"},
    ],
    "b.py": [
        {"kind": "method", "name": "leaf", "line": 2, "end_line": 4, "class": "L"},
        {"kind": "function", "name": "other", "line": 6, "end_line": 7},
    ],
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path TEXT, symbols_json TEXT)")
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER PRIMARY KEY, name TEXT, kind TEXT, "
        "file_path TEXT, line INTEGER)"
    )
    conn.execute(
        "CREATE TABLE edges (kind TEXT, caller_name TEXT, file_path TEXT, "
        "caller_line INTEGER, line INTEGER, callee_name TEXT, callee_full TEXT, "
        "callee_resolution TEXT, callee_resolved_file TEXT, callee_symbol_id INTEGER, "
        "metadata TEXT)"
    )
    for file, symbols in _SYMBOLS.items():
        conn.execute(
            "INSERT INTO ast_index VALUES (?, ?)",
            (file, json.dumps({"symbols": symbols})),
        )
        for sym in symbols:
            conn.execute(
                "INSERT INTO ast_symbol_rows (name, kind, file_path, line) "
                "VALUES (?, ?, ?, ?)",
                (sym["name"], sym["kind"], file, sym["line"]),
            )
    leaf_id = conn.execute(
        "SELECT id FROM ast_symbol_rows WHERE name = 'leaf'"
    ).fetchone()[0]
    rows = [
        # top -> M.mid, bound to a file with two `mid`: ambiguous, so unbound
        ("top", "a.py", 1, 2, "mid", "x.mid", "unknown", "", None),
        # top -> L.leaf through a bound symbol
        ("top", "a.py", 1, 3, "leaf", "self.leaf", "project", "b.py", leaf_id),
        # L.leaf -> other through an untyped receiver
        ("leaf", "b.py", 2, 3, "other", "y.other", "unknown", "", None),
        # L.leaf -> len (builtin): never an open site
        ("leaf", "b.py", 2, 4, "len", "len", "builtin", "", None),
    ]
    for row in rows:
        conn.execute(
            "INSERT INTO edges VALUES ('calls', ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')", row
        )
    return conn


def _definition(book: SymbolBook, name: str, file: str) -> Definition:
    return book.at(name, file)[0]


def test_resolved_hop_then_name_only_hop_onto_the_target() -> None:
    conn = _conn()
    book = SymbolBook(conn)
    top = _definition(book, "top", "a.py")
    other = _definition(book, "other", "b.py")

    found = find_pinned_paths(conn, book, top, other, max_depth=5, max_paths=3)

    assert [s["callee"] for s in found.open_sites] == ["x.mid"]
    [hops] = found.paths
    assert [(h["caller"], h["callee"], h["callee_resolution"]) for h in hops] == [
        ("top", "L.leaf", "resolved"),
        ("L.leaf", "other", NAME_ONLY),
    ]
    assert hops[1]["callee_expression"] == "y.other"


def test_unbound_calls_on_the_frontier_make_no_path_incomplete() -> None:
    conn = _conn()
    book = SymbolBook(conn)
    top = _definition(book, "top", "a.py")
    target = Definition("absent", "c.py", 1)

    found = find_pinned_paths(conn, book, top, target, max_depth=5, max_paths=3)

    assert found.paths == []
    assert [(s["file"], s["line"]) for s in found.open_sites] == [
        ("a.py", 2),
        ("b.py", 3),
    ]
    assert found.reasons == [OPEN_SITES_REASON]
    shallow = find_pinned_paths(conn, book, top, target, max_depth=1, max_paths=3)
    assert DEPTH_REASON in shallow.reasons


def test_neighbours_and_symbol_lookups() -> None:
    conn = _conn()
    book = SymbolBook(conn)
    leaf = _definition(book, "leaf", "b.py")
    other = _definition(book, "other", "b.py")

    assert [r["callee_name"] for r in outgoing(conn, leaf)] == ["other", "len"]
    assert [r["resolution"] for r in incoming(conn, book, leaf)] == ["resolved"]
    assert [r["resolution"] for r in incoming(conn, book, other)] == [NAME_ONLY]
    assert (
        callee_of(book, {"callee_name": "mid", "callee_resolved_file": "a.py"}) is None
    )
    assert book.by_id(999) is None
    assert book.declared("leaf") and not book.declared("nothing")
    assert [d.label for d in book.named("mid")] == ["M.mid", "N.mid"]


def test_unreadable_index_degrades_to_no_definitions() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    book = SymbolBook(conn)
    node = Definition("f", "a.py", 1)

    assert book.named("f") == []
    assert book.in_file("a.py") == []
    assert book.symbol_id(node) is None
    assert book.by_id(1) is None
    assert book.declared("f") is True  # unreadable: assume it may exist
    assert outgoing(conn, node) == []
    assert incoming(conn, book, node) == []


def test_endpoint_resolution_and_retry_text() -> None:
    book = SymbolBook(_conn())

    resolved = endpoints.resolve(book, "source", "L.leaf", None)
    assert resolved.status == "resolved"
    ambiguous = endpoints.resolve(book, "source", "mid", "a.py")
    assert ambiguous.status == "ambiguous"
    module = endpoints.resolve(book, "target", "pkg.L.leaf", "./b.py")
    assert module.status == "resolved"
    missing = endpoints.resolve(book, "target", "Q.zzz", None)
    assert missing.status == "not_resolved" and missing.candidates == ()

    failed = endpoints.failure_response([ambiguous, missing])
    assert failed["path_status"] == endpoints.NOT_RESOLVED
    assert "--call-path-source-file a.py" in failed["next_step"]
    assert "names no function or method" in failed["next_step"]
    assert endpoints.failure_response([ambiguous])["path_status"] == endpoints.AMBIGUOUS
    assert not endpoints.is_qualified("pkg/mod.py:f")
