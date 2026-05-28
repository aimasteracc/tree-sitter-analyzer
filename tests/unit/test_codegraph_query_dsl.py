"""Tests for the codegraph_query chain DSL parser (parse_chain and helpers)."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools._codegraph_query_dsl import (
    _ChainStep,
    bool_kw,
    first_int,
    first_str,
    int_kw,
    string_args,
)
from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    parse_chain,
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

    def test_parses_semantic_search_step(self):
        steps = parse_chain("semantic('user formatting', limit=5)")

        assert steps[0].name == "semantic"
        assert steps[0].args == ["user formatting"]
        assert steps[0].kwargs == {"limit": 5}

    def test_parses_uml_chain_step(self):
        steps = parse_chain("search('run').callees().uml(direction='TD', limit=12)")

        assert [step.name for step in steps] == ["search", "callees", "uml"]
        assert steps[2].kwargs == {"direction": "TD", "limit": 12}

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

    def test_parses_selection_filter_steps(self):
        steps = parse_chain(
            "search('run').filter(kind='function', path='src/', test=False)"
            ".where(regex='Service$').exclude(generated=True).not(file='vendor/')"
        )

        assert [step.name for step in steps] == [
            "search",
            "filter",
            "where",
            "exclude",
            "not",
        ]
        assert steps[1].kwargs == {
            "kind": "function",
            "path": "src/",
            "test": False,
        }
        assert steps[2].kwargs == {"regex": "Service$"}

    def test_parses_relation_aware_has_step(self):
        steps = parse_chain(
            "search('Handler').has(callees=True, name='authorize', depth=2, limit=5)"
            ".has(callers=True, regex='Controller$', test=False)"
        )

        assert [step.name for step in steps] == ["search", "has", "has"]
        assert steps[1].kwargs == {
            "callees": True,
            "name": "authorize",
            "depth": 2,
            "limit": 5,
        }
        assert steps[2].kwargs == {
            "callers": True,
            "regex": "Controller$",
            "test": False,
        }

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
