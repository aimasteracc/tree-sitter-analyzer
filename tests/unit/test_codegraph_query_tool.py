"""Tests for codegraph_query_tool.py — chained graph query surface."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools._codegraph_query_dsl import (
    _ChainStep,
    bool_kw,
    first_int,
    first_str,
    int_kw,
)
from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    CodeGraphQueryTool,
    _build_file_entries,
    _dedupe_symbols,
    _QueryState,
    _relation_step,
    _resolve_query,
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
            ("search(['x'])", "chain arguments must be scalar literals"),
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

        with pytest.raises(ValueError, match=r"search\(\) requires a string query"):
            first_str(_ChainStep("search", [], {}), required=True)


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

    def test_dedupe_symbols_keeps_first_instance(self):
        symbols = [
            {"file": "main.py", "line": 1, "name": "run"},
            {"file": "main.py", "line": 1, "name": "run"},
            {"file": "main.py", "line": 2, "name": "run"},
        ]

        assert _dedupe_symbols(symbols) == [symbols[0], symbols[2]]
