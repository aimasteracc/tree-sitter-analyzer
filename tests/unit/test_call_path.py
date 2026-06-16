"""Unit tests for call_path.py — CallPathFinder, CallChain, CallPathResult."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from tree_sitter_analyzer.call_path import (
    CallChain,
    CallPathFinder,
    CallPathResult,
    _files_in_chain,
    _path_signature,
)
from tree_sitter_analyzer.graph.edge_store import EdgeKind, symbol_node


def _make_cache_with_edges(tmp_path: Path, edges: list[dict]) -> MagicMock:
    """Build a cache whose DB holds the call edges in the unified ``edges`` table.

    B1.2 moved the CALLS read path from ``ast_call_edges`` to ``edges``, so the
    fixture populates ``edges`` CALLS rows in the production shape (node ids via
    ``symbol_node``, scalars in metadata JSON, real name/file columns).
    """
    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(cache_dir / "index.db")
    cache = MagicMock()
    cache._project_root = str(tmp_path)
    cache.project_root = str(tmp_path)
    cache.has_call_edges.return_value = True

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS edges ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  source_node_id TEXT NOT NULL,"
        "  target_node_id TEXT NOT NULL,"
        "  kind TEXT NOT NULL,"
        "  line INTEGER,"
        "  provenance TEXT DEFAULT 'tree-sitter',"
        "  metadata TEXT,"
        "  caller_name TEXT NOT NULL DEFAULT '',"
        "  callee_name TEXT NOT NULL DEFAULT '',"
        "  file_path TEXT NOT NULL DEFAULT '',"
        "  UNIQUE(source_node_id, target_node_id, kind, line)"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_edges_callee_name ON edges(callee_name, kind)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_edges_caller_name ON edges(caller_name, kind)"
    )
    for e in edges:
        caller_name = e["caller_name"]
        caller_file = e["caller_file"]
        caller_line = e.get("caller_line", 1)
        callee_name = e["callee_name"]
        callee_line = e.get("callee_line", 1)
        resolved = e.get("callee_resolved_file", "")
        source = symbol_node(caller_file, caller_name, caller_line)
        target = symbol_node(resolved or caller_file, callee_name, callee_line)
        metadata = {
            "language": e.get("language", "python"),
            "caller_name": caller_name,
            "caller_line": caller_line,
            "callee_name": callee_name,
            "callee_full": e.get("callee_full", callee_name),
            "callee_resolution": "unknown",
            "callee_resolved_file": resolved,
        }
        conn.execute(
            "INSERT OR REPLACE INTO edges (source_node_id, target_node_id, kind,"
            "  line, provenance, metadata, caller_name, callee_name, file_path)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source,
                target,
                EdgeKind.CALLS.value,
                callee_line,
                "tree-sitter",
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                caller_name,
                callee_name,
                caller_file,
            ),
        )
    conn.commit()
    cache.get_conn.return_value = conn
    cache._get_conn.return_value = conn  # backward-compat alias
    return cache


# Simple linear chain: main -> foo -> bar
_LINEAR_EDGES = [
    {
        "caller_name": "main",
        "caller_file": "a.py",
        "callee_name": "foo",
        "callee_file": "b.py",
        "callee_resolved_file": "b.py",
    },
    {
        "caller_name": "foo",
        "caller_file": "b.py",
        "callee_name": "bar",
        "callee_file": "c.py",
        "callee_resolved_file": "c.py",
    },
]

# Diamond: main -> foo, main -> baz, foo -> bar, baz -> bar
_DIAMOND_EDGES = [
    {
        "caller_name": "main",
        "caller_file": "a.py",
        "callee_name": "foo",
        "callee_resolved_file": "b.py",
    },
    {
        "caller_name": "main",
        "caller_file": "a.py",
        "callee_name": "baz",
        "callee_resolved_file": "d.py",
    },
    {
        "caller_name": "foo",
        "caller_file": "b.py",
        "callee_name": "bar",
        "callee_resolved_file": "c.py",
    },
    {
        "caller_name": "baz",
        "caller_file": "d.py",
        "callee_name": "bar",
        "callee_resolved_file": "c.py",
    },
]


class TestCallChain:
    def test_empty_chain(self):
        chain = CallChain()
        d = chain.to_dict()
        assert d["total_hops"] == 0
        assert d["files_crossed"] == 0
        assert d["hops"] == []

    def test_chain_with_hops(self):
        chain = CallChain(
            hops=[
                {"caller": "main", "callee": "foo", "file": "a.py"},
                {"caller": "foo", "callee": "bar", "file": "b.py"},
            ],
            total_hops=2,
            files_crossed=2,
        )
        d = chain.to_dict()
        assert d["total_hops"] == 2
        assert d["files_crossed"] == 2
        assert len(d["hops"]) == 2


class TestCallPathResult:
    def test_no_paths(self):
        r = CallPathResult(source="main", target="missing")
        d = r.to_dict()
        assert d["path_count"] == 0
        assert d["truncated"] is False

    def test_with_paths(self):
        r = CallPathResult(
            source="main",
            target="bar",
            paths=[CallChain(hops=[{"a": 1}], total_hops=1, files_crossed=1)],
            data_source="sql",
        )
        d = r.to_dict()
        assert d["path_count"] == 1
        assert d["data_source"] == "sql"


class TestFilesInChain:
    def test_empty(self):
        assert _files_in_chain([]) == 0

    def test_single_file(self):
        assert _files_in_chain([{"file": "a.py"}, {"file": "a.py"}]) == 1

    def test_cross_file(self):
        assert _files_in_chain([{"file": "a.py"}, {"file": "b.py"}]) == 2


class TestCallPathFinderForward:
    def test_linear_forward(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="forward")
        assert result.source == "main"
        assert result.target == "bar"
        assert len(result.paths) == 1
        assert result.data_source == "sql"
        if result.paths:
            assert result.paths[0].total_hops == 2

    def test_no_path_forward(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("bar", "main", direction="forward")
        assert len(result.paths) == 0

    def test_diamond_forward(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _DIAMOND_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="forward")
        assert len(result.paths) == 2

    def test_max_depth_respected(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="forward", max_depth=1)
        assert len(result.paths) == 0

    def test_max_paths_respected(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _DIAMOND_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="forward", max_paths=1)
        assert len(result.paths) <= 1


class TestCallPathFinderBackward:
    def test_linear_backward(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="backward")
        assert len(result.paths) == 1

    def test_no_path_backward(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("bar", "main", direction="backward")
        assert len(result.paths) == 0


class TestCallPathFinderBidirectional:
    def test_linear_bidirectional(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="bidirectional")
        assert len(result.paths) == 1

    def test_diamond_bidirectional(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _DIAMOND_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="bidirectional")
        assert len(result.paths) == 2

    def test_same_function(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "main", direction="bidirectional")
        assert result.data_source == "sql"
        assert result.paths is not None

    def test_direct_call_bidirectional_no_target_file(self, tmp_path):
        """#797: bidirectional with no target_file must find a direct 1-hop call.

        When source calls target directly (1 hop) and target_file is not
        specified (None), the bidirectional BFS must still produce a path.
        The bug was that backward_visited stored (target, None) but forward
        BFS discovered (target, resolved_file), so the intersection test failed.
        """
        edges = [
            {
                "caller_name": "entry",
                "caller_file": "src/a.py",
                "callee_name": "helper",
                "callee_resolved_file": "src/b.py",
            }
        ]
        cache = _make_cache_with_edges(tmp_path, edges)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        # No source_file or target_file — exercises the None-vs-resolved-file bug
        result = finder.find_path("entry", "helper", direction="bidirectional")
        assert result.data_source == "sql"
        assert len(result.paths) == 1

    def test_direct_call_forward_finds_path(self, tmp_path):
        """Baseline: forward BFS always finds the direct 1-hop call."""
        edges = [
            {
                "caller_name": "entry",
                "caller_file": "src/a.py",
                "callee_name": "helper",
                "callee_resolved_file": "src/b.py",
            }
        ]
        cache = _make_cache_with_edges(tmp_path, edges)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("entry", "helper", direction="forward")
        assert result.data_source == "sql"
        assert len(result.paths) == 1


class TestCallPathFinderCrossFile:
    """#734: 2-hop cross-file chains must not dead-end when the intermediate
    node has callee_resolved_file=''.

    The bug: _fwd_state() sets the intermediate node's file to
    ``callee_resolved_file or file_path``.  When callee_resolved_file is empty,
    file_path (the *caller* side) is used.  The next BFS iteration then queries
    ``WHERE caller_name=? AND file_path=<caller-side-file>``, but the outgoing
    edges for that node are stored under its *definition* file — so the query
    returns 0 rows and the BFS silently dead-ends.

    The fix adds a fallback: retry with name-only when file-filtered returns 0.
    """

    def test_two_hop_cross_file_with_unresolved_intermediate(self, tmp_path):
        """main(a.py) → foo(b.py, unresolved) → bar(c.py) must yield 1 path."""
        edges = [
            {
                "caller_name": "main",
                "caller_file": "a.py",
                "callee_name": "foo",
                # callee_resolved_file intentionally empty — triggers the bug
                "callee_resolved_file": "",
            },
            {
                "caller_name": "foo",
                "caller_file": "b.py",
                "callee_name": "bar",
                "callee_resolved_file": "c.py",
            },
        ]
        cache = _make_cache_with_edges(tmp_path, edges)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="forward")
        assert result.data_source == "sql"
        assert len(result.paths) == 1
        assert result.paths[0].total_hops == 2

    def test_two_hop_cross_file_with_resolved_intermediate(self, tmp_path):
        """Baseline: same chain with callee_resolved_file set must also work."""
        edges = [
            {
                "caller_name": "main",
                "caller_file": "a.py",
                "callee_name": "foo",
                "callee_resolved_file": "b.py",
            },
            {
                "caller_name": "foo",
                "caller_file": "b.py",
                "callee_name": "bar",
                "callee_resolved_file": "c.py",
            },
        ]
        cache = _make_cache_with_edges(tmp_path, edges)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="forward")
        assert result.data_source == "sql"
        assert len(result.paths) == 1
        assert result.paths[0].total_hops == 2


class TestCallPathFinderFallback:
    def test_no_cache_falls_back(self, tmp_path):
        cache = MagicMock()
        cache.has_call_edges.return_value = False
        cache.get_stats.return_value = {"total_files": 0}
        cache._project_root = str(tmp_path)
        cache.project_root = str(tmp_path)
        finder = CallPathFinder(str(tmp_path), cache=None)
        result = finder.find_path("nonexistent_a", "nonexistent_b")
        assert result.data_source in ("parse", "error", "unknown")


class TestCallPathFinderCLI:
    def test_cli_tool_instantiation(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.call_path_tool import CodeGraphCallPathTool

        tool = CodeGraphCallPathTool(str(tmp_path))
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_call_path"
        assert "source_function" in defn["inputSchema"]["properties"]
        assert "target_function" in defn["inputSchema"]["properties"]
        schema = tool.get_tool_schema()
        assert schema["required"] == ["source_function", "target_function"]

    def test_validate_missing_source(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.call_path_tool import CodeGraphCallPathTool

        tool = CodeGraphCallPathTool(str(tmp_path))
        try:
            tool.validate_arguments({"target_function": "bar"})
            assert False, "Should have raised"
        except ValueError as e:
            assert "source_function" in str(e)

    def test_validate_missing_target(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.call_path_tool import CodeGraphCallPathTool

        tool = CodeGraphCallPathTool(str(tmp_path))
        try:
            tool.validate_arguments({"source_function": "foo"})
            assert False, "Should have raised"
        except ValueError as e:
            assert "target_function" in str(e)


class TestCallPathHopCalleFile:
    """#735: hop callee_file must be the DEFINITION file, not the call-site file."""

    def test_hop_callee_file_is_definition_file_not_caller_file(self, tmp_path):
        """When callee_resolved_file is set, callee_file in the hop must use it."""
        edges = [
            {
                "caller_name": "index_project",
                "caller_file": "ast_cache.py",
                "callee_name": "_commit_index_results",
                "callee_resolved_file": "_ast_cache_helpers.py",
            }
        ]
        cache = _make_cache_with_edges(tmp_path, edges)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path(
            "index_project",
            "_commit_index_results",
            source_file="ast_cache.py",
            direction="forward",
        )
        assert len(result.paths) == 1
        hop = result.paths[0].hops[0]
        # callee_file must be the definition file, not the call-site file
        assert hop["callee_file"] == "_ast_cache_helpers.py"
        assert hop["caller_file"] == "ast_cache.py"

    def test_hop_callee_file_empty_when_resolution_unknown(self, tmp_path):
        """When callee_resolved_file is empty, callee_file must be '' not the caller's file."""
        edges = [
            {
                "caller_name": "caller_fn",
                "caller_file": "caller.py",
                "callee_name": "unknown_callee",
                "callee_resolved_file": "",  # resolution failed
            }
        ]
        cache = _make_cache_with_edges(tmp_path, edges)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path(
            "caller_fn",
            "unknown_callee",
            source_file="caller.py",
            direction="forward",
        )
        assert len(result.paths) == 1
        hop = result.paths[0].hops[0]
        # When resolution is unknown, callee_file must be '' not 'caller.py'
        assert hop["callee_file"] == ""
        assert hop["caller_file"] == "caller.py"

    def test_bidirectional_hop_callee_file_is_definition_file(self, tmp_path):
        """Same fix must apply in the bidirectional BFS path."""
        edges = [
            {
                "caller_name": "entry",
                "caller_file": "main.py",
                "callee_name": "helper",
                "callee_resolved_file": "lib.py",
            }
        ]
        cache = _make_cache_with_edges(tmp_path, edges)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path(
            "entry",
            "helper",
            source_file="main.py",
            direction="bidirectional",
        )
        assert len(result.paths) == 1
        hop = result.paths[0].hops[0]
        assert hop["callee_file"] == "lib.py"
        assert hop["caller_file"] == "main.py"


# 4-hop linear chain: s -> a -> b -> t (frontiers meet on the forward side at b)
_FOUR_HOP_EDGES = [
    {
        "caller_name": "s",
        "caller_file": "s.py",
        "callee_name": "a",
        "callee_resolved_file": "a.py",
    },
    {
        "caller_name": "a",
        "caller_file": "a.py",
        "callee_name": "b",
        "callee_resolved_file": "b.py",
    },
    {
        "caller_name": "b",
        "caller_file": "b.py",
        "callee_name": "t",
        "callee_resolved_file": "t.py",
    },
]


# #968: two chains differing ONLY by the file of the intermediate ``worker``:
#   s.py:s -> pkg1.py:worker -> t.py:t
#   s.py:s -> pkg2.py:worker -> t.py:t
# A name-only signature collapses both to (s,worker),(worker,t) and drops one.
_DISTINCT_BY_FILE_EDGES = [
    {
        "caller_name": "s",
        "caller_file": "s.py",
        "callee_name": "worker",
        "callee_resolved_file": "pkg1.py",
    },
    {
        "caller_name": "s",
        "caller_file": "s.py",
        "callee_name": "worker",
        "callee_resolved_file": "pkg2.py",
    },
    {
        "caller_name": "worker",
        "caller_file": "pkg1.py",
        "callee_name": "t",
        "callee_resolved_file": "t.py",
    },
    {
        "caller_name": "worker",
        "caller_file": "pkg2.py",
        "callee_name": "t",
        "callee_resolved_file": "t.py",
    },
]


class TestPathSignatureFileAware:
    """#968: dedup signature must distinguish chains by node file identity."""

    def test_same_names_different_file_have_distinct_signatures(self):
        chain_via_pkg1 = [
            {
                "caller": "s",
                "caller_file": "s.py",
                "callee": "worker",
                "callee_file": "pkg1.py",
            },
            {
                "caller": "worker",
                "caller_file": "pkg1.py",
                "callee": "t",
                "callee_file": "t.py",
            },
        ]
        chain_via_pkg2 = [
            {
                "caller": "s",
                "caller_file": "s.py",
                "callee": "worker",
                "callee_file": "pkg2.py",
            },
            {
                "caller": "worker",
                "caller_file": "pkg2.py",
                "callee": "t",
                "callee_file": "t.py",
            },
        ]
        assert _path_signature(chain_via_pkg1) != _path_signature(chain_via_pkg2)

    def test_identical_chains_share_signature(self):
        chain = [
            {
                "caller": "s",
                "caller_file": "s.py",
                "callee": "worker",
                "callee_file": "pkg1.py",
            },
        ]
        assert _path_signature(list(chain)) == _path_signature(list(chain))


class TestBidirectionalDistinctByFile:
    """#968: distinct-by-file chains must both survive the bidirectional BFS."""

    def test_two_chains_differing_only_by_intermediate_file_preserved(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _DISTINCT_BY_FILE_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("s", "t", direction="bidirectional")
        assert result.data_source == "sql"
        # Both worker-via-pkg1 and worker-via-pkg2 chains are kept.
        assert len(result.paths) == 2
        intermediate_files = sorted(p.hops[0]["callee_file"] for p in result.paths)
        assert intermediate_files == ["pkg1.py", "pkg2.py"]


class TestBidirectionalMeetingOrder:
    """#951: forward-side meetings must reconstruct in caller->callee order."""

    def test_three_plus_hop_path_in_executable_order(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _FOUR_HOP_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("s", "t", direction="bidirectional")
        assert result.data_source == "sql"
        assert len(result.paths) == 1
        hops = result.paths[0].hops
        # Hops must be ordered s->a, a->b, b->t — a non-executable scramble
        # (e.g. s->a, b->t, a->b) is the bug this guards against.
        assert [(h["caller"], h["callee"]) for h in hops] == [
            ("s", "a"),
            ("a", "b"),
            ("b", "t"),
        ]

    def test_no_duplicate_paths_from_both_frontiers(self, tmp_path):
        """A meeting node found by both passes is recorded exactly once."""
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="bidirectional")
        assert len(result.paths) == 1


class TestFallbackBackwardGate:
    """#968: parse-fallback backward pass runs and is merged with signature dedup.

    The earlier gate (#951) skipped backward entirely once forward found any path,
    which dropped genuinely-distinct chains the forward pass missed because
    ``_bfs_graph_core`` marks intermediate states visited.  Backward now runs, but
    its chains are merged only when their (file-aware) signature is new, so an
    identical chain re-found by both directions is still recorded exactly once.
    """

    def test_bidirectional_fallback_backward_duplicate_deduped(self, tmp_path):
        from tree_sitter_analyzer.call_graph import CallGraph

        graph = CallGraph(str(tmp_path))
        graph.build = lambda: None  # type: ignore[method-assign]
        finder = CallPathFinder(str(tmp_path), cache=None)

        same_hop = [
            {"caller": "s", "caller_file": "a.py", "callee": "t", "callee_file": "b.py"}
        ]

        def fake_forward(g, *a):  # noqa: ANN001, ANN002
            paths = a[-1]
            paths.append(CallChain(hops=list(same_hop), total_hops=1, files_crossed=2))

        def fake_backward(g, *a):  # noqa: ANN001, ANN002
            # Backward re-discovers the SAME chain (identical signature).
            paths = a[-1]
            paths.append(CallChain(hops=list(same_hop), total_hops=1, files_crossed=2))

        finder._bfs_graph_forward = fake_forward  # type: ignore[assignment]
        finder._bfs_graph_backward = fake_backward  # type: ignore[assignment]
        import unittest.mock as _m

        with _m.patch.object(
            __import__("tree_sitter_analyzer.call_graph", fromlist=["CallGraph"]),
            "CallGraph",
            return_value=graph,
        ):
            result = finder._fallback_graph("s", "t", None, None, 6, 5, "bidirectional")
        # Same chain found by both passes → recorded exactly once.
        assert len(result.paths) == 1

    def test_bidirectional_fallback_backward_adds_distinct_chain(self, tmp_path):
        from tree_sitter_analyzer.call_graph import CallGraph

        graph = CallGraph(str(tmp_path))
        graph.build = lambda: None  # type: ignore[method-assign]
        finder = CallPathFinder(str(tmp_path), cache=None)

        def fake_forward(g, *a):  # noqa: ANN001, ANN002
            paths = a[-1]
            paths.append(
                CallChain(
                    hops=[
                        {
                            "caller": "s",
                            "caller_file": "a.py",
                            "callee": "t",
                            "callee_file": "b.py",
                        }
                    ],
                    total_hops=1,
                    files_crossed=2,
                )
            )

        def fake_backward(g, *a):  # noqa: ANN001, ANN002
            # Backward finds a DISTINCT chain the forward pass missed.
            paths = a[-1]
            paths.append(
                CallChain(
                    hops=[
                        {
                            "caller": "s",
                            "caller_file": "a.py",
                            "callee": "t",
                            "callee_file": "c.py",
                        }
                    ],
                    total_hops=1,
                    files_crossed=2,
                )
            )

        finder._bfs_graph_forward = fake_forward  # type: ignore[assignment]
        finder._bfs_graph_backward = fake_backward  # type: ignore[assignment]
        import unittest.mock as _m

        with _m.patch.object(
            __import__("tree_sitter_analyzer.call_graph", fromlist=["CallGraph"]),
            "CallGraph",
            return_value=graph,
        ):
            result = finder._fallback_graph("s", "t", None, None, 6, 5, "bidirectional")
        # Distinct chain (differs by callee_file) is preserved, not dropped.
        assert len(result.paths) == 2
