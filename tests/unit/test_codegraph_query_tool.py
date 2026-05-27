"""Tests for codegraph_query_tool.py — chained graph query surface."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import ANY, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools import _codegraph_query_concepts as concepts
from tree_sitter_analyzer.mcp.tools._codegraph_query_dsl import (
    _ChainStep,
    bool_kw,
    first_int,
    first_str,
    int_kw,
    string_args,
)
from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    CodeGraphQueryTool,
    _absolute_path,
    _affected_tests_facet,
    _apply_concept_fallback,
    _build_file_entries,
    _compact_facets,
    _complexity_facet,
    _dedupe_symbols,
    _drop_test_shadow_symbols,
    _health_facet,
    _include_facets,
    _QueryState,
    _relation_step,
    _resolve_queries,
    _resolve_query,
    _risk_facet,
    _sort_state,
    _source_preference_key,
    parse_chain,
)
from tree_sitter_analyzer.symbol_resolver import DefinitionLocation, ResolveResult


def _make_def(
    file: str = "main.py",
    name: str = "run",
    line: int = 1,
    end_line: int = 2,
) -> DefinitionLocation:
    return DefinitionLocation(
        file=file,
        name=name,
        kind="function",
        line=line,
        end_line=end_line,
        language="python",
    )


def _patch_resolver_with(defs_per_token: dict[str, list[DefinitionLocation]]):
    def _resolve(token: str) -> ResolveResult:
        return ResolveResult(symbol=token, definitions=defs_per_token.get(token, []))

    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = _resolve
    return patch(
        "tree_sitter_analyzer.symbol_resolver.SymbolResolver",
        return_value=mock_resolver,
    )


class TestParseChain:
    def test_plain_query_expands_to_explore_related(self):
        steps = parse_chain("CommandService executeCommand")

        assert [step.name for step in steps] == ["explore", "related"]
        assert steps[0].args == ["CommandService executeCommand"]

    def test_parses_dotted_chain_without_splitting_inside_quotes(self):
        steps = parse_chain(
            "search('src/a.b.ts CommandService').explore(max_files=4).callees(depth=2)"
        )

        assert [step.name for step in steps] == ["search", "explore", "callees"]
        assert steps[0].args == ["src/a.b.ts CommandService"]
        assert steps[1].kwargs == {"max_files": 4}
        assert steps[2].kwargs == {"depth": 2}

    def test_rejects_unsupported_step(self):
        with pytest.raises(ValueError, match="unsupported chain step"):
            parse_chain("search('x').delete()")

    def test_parses_batch_seed_and_answer_pack_steps(self):
        steps = parse_chain(
            "search(['Router', 'Handler']).include(callers=True, source=True)"
            ".sort(by='fan_in', desc=True).answer(compact=True)"
        )

        assert [step.name for step in steps] == [
            "search",
            "include",
            "sort",
            "answer",
        ]
        assert string_args(steps[0], required=True) == ["Router", "Handler"]
        assert steps[1].kwargs == {"callers": True, "source": True}
        assert steps[3].kwargs == {"compact": True}

    def test_parses_kwargs_and_escaped_quotes(self):
        steps = parse_chain(r'search(query="src/a.\"b.py Run").take(2)')

        assert steps[0].kwargs == {"query": 'src/a."b.py Run'}
        assert steps[1].args == [2]

    @pytest.mark.parametrize(
        ("query", "match"),
        [
            ("search('x'))", r"unbalanced '\)'"),
            ("search('x)", "unbalanced quote or parentheses"),
            ("search('x').callers", "invalid chain step"),
            ("search({'x': 1})", "chain arguments must be scalar literals"),
            ("search('x', **{'limit': 1})", r"does not support \*\*kwargs"),
            ("search('x', unknown=True)", "does not support keyword"),
        ],
    )
    def test_rejects_malformed_chains(self, query, match):
        with pytest.raises(ValueError, match=match):
            parse_chain(query)

    def test_chain_argument_helpers_cover_defaults_and_fallbacks(self):
        step = _ChainStep(
            "search",
            [],
            {"query": "needle", "limit": "not-an-int", "enabled": 0},
        )

        assert first_str(step, required=True) == "needle"
        assert first_int(_ChainStep("take", [3], {}), default=9) == 3
        assert first_int(_ChainStep("take", [], {}), default=9) == 9
        assert int_kw(step, "limit", default=7, cap=10) == 7
        assert int_kw(_ChainStep("search", [], {"limit": 99}), "limit", 7, 10) == 10
        assert bool_kw(step, "enabled", default=True) is False
        assert bool_kw(_ChainStep("explore", [], {}), "include_code", True) is True
        assert string_args(_ChainStep("search", [["a", "b"]], {}), required=True) == [
            "a",
            "b",
        ]

        with pytest.raises(ValueError, match=r"search\(\) requires a string query"):
            first_str(_ChainStep("search", [], {}), required=True)

    @pytest.mark.parametrize(
        ("query", "match"),
        [
            ("x" * 4097 + "()", "query exceeds"),
            (".".join(["answer()"] * 21), "query exceeds 20 chain steps"),
            ("search(['ok', 1])", "list arguments must contain only strings"),
            ("search(" + repr(["x"] * 9) + ")", "list arguments must contain <= 8"),
            ("search(" + repr("x" * 161) + ")", "string arguments must be <= 160"),
            (
                "search(" + repr(["ok", "x" * 161]) + ")",
                "string arguments must be <= 160",
            ),
        ],
    )
    def test_parser_rejects_guardrail_violations(self, query, match):
        with pytest.raises(ValueError, match=match):
            parse_chain(query)

    def test_argument_helpers_cover_keyword_lists_and_limits(self):
        step = _ChainStep("search", ["positional"], {"query": ["kw1", "kw2"]})

        assert string_args(step, required=True) == ["kw1", "kw2"]
        assert (
            first_str(_ChainStep("search", ["needle"], {}), required=True) == "needle"
        )
        assert first_str(_ChainStep("include", [], {}), required=False) == ""
        assert first_int(_ChainStep("take", [], {"limit": 4}), default=9) == 4


class TestCodeGraphQueryTool:
    def test_definition(self):
        definition = CodeGraphQueryTool().get_tool_definition()

        assert definition["name"] == "codegraph_query"
        assert definition["annotations"]["readOnlyHint"] is True

    def test_schema_requires_query(self):
        schema = CodeGraphQueryTool().get_tool_schema()

        assert schema["required"] == ["query"]
        assert schema["additionalProperties"] is False

    def test_validate_requires_query(self):
        with pytest.raises(ValueError, match="query is required"):
            CodeGraphQueryTool().validate_arguments({})

    def test_get_cache_requires_project_root_and_reuses_instance(self, tmp_path):
        with pytest.raises(ValueError, match="Project root not set"):
            CodeGraphQueryTool()._get_cache()

        mock_cache = MagicMock()
        tool = CodeGraphQueryTool(str(tmp_path))
        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache
        ) as ast_cache:
            assert tool._get_cache() is mock_cache
            assert tool._get_cache() is mock_cache

        ast_cache.assert_called_once_with(str(tmp_path))
        tool.set_project_path(str(tmp_path / "next"))
        assert tool._cache is None

    @pytest.mark.asyncio
    async def test_execute_runs_chain_in_one_tool(self, tmp_path):
        source = tmp_path / "main.py"
        source.write_text(
            "def run():\n    return helper()\n\ndef helper():\n    return 1\n",
            encoding="utf-8",
        )
        mock_cache = MagicMock()
        mock_cache.query_callees.return_value = [
            {
                "caller_name": "run",
                "caller_file": "main.py",
                "caller_line": 1,
                "callee_name": "helper",
                "callee_file": "main.py",
                "callee_line": 4,
                "depth": 1,
            }
        ]
        mock_cache.query_callers.return_value = []

        with (
            patch(
                "tree_sitter_analyzer.ast_cache.ASTCache",
                return_value=mock_cache,
            ),
            _patch_resolver_with({"run": [_make_def(name="run")]}),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run').explore(max_files=2).callees(depth=1)",
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["stats"]["steps"] == 3
        assert result["stats"]["symbols_returned"] == 2
        assert result["files"][0]["file_path"] == "main.py"
        assert "code" in result["files"][0]["symbols"][0]
        assert (
            result["relationships"]["callees"]["main.py:1:run"][0]["name"] == "helper"
        )

    @pytest.mark.asyncio
    async def test_execute_returns_error_envelope_for_bad_chain(self):
        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()):
            result = await CodeGraphQueryTool("/tmp").execute(
                {
                    "query": "search('run').delete()",
                    "output_format": "json",
                }
            )

        assert result["success"] is False
        assert result["verdict"] == "ERROR"
        assert "unsupported chain step" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_collects_step_warnings_for_invalid_search_arg(
        self, tmp_path
    ):
        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search()",
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "NOT_FOUND"
        assert result["warnings"] == ["search() requires a string query"]

    @pytest.mark.asyncio
    async def test_execute_explore_callers_related_and_take(self, tmp_path):
        (tmp_path / "main.py").write_text(
            "def run():\n    return 1\n",
            encoding="utf-8",
        )
        mock_cache = MagicMock()

        def _query_callers(name, file_path, max_depth):
            if name == "run":
                return [
                    {
                        "caller_name": "entry",
                        "caller_file": "entry.py",
                        "caller_line": 10,
                        "depth": max_depth,
                    },
                    {"caller_name": "", "caller_file": "ignored.py", "caller_line": 1},
                ]
            return []

        def _query_callees(name, file_path, max_depth):
            if name == "entry":
                return [
                    {
                        "callee_name": "helper",
                        "callee_file": file_path or "helper.py",
                        "callee_line": 4,
                        "depth": max_depth,
                    }
                ]
            return []

        mock_cache.query_callers.side_effect = _query_callers
        mock_cache.query_callees.side_effect = _query_callees
        defs = {
            "run": [
                _make_def(file="main.py", name="run", line=1),
                _make_def(file="main.py", name="run", line=1),
                _make_def(file="other.py", name="run", line=1),
            ]
        }

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "explore('main.py run', max_symbols=3, include_code=False)"
                        ".callers(depth=1).related(limit=2).take(2)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert [symbol["name"] for symbol in result["symbols"]] == ["run", "entry"]
        assert result["symbols"][0]["file"] == "main.py"
        assert result["symbols"][1]["file"] == "entry.py"
        assert "code" not in result["files"][0]["symbols"][0]
        assert result["relationships"]["callers"]["main.py:1:run"][0]["name"] == "entry"
        assert (
            result["relationships"]["callees"]["entry.py:10:entry"][0]["name"]
            == "helper"
        )

    @pytest.mark.asyncio
    async def test_execute_search_limit_caps_symbols(self, tmp_path):
        defs = {
            "run": [
                _make_def(file="main.py", name="run", line=1),
                _make_def(file="main.py", name="helper", line=5),
            ]
        }

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run', limit=1)",
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert [symbol["name"] for symbol in result["symbols"]] == ["run"]

    @pytest.mark.asyncio
    async def test_execute_explore_falls_back_to_concept_search_for_plain_language(
        self, tmp_path
    ):
        source = tmp_path / "router.py"
        source.write_text(
            "def handle_route():\n    # route matching lives here\n    return True\n",
            encoding="utf-8",
        )
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT,
                language TEXT,
                file_size INTEGER,
                symbols_json TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
            (
                "router.py",
                "python",
                source.stat().st_size,
                json.dumps(
                    {
                        "symbols": [
                            {
                                "name": "handle_route",
                                "kind": "function",
                                "line": 1,
                                "end_line": 3,
                            }
                        ]
                    }
                ),
            ),
        )
        mock_cache = MagicMock()
        mock_cache._get_conn.return_value = conn
        mock_cache.query_callers.return_value = []
        mock_cache.query_callees.return_value = []

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with({}),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search('route matching').explore(max_files=3)"
                        ".include(source=True).answer(compact=True)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["stats"]["concept_files_returned"] == 1
        assert result["symbols"][0]["name"] == "handle_route"
        source_facet = result["facets"]["source"]["files"][0]
        assert source_facet["file"] == "router.py"
        assert any(match["line"] == 2 for match in source_facet["matches"])
        assert source_facet["symbols"][0]["name"] == "handle_route"

    @pytest.mark.asyncio
    async def test_execute_include_source_can_trigger_concept_fallback(self, tmp_path):
        source = tmp_path / "router.py"
        source.write_text(
            "def handle_route():\n    # route matching lives here\n    return True\n",
            encoding="utf-8",
        )
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT,
                language TEXT,
                file_size INTEGER,
                symbols_json TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
            (
                "router.py",
                "python",
                source.stat().st_size,
                json.dumps(
                    {
                        "symbols": [
                            {
                                "name": "handle_route",
                                "kind": "function",
                                "line": 1,
                                "end_line": 3,
                            }
                        ]
                    }
                ),
            ),
        )
        mock_cache = MagicMock()
        mock_cache._get_conn.return_value = conn

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with({}),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search('route matching')"
                        ".include(source=True).answer(compact=True)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["verdict"] == "INFO"
        assert result["stats"]["concept_files_returned"] == 1
        assert result["facets"]["source"]["files"][0]["file"] == "router.py"

    @pytest.mark.asyncio
    async def test_execute_batch_seed_include_sort_and_answer(self, tmp_path):
        source = tmp_path / "main.py"
        source.write_text(
            "def run():\n    return helper()\n\ndef helper():\n    return 1\n",
            encoding="utf-8",
        )
        mock_cache = MagicMock()
        mock_cache.query_callers.return_value = [
            {
                "caller_name": "entry",
                "caller_file": "tests/test_main.py",
                "caller_line": 8,
                "depth": 1,
            }
        ]
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "helper",
                "callee_file": "main.py",
                "callee_line": 4,
                "depth": 1,
            }
        ]

        defs = {
            "run": [_make_def(file="main.py", name="run", line=1)],
            "helper": [_make_def(file="main.py", name="helper", line=4)],
        }

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search(['run', 'helper']).explore(max_files=2)"
                        ".include(source=True, callers=True, callees=True, "
                        "affected_tests=True, risk=True)"
                        ".sort(by='fan_in', desc=True).answer()"
                    ),
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["stats"]["facets_returned"] == 5
        assert result["facets"]["source"]["file_count"] == 1
        assert result["facets"]["callers"]["edges"]
        assert result["facets"]["callees"]["edges"]
        assert result["facets"]["affected_tests"]["files"] == ["tests/test_main.py"]
        assert result["facets"]["risk"]["level"] == "info"
        assert result["normalized_chain"][-1]["name"] == "answer"

    @pytest.mark.asyncio
    async def test_execute_compact_answer_removes_duplicate_source_payload(
        self, tmp_path
    ):
        source = tmp_path / "main.py"
        source.write_text(
            "def run():\n    return helper()\n\ndef helper():\n    return 1\n",
            encoding="utf-8",
        )
        mock_cache = MagicMock()
        mock_cache.query_callers.return_value = []
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "helper",
                "callee_file": "main.py",
                "callee_line": 4,
                "depth": 1,
            }
        ]
        defs = {"run": [_make_def(file="main.py", name="run", line=1)]}

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search('run').explore(max_files=1)"
                        ".include(source=True, callees=True).answer(compact=True)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["stats"]["compact"] is True
        assert result["files"] == []
        assert result["facets"]["source"]["files"][0]["file"] == "main.py"
        assert result["facets"]["source"]["files"][0]["symbols"][0]["lines"] == "1-2"
        assert "language" not in result["relationships"]["callees"]["main.py:1:run"][0]

    def test_apply_step_rejects_unknown_step(self):
        with pytest.raises(ValueError, match="unsupported chain step"):
            CodeGraphQueryTool("/tmp")._apply_step(
                cache=MagicMock(),
                state=_QueryState(),
                step=_ChainStep("unknown", [], {}),
                default_max_symbols=10,
                default_max_files=3,
                default_include_code=True,
            )


class TestCodeGraphQueryInternals:
    def test_query_state_add_symbols_dedupes_repeated_entries(self):
        state = _QueryState()
        symbol = {"file": "main.py", "line": 1, "name": "run"}

        state.add_symbols([symbol, dict(symbol)])

        assert state.symbols == [symbol]

    def test_resolve_query_uses_raw_query_fallback_and_handles_resolver_errors(self):
        with _patch_resolver_with({"   ": [_make_def(name="fallback")]}):
            assert _resolve_query(MagicMock(), "   ", limit=5)[0]["name"] == "fallback"

        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = RuntimeError("boom")
        with patch(
            "tree_sitter_analyzer.symbol_resolver.SymbolResolver",
            return_value=mock_resolver,
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

    def test_relation_step_skips_symbols_without_names_and_empty_rows(self):
        mock_cache = MagicMock()
        mock_cache.query_callers.return_value = [
            {"caller_name": "", "caller_file": "ignored.py", "caller_line": 1},
            {
                "caller_name": "entry",
                "caller_file": "entry.py",
                "caller_line": 10,
                "depth": 2,
            },
        ]
        state = _QueryState()
        state.current = [
            {"file": "ignored.py", "line": 1},
            {"name": "run", "file": "main.py", "line": 2},
        ]

        related = _relation_step(
            mock_cache,
            state,
            direction="callers",
            step=_ChainStep("callers", [], {"depth": "bad", "limit": 2}),
        )

        assert [symbol["name"] for symbol in related] == ["entry"]
        mock_cache.query_callers.assert_called_once_with("run", "main.py", max_depth=1)
        assert state.relationships["callers"]["main.py:2:run"][0]["name"] == "entry"

    def test_relation_step_sorts_source_edges_before_tests_then_limits(self):
        mock_cache = MagicMock()
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "ServeHTTP",
                "callee_file": "utils_test.go",
                "callee_line": 33,
                "depth": 1,
            },
            {
                "callee_name": "ServeHTTP",
                "callee_file": "gin.go",
                "callee_line": 623,
                "depth": 1,
            },
        ]
        state = _QueryState()
        state.current = [{"name": "dispatch", "file": "gin.go", "line": 600}]

        related = _relation_step(
            mock_cache,
            state,
            direction="callees",
            step=_ChainStep("callees", [], {"limit": 1}),
        )

        assert [symbol["file"] for symbol in related] == ["gin.go"]
        assert state.relationships["callees"]["gin.go:600:dispatch"][0]["line"] == 623

    def test_source_preference_key_identifies_test_fixture_and_generated_paths(self):
        source = {"file": "gin.go", "line": 2, "name": "run"}
        test = {"file": "tests/fixtures/gin_test.go", "line": 1, "name": "run"}
        generated = {"file": "src/generated/gin.go", "line": 1, "name": "run"}

        assert _source_preference_key(source) < _source_preference_key(test)
        assert _source_preference_key(source) < _source_preference_key(generated)
        assert _drop_test_shadow_symbols([test, source]) == [source]
        assert _drop_test_shadow_symbols([test]) == [test]

    def test_sort_state_supports_path_alias_fan_out_and_rejects_unknown_fields(self):
        state = _QueryState()
        state.current = [
            {"file": "b.py", "line": 2, "name": "b"},
            {"file": "a.py", "line": 1, "name": "a"},
        ]
        state.symbols = list(state.current)
        state.relationships["callees"] = {"a.py:1:a": [{}, {}], "b.py:2:b": [{}]}

        _sort_state(state, _ChainStep("sort", [], {"by": "path"}))
        assert [symbol["file"] for symbol in state.current] == ["a.py", "b.py"]

        _sort_state(state, _ChainStep("sort", [], {"by": "fan_out", "desc": True}))
        assert [symbol["name"] for symbol in state.current] == ["a", "b"]

        with pytest.raises(ValueError, match="unsupported field"):
            _sort_state(state, _ChainStep("sort", [], {"by": "unknown"}))

    def test_build_file_entries_skips_blank_files_and_omits_oversized_snippets(
        self, tmp_path
    ):
        source = tmp_path / "main.py"
        source.write_text("def run():\n    return 1\n", encoding="utf-8")

        entries = _build_file_entries(
            project_root=str(tmp_path),
            symbols=[
                {"name": "nameless", "file": "", "line": 1, "end_line": 1},
                {
                    "name": "run",
                    "kind": "function",
                    "file": "main.py",
                    "line": 1,
                    "end_line": 999,
                    "language": "python",
                },
            ],
            max_files=3,
            include_code=True,
        )

        assert entries == [
            {
                "file_path": "main.py",
                "language": "python",
                "symbols": [
                    {
                        "name": "run",
                        "kind": "function",
                        "start_line": 1,
                        "end_line": 999,
                    }
                ],
            }
        ]

    def test_include_facets_collects_quality_health_tests_and_risk(self, tmp_path):
        source = tmp_path / "main.py"
        source.write_text("def run():\n    return 1\n", encoding="utf-8")
        mock_cache = MagicMock()
        mock_cache.query_callers.return_value = [
            {"caller_name": f"caller_{i}", "caller_file": f"c{i}.py", "caller_line": i}
            for i in range(10)
        ]
        mock_cache.query_callees.return_value = [
            {"callee_name": "helper", "callee_file": "helper.py", "callee_line": 7}
        ]
        state = _QueryState()
        state.current = [
            {"file": "main.py", "line": 1, "name": "run", "kind": "function"},
            {
                "file": "tests/test_main.py",
                "line": 3,
                "name": "test_run",
                "kind": "function",
            },
        ]
        state.symbols = list(state.current)

        complexity_row = MagicMock(name="run", line=1, complexity=22)
        health_score = MagicMock(total=51, grade="D", dimensions={"complexity": 20})
        with (
            patch(
                "tree_sitter_analyzer.complexity_heatmap."
                "analyze_file_complexity_from_cache",
                return_value=[complexity_row],
            ),
            patch("tree_sitter_analyzer.health_scorer.HealthScorer") as scorer_cls,
        ):
            scorer_cls.return_value.score_file.return_value = health_score
            _include_facets(
                cache=mock_cache,
                project_root=str(tmp_path),
                state=state,
                step=_ChainStep(
                    "include",
                    [],
                    {
                        "source": True,
                        "callers": True,
                        "callees": True,
                        "complexity": True,
                        "health": True,
                        "affected_tests": True,
                        "risk": True,
                        "include_code": False,
                    },
                ),
                default_max_symbols=10,
                default_max_files=5,
                default_include_code=True,
            )

        assert set(state.facets) == {
            "source",
            "callers",
            "callees",
            "complexity",
            "health",
            "affected_tests",
            "risk",
        }
        assert state.facets["complexity"]["files"][0]["max_complexity"] == 22
        assert state.facets["health"]["files"][0]["grade"] == "D"
        assert state.facets["affected_tests"]["files"] == ["tests/test_main.py"]
        assert state.facets["risk"]["level"] == "review"

    def test_compact_facets_trim_source_relationship_and_quality_shapes(self):
        facets = {
            "source": {
                "status": "included",
                "file_count": 1,
                "files": [
                    {
                        "file_path": "main.py",
                        "language": "python",
                        "symbols": [
                            {
                                "name": "run",
                                "kind": "function",
                                "start_line": 1,
                                "end_line": 2,
                                "code": "def run():\n    pass\n",
                            }
                        ],
                    }
                ],
            },
            "callees": {
                "status": "included",
                "edges": {
                    "main.py:1:run": [
                        {
                            "name": "helper",
                            "kind": "function",
                            "file": "main.py",
                            "line": 4,
                            "end_line": 4,
                            "language": "",
                            "depth": 1,
                        }
                    ]
                },
            },
            "complexity": {
                "status": "included",
                "files": [
                    {
                        "file": "main.py",
                        "status": "included",
                        "max_complexity": 12,
                        "total_complexity": 20,
                        "hotspots": [{"name": "run", "line": 1, "complexity": 12}],
                    }
                ],
            },
            "health": {
                "status": "included",
                "files": [
                    {
                        "file": "main.py",
                        "status": "included",
                        "total": 82,
                        "grade": "B",
                        "dimensions": {"complexity": 80},
                    }
                ],
            },
        }

        compact = _compact_facets(facets)

        assert compact["source"]["files"][0]["file"] == "main.py"
        assert compact["source"]["files"][0]["symbols"][0]["lines"] == "1-2"
        assert compact["callees"]["edges"]["main.py:1:run"] == [
            {
                "name": "helper",
                "file": "main.py",
                "line": 4,
                "kind": "function",
                "depth": 1,
            }
        ]
        assert compact["complexity"]["files"][0]["hotspots"][0]["cc"] == 12
        assert "dimensions" not in compact["health"]["files"][0]

    def test_quality_facets_cover_empty_error_and_missing_paths(self, tmp_path):
        symbols = [{"file": "main.py", "line": 1, "name": "run"}]

        with patch(
            "tree_sitter_analyzer.complexity_heatmap.analyze_file_complexity_from_cache",
            side_effect=[[], RuntimeError("boom")],
        ):
            result = _complexity_facet(
                MagicMock(),
                str(tmp_path),
                [*symbols, {"file": "other.py", "line": 2, "name": "other"}],
                max_files=2,
            )

        assert result["files"][0]["status"] == "no_functions"
        assert result["files"][1]["status"] == "error"

        with patch("tree_sitter_analyzer.health_scorer.HealthScorer") as scorer_cls:
            scorer_cls.return_value.score_file.side_effect = RuntimeError("bad health")
            health = _health_facet(str(tmp_path), symbols, max_files=1)

        assert health["files"] == [
            {"file": "main.py", "status": "error", "error": "bad health"}
        ]

        empty_state = _QueryState()
        assert _affected_tests_facet(empty_state)["status"] == "missing"
        assert _risk_facet(empty_state)["level"] == "info"
        assert _absolute_path(str(tmp_path), str(tmp_path / "main.py")) == str(
            tmp_path / "main.py"
        )

    def test_dedupe_symbols_keeps_first_instance(self):
        symbols = [
            {"file": "main.py", "line": 1, "name": "run"},
            {"file": "main.py", "line": 1, "name": "run"},
            {"file": "main.py", "line": 2, "name": "run"},
        ]

        assert _dedupe_symbols(symbols) == [symbols[0], symbols[2]]
