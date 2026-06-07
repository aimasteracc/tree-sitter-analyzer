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


def test_is_test_file_detects_cross_language_test_paths() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import _is_test_file

    # Test files across languages → 1
    assert _is_test_file("response_writer_test.go") == 1  # Go
    assert _is_test_file("pkg/router_test.go") == 1
    assert _is_test_file("foo.spec.ts") == 1  # TS
    assert _is_test_file("src/app/foo.test.tsx") == 1
    assert _is_test_file("tests/test_thing.py") == 1  # Python dir + prefix
    assert _is_test_file("test_thing.py") == 1
    assert _is_test_file("thing_test.py") == 1
    assert _is_test_file("src/test/java/FooTest.java") == 1  # Maven layout
    assert _is_test_file("__tests__/comp.jsx") == 1
    assert _is_test_file("project/testdata/sample.go") == 1
    # Production files → 0 (no false positives on test-like names)
    assert _is_test_file("response_writer.go") == 0
    assert _is_test_file("src/TestRunner.java") == 0  # production class
    assert _is_test_file("latest.java") == 0  # not '*test.java' substring trap
    assert _is_test_file("contest.py") == 0
    assert _is_test_file("") == 0


def test_entry_rank_v2_sinks_test_file_below_impl() -> None:
    """A test-file hit must rank BELOW an implementation hit of equal relevance.

    Concept queries whose substring-cascade lands in Go ``*_test.go`` (or
    ``*.spec.ts`` etc.) used to surface ``TestResponseWriterWrite`` above the
    real ``ResponseWriter`` because is_test only matched ``/tests/`` paths.
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    class TestVsImplCache:
        def fts_search_ranked(self, candidate: str, limit: int):
            # Test symbol has the STRONGER name match, but lives in a test file;
            # the impl must still win on the non-test tier.
            return [
                {
                    "name": "TestResponseWriterWrite",
                    "kind": "function",
                    "file": "response_writer_test.go",
                    "line": 10,
                },
                {
                    "name": "ResponseWriter",
                    "kind": "class",
                    "file": "response_writer.go",
                    "line": 20,
                },
            ]

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = TestVsImplCache()

    hits = tool._resolve_entry_points(["ResponseWriter"], limit=5)

    assert hits[0]["name"] == "ResponseWriter"
    assert hits[0]["file"] == "response_writer.go"


def test_task_wants_tests_detects_test_intent() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _task_wants_tests,
    )

    assert _task_wants_tests("response writer tests") is True
    assert _task_wants_tests("how is routing tested") is True
    assert _task_wants_tests("the spec for the parser") is True
    assert _task_wants_tests("router benchmark") is True
    # No test intent → False (and no false positive on 'latest'/'contest').
    assert _task_wants_tests("how does route matching work") is False
    assert _task_wants_tests("latest contest results parser") is False
    assert _task_wants_tests("") is False


def test_resolve_entry_points_keeps_tests_when_task_wants_tests() -> None:
    """When the task asks about tests, test symbols must NOT be demoted.

    Codex P2 on #291: unconditional test demotion (is_test as the first sort
    tier) pushes the relevant test past the limit for a test-intent query like
    'response writer tests'. With wants_tests set, the stronger name match
    wins and the test symbol ranks first.
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    class TestIntentCache:
        def fts_search_ranked(self, candidate: str, limit: int):
            return [
                {
                    "name": "TestResponseWriterWrite",
                    "kind": "function",
                    "file": "response_writer_test.go",
                    "line": 10,
                },
                {
                    "name": "ResponseWriter",
                    "kind": "class",
                    "file": "response_writer.go",
                    "line": 20,
                },
            ]

    tool = CodeGraphContextTool(str(Path.cwd()))
    tool._cache = TestIntentCache()

    # Default (no test intent): impl wins.
    impl_first = tool._resolve_entry_points(["ResponseWriter"], limit=5)
    assert impl_first[0]["name"] == "ResponseWriter"

    # Test intent: the test symbol (stronger name match) is kept on top.
    test_first = tool._resolve_entry_points(
        ["ResponseWriter"], limit=5, wants_tests=True
    )
    assert test_first[0]["name"] == "TestResponseWriterWrite"


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


def test_build_code_blocks_truncates_long_bodies(tmp_path: Path) -> None:
    """A long function body is capped to _MAX_BLOCK_LINES with a marker.

    Full 40-line bodies made nav context 2-4x larger than peer tools for no
    added value. The block keeps the signature + head and points at the rest.
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _MAX_BLOCK_LINES,
        _build_code_blocks,
        _node_id,
    )

    body = "def big():\n" + "".join(f"    x{i} = {i}\n" for i in range(60))
    src = tmp_path / "big.py"
    src.write_text(body, encoding="utf-8")

    blocks = _build_code_blocks(
        [
            {
                "id": _node_id("big", "big.py", 1),
                "name": "big",
                "file": "big.py",
                "line": 1,
                "end_line": 61,
            }
        ],
        [],
        5,
        str(tmp_path),
    )

    assert len(blocks) == 1
    content = blocks[0]["content"]
    # Body proper is capped to _MAX_BLOCK_LINES; the marker line is extra.
    assert blocks[0]["end_line"] == _MAX_BLOCK_LINES
    assert "more lines" in content
    assert "big.py:" in content  # marker points at the remaining range
    # The full 60-line body is NOT inlined.
    assert "x59 = 59" not in content


def test_build_code_blocks_hints_when_end_unknown(tmp_path: Path) -> None:
    """A call-graph node with no end_line still gets an 'end unknown' hint.

    Codex P2 on #293: callee/caller nodes have end_line=0, so the cap-window
    fallback equalled capped_end and NO marker was emitted — lines past the cap
    were silently dropped. Now an explicit hint is added when the snippet is
    capped before EOF with an unknown end.
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _build_code_blocks,
        _node_id,
    )

    body = "func big() {\n" + "".join(f"    line{i}();\n" for i in range(40)) + "}\n"
    src = tmp_path / "big.go"
    src.write_text(body, encoding="utf-8")

    blocks = _build_code_blocks(
        [
            {
                "id": _node_id("big", "big.go", 1),
                "name": "big",
                "file": "big.go",
                "line": 1,
                # No end_line key → simulates a call-graph-expansion node.
            }
        ],
        [],
        5,
        str(tmp_path),
    )

    assert len(blocks) == 1
    content = blocks[0]["content"]
    assert "end unknown" in content
    assert "big.go:" in content
    assert "line39();" not in content  # full body NOT inlined


def test_build_code_blocks_keeps_short_bodies_untruncated(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _build_code_blocks,
        _node_id,
    )

    src = tmp_path / "small.py"
    src.write_text("def small():\n    return 1\n", encoding="utf-8")

    blocks = _build_code_blocks(
        [
            {
                "id": _node_id("small", "small.py", 1),
                "name": "small",
                "file": "small.py",
                "line": 1,
                "end_line": 2,
            }
        ],
        [],
        5,
        str(tmp_path),
    )

    assert len(blocks) == 1
    assert "more lines" not in blocks[0]["content"]
    assert "return 1" in blocks[0]["content"]


@pytest.mark.asyncio
async def test_context_caps_inline_edges(indexed_project: Path) -> None:
    """execute() with include_graph=true caps echoed edges and records totals.

    RFC-0006: edges are only present in the full-graph path (include_graph=true).
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _MAX_INLINE_EDGES,
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool(str(indexed_project))
    result = await tool.execute(
        {
            "task": "trace handle_request to UserService.get_user",
            "output_format": "json",
            "include_graph": True,
        }
    )

    assert len(result["edges"]) <= _MAX_INLINE_EDGES
    assert result["stats"]["edges"] == len(result["edges"])
    assert result["stats"]["edges_total"] >= result["stats"]["edges"]


@pytest.mark.asyncio
async def test_context_returns_entry_points_graph_and_source(
    indexed_project: Path,
) -> None:
    """include_graph=true returns entry points, nodes, edges, and source blocks."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool(str(indexed_project))
    result = await tool.execute(
        {
            "task": "trace handle_request to UserService.get_user",
            "output_format": "json",
            "include_graph": True,
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


# ---------------------------------------------------------------------------
# RFC-0006: Progressive disclosure — lean default, opt-in full graph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_lean_default_omits_nodes_edges(
    indexed_project: Path,
) -> None:
    """Default call (no include_graph) must omit nodes/edges, include related_symbols.

    RED on current code — current code always returns nodes and edges keys.
    After RFC-0006 implementation: default omits the verbose adjacency dump.
    """
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool(str(indexed_project))
    # Default: include_graph not passed (defaults to False)
    lean_result = await tool.execute(
        {
            "task": "trace handle_request to UserService.get_user",
            "output_format": "json",
        }
    )
    full_result = await tool.execute(
        {
            "task": "trace handle_request to UserService.get_user",
            "output_format": "json",
            "include_graph": True,
        }
    )

    # Lean result must NOT have nodes/edges keys
    assert "nodes" not in lean_result, "lean default must omit 'nodes'"
    assert "edges" not in lean_result, "lean default must omit 'edges'"

    # Lean result MUST have related_symbols and code_blocks
    assert "related_symbols" in lean_result
    assert "code_blocks" in lean_result
    assert lean_result["success"] is True

    # Full result must still have nodes and edges
    assert "nodes" in full_result
    assert "edges" in full_result

    # Lean payload must be materially smaller.
    # The ≥40% threshold applies at real-world scale (30 nodes / 37 edges).
    # The test fixture is tiny (5 symbols), so the minimum threshold is lower
    # here — but the lean path MUST still be strictly smaller because nodes/edges
    # are omitted even when small.
    import json

    lean_chars = len(json.dumps(lean_result))
    full_chars = len(json.dumps(full_result))
    assert lean_chars < full_chars, (
        f"lean payload must be smaller than full; got lean={lean_chars}, full={full_chars}"
    )
    reduction = (full_chars - lean_chars) / full_chars
    # On a realistic project with 30+ nodes/37+ edges the reduction exceeds 40%.
    # The fixture is a 5-symbol project, so we assert ≥20% to confirm savings.
    assert reduction >= 0.20, (
        f"RFC-0006 requires meaningful payload reduction; got {reduction:.1%} "
        f"(lean={lean_chars}, full={full_chars})"
    )


@pytest.mark.asyncio
async def test_context_include_graph_true_returns_full_nodes_edges(
    indexed_project: Path,
) -> None:
    """include_graph=true must return the full nodes + edges (back-compat)."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool(str(indexed_project))
    result = await tool.execute(
        {
            "task": "trace handle_request to UserService.get_user",
            "output_format": "json",
            "include_graph": True,
        }
    )

    assert result["success"] is True
    assert "nodes" in result
    assert isinstance(result["nodes"], list)
    assert len(result["nodes"]) > 0
    assert "edges" in result
    assert isinstance(result["edges"], list)
    # Back-compat: stats still has per-inline counts
    assert "nodes" in result["stats"]
    assert "edges" in result["stats"]


@pytest.mark.asyncio
async def test_context_include_graph_string_false_stays_lean(
    indexed_project: Path,
) -> None:
    """Codex P2 #320: include_graph='false' / '0' (JS-style string) must stay
    lean, not take the full-graph path (bool('false') is True)."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )

    tool = CodeGraphContextTool(str(indexed_project))
    for falsey in ("false", "0", "no", "off"):
        result = await tool.execute(
            {
                "task": "trace handle_request to UserService.get_user",
                "output_format": "json",
                "include_graph": falsey,
            }
        )
        assert result["success"] is True
        # Lean path: no bulky edges echoed for a string-falsey value.
        assert not result.get("edges"), (
            f"include_graph={falsey!r} must stay lean, got edges"
        )
    # And a string-truthy value still opens the graph.
    result_true = await tool.execute(
        {
            "task": "trace handle_request to UserService.get_user",
            "output_format": "json",
            "include_graph": "true",
        }
    )
    assert result_true.get("nodes"), "include_graph='true' must return the graph"


@pytest.mark.asyncio
async def test_context_lean_stats_advertise_graph_totals(
    indexed_project: Path,
) -> None:
    """Lean response stats must expose nodes_total and edges_total.

    The agent needs to know more graph is available before deciding to
    re-request with include_graph=true — totals are the progressive-disclosure
    contract.
    """
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

    stats = result["stats"]
    assert "nodes_total" in stats, "lean stats must advertise nodes_total"
    assert "edges_total" in stats, "lean stats must advertise edges_total"
    assert isinstance(stats["nodes_total"], int)
    assert isinstance(stats["edges_total"], int)

    # next_step must mention include_graph so agent knows the opt-in flag
    next_step = result["agent_summary"]["next_step"]
    assert "include_graph" in next_step, (
        f"next_step must mention 'include_graph' flag; got: {next_step!r}"
    )


@pytest.mark.asyncio
async def test_context_related_symbols_grouped_by_file(
    indexed_project: Path,
) -> None:
    """related_symbols must be a list of {file, symbols:[name:line]} dicts."""
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

    related = result.get("related_symbols", [])
    assert isinstance(related, list)
    # With an indexed project we expect at least one file group
    assert len(related) > 0

    for group in related:
        assert "file" in group, f"each group must have 'file'; got {group!r}"
        assert "symbols" in group, f"each group must have 'symbols'; got {group!r}"
        assert isinstance(group["symbols"], list)
        for sym in group["symbols"]:
            assert isinstance(sym, str)
            # Format must be "name:line"
            assert ":" in sym, f"symbol entry must be 'name:line'; got {sym!r}"
            parts = sym.rsplit(":", 1)
            assert parts[1].isdigit(), f"symbol line must be a digit; got {sym!r}"


def test_build_related_symbols_groups_by_file() -> None:
    """Unit test for _build_related_symbols pure function."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _build_related_symbols,
        _node_id,
    )

    nodes = [
        {
            "id": _node_id("alpha", "a.py", 10),
            "name": "alpha",
            "file": "a.py",
            "line": 10,
        },
        {
            "id": _node_id("beta", "b.py", 5),
            "name": "beta",
            "file": "b.py",
            "line": 5,
        },
        {
            "id": _node_id("gamma", "a.py", 20),
            "name": "gamma",
            "file": "a.py",
            "line": 20,
        },
        # Node with no file should be skipped
        {"id": "no-file", "name": "orphan", "file": "", "line": 1},
    ]

    groups = _build_related_symbols(nodes)

    assert isinstance(groups, list)
    # Two distinct files: a.py and b.py
    files = {g["file"] for g in groups}
    assert files == {"a.py", "b.py"}

    a_group = next(g for g in groups if g["file"] == "a.py")
    # Sorted by line: alpha:10 before gamma:20
    assert a_group["symbols"] == ["alpha:10", "gamma:20"]

    b_group = next(g for g in groups if g["file"] == "b.py")
    assert b_group["symbols"] == ["beta:5"]


def test_entry_point_body_inlines_full_under_budget(tmp_path: Path) -> None:
    """RFC-0009 A: an entry-point symbol whose body fits the entry budget inlines
    in FULL — no '… more lines' truncation marker — so the agent answers in one
    call. The old blanket 16-line cap truncated it (RED)."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _build_code_blocks,
        _node_id,
    )

    body = "def big():\n" + "".join(f"    x{i} = {i}\n" for i in range(1, 40))
    f = tmp_path / "big.py"
    f.write_text(body, encoding="utf-8")  # 'big' spans lines 1..40
    nodes = [
        {
            "id": _node_id("big", "big.py", 1),
            "name": "big",
            "file": "big.py",
            "line": 1,
            "end_line": 40,
            "is_entry": True,
        }
    ]
    blocks = _build_code_blocks(nodes, [], 5, str(tmp_path))
    assert len(blocks) == 1
    block = blocks[0]
    assert "more lines" not in block["content"], "entry body was truncated"
    assert "snippet capped" not in block["content"]
    assert block["end_line"] == 40, block
    assert "x39 = 39" in block["content"], "full body not inlined"


def test_entry_point_ranked_before_high_degree_noise(tmp_path: Path) -> None:
    """RFC-0009 B: a task's named entry point gets a code block BEFORE a
    high-edge-degree non-entry hub (e.g. a cache accessor). The old degree-only
    ranking put the hub first and could starve the entry of a slot (RED)."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _build_code_blocks,
        _node_id,
    )

    f = tmp_path / "m.py"
    f.write_text(
        "def answer():\n    return 1\n\n\ndef cache_get():\n    return 2\n",
        encoding="utf-8",
    )
    entry = {
        "id": _node_id("answer", "m.py", 1),
        "name": "answer",
        "file": "m.py",
        "line": 1,
        "end_line": 2,
        "is_entry": True,
    }
    noise = {
        "id": _node_id("cache_get", "m.py", 5),
        "name": "cache_get",
        "file": "m.py",
        "line": 5,
        "end_line": 6,
    }
    # cache_get has high edge degree; answer has none.
    edges = [{"source": noise["id"], "target": f"x{i}"} for i in range(8)] + [
        {"source": f"x{i}", "target": noise["id"]} for i in range(8)
    ]
    # only ONE block slot — the entry must win it.
    blocks = _build_code_blocks([noise, entry], edges, 1, str(tmp_path))
    assert [b["name"] for b in blocks] == ["answer"], blocks


def test_generic_verbs_dropped_when_specific_candidate_present() -> None:
    """RFC-0009 C: a bare generic verb ('dispatch') is dropped from candidates
    when the task also names a specific snake_case/CamelCase symbol — it only
    matches unrelated event dispatchers and wastes entry-point slots. The old
    tokeniser kept it (RED)."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _extract_symbol_candidates,
    )

    cands = _extract_symbol_candidates(
        "how does resolve_callee dispatch a Java call to resolve_java_callee"
    )
    assert "dispatch" not in cands, cands
    # the specific symbols the task is actually about are preserved
    assert "resolve_callee" in cands
    assert "resolve_java_callee" in cands


def test_generic_verb_kept_when_sole_signal() -> None:
    """RFC-0009 C is conservative: when a generic verb is the ONLY signal (no
    specific symbol named), it is KEPT so 'find the dispatch function' still
    resolves to the dispatch symbol."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _extract_symbol_candidates,
    )

    cands = _extract_symbol_candidates("find the dispatch function")
    assert "dispatch" in cands, cands


def test_quoted_generic_verb_is_kept_as_explicit_symbol() -> None:
    """RFC-0009 C / Codex P2 #333: a generic verb the user QUOTED (`` `dispatch` ``)
    is an explicit symbol name and must survive the generic-verb filter even when
    a snake_case symbol co-occurs — only BARE generic verbs are dropped."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _extract_symbol_candidates,
    )

    cands = _extract_symbol_candidates("trace resolve_callee through `dispatch`")
    assert "dispatch" in cands, cands
    assert "resolve_callee" in cands


def test_qualified_generic_method_is_kept() -> None:
    """RFC-0009 C / Codex P2 #333 (re-review): a generic verb that is the METHOD
    of a qualified symbol (``UserService.handle``, ``Database.fetch``) is named
    deliberately and must survive the filter — the tokenizer splits the qualified
    token, so the method part must count as explicit, not bare."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _extract_symbol_candidates,
    )

    cands = _extract_symbol_candidates("trace UserService.handle to Database.fetch")
    assert "handle" in cands, cands
    assert "fetch" in cands, cands
    assert "UserService" in cands


def test_non_dot_qualified_generic_methods_are_kept() -> None:
    """RFC-0009 C / Codex P2 #333 (3rd round): C++/Rust/PHP-style qualifiers
    (``Class::handle``, ``obj->fetch``) and called verbs (``dispatch()``) name a
    method explicitly and must survive the generic-verb filter, just like dot
    qualifiers and quotes. One post-hoc check against the task text covers all
    qualifier syntaxes."""
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        _extract_symbol_candidates,
    )

    assert "handle" in _extract_symbol_candidates(
        "trace MyClass::handle alongside resolve_callee"
    )
    assert "fetch" in _extract_symbol_candidates(
        "trace obj->fetch alongside resolve_callee"
    )
    assert "dispatch" in _extract_symbol_candidates(
        "does resolve_callee invoke dispatch() here"
    )
    # Go/path-style qualifier (slash) also counts as explicit
    assert "parse" in _extract_symbol_candidates(
        "trace pkg/parser/parse alongside resolve_callee"
    )
    # bare prose verb is still dropped when a specific symbol co-occurs
    assert "dispatch" not in _extract_symbol_candidates(
        "how does resolve_callee dispatch a Java call to resolve_java_callee"
    )
