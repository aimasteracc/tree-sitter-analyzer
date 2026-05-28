"""Tests for codegraph_query_tool filter helpers, query state, resolve, and concepts."""

from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

import pytest

from tests.unit._codegraph_query_helpers import _make_def, _patch_resolver_with
from tree_sitter_analyzer.mcp.tools import _codegraph_query_concepts as concepts
from tree_sitter_analyzer.mcp.tools import _codegraph_query_filters as filters
from tree_sitter_analyzer.mcp.tools._codegraph_query_dsl import _ChainStep
from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    _apply_concept_fallback,
    _filter_declaration_query_symbols,
    _QueryState,
    _resolve_queries,
    _resolve_query,
    _uml_facet,
)


class TestCodeGraphQueryInternals:
    def test_filter_symbols_supports_predicates_and_inverse_selection(self):
        symbols = [
            {
                "name": "RouterService",
                "kind": "class",
                "file": "src/router.py",
                "language": "python",
                "line": 1,
            },
            {
                "name": "RouterServiceTest",
                "kind": "class",
                "file": "tests/test_router.py",
                "language": "python",
                "line": 1,
            },
            {
                "name": "GeneratedRouter",
                "kind": "class",
                "file": "src/generated/router.py",
                "language": "python",
                "line": 1,
            },
        ]
        step = _ChainStep(
            "filter",
            [],
            {"kind": ["class"], "regex": "Service$", "test": False},
        )

        assert [s["name"] for s in filters.filter_symbols(symbols, step)] == [
            "RouterService"
        ]
        assert [
            s["name"] for s in filters.filter_symbols(symbols, step, invert=True)
        ] == ["RouterServiceTest", "GeneratedRouter"]

    def test_filter_symbols_reports_bad_regex(self):
        with pytest.raises(ValueError, match=r"filter\(\) invalid regex"):
            filters.filter_symbols(
                [{"name": "run", "file": "main.py"}],
                _ChainStep("filter", [], {"regex": "["}),
            )

    def test_filter_symbols_covers_empty_case_and_negative_predicates(self):
        symbols = [
            {"name": "RunService", "file": "src/run.py", "kind": "class"},
            {"name": "runservice", "file": "tests/test_run.py", "kind": "class"},
            {"name": "Generated", "file": "src/generated/run.py", "kind": "class"},
        ]

        assert filters.filter_symbols(symbols, _ChainStep("filter", [], {})) == symbols
        assert filters.filter_symbols(
            symbols,
            _ChainStep("filter", [], {"name": "Run", "case": True}),
        ) == [symbols[0]]
        assert filters.filter_symbols(
            symbols,
            _ChainStep("filter", [], {"test": False, "generated": False}),
        ) == [symbols[0]]
        assert (
            filters.filter_symbols(
                symbols,
                _ChainStep("filter", [], {"name": ""}),
            )
            == symbols
        )
        with pytest.raises(ValueError, match="regex must be a non-empty string"):
            filters.filter_symbols(symbols, _ChainStep("filter", [], {"regex": 1}))

    def test_query_state_add_symbols_dedupes_repeated_entries(self):
        state = _QueryState()
        symbol = {"file": "main.py", "line": 1, "name": "run"}

        state.add_symbols([symbol, dict(symbol)])

        assert state.symbols == [symbol]

    def test_uml_facet_uses_current_symbols_when_no_relationships(self):
        state = _QueryState()
        state.current = [{"file": "main.py", "line": 1, "name": "run"}]

        facet = _uml_facet(state, direction="LR", max_edges=5)

        assert facet["status"] == "included"
        assert facet["edge_count"] == 0
        assert facet["mermaid"] == 'flowchart LR\n  run["run"]'

    def test_resolve_query_uses_raw_query_fallback_and_handles_resolver_errors(self):
        with _patch_resolver_with({"   ": [_make_def(name="fallback")]}):
            assert _resolve_query(MagicMock(), "   ", limit=5)[0]["name"] == "fallback"

        class FailingBackend:
            def __init__(self, cache):
                pass

            def resolve_definitions(self, token):
                raise RuntimeError("boom")

        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_query_tool.CodeGraphQueryBackend",
            FailingBackend,
        ):
            assert _resolve_query(MagicMock(), "run", limit=5) == []

    def test_resolve_query_normalizes_code_like_signature_tokens(self):
        defs = {
            "handleHTTPRequest": [
                _make_def(file="gin.go", name="handleHTTPRequest", line=690)
            ],
            "engine": [_make_def(file="wrong.go", name="Engine", line=1)],
        }

        with _patch_resolver_with(defs):
            result = _resolve_query(
                MagicMock(),
                "func (engine .*handleHTTPRequest)",
                limit=5,
            )

        assert [symbol["name"] for symbol in result] == ["handleHTTPRequest"]

    def test_resolve_query_filters_non_declaration_for_type_query(self):
        defs = {
            "Param": [
                _make_def(file="context.go", name="Param", kind="function", line=503)
            ]
        }

        with _patch_resolver_with(defs):
            result = _resolve_query(MagicMock(), "type Param struct", limit=5)

        assert result == []

    def test_resolve_query_keeps_matching_declaration_for_type_query(self):
        defs = {
            "Param": [
                _make_def(file="context.go", name="Param", kind="function", line=503),
                _make_def(
                    file="tree.go",
                    name="Param",
                    kind="type",
                    line=17,
                    end_line=20,
                    language="go",
                ),
            ]
        }

        with _patch_resolver_with(defs):
            result = _resolve_query(MagicMock(), "type Param struct", limit=5)

        assert [symbol["file"] for symbol in result] == ["tree.go"]
        assert result[0]["kind"] == "type"

    def test_declaration_query_filter_keeps_unrelated_symbols(self):
        symbols = [{"name": "Other", "kind": "function", "file": "main.go", "line": 1}]

        assert (
            _filter_declaration_query_symbols("type Param struct", symbols) == symbols
        )

    def test_resolve_query_drops_test_shadow_when_source_definition_exists(self):
        defs = {
            "ServeHTTP": [
                _make_def(file="utils_test.go", name="ServeHTTP", line=33),
                _make_def(file="gin.go", name="ServeHTTP", line=623),
            ]
        }

        with _patch_resolver_with(defs):
            result = _resolve_query(MagicMock(), "ServeHTTP", limit=5)

        assert [symbol["file"] for symbol in result] == ["gin.go"]

    def test_resolve_query_keeps_test_shadow_with_file_hint(self):
        defs = {
            "ServeHTTP": [
                _make_def(file="utils_test.go", name="ServeHTTP", line=33),
                _make_def(file="gin.go", name="ServeHTTP", line=623),
            ]
        }

        with _patch_resolver_with(defs):
            result = _resolve_query(MagicMock(), "utils_test.go ServeHTTP", limit=5)

        assert [symbol["file"] for symbol in result] == ["utils_test.go"]

    def test_query_concept_token_normalization_prefers_signature_names(self):
        assert concepts.symbol_candidate_tokens("func (trees methodTrees) get") == [
            "get",
            "methodTrees",
        ]
        assert concepts.normalized_query_terms("route matching") == [
            "route",
            "matching",
        ]
        assert concepts.concept_query_terms("type node struct") == [
            "node",
            "type",
            "struct",
        ]
        assert concepts.symbol_candidate_tokens("type HandlerFunc func(*Context)") == [
            "HandlerFunc"
        ]
        assert concepts.declared_type_name("type Param struct") == "Param"
        assert concepts.concept_query_terms("type HandlerFunc func(*Context)") == [
            "HandlerFunc",
            "type",
        ]
        assert concepts.symbol_candidate_tokens("static nodeType = iota") == [
            "static",
            "nodeType",
            "iota",
        ]
        assert concepts.concept_query_terms("static nodeType = iota") == [
            "static",
            "nodeType",
            "iota",
            "const",
        ]
        assert concepts.symbol_candidate_tokens("const static nodeType = iota") == [
            "static",
            "nodeType",
            "iota",
        ]
        assert concepts.concept_query_terms("const static nodeType = iota") == [
            "static",
            "nodeType",
            "iota",
            "const",
        ]
        assert concepts.concept_query_terms("catchAll nodeType") == [
            "catchAll",
            "nodeType",
            "const",
        ]
        assert concepts.normalized_query_terms("func (engine .*handleHTTPRequest)") == [
            "handleHTTPRequest"
        ]
        assert concepts.normalized_query_terms("...") == []

    def test_declared_type_entries_prefer_exact_type_declaration(self):
        entries = [
            {
                "file_path": "tree.go",
                "matches": [{"text": "type Param struct {"}],
            },
            {
                "file_path": "logger.go",
                "matches": [{"text": "type LogFormatterParams struct {"}],
            },
        ]

        narrowed = concepts.narrow_declared_type_entries(["type Param struct"], entries)

        assert [entry["file_path"] for entry in narrowed] == ["tree.go"]

    def test_declared_type_entries_keep_broad_matches_without_exact_declaration(self):
        entries = [
            {
                "file_path": "logger.go",
                "matches": [{"text": "type LogFormatterParams struct {"}],
            }
        ]

        assert (
            concepts.narrow_declared_type_entries(["type Param struct"], entries)
            == entries
        )
        assert concepts._primary_signature_terms("func ()", []) == []

    def test_resolve_queries_stops_at_limit_and_dedupes(self):
        defs = {
            "run": [
                _make_def(file="main.py", name="run", line=1),
                _make_def(file="main.py", name="run", line=1),
            ],
            "helper": [_make_def(file="helper.py", name="helper", line=3)],
        }

        with _patch_resolver_with(defs):
            assert [
                symbol["name"]
                for symbol in _resolve_queries(MagicMock(), ["run", "helper"], limit=1)
            ] == ["run"]

    def test_apply_concept_fallback_degrades_on_missing_seed_or_matches(self):
        state = _QueryState()
        _apply_concept_fallback(
            cache=MagicMock(),
            project_root="/tmp",
            state=state,
            max_files=2,
            max_symbols=2,
        )
        assert state.files == []

        state.seed_queries = ["missing concept"]
        with patch(
            "tree_sitter_analyzer.mcp.tools._codegraph_query_concepts."
            "concept_entries_for_queries",
            return_value=[],
        ):
            _apply_concept_fallback(
                cache=MagicMock(),
                project_root="/tmp",
                state=state,
                max_files=2,
                max_symbols=2,
            )

        assert state.files == []
        assert state.current == []

    def test_query_concept_helpers_cover_empty_dedupe_and_limit_paths(self):
        assert (
            concepts.concept_entries_for_queries(
                MagicMock(),
                ["  "],
                project_root="/tmp",
                max_files=2,
            )
            == []
        )

        with patch.object(
            concepts._h,
            "concept_search",
            return_value=[{"file_path": "src/router.py"}],
        ) as concept_search:
            assert concepts.concept_entries_for_queries(
                MagicMock(),
                ["src/router.py route route src/router.py"],
                project_root="/tmp",
                max_files=2,
            ) == [{"file_path": "src/router.py"}]

        concept_search.assert_called_once_with(
            ANY,
            ["route"],
            ["src/router.py"],
            "/tmp",
            2,
        )

        entries = [
            {
                "file_path": "src/router.py",
                "language": "python",
                "symbols": [
                    {"name": "", "kind": "function", "start_line": 1},
                    {"name": "missing_line", "kind": "function", "start_line": 0},
                    {
                        "name": "handle_route",
                        "kind": "function",
                        "start_line": 2,
                        "end_line": 4,
                    },
                    {
                        "name": "handle_route",
                        "kind": "function",
                        "start_line": 2,
                        "end_line": 4,
                    },
                    {"name": "helper", "kind": "function", "start_line": 8},
                ],
            },
            {
                "file_path": "",
                "language": "python",
                "symbols": [{"name": "ignored", "kind": "function", "start_line": 1}],
            },
        ]

        limited = concepts.symbols_from_concept_entries(entries, limit=1)
        assert [symbol["name"] for symbol in limited] == ["handle_route"]

        all_symbols = concepts.symbols_from_concept_entries(entries, limit=10)
        assert [symbol["name"] for symbol in all_symbols] == [
            "handle_route",
            "helper",
        ]
