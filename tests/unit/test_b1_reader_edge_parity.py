"""B1.2 parity tests: the 5 readers must return identical results whether the
underlying CALLS data lives in the legacy ``ast_call_edges`` table or in the
unified ``edges`` table.

The migration (B1.2) switches each reader's SQL source from ``ast_call_edges``
to ``edges`` (with a ``kind='calls'`` predicate). These tests build a single
DB that holds BOTH tables, populated from the same edge specs in the exact
shape the production write path produces, then assert each reader yields
byte-for-byte identical output regardless of which table is queried.

A ``drop_ast_call_edges`` fixture knob removes the legacy table so each parity
test can prove the reader works against ``edges`` ALONE (the post-migration
state) — not merely that it happens to read the legacy table.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from tree_sitter_analyzer.graph.edge_store import EdgeKind, symbol_node

# ---------------------------------------------------------------------------
# Shared fixture: build a DB holding ast_call_edges + edges from one spec list
# ---------------------------------------------------------------------------

_AST_CALL_EDGES_DDL = """
CREATE TABLE IF NOT EXISTS ast_call_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_name TEXT NOT NULL,
    caller_file TEXT NOT NULL,
    caller_line INTEGER NOT NULL,
    callee_name TEXT NOT NULL,
    callee_full TEXT NOT NULL DEFAULT '',
    callee_line INTEGER NOT NULL DEFAULT 0,
    callee_resolution TEXT NOT NULL DEFAULT 'unknown',
    callee_resolved_file TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL,
    language TEXT NOT NULL
)
""".strip()

_EDGES_DDL = """
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER,
    provenance TEXT DEFAULT 'tree-sitter',
    metadata TEXT,
    caller_name TEXT NOT NULL DEFAULT '',
    callee_name TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    UNIQUE(source_node_id, target_node_id, kind, line)
)
""".strip()


def _normalise(spec: dict[str, Any]) -> dict[str, Any]:
    caller_file = spec["caller_file"]
    return {
        "caller_name": spec["caller_name"],
        "caller_file": caller_file,
        "caller_line": int(spec.get("caller_line", 1)),
        "callee_name": spec["callee_name"],
        "callee_full": spec.get("callee_full", spec["callee_name"]),
        "callee_line": int(spec.get("callee_line", 1)),
        "callee_resolution": spec.get("callee_resolution", "unknown"),
        "callee_resolved_file": spec.get("callee_resolved_file", ""),
        "file_path": caller_file,
        "language": spec.get("language", "python"),
    }


def _build_db(
    tmp_path: Path,
    specs: list[dict[str, Any]],
    *,
    drop_ast_call_edges: bool = False,
) -> sqlite3.Connection:
    """Build a DB with both tables populated identically from ``specs``.

    Mirrors the production write path: ``ast_call_edges`` rows come from
    ``write_call_edges`` (+ resolution columns), and ``edges`` CALLS rows are
    produced exactly as ``write_graph_edges_for_file`` would (node ids via
    ``symbol_node``, scalars in the metadata JSON blob, real name columns).
    """
    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cache_dir / "index.db"))
    conn.row_factory = sqlite3.Row
    conn.execute(_AST_CALL_EDGES_DDL)
    conn.execute(_EDGES_DDL)
    # symbol_resolver._find_references also consults ast_index for import refs;
    # an empty table keeps that path a no-op so the parity check isolates the
    # call-edge source migration.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ast_index ("
        " file_path TEXT, language TEXT, symbols_json TEXT, imports_json TEXT)"
    )

    for e in (_normalise(s) for s in specs):
        conn.execute(
            "INSERT INTO ast_call_edges (caller_name, caller_file, caller_line,"
            " callee_name, callee_full, callee_line, callee_resolution,"
            " callee_resolved_file, file_path, language)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                e["caller_name"],
                e["caller_file"],
                e["caller_line"],
                e["callee_name"],
                e["callee_full"],
                e["callee_line"],
                e["callee_resolution"],
                e["callee_resolved_file"],
                e["file_path"],
                e["language"],
            ),
        )

        source = symbol_node(e["caller_file"], e["caller_name"], e["caller_line"])
        target_file = e["callee_resolved_file"] or e["caller_file"]
        target = symbol_node(target_file, e["callee_name"], e["callee_line"])
        metadata = {
            "language": e["language"],
            "caller_name": e["caller_name"],
            "caller_line": e["caller_line"],
            "callee_name": e["callee_name"],
            "callee_full": e["callee_full"],
            "callee_resolution": e["callee_resolution"],
            "callee_resolved_file": e["callee_resolved_file"],
        }
        conn.execute(
            "INSERT OR REPLACE INTO edges"
            " (source_node_id, target_node_id, kind, line, provenance, metadata,"
            "  caller_name, callee_name, file_path)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source,
                target,
                EdgeKind.CALLS.value,
                e["callee_line"],
                "tree-sitter",
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                e["caller_name"],
                e["callee_name"],
                e["file_path"],
            ),
        )

    if drop_ast_call_edges:
        conn.execute("DROP TABLE ast_call_edges")
    conn.commit()
    return conn


def _mock_cache(tmp_path: Path, conn: sqlite3.Connection) -> MagicMock:
    cache = MagicMock()
    cache._project_root = str(tmp_path)
    cache.project_root = str(tmp_path)
    cache.has_call_edges.return_value = True
    cache.get_conn.return_value = conn
    cache._get_conn.return_value = conn
    return cache


# A spec exercising resolved + unresolved + qualified-callee cases.
_SPECS: list[dict[str, Any]] = [
    {
        "caller_name": "main",
        "caller_file": "a.py",
        "caller_line": 10,
        "callee_name": "foo",
        "callee_full": "mod.foo",
        "callee_line": 12,
        "callee_resolution": "project",
        "callee_resolved_file": "b.py",
        "language": "python",
    },
    {
        "caller_name": "foo",
        "caller_file": "b.py",
        "caller_line": 5,
        "callee_name": "bar",
        "callee_full": "bar",
        "callee_line": 7,
        "callee_resolution": "project",
        "callee_resolved_file": "c.py",
        "language": "python",
    },
    {
        "caller_name": "main",
        "caller_file": "a.py",
        "caller_line": 11,
        "callee_name": "ext",
        "callee_full": "ext",
        "callee_line": 13,
        "callee_resolution": "unknown",
        "callee_resolved_file": "",
        "language": "python",
    },
]


# ---------------------------------------------------------------------------
# call_path.py — _query_forward_edges / _query_backward_edges
# ---------------------------------------------------------------------------


class TestCallPathParity:
    def _run(self, conn: sqlite3.Connection):
        from tree_sitter_analyzer.call_path import CallPathFinder

        fwd_all = CallPathFinder._query_forward_edges(conn, "main", None)
        fwd_scoped = CallPathFinder._query_forward_edges(conn, "main", "a.py")
        bwd_all = CallPathFinder._query_backward_edges(conn, "bar", None)
        bwd_scoped = CallPathFinder._query_backward_edges(conn, "foo", "b.py")
        return fwd_all, fwd_scoped, bwd_all, bwd_scoped

    def test_edges_only_matches_legacy(self, tmp_path: Path):
        legacy = self._run(_build_db(tmp_path / "legacy", _SPECS))
        migrated = self._run(
            _build_db(tmp_path / "mig", _SPECS, drop_ast_call_edges=True)
        )
        assert migrated == legacy


# ---------------------------------------------------------------------------
# _ast_cache_graph.py — _bfs_callers_impl / _bfs_callees_impl
# ---------------------------------------------------------------------------


class TestAstCacheGraphParity:
    def _run(self, conn: sqlite3.Connection):
        from tree_sitter_analyzer._ast_cache_graph import bfs_callees, bfs_callers

        callers = bfs_callers(conn, "bar", None, max_depth=2)
        callers_scoped = bfs_callers(conn, "foo", "b.py", max_depth=1)
        callees = bfs_callees(conn, "main", None, max_depth=2)
        callees_scoped = bfs_callees(conn, "main", "a.py", max_depth=1)
        return callers, callers_scoped, callees, callees_scoped

    def test_edges_only_matches_legacy(self, tmp_path: Path):
        legacy = self._run(_build_db(tmp_path / "legacy", _SPECS))
        migrated = self._run(
            _build_db(tmp_path / "mig", _SPECS, drop_ast_call_edges=True)
        )
        assert migrated == legacy


# ---------------------------------------------------------------------------
# xref.py — _find_callers / _find_callees / _file_callers / _file_callees /
#           _find_file_dependents
# ---------------------------------------------------------------------------


class TestXrefParity:
    def _run(self, tmp_path: Path, conn: sqlite3.Connection):
        from tree_sitter_analyzer.xref import XRefEngine

        cache = _mock_cache(tmp_path, conn)
        tool = XRefEngine(cache)
        return {
            "callers": tool._find_callers(conn, "foo", None),
            "callers_scoped": tool._find_callers(conn, "foo", "a.py"),
            "callees": tool._find_callees(conn, "main", None),
            "callees_scoped": tool._find_callees(conn, "main", "a.py"),
            "file_callers": tool._file_callers(conn, "b.py"),
            "file_callees": tool._file_callees(conn, "a.py"),
            "file_dependents": tool._find_file_dependents(conn, "b.py"),
        }

    def test_edges_only_matches_legacy(self, tmp_path: Path):
        legacy = self._run(tmp_path, _build_db(tmp_path / "legacy", _SPECS))
        migrated = self._run(
            tmp_path, _build_db(tmp_path / "mig", _SPECS, drop_ast_call_edges=True)
        )
        assert migrated == legacy


# ---------------------------------------------------------------------------
# symbol_resolver.py — _find_references
# ---------------------------------------------------------------------------


class TestSymbolResolverParity:
    def _run(self, tmp_path: Path, conn: sqlite3.Connection):
        from tree_sitter_analyzer.symbol_resolver import SymbolResolver

        resolver = SymbolResolver(_mock_cache(tmp_path, conn))
        refs = resolver._find_references("foo", "foo")
        return [(r.file, r.name, r.kind, r.line, r.language) for r in refs]

    def test_edges_only_matches_legacy(self, tmp_path: Path):
        legacy = self._run(tmp_path, _build_db(tmp_path / "legacy", _SPECS))
        migrated = self._run(
            tmp_path, _build_db(tmp_path / "mig", _SPECS, drop_ast_call_edges=True)
        )
        assert migrated == legacy


# ---------------------------------------------------------------------------
# ast_cache.py — ASTCache.get_call_edges  (B1.2b: the 6th content reader)
# ---------------------------------------------------------------------------


class TestGetCallEdgesParity:
    """``ASTCache.get_call_edges`` must return byte-for-byte identical rows
    whether sourced from ``ast_call_edges`` or from the unified ``edges`` table.
    """

    def _run(self, tmp_path: Path, conn: sqlite3.Connection):
        from tree_sitter_analyzer.ast_cache import ASTCache

        cache = _mock_cache(tmp_path, conn)
        # Invoke the real, unbound method against the mock's connection so the
        # parity check exercises the production SQL, not the MagicMock stub.
        rows = ASTCache.get_call_edges(cache)
        # Sort for a deterministic comparison independent of row insertion order
        # / table physical layout (ast_call_edges has an id PK; edges does too,
        # but the migrated SELECT carries no ORDER BY — matching legacy).
        return sorted(
            rows,
            key=lambda r: (
                r["caller_name"],
                r["caller_file"],
                r["caller_line"],
                r["callee_name"],
                r["callee_line"],
            ),
        )

    def test_edges_only_matches_legacy(self, tmp_path: Path):
        legacy = self._run(tmp_path, _build_db(tmp_path / "legacy", _SPECS))
        migrated = self._run(
            tmp_path, _build_db(tmp_path / "mig", _SPECS, drop_ast_call_edges=True)
        )
        assert migrated == legacy

    def test_returns_all_columns_from_edges_alone(self, tmp_path: Path):
        """The post-migration reader must surface every legacy column from the
        ``edges`` table by itself (real columns + json_extract scalars)."""
        rows = self._run(
            tmp_path, _build_db(tmp_path / "mig", _SPECS, drop_ast_call_edges=True)
        )
        assert len(rows) == len(_SPECS)
        expected_keys = {
            "caller_name",
            "caller_file",
            "caller_line",
            "callee_name",
            "callee_full",
            "callee_line",
            "file_path",
            "language",
        }
        for row in rows:
            assert set(row.keys()) == expected_keys
        # Spot-check the resolved/qualified-callee row carries its scalars.
        a_to_b = next(
            r for r in rows if r["caller_name"] == "main" and r["callee_name"] == "foo"
        )
        assert a_to_b["caller_file"] == "a.py"
        assert a_to_b["caller_line"] == 10
        assert a_to_b["callee_full"] == "mod.foo"
        assert a_to_b["callee_line"] == 12
        assert a_to_b["file_path"] == "a.py"
        assert a_to_b["language"] == "python"


# ---------------------------------------------------------------------------
# constraints/evaluator.py — evaluate
# ---------------------------------------------------------------------------


class TestConstraintEvaluatorParity:
    def _run(self, conn: sqlite3.Connection):
        from tree_sitter_analyzer.constraints.evaluator import evaluate
        from tree_sitter_analyzer.constraints.schema import Constraint

        constraints = [
            Constraint(
                id="no-a-to-b",
                severity="error",
                rule="forbid",
                from_glob="a.py",
                to_glob="b.py",
                reason="test",
            )
        ]
        violations = evaluate(constraints, conn)
        return [
            (
                v.rule_id,
                v.caller_file,
                v.caller_name,
                v.caller_line,
                v.callee_name,
                v.callee_file,
            )
            for v in violations
        ]

    def test_edges_only_matches_legacy(self, tmp_path: Path):
        legacy = self._run(_build_db(tmp_path / "legacy", _SPECS))
        migrated = self._run(
            _build_db(tmp_path / "mig", _SPECS, drop_ast_call_edges=True)
        )
        assert migrated == legacy
