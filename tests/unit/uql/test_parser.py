"""RFC-0041 parser + IR: one grammar, typed errors with a suggested fix."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.uql import errors as E
from tree_sitter_analyzer.uql.errors import Err, Ok
from tree_sitter_analyzer.uql.ir import (
    HasTests,
    Refine,
    Relate,
    Select,
    Sort,
    SymbolSource,
    Take,
)
from tree_sitter_analyzer.uql.parser import parse_chain, parse_query


def _ok(text: str):
    result = parse_query(text)
    assert isinstance(result, Ok), result
    return result.value


def _err(text: object) -> E.QueryError:
    result = parse_query(text)
    assert isinstance(result, Err), result
    return result.error


def test_pipeline_parses_into_ordered_stages() -> None:
    query = _ok("symbol('parse').callers(depth=2).filter(path='src/').tests().take(5)")
    assert query.stages == (
        SymbolSource(("parse",)),
        Relate("callers", 2),
        Refine("filter", (("path", "src/"),)),
        Relate("tests"),
        Take(5),
    )


def test_bare_selector_is_a_select_source() -> None:
    query = _ok(".function:in(src/)")
    assert (query.dialect, type(query.stages[0]), query.stages[0].text) == (
        "tql",
        Select,
        ".function:in(src/)",
    )


def test_select_stage_embeds_a_tql_selector() -> None:
    query = _ok("select('.class:has(#run)').callers()")
    assert (type(query.stages[0]), query.stages[1]) == (Select, Relate("callers", 1))


def test_symbol_accepts_names_list_and_file() -> None:
    query = _ok("symbol(['A.run', 'b'], file='src/a.py')")
    assert query.stages[0] == SymbolSource(("A.run", "b"), "src/a.py")


def test_chain_search_alias_is_a_symbol_source() -> None:
    assert _ok("search('X').callers()").stages[0] == SymbolSource(("X",))


def test_refinement_vocabulary() -> None:
    query = _ok(
        "symbol('x').callers().exclude(test=true).untested().sort(by='file', desc=true)"
    )
    assert query.stages[2:] == (
        Refine("exclude", (("test", True),)),
        HasTests(want_tests=False),
        Sort("file", True),
    )


def test_impact_defaults_to_closure_depth_cap() -> None:
    assert _ok("symbol('x').impact()").stages[1] == Relate("impact", 10)


@pytest.mark.parametrize("text", [None, "", "   ", 3])
def test_empty_query_is_typed(text: object) -> None:
    assert _err(text).code == E.EMPTY_QUERY


def test_pipe_separator_gives_corrected_query() -> None:
    error = _err("symbol('x') | callers()")
    assert (error.code, error.fixed_query) == (
        E.WRONG_SEPARATOR,
        "symbol('x').callers()",
    )


def test_unknown_stage_suggests_closest() -> None:
    error = _err("symbol('x').caller()")
    assert (error.code, error.stage_index, error.suggestion) == (
        E.UNKNOWN_STAGE,
        1,
        "Did you mean callers()?",
    )


def test_chain_only_stage_points_at_chain_action() -> None:
    error = _err("symbol('x').explore()")
    assert (error.code, "search action=chain" in (error.suggestion or "")) == (
        E.CHAIN_ONLY_STAGE,
        True,
    )


def test_unknown_keyword_lists_accepted_ones() -> None:
    error = _err("symbol('x').callers(limit=3)")
    assert (error.code, error.suggestion) == (
        E.UNKNOWN_ARGUMENT,
        "Accepted keywords for callers(): depth.",
    )


@pytest.mark.parametrize(
    "text",
    [
        "symbol('x').callers(depth=0)",
        "symbol('x').callers(depth=6)",
        "symbol('x').impact(depth=11)",
    ],
)
def test_depth_out_of_range_is_invalid_argument(text: str) -> None:
    assert _err(text).code == E.INVALID_ARGUMENT


def test_relation_before_source_is_invalid_order() -> None:
    error = _err("callers().tests()")
    assert (error.code, error.fixed_query) == (
        E.INVALID_ORDER,
        "symbol('Name').callers().tests()",
    )


def test_second_source_is_invalid_order() -> None:
    assert _err("symbol('a').symbol('b')").code == E.INVALID_ORDER


def test_bare_word_suggests_symbol_source() -> None:
    error = _err("parse")
    assert (error.code, error.fixed_query) == (E.BARE_WORD, "symbol('parse')")


def test_unbalanced_parentheses_are_typed() -> None:
    assert _err("symbol('x'").code == E.UNBALANCED


def test_selector_syntax_error_is_typed() -> None:
    assert _err(".function:in(").code == E.SELECTOR_SYNTAX


def test_unknown_pseudo_class_gets_did_you_mean_fix() -> None:
    error = _err(".function:cals(#X)")
    assert (error.code, error.fixed_query) == (
        E.UNKNOWN_PSEUDO_CLASS,
        ".function:calls(#X)",
    )


def test_unknown_attribute_is_rejected_not_silently_empty() -> None:
    # RFC-0041 §4: the Hyphae evaluator returns [] for an unknown attribute.
    error = _err(".function[fiel=src]")
    assert (error.code, error.fixed_query) == (E.SELECTOR_SYNTAX, ".function[file=src]")


def test_nested_selector_pseudo_classes_are_validated() -> None:
    assert _err(".class:not(.function:hott)").code == E.UNKNOWN_PSEUDO_CLASS


def test_error_code_registry_is_closed() -> None:
    with pytest.raises(ValueError, match="unregistered"):
        E.QueryError("UQL_NOT_A_CODE", "x")


def test_error_codes_pinned() -> None:
    assert len(E.ERROR_CODES) == 18


def test_chain_dialect_shares_the_step_owner() -> None:
    result = parse_chain("search('Foo').callers(depth=2).answer(compact=true)")
    assert isinstance(result, Ok)
    assert [(s.name, s.kwargs) for s in result.value] == [
        ("search", {}),
        ("callers", {"depth": 2}),
        ("answer", {"compact": True}),
    ]


def test_chain_dialect_keeps_plain_string_fallback() -> None:
    result = parse_chain("parse query")
    assert isinstance(result, Ok)
    assert [s.name for s in result.value] == ["explore", "related"]
