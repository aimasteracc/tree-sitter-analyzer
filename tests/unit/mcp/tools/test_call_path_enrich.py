"""Deterministic tests for call_path body inlining (coordinates -> content).

Verifies the turn-saving upgrade: call_path now inlines verbatim source
bodies + a deterrent ``next_step`` (path found), and inlines both endpoints'
bodies + neighbours on a dead end. No benchmark needed — assertions check the
response shape directly.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.unit._navigation_test_support import assert_sqlite_deadline_falls_back
from tree_sitter_analyzer.mcp.tools import call_path_enrich as enrich
from tree_sitter_analyzer.mcp.tools.call_path_tool import CodeGraphCallPathTool

# Source files written to disk so bodies can be read verbatim.
_SRC_A = '''def alpha():
    """alpha doc."""
    beta()
    return 1
'''

_SRC_B = """def beta():
    # beta calls gamma
    gamma()
    return 2
"""

_SRC_C = """def gamma():
    return "GAMMA_BODY_MARKER"
"""

_EDGES = [
    {
        "caller_name": "alpha",
        "caller_file": "a.py",
        "caller_line": 3,
        "callee_name": "beta",
        "callee_line": 1,
        "callee_resolved_file": "b.py",
    },
    {
        "caller_name": "beta",
        "caller_file": "b.py",
        "caller_line": 3,
        "callee_name": "gamma",
        "callee_line": 1,
        "callee_resolved_file": "c.py",
    },
]

# (file, [symbols]) — symbols carry def spans for body lookup.
_SYMBOLS = {
    "a.py": [{"name": "alpha", "kind": "function", "line": 1, "end_line": 4}],
    "b.py": [{"name": "beta", "kind": "function", "line": 1, "end_line": 4}],
    "c.py": [{"name": "gamma", "kind": "function", "line": 1, "end_line": 2}],
}


def _reader(root: Path):
    return lambda path: (root / path).read_text(encoding="utf-8")


def _build_cache(tmp_path: Path) -> MagicMock:
    """Build a fixture cache with ast_call_edges + ast_index + real files."""
    (tmp_path / "a.py").write_text(_SRC_A)
    (tmp_path / "b.py").write_text(_SRC_B)
    (tmp_path / "c.py").write_text(_SRC_C)

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE ast_call_edges ("
        " caller_name TEXT, caller_file TEXT, caller_line INTEGER,"
        " callee_name TEXT, callee_full TEXT DEFAULT '', callee_line INTEGER DEFAULT 0,"
        " callee_resolved_file TEXT DEFAULT '', file_path TEXT, language TEXT)"
    )
    for e in _EDGES:
        db.execute(
            "INSERT INTO ast_call_edges (caller_name, caller_file, caller_line,"
            " callee_name, callee_line, callee_resolved_file, file_path, language)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                e["caller_name"],
                e["caller_file"],
                e["caller_line"],
                e["callee_name"],
                e["callee_line"],
                e["callee_resolved_file"],
                e["caller_file"],
                "python",
            ),
        )
    # B1: the path-finder reads the unified ``edges`` table (kind='calls'),
    # not the legacy ``ast_call_edges`` table.  Mirror the same edges here so
    # CallPathFinder finds the alpha->beta->gamma chain on this branch.
    db.execute(
        "CREATE TABLE edges ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " source_node_id TEXT NOT NULL DEFAULT '',"
        " target_node_id TEXT NOT NULL DEFAULT '',"
        " kind TEXT NOT NULL,"
        " line INTEGER,"
        " metadata TEXT,"
        " caller_name TEXT NOT NULL DEFAULT '',"
        " callee_name TEXT NOT NULL DEFAULT '',"
        " file_path TEXT NOT NULL DEFAULT '',"
        " callee_resolved_file TEXT NOT NULL DEFAULT '')"
    )
    for e in _EDGES:
        db.execute(
            "INSERT INTO edges (source_node_id, target_node_id, kind, line,"
            " metadata, caller_name, callee_name, file_path,"
            " callee_resolved_file) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                f"{e['caller_file']}>{e['caller_name']}",
                f"{e['callee_resolved_file']}>{e['callee_name']}",
                "calls",
                e["callee_line"],
                json.dumps(
                    {
                        "caller_line": e["caller_line"],
                        "callee_resolved_file": e["callee_resolved_file"],
                    }
                ),
                e["caller_name"],
                e["callee_name"],
                e["caller_file"],
                e["callee_resolved_file"],
            ),
        )
    db.execute(
        "CREATE TABLE ast_index ("
        " file_path TEXT PRIMARY KEY, symbols_json TEXT, language TEXT)"
    )
    for file_path, symbols in _SYMBOLS.items():
        db.execute(
            "INSERT INTO ast_index (file_path, symbols_json, language) VALUES (?,?,?)",
            (file_path, json.dumps({"symbols": symbols}), "python"),
        )
    db.commit()

    cache = MagicMock()
    cache.has_call_edges.return_value = True
    cache.get_conn.return_value = db
    cache._get_conn.return_value = db
    cache.get_functions.side_effect = AssertionError(
        "enrich must use targeted ast_index scan, not full get_functions()"
    )

    # Real callers/callees backed by the same edge table.
    def _callers(name, file=None, depth=1):
        rows = db.execute(
            "SELECT caller_name, caller_file, caller_line FROM ast_call_edges"
            " WHERE callee_name = ?",
            (name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _callees(name, file=None, depth=1):
        rows = db.execute(
            "SELECT callee_name, callee_resolved_file, callee_line FROM ast_call_edges"
            " WHERE caller_name = ?",
            (name,),
        ).fetchall()
        return [dict(r) for r in rows]

    cache.query_callers.side_effect = _callers
    cache.query_callees.side_effect = _callees
    return cache


# ---------------------------------------------------------------------------
# Helper-level: inline_path_bodies
# ---------------------------------------------------------------------------


def test_inline_path_bodies_returns_verbatim_bodies(tmp_path):
    cache = _build_cache(tmp_path)
    paths = [
        {
            "hops": [
                {
                    "caller": "alpha",
                    "caller_file": "a.py",
                    "callee": "beta",
                    "callee_file": "b.py",
                    "line": 3,
                },
                {
                    "caller": "beta",
                    "caller_file": "b.py",
                    "callee": "gamma",
                    "callee_file": "c.py",
                    "line": 3,
                },
            ]
        }
    ]
    bodies, truncated = enrich.inline_path_bodies(
        str(tmp_path), cache, paths, source_reader=_reader(tmp_path)
    )
    names = {b["name"] for b in bodies}
    assert names == {"alpha", "beta", "gamma"}  # deduped, all three
    assert truncated is False
    # Verbatim source body — not just file:line.
    gamma = next(b for b in bodies if b["name"] == "gamma")
    # PR #1491：认证正文必须逐字保留原始换行符。
    assert gamma["content"] == _SRC_C


def test_inline_path_bodies_cpp_header_callee_lang_hint(tmp_path):
    """#865: .h callee must not gate out C++ caller definitions.

    Path: caller_func (no caller_file) → foo (include/foo.h).
    caller_func is indexed as "cpp".  Before the fix, path_lang_hint="c"
    from the .h callee caused _resolve_def to reject the cpp candidate via
    the directional rule languages_compatible("c","cpp") == False.
    """
    (tmp_path / "caller.cpp").write_text("void caller_func() { foo(); }\n")

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE ast_index"
        " (file_path TEXT PRIMARY KEY, symbols_json TEXT, language TEXT)"
    )
    db.execute(
        "INSERT INTO ast_index (file_path, symbols_json, language) VALUES (?,?,?)",
        (
            "caller.cpp",
            json.dumps(
                {
                    "symbols": [
                        {
                            "name": "caller_func",
                            "kind": "function",
                            "line": 1,
                            "end_line": 1,
                        }
                    ]
                }
            ),
            "cpp",
        ),
    )
    db.commit()

    cache = MagicMock()
    cache.has_call_edges.return_value = True
    cache.get_conn.return_value = db

    paths = [
        {
            "hops": [
                {
                    "caller": "caller_func",
                    "caller_file": "",  # source_file not provided
                    "callee": "foo",
                    "callee_file": "include/foo.h",  # .h → "c" without fix
                    "line": 1,
                }
            ]
        }
    ]

    bodies, _ = enrich.inline_path_bodies(
        str(tmp_path), cache, paths, source_reader=_reader(tmp_path)
    )
    names = {b["name"] for b in bodies}
    # Without fix: lang_hint="c" from .h gates out the cpp definition → names={}
    # With fix: "" (neutral) used as path_lang_hint → no lang filter → caller_func inlined
    assert "caller_func" in names


def test_inline_path_bodies_cpp_with_explicit_h_callee_file(tmp_path):
    """.h as explicit callee_file must not gate out C++ caller definitions (#865 P2).

    Codex P2: when callee_file is an explicit ".h" path (not just the fallback
    path_lang_hint), the per-function lang_hint was still derived from
    language_from_path("foo.h") = "c", blocking C++ callers via
    languages_compatible("c","cpp") == False.
    Fix: _lang_hint_for_path returns "" for .h so _resolve_def skips language filter.
    """
    (tmp_path / "caller.cpp").write_text("void caller_func() { foo(); }\n")

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE ast_index"
        " (file_path TEXT PRIMARY KEY, symbols_json TEXT, language TEXT)"
    )
    db.execute(
        "INSERT INTO ast_index (file_path, symbols_json, language) VALUES (?,?,?)",
        (
            "caller.cpp",
            json.dumps(
                {
                    "symbols": [
                        {
                            "name": "caller_func",
                            "kind": "function",
                            "line": 1,
                            "end_line": 1,
                        }
                    ]
                }
            ),
            "cpp",
        ),
    )
    db.commit()

    cache = MagicMock()
    cache.has_call_edges.return_value = True
    cache.get_conn.return_value = db

    paths = [
        {
            "hops": [
                {
                    "caller": "caller_func",
                    "caller_file": "src/main.cpp",  # explicit .cpp caller_file
                    "callee": "foo",
                    "callee_file": "include/foo.h",  # explicit .h callee_file
                    "line": 1,
                }
            ]
        }
    ]

    bodies, _ = enrich.inline_path_bodies(
        str(tmp_path), cache, paths, source_reader=_reader(tmp_path)
    )
    names = {b["name"] for b in bodies}
    # caller_func body must be inlined even when callee_file is an explicit .h path
    assert "caller_func" in names


def test_inline_path_bodies_dedupes(tmp_path):
    cache = _build_cache(tmp_path)
    # Two paths that share the alpha->beta prefix.
    hop_ab = {
        "caller": "alpha",
        "caller_file": "a.py",
        "callee": "beta",
        "callee_file": "b.py",
        "line": 3,
    }
    paths = [{"hops": [hop_ab]}, {"hops": [hop_ab]}]
    bodies, _ = enrich.inline_path_bodies(
        str(tmp_path), cache, paths, source_reader=_reader(tmp_path)
    )
    names = [b["name"] for b in bodies]
    assert names.count("alpha") == 1
    assert names.count("beta") == 1


def test_body_truncation_caps_lines(tmp_path, monkeypatch):
    cache = _build_cache(tmp_path)
    # Force a tiny per-body cap so the 4-line alpha body truncates.
    monkeypatch.setattr(enrich, "MAX_BODY_LINES", 2)
    paths = [
        {
            "hops": [
                {
                    "caller": "alpha",
                    "caller_file": "a.py",
                    "callee": "beta",
                    "callee_file": "b.py",
                    "line": 3,
                }
            ]
        }
    ]
    bodies, truncated = enrich.inline_path_bodies(
        str(tmp_path), cache, paths, source_reader=_reader(tmp_path)
    )
    alpha = next(b for b in bodies if b["name"] == "alpha")
    assert alpha.get("truncated") is True
    assert "full_at" in alpha
    assert truncated is True


# ---------------------------------------------------------------------------
# Helper-level: build_dead_end
# ---------------------------------------------------------------------------


def test_build_dead_end_inlines_both_endpoints(tmp_path):
    cache = _build_cache(tmp_path)
    out = enrich.build_dead_end(
        str(tmp_path),
        cache,
        "alpha",
        "gamma",
        None,
        None,
        source_reader=_reader(tmp_path),
    )
    src = out["source_endpoint"]
    tgt = out["target_endpoint"]
    assert src["name"] == "alpha"
    assert "def alpha" in src["body"]["content"]
    assert "GAMMA_BODY_MARKER" in tgt["body"]["content"]
    # Neighbours inlined for reasoning about the gap.
    assert any(c["name"] == "beta" for c in src["callees"])
    assert any(c["name"] == "beta" for c in tgt["callers"])


# ---------------------------------------------------------------------------
# Tool-level: full execute envelope
# ---------------------------------------------------------------------------


def _run_tool(tmp_path, cache, args):
    tool = CodeGraphCallPathTool(str(tmp_path))
    tool._finder = MagicMock()
    tool._finder._try_get_cache.return_value = cache
    # Real finder logic over the fixture cache.
    from tree_sitter_analyzer.call_path import CallPathFinder

    real = CallPathFinder(str(tmp_path), cache=cache)
    tool._finder.find_path.side_effect = real.find_path
    return asyncio.run(tool.execute(args))


def test_tool_path_found_inlines_bodies_and_deterrent(tmp_path):
    cache = _build_cache(tmp_path)
    result = _run_tool(
        tmp_path,
        cache,
        {
            "source_function": "alpha",
            "target_function": "gamma",
            "direction": "forward",
            "output_format": "json",
        },
    )
    assert result["verdict"] == "PATH_FOUND"
    assert "source_bodies" in result
    assert result["source_bodies"] == []
    assert "no Read needed" not in result["next_step"]


def test_dead_end_reader_failure_drops_body(tmp_path):
    cache = _build_cache(tmp_path)

    def unavailable(_path):
        raise RuntimeError("SOURCE_GENERATION_MISMATCH")

    result = enrich.build_dead_end(
        str(tmp_path),
        cache,
        "alpha",
        "gamma",
        None,
        None,
        source_reader=unavailable,
    )
    assert "body" not in result["source_endpoint"]
    assert "body" not in result["target_endpoint"]


async def test_call_path_without_root_does_not_acquire_owner():
    tool = CodeGraphCallPathTool()
    with pytest.raises(ValueError, match="Project root not set"):
        await tool.execute(
            {
                "source_function": "a",
                "target_function": "b",
                "output_format": "json",
            }
        )


def test_tool_dead_end_inlines_endpoints_and_deterrent(tmp_path):
    cache = _build_cache(tmp_path)
    # gamma -> alpha has no forward path.
    result = _run_tool(
        tmp_path,
        cache,
        {
            "source_function": "gamma",
            "target_function": "alpha",
            "direction": "forward",
            "output_format": "json",
        },
    )
    assert result["verdict"] == "NO_PATH"
    assert "dead_end" in result
    de = result["dead_end"]
    assert "body" not in de["source_endpoint"]
    assert "body" not in de["target_endpoint"]
    assert "next_step" in result
    assert "No static path" in result["next_step"]
    assert "no Read needed" not in result["next_step"]


async def test_certified_call_path_restores_bodies(tmp_path):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "path.py").write_text(
        "def alpha():\n    return beta()\n\ndef beta():\n"
        "    return 'CERTIFIED_PATH_BODY'\n",
        encoding="utf-8",
    )
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    result = await CodeGraphCallPathTool(str(tmp_path)).execute(
        {
            "source_function": "alpha",
            "target_function": "beta",
            "direction": "forward",
            "output_format": "json",
        }
    )
    joined = "\n".join(body["content"] for body in result["source_bodies"])
    assert "CERTIFIED_PATH_BODY" in joined


async def test_sqlite_deadline_falls_back_to_coordinate_query(tmp_path, monkeypatch):
    await assert_sqlite_deadline_falls_back(
        tmp_path,
        monkeypatch,
        CodeGraphCallPathTool(str(tmp_path)),
        {"source_function": "source", "target_function": "target"},
    )


async def test_move_after_bound_path_query_drops_bodies(tmp_path, monkeypatch):
    from tree_sitter_analyzer.call_path import CallPathFinder
    from tree_sitter_analyzer.index_snapshot_query import CertifiedSnapshotCache
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    source = tmp_path / "path.py"
    source.write_text(
        "def alpha():\n    return beta()\n\ndef beta():\n    return 'INDEXED'\n",
        encoding="utf-8",
    )
    assert (
        await CodeGraphFullIndexTool(str(tmp_path)).execute(
            {"mode": "full", "max_files": 10}
        )
    )["published"] is True
    original = CallPathFinder.find_path

    def find_then_move(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if isinstance(self._cache, CertifiedSnapshotCache):
            source.write_text(
                "\n\ndef alpha():\n    return beta()\n\ndef beta():\n    return 'MOVED'\n",
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(CallPathFinder, "find_path", find_then_move)
    result = await CodeGraphCallPathTool(str(tmp_path)).execute(
        {
            "source_function": "alpha",
            "target_function": "beta",
            "direction": "forward",
            "output_format": "json",
        }
    )
    assert result["source_bodies"] == []
    assert "no Read needed" not in result["next_step"]
