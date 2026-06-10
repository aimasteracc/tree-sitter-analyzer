"""Regression test: builtin-receiver gate — dict.get must NOT bind to a project .get.

Issue #447: callee_tree binds ``result.get("format")`` (a dict.get() call) to
``SearchCache.get`` because the second-pass resolver (_choose_candidate path) lacks
the builtin-method guard that the synapse cascade already has.

The conservative policy (consistent with issue spec): when the receiver is an
unidentifiable variable (not imported, not self/cls) AND the method name is in
STDLIB_METHODS_PY, leave the call unresolved rather than bind it to a project symbol.

Tests:
1. RED (bug repro): dict.get with project-owned .get → NOT project-resolved to SearchCache
2. Counter-case: actual SearchCache import + instance.get() → DOES bind to SearchCache.get
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache


def _index(tmp_path: Path, files: dict[str, str]) -> str:
    """Index files under tmp_path and return the .ast-cache DB path."""
    proj = tmp_path / "pkg"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "__init__.py").write_text("# pkg\n")
    for name, body in files.items():
        (proj / name).write_text(body)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return str(tmp_path / ".ast-cache" / "index.db")


def _edges_for(db_path: str, callee_name: str) -> list[dict]:
    """Return all CALLS edges for callee_name as dicts."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT callee_name, callee_resolution, callee_resolved_file, file_path "
            "FROM edges WHERE kind = 'calls' AND callee_name = ?",
            (callee_name,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def test_dict_get_does_not_bind_to_project_search_cache_get(tmp_path: Path) -> None:
    """Bug repro #447: result.get("format") in a file that does NOT import SearchCache
    must not be resolved to SearchCache.get.

    The project defines SearchCache.get (so the project-ownership gate in
    _try_stdlib_method correctly prevents stdlib classification by synapse).
    The second-pass resolver (_choose_candidate) must also NOT bind this to a
    project symbol — it must stay unresolved (unknown or stdlib).
    """
    db = _index(
        tmp_path,
        {
            # Project has SearchCache with a .get method — the source of the mis-wire.
            "search_cache.py": (
                "class SearchCache:\n"
                "    def get(self, cache_key: str):\n"
                "        return None\n"
            ),
            # format_helper.py does NOT import search_cache; result is a plain dict.
            "format_helper.py": (
                "def apply_toon_format_to_response(result):\n"
                "    if result.get('format') != 'toon':\n"
                "        return result\n"
                "    if result.get('success') is True:\n"
                "        return result\n"
                "    return result\n"
            ),
        },
    )

    edges = _edges_for(db, "get")
    assert edges, "expected call edges for 'get'"

    # None of the dict.get() calls from format_helper.py must resolve to a project
    # symbol — no callee_resolved_file pointing to search_cache.py.
    format_helper_edges = [e for e in edges if "format_helper" in e["file_path"]]
    assert format_helper_edges, "expected get() edges in format_helper.py"

    project_resolved = [
        e
        for e in format_helper_edges
        if e["callee_resolution"] == "project"
        and "search_cache" in (e["callee_resolved_file"] or "")
    ]
    assert project_resolved == [], (
        f"dict.get() in format_helper.py must NOT bind to SearchCache.get "
        f"(builtin-receiver gate missing in path 2); got {project_resolved}"
    )


def test_imported_search_cache_get_still_binds(tmp_path: Path) -> None:
    """Counter-case: when the caller IMPORTS SearchCache and uses an instance,
    sc.get() SHOULD bind to SearchCache.get — the gate must not over-block.

    This tests that the fix does not regress legitimate project-symbol resolution.
    """
    db = _index(
        tmp_path,
        {
            "search_cache.py": (
                "class SearchCache:\n"
                "    def get(self, cache_key: str):\n"
                "        return None\n"
            ),
            "consumer.py": (
                "from pkg.search_cache import SearchCache\n\n"
                "def use_cache():\n"
                "    sc = SearchCache()\n"
                "    return sc.get('key')\n"
            ),
        },
    )

    edges = _edges_for(db, "get")
    consumer_edges = [e for e in edges if "consumer" in e["file_path"]]
    assert consumer_edges, "expected get() edges in consumer.py"

    # At least one edge from consumer.py must resolve to search_cache.py
    project_edges = [
        e
        for e in consumer_edges
        if e["callee_resolution"] == "project"
        and "search_cache" in (e["callee_resolved_file"] or "")
    ]
    assert project_edges, (
        f"sc.get() with explicit SearchCache import must bind to SearchCache.get; "
        f"got {consumer_edges}"
    )
