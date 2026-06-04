"""Focused tests for codegraph_context."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache


@pytest.fixture
def indexed_project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text(
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        return self._find_user(user_id)\n"
        "\n"
        "    def _find_user(self, user_id):\n"
        "        return {'id': user_id}\n"
        "\n"
        "def handle_request(request):\n"
        "    svc = UserService()\n"
        "    return svc.get_user(1)\n",
        encoding="utf-8",
    )
    (project / "routes.py").write_text(
        "from app import handle_request\n"
        "\n"
        "def dispatch(request):\n"
        "    return handle_request(request)\n",
        encoding="utf-8",
    )

    cache = ASTCache(str(project))
    cache.index_project(max_files=20)
    cache.close()
    return project


def test_codegraph_context_registered() -> None:
    # Wave C2: codegraph_context is folded into the nav facade as action=context.
    # fix 0f3f07d7: context became a BESPOKE route (symbol/query -> task
    # normalization), so it lives in bespoke_map, not action_map. The closure
    # delegates to a held CodeGraphContextTool instance after normalizing args.
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    _, lookup = create_tool_registry(project_root=None)
    assert "nav" in lookup
    assert "context" in lookup["nav"].bespoke_map
    assert any(
        type(inner).__name__ == "CodeGraphContextTool"
        for inner in lookup["nav"]._bespoke_inners
    )


def test_extract_symbol_candidates_handles_identifiers() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _extract_symbol_candidates,
    )

    candidates = _extract_symbol_candidates(
        "trace `UserService.get_user` through handle_request"
    )

    assert "UserService" in candidates
    assert "get_user" in candidates
    assert "handle_request" in candidates
    assert "trace" not in candidates


def test_schema_requires_task() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool()
    with pytest.raises(ValueError, match="task"):
        tool.validate_arguments({})


def test_tool_accessors_require_project_root() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool()

    with pytest.raises(ValueError, match="Project root"):
        tool._get_cache()
    with pytest.raises(ValueError, match="Project root"):
        tool._get_edge_store()
    with pytest.raises(ValueError, match="Project root"):
        tool._get_call_graph()


def test_edge_store_accessor_degrades_without_cache_connection() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = object()

    assert tool._get_edge_store() is None


def test_call_graph_falls_back_when_edgestore_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tree_sitter_analyzer.call_graph as call_graph
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    class BrokenEdgeStore:
        def has_edges(self, edge_kind):
            raise RuntimeError("edge metadata unavailable")

    class FakeCache:
        pass

    class FakeCachedCallGraph:
        def __init__(self, project_root, cache=None, fallback=True):
            self.project_root = project_root
            self.cache = cache
            self.fallback = fallback
            self.built = False

        def build(self):
            self.built = True

    monkeypatch.setattr(call_graph, "CachedCallGraph", FakeCachedCallGraph)

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = FakeCache()
    tool._edge_store = BrokenEdgeStore()

    graph = tool._get_call_graph()

    assert isinstance(graph, FakeCachedCallGraph)
    assert graph.cache is tool._cache
    assert graph.fallback is False
    assert graph.built is True


def test_resolve_entry_points_degrades_and_dedupes() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    class FallbackCache:
        def fts_search_ranked(self, candidate: str, limit: int):
            raise RuntimeError("fts5 unavailable")

        def fts_search(self, candidate: str, limit: int):
            return [
                {"name": "", "kind": "function", "file": "x.py", "line": 1},
                {"name": "os", "kind": "import", "file": "x.py", "line": 2},
                {"name": "alpha", "kind": "function", "file": "a.py", "line": 3},
                {"name": "alpha", "kind": "function", "file": "a.py", "line": 3},
                {"name": "beta", "kind": "class", "file": "tests/b.py", "line": 4},
            ]

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = FallbackCache()

    assert tool._resolve_entry_points([], limit=5) == []
    hits = tool._resolve_entry_points(["alpha"], limit=5)

    assert [hit["name"] for hit in hits] == ["alpha", "beta"]


def test_resolve_entry_points_handles_cache_and_search_errors() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    class BrokenCache:
        def fts_search_ranked(self, candidate: str, limit: int):
            raise RuntimeError("ranked failed")

        def fts_search(self, candidate: str, limit: int):
            raise RuntimeError("fallback failed")

    tool_without_root = CodeGraphContextTool()
    assert tool_without_root._resolve_entry_points(["anything"], limit=5) == []

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = BrokenCache()
    assert tool._resolve_entry_points(["anything"], limit=5) == []


def test_resolve_entry_points_stops_at_limit() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    class ManyHitsCache:
        def fts_search_ranked(self, candidate: str, limit: int):
            return [
                {"name": "first", "kind": "function", "file": "a.py", "line": 1},
                {"name": "second", "kind": "function", "file": "b.py", "line": 2},
            ]

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = ManyHitsCache()

    hits = tool._resolve_entry_points(["first", "second"], limit=1)

    assert [hit["name"] for hit in hits] == ["first"]


def test_resolve_entry_points_ranks_multiword_name_match_first() -> None:
    """A symbol whose name matches MORE task words must rank first.

    Regression for the dogfood loss: task 'IndexShard apply index operation'
    used to surface ScriptedSimilarityProvider.apply (matches 'apply' only)
    above IndexShard.applyIndexOperationOnPrimary (matches apply+index+
    operation) because ranking was by file name, not relevance. The file
    names below are chosen so the OLD alphabetical tie-break would pick the
    wrong symbol — only name-match weighting yields the correct order.
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    class RankedCache:
        def fts_search_ranked(self, candidate: str, limit: int):
            # Both symbols returned for every candidate; correct ordering
            # must come from name-match weighting, not file/insertion order.
            return [
                {
                    "name": "apply",
                    "kind": "method",
                    "file": "a_similarity.py",
                    "line": 10,
                },
                {
                    "name": "applyIndexOperationOnPrimary",
                    "kind": "method",
                    "file": "z_shard.py",
                    "line": 20,
                },
            ]

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = RankedCache()

    hits = tool._resolve_entry_points(["apply", "index", "operation"], limit=2)

    assert hits[0]["name"] == "applyIndexOperationOnPrimary"


def test_name_match_score_counts_distinct_task_words() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _name_match_score,
    )

    cands = ["apply", "index", "operation"]
    assert _name_match_score("applyIndexOperationOnPrimary", cands) == 3
    assert _name_match_score("apply", cands) == 1
    assert _name_match_score("unrelatedHelper", cands) == 0
    assert _name_match_score("", cands) == 0


def test_compound_candidates_builds_camelcase_word_pairs() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _compound_candidates,
    )

    out = _compound_candidates(["apply", "index", "operation"])
    # Ordered camelCase joins of word pairs surface multi-word method names
    # that single-word FTS cannot reach (applyIndexOperationOnPrimary).
    assert "applyIndex" in out
    assert "indexOperation" in out
    assert "applyOperation" in out
    # Single 2-char/stop tokens excluded; no self-joins.
    assert "applyApply" not in out
    assert _compound_candidates([]) == []
    assert _compound_candidates(["x"]) == []


def test_resolve_entry_points_uses_compound_recall_for_multiword() -> None:
    """Compound recall surfaces multi-word methods FTS misses on plain words.

    Simulates the ES dogfood case: single-word FTS only returns generic
    same-name symbols (apply), while a cascade substring query on the
    compound 'applyIndex' recalls the real write method. The resolver must
    merge both and rank the multi-word method first.
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    class CompoundCache:
        def fts_search_ranked(self, candidate: str, limit: int):
            # Plain words only ever match the generic same-name method.
            if candidate in ("apply", "index", "operation"):
                return [
                    {
                        "name": candidate,
                        "kind": "method",
                        "file": "generic.py",
                        "line": 1,
                    }
                ]
            return []

        def search_symbols_cascade(self, query: str, limit: int):
            # Compound camelCase queries reach the real multi-word method.
            if query.lower().startswith("applyindex"):
                return [
                    {
                        "name": "applyIndexOperationOnPrimary",
                        "kind": "method",
                        "file": "shard.py",
                        "line": 99,
                    }
                ]
            return []

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = CompoundCache()

    hits = tool._resolve_entry_points(["apply", "index", "operation"], limit=5)
    names = [h["name"] for h in hits]
    assert "applyIndexOperationOnPrimary" in names
    assert names[0] == "applyIndexOperationOnPrimary"


def test_resolve_entry_points_single_word_falls_back_to_substring_cascade() -> None:
    """A plain concept word with NO FTS hits must fall back to the cascade.

    Cost root cause: FTS5 tokenizes a camelCase identifier (``addRoute``) as
    ONE token, so a natural-language word like ``route`` returns zero FTS
    hits and the whole query collapses to NOT_FOUND — forcing the agent to
    abandon the index and Read raw files (the gin file_r=5-vs-2 gap). The
    resolver must run the substring cascade for any single word that FTS
    cannot resolve, so ``route`` recalls {addRoute, updateRouteTree, ...}.
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    class CamelCaseCache:
        def fts_search_ranked(self, candidate: str, limit: int):
            # FTS5 whole-token match: the plain word never hits camelCase names.
            return []

        def search_symbols_cascade(self, query: str, limit: int):
            if query.lower() == "route":
                return [
                    {
                        "name": "addRoute",
                        "kind": "function",
                        "file": "router.go",
                        "line": 10,
                    },
                    {
                        "name": "updateRouteTree",
                        "kind": "function",
                        "file": "tree.go",
                        "line": 20,
                    },
                ]
            return []

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = CamelCaseCache()

    hits = tool._resolve_entry_points(["route"], limit=5)
    names = {h["name"] for h in hits}

    assert names == {"addRoute", "updateRouteTree"}


def test_resolve_entry_points_skips_cascade_when_fts_has_hits() -> None:
    """The substring cascade is a FALLBACK — it must not run when FTS hits.

    Guards against double-querying (and over-broad substring noise) on the
    common exact-match path: an exact symbol word that FTS resolves should
    return the FTS hit without invoking the cascade at all.
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    cascade_calls: list[str] = []

    class ExactCache:
        def fts_search_ranked(self, candidate: str, limit: int):
            return [
                {
                    "name": "Engine",
                    "kind": "class",
                    "file": "gin.go",
                    "line": 1,
                }
            ]

        def search_symbols_cascade(self, query: str, limit: int):
            cascade_calls.append(query)
            return [{"name": "EngineNoise", "kind": "class", "file": "x.go", "line": 9}]

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = ExactCache()

    hits = tool._resolve_entry_points(["Engine"], limit=5)
    names = {h["name"] for h in hits}

    # Single-word cascade NOT triggered for "Engine" (FTS already hit). The
    # compound-recall tier never fires for a single candidate either.
    assert "Engine" in names
    assert "Engine" not in cascade_calls


def test_resolve_entry_points_falls_back_when_fts_only_returns_imports() -> None:
    """Cascade must run when FTS rows are non-empty but all UNUSABLE.

    Codex P2 on #288: gating the fallback on ``raw_hits`` being non-empty is
    wrong — FTS can return only ``kind == "import"`` rows, which ``_absorb``
    discards, so the candidate adds no entry point yet the cascade is
    suppressed and the query still ends NOT_FOUND, missing camelCase symbols.
    The fallback must trigger on zero USABLE hits, not zero raw rows.
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    class ImportOnlyCache:
        def fts_search_ranked(self, candidate: str, limit: int):
            # Non-empty, but every row is an import → all discarded by _absorb.
            return [
                {"name": "route", "kind": "import", "file": "imp.go", "line": 1},
                {"name": "", "kind": "function", "file": "x.go", "line": 2},
            ]

        def search_symbols_cascade(self, query: str, limit: int):
            if query.lower() == "route":
                return [
                    {
                        "name": "addRoute",
                        "kind": "function",
                        "file": "router.go",
                        "line": 10,
                    }
                ]
            return []

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = ImportOnlyCache()

    hits = tool._resolve_entry_points(["route"], limit=5)
    names = {h["name"] for h in hits}

    assert names == {"addRoute"}


def test_expand_nodes_handles_graph_limits_and_trace_chain() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
        _node_id,
    )

    class FakeGraph:
        def callees_of(self, name: str, file_path: str | None = None):
            return [
                {"name": "", "kind": "function", "file": "empty.py", "line": 1},
                {"name": "callee", "kind": "function", "file": "b.py", "line": 2},
                {"name": "extra", "kind": "function", "file": "c.py", "line": 3},
            ]

        def callers_of(self, name: str, file_path: str | None = None):
            return [{"name": "caller", "kind": "function", "file": "d.py", "line": 4}]

        def call_chain(self, name: str, file_path: str | None = None, depth: int = 4):
            return [
                {"callee": "not-a-dict"},
                {
                    "callee": {
                        "name": "chain",
                        "kind": "function",
                        "file": "e.py",
                        "line": 5,
                    }
                },
            ]

    seed = [
        {
            "id": _node_id("seed", "a.py", 1),
            "name": "seed",
            "kind": "function",
            "file": "a.py",
            "line": 1,
        }
    ]
    no_graph = CodeGraphContextTool()
    assert no_graph._expand_nodes(seed, "trace seed", max_nodes=5) == seed

    limited = CodeGraphContextTool(str(Path.cwd()))
    limited._call_graph = FakeGraph()
    assert limited._expand_nodes(seed, "trace seed", max_nodes=1) == seed

    assert [
        node["name"] for node in limited._expand_nodes(seed, "trace seed", max_nodes=2)
    ] == [
        "seed",
        "callee",
    ]
    assert [
        node["name"] for node in limited._expand_nodes(seed, "plain seed", max_nodes=3)
    ] == [
        "seed",
        "callee",
        "extra",
    ]

    expanded = limited._expand_nodes(seed, "trace seed", max_nodes=5)

    assert {node["name"] for node in expanded} == {
        "seed",
        "callee",
        "extra",
        "caller",
        "chain",
    }


def test_expand_nodes_handles_edgestore_query_errors() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
        _node_id,
    )

    class BrokenEdgeGraph:
        def query_callees(self, name: str, file_path: str | None = None, max_depth=1):
            raise RuntimeError("callees unavailable")

        def query_callers(self, name: str, file_path: str | None = None):
            raise RuntimeError("callers unavailable")

    seed = [
        {
            "id": _node_id("seed", "a.py", 1),
            "name": "seed",
            "kind": "function",
            "file": "a.py",
            "line": 1,
        }
    ]
    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._call_graph = BrokenEdgeGraph()

    assert tool._expand_nodes(seed, "trace seed", max_nodes=5) == seed


def test_build_edges_handles_fallback_targets_and_duplicates() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
        _node_id,
    )

    class EdgeGraph:
        def callees_of(self, name: str, file_path: str | None = None):
            if name != "source":
                return []
            return [
                {"name": "target", "kind": "function", "file": "", "line": 2},
                {"name": "target", "kind": "function", "file": "", "line": 2},
                {"name": "source", "kind": "function", "file": "a.py", "line": 1},
                {"name": "missing", "kind": "function", "file": "z.py", "line": 9},
            ]

    nodes = [
        {
            "id": _node_id("source", "a.py", 1),
            "name": "source",
            "kind": "function",
            "file": "a.py",
            "line": 1,
        },
        {
            "id": _node_id("target", "b.py", 2),
            "name": "target",
            "kind": "function",
            "file": "b.py",
            "line": 2,
        },
    ]
    no_graph = CodeGraphContextTool()
    assert no_graph._build_edges(nodes) == []

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._call_graph = EdgeGraph()

    assert tool._build_edges(nodes) == [
        {
            "source": _node_id("source", "a.py", 1),
            "target": _node_id("target", "b.py", 2),
            "kind": "calls",
            "line": 1,
        }
    ]


def test_build_edges_handles_edgestore_targets_and_duplicates() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
        _node_id,
    )

    class EdgeStoreGraph:
        def query_callees(
            self, name: str, file_path: str | None = None, max_depth: int = 1
        ):
            if name != "source":
                return []
            return [
                {"callee_name": "target", "callee_file": "b.py", "callee_line": 2},
                {"callee_name": "target", "callee_file": "b.py", "callee_line": 2},
                {"callee_name": "target", "callee_file": "", "callee_line": 2},
                {"callee_name": "source", "callee_file": "a.py", "callee_line": 1},
                {"callee_name": "missing", "callee_file": "z.py", "callee_line": 9},
            ]

    nodes = [
        {
            "id": _node_id("source", "a.py", 1),
            "name": "source",
            "kind": "function",
            "file": "a.py",
            "line": 1,
        },
        {
            "id": _node_id("target", "b.py", 2),
            "name": "target",
            "kind": "function",
            "file": "b.py",
            "line": 2,
        },
    ]
    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._call_graph = EdgeStoreGraph()

    assert tool._build_edges(nodes) == [
        {
            "source": _node_id("source", "a.py", 1),
            "target": _node_id("target", "b.py", 2),
            "kind": "calls",
            "line": 2,
        }
    ]


def test_small_helpers_cover_bounds_and_fallbacks(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _bounded_int,
        _build_code_blocks,
        _extract_symbol_candidates,
        _next_step,
        _node_id,
        _nodes_from_hits,
        _safe_chain,
        _safe_refs,
    )

    assert _bounded_int("bad", 1, 5) == 1
    assert _bounded_int(99, 1, 5) == 5
    assert _extract_symbol_candidates("go -> _ :: ab abc okLong Name Name") == [
        "okLong",
        "Name",
    ]
    assert _next_step(False, True).startswith("Use the nodes")

    hits = [
        {"name": "one", "kind": "function", "file": "a.py", "line": 1},
        {"name": "one", "kind": "function", "file": "a.py", "line": 1},
        {"name": "two", "kind": "function", "file": "b.py", "line": 2},
    ]
    assert [node["name"] for node in _nodes_from_hits(hits, max_nodes=2)] == [
        "one",
        "two",
    ]
    assert [node["name"] for node in _nodes_from_hits(hits, max_nodes=1)] == ["one"]

    def always_fails(*args):
        raise RuntimeError("boom")

    def falls_back_to_one_arg(*args):
        if len(args) == 2:
            raise RuntimeError("two-arg unavailable")
        return [{"name": args[0]}]

    assert _safe_refs(lambda name, file_path: [{"name": name}], "x", "x.py") == [
        {"name": "x"}
    ]
    assert _safe_refs(falls_back_to_one_arg, "x", None) == [{"name": "x"}]
    assert _safe_refs(always_fails, "x", None) == []

    class ChainFallback:
        def call_chain(self, name: str, file_path: str | None = None, depth: int = 4):
            if file_path is not None:
                raise RuntimeError("two-arg unavailable")
            return [{"callee": {"name": name, "file": "x.py", "line": 1}}]

    class ChainBroken:
        def call_chain(self, *args, **kwargs):
            raise RuntimeError("broken")

    assert _safe_chain(ChainFallback(), "x", "x.py", 4)
    assert _safe_chain(ChainBroken(), "x", "x.py", 4) == []

    rel = tmp_path / "rel.py"
    rel.write_text(
        "def alpha():\n    return 1\n\ndef beta():\n    return 2\n", encoding="utf-8"
    )
    abs_file = tmp_path / "abs.py"
    abs_file.write_text("def gamma():\n    return 3\n", encoding="utf-8")
    nodes = [
        {"id": "bad-file", "name": "bad", "file": "", "line": 1},
        {"id": "bad-line", "name": "bad", "file": "rel.py", "line": 0},
        {"id": "missing", "name": "missing", "file": "missing.py", "line": 1},
        {"id": "empty", "name": "empty", "file": "rel.py", "line": 99},
        {
            "id": _node_id("alpha", "rel.py", 1),
            "name": "alpha",
            "file": "rel.py",
            "line": 1,
        },
        {
            "id": _node_id("alpha", "rel.py", 1),
            "name": "alpha",
            "file": "rel.py",
            "line": 1,
        },
        {
            "id": _node_id("gamma", str(abs_file), 1),
            "name": "gamma",
            "file": str(abs_file),
            "line": 1,
            "end_line": 50,
        },
    ]

    assert _build_code_blocks(nodes, [], 0, str(tmp_path)) == []
    blocks = _build_code_blocks(
        nodes,
        [{"source": "outside", "target": "outside"}],
        2,
        str(tmp_path),
    )

    assert [block["name"] for block in blocks] == ["alpha", "gamma"]
    assert [
        block["name"] for block in _build_code_blocks(nodes, [], 1, str(tmp_path))
    ] == ["alpha"]


def test_build_code_blocks_skips_empty_snippets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tree_sitter_analyzer.mcp.tools.codegraph_context_tool as context_tool

    source = tmp_path / "source.py"
    source.write_text("def empty():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(context_tool, "extract_snippet_from_lines", lambda *args: "")

    blocks = context_tool._build_code_blocks(
        [
            {
                "id": "source.py:empty:1",
                "name": "empty",
                "file": "source.py",
                "line": 1,
            }
        ],
        [],
        1,
        str(tmp_path),
    )

    assert blocks == []


@pytest.mark.asyncio
async def test_context_returns_entry_points_graph_and_source(
    indexed_project: Path,
) -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool(str(indexed_project))
    result = await tool.execute(
        {
            "task": "trace handle_request to UserService.get_user",
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["verdict"] == "INFO"
    assert result["entry_points"]
    assert result["nodes"]
    assert result["stats"]["nodes"] == len(result["nodes"])
    assert result["code_blocks"]
    names = {node["name"] for node in result["nodes"]}
    assert {"handle_request", "UserService"} & names
    assert any("handle_request" in block["content"] for block in result["code_blocks"])


@pytest.mark.asyncio
async def test_context_uses_edgestore_without_lazy_callgraph_parse(
    indexed_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer import call_graph
    from tree_sitter_analyzer.graph.edge_store import EdgeStore
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    def fail_if_lazy_parse_builds(self):
        raise AssertionError("codegraph_context triggered lazy CallGraph.build()")

    monkeypatch.setattr(call_graph.CallGraph, "build", fail_if_lazy_parse_builds)

    tool = CodeGraphContextTool(str(indexed_project))
    result = await tool.execute(
        {
            "task": "trace handle_request to UserService.get_user",
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert isinstance(tool._call_graph, EdgeStore)


def test_context_ignores_edgestore_when_only_non_call_edges(tmp_path: Path) -> None:
    from tree_sitter_analyzer.call_graph import CachedCallGraph
    from tree_sitter_analyzer.graph.edge_store import EdgeKind, EdgeStore
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    (tmp_path / "models.py").write_text(
        "class Base:\n    pass\n\nclass Child(Base):\n    pass\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=10)
    finally:
        cache.close()

    tool = CodeGraphContextTool(str(tmp_path))
    store = tool._get_edge_store()

    assert isinstance(store, EdgeStore)
    assert store.has_edges(EdgeKind.EXTENDS)
    assert not store.has_edges(EdgeKind.CALLS)
    assert isinstance(tool._get_call_graph(), CachedCallGraph)


@pytest.mark.asyncio
async def test_context_not_found_is_a_successful_stop_signal(
    indexed_project: Path,
) -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool(str(indexed_project))
    result = await tool.execute(
        {"task": "XyzNeverDefinedFlow", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["verdict"] == "NOT_FOUND"
    assert result["entry_points"] == []
    assert "codegraph_symbol_search" in result["agent_summary"]["next_step"]
