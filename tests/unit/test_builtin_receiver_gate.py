"""Regression + new-design tests: inverted builtin-receiver gate.

Issue #447 (original): callee_tree bound ``result.get("format")`` (a dict.get()
call) to ``SearchCache.get`` because path 2 (_choose_candidate) lacked the
builtin-receiver guard that synapse path 1 already had.

Adversarial P1 (live-confirmed over-gating): the OLD gate fired on ANY
non-self/cls receiver whose bare method name was in STDLIB_METHODS_PY — losing
CORRECT edges for untyped receivers (``store.get()`` with unique project
DataStore.get was blocked; ``unknown > correct`` violated).

NEW DESIGN (inverted): the gate fires ONLY when the receiver is POSITIVELY
inferred as a builtin type by the extractor:
  - ``result = {}`` / ``result = dict()`` → callee_full rewritten to
    ``dict.get``; qualifier == "dict" IS in BUILTIN_TYPE_NAMES_PY → blocked.
  - ``store`` (untyped param) → qualifier == "store" NOT in BUILTIN_TYPE_NAMES_PY
    → allowed through to unique-method binding.

Tests:
1. RED (bug repro, inference-provable builtin): ``result = {}; result.get()`` in
   a file that does NOT import SearchCache → must NOT bind to SearchCache.get.
2. Counter-case: explicit SearchCache import + sc.get() → DOES bind.
3. NEW: untyped param receiver ``store.get()`` with unique DataStore.get →
   MUST bind (restores P1-regressed case).
4. NEW: self._store.get() where DataStore.get is unique → MUST bind.
5. NEW: module-level singleton CACHE.get() where CacheStore.get is unique →
   MUST bind (the CACHE singleton case is P3).
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
    """Bug repro #447 (adjusted for new-design): ``result = {}; result.get()`` in
    a file that does NOT import SearchCache must not be resolved to SearchCache.get.

    The extractor infers ``result`` has type ``dict`` (from the literal assignment),
    rewrites callee_full to ``dict.get``, so qualifier == "dict" is in
    BUILTIN_TYPE_NAMES_PY and the gate fires correctly.  ``unknown > wrong``.
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
            # format_helper.py does NOT import search_cache.
            # result is a LOCAL DICT LITERAL — the extractor infers its type.
            "format_helper.py": (
                "def apply_toon_format_to_response(raw_result):\n"
                "    result = {}\n"
                "    result['key'] = raw_result\n"
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


def test_untyped_param_receiver_unique_method_binds(tmp_path: Path) -> None:
    """P1 adversarial regression: untyped param ``store`` calling ``store.get()``
    where DataStore.get is the ONLY project ``get`` method must bind to DataStore.get.

    The OLD gate (STDLIB_METHODS_PY match on any receiver) blocked this — lost a
    correct edge. The new inverted gate only fires when the receiver is positively
    inferred as a builtin type. ``store`` is a param name, not in
    BUILTIN_TYPE_NAMES_PY, so it passes through to unique-method binding.
    """
    db = _index(
        tmp_path,
        {
            "data_store.py": (
                "class DataStore:\n    def get(self, key: str):\n        return None\n"
            ),
            "processor.py": (
                "def process(store):\n    value = store.get('key')\n    return value\n"
            ),
        },
    )

    edges = _edges_for(db, "get")
    proc_edges = [e for e in edges if "processor" in e["file_path"]]
    assert proc_edges, "expected get() edges in processor.py"

    project_edges = [
        e
        for e in proc_edges
        if e["callee_resolution"] == "project"
        and "data_store" in (e["callee_resolved_file"] or "")
    ]
    assert project_edges, (
        f"store.get() with unique DataStore.get must bind to DataStore.get "
        f"(inverted gate must not over-block untyped params); got {proc_edges}"
    )


def test_self_attr_receiver_unique_method_binds(tmp_path: Path) -> None:
    """P1 adversarial case: ``self._store.get()`` where DataStore.get is unique
    must bind. ``self._store`` has qualifier ``self._store``; its last segment
    ``_store`` is not in BUILTIN_TYPE_NAMES_PY, so the gate does not fire.
    """
    db = _index(
        tmp_path,
        {
            "data_store.py": (
                "class DataStore:\n    def get(self, key: str):\n        return None\n"
            ),
            "service.py": (
                "from pkg.data_store import DataStore\n\n"
                "class MyService:\n"
                "    def __init__(self):\n"
                "        self._store = DataStore()\n"
                "    def fetch(self, key):\n"
                "        return self._store.get(key)\n"
            ),
        },
    )

    edges = _edges_for(db, "get")
    svc_edges = [e for e in edges if "service" in e["file_path"]]
    assert svc_edges, "expected get() edges in service.py"

    project_edges = [
        e
        for e in svc_edges
        if e["callee_resolution"] == "project"
        and "data_store" in (e["callee_resolved_file"] or "")
    ]
    assert project_edges, (
        f"self._store.get() with DataStore.get must bind; got {svc_edges}"
    )


def test_singleton_receiver_unique_method_binds(tmp_path: Path) -> None:
    """P3 adversarial case: module-level singleton ``CACHE.get()`` where
    CacheStore.get is the only project ``get`` — must bind.
    ``CACHE`` is a module-level name, not a builtin type name.
    """
    db = _index(
        tmp_path,
        {
            "cache_store.py": (
                "class CacheStore:\n    def get(self, key: str):\n        return None\n"
            ),
            "cache_client.py": (
                "from pkg.cache_store import CacheStore\n\n"
                "CACHE = CacheStore()\n\n"
                "def lookup(key):\n"
                "    return CACHE.get(key)\n"
            ),
        },
    )

    edges = _edges_for(db, "get")
    client_edges = [e for e in edges if "cache_client" in e["file_path"]]
    assert client_edges, "expected get() edges in cache_client.py"

    project_edges = [
        e
        for e in client_edges
        if e["callee_resolution"] == "project"
        and "cache_store" in (e["callee_resolved_file"] or "")
    ]
    assert project_edges, (
        f"CACHE.get() singleton with unique CacheStore.get must bind; got {client_edges}"
    )
