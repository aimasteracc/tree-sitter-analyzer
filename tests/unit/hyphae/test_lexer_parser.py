"""Tests for the Hyphae lexer and parser."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.hyphae.ast import (
    AttributeSelector,
    Combined,
    SelectorList,
    SimpleSelector,
)
from tree_sitter_analyzer.hyphae.lexer import tokenize
from tree_sitter_analyzer.hyphae.parser import HyphaeSyntaxError, parse


def _types(text: str) -> list[str]:
    return [t.type for t in tokenize(text)]


def test_lexer_prefix_symbols_absorb_identifier() -> None:
    toks = tokenize("#login")
    assert toks[0].type == "HASH" and toks[0].value == "login"
    assert tokenize(".function")[0] == type(toks[0])("DOT", "function")
    assert tokenize(":calls")[0].type == "COLON"
    assert tokenize(":calls")[0].value == "calls"


def test_lexer_path_ident_keeps_dots_and_slashes() -> None:
    toks = tokenize("[file=src/lib.rs]")
    # The path value is one IDENT, not split on '.' or '/'.
    idents = [t.value for t in toks if t.type == "IDENT"]
    assert "src/lib.rs" in idents


def test_lexer_hash_name_allows_hyphen() -> None:
    assert tokenize("#my-symbol")[0].value == "my-symbol"


def test_lexer_structural_tokens() -> None:
    assert _types("#a > #b") == ["HASH", "WS", "GT", "WS", "HASH", "EOF"]
    assert "TILDE" in _types("#a ~ #b")
    assert "NUMBER" in _types(":nth-child(2)")


def test_parse_simple_name() -> None:
    sl = parse("#IndexShard")
    assert sl == SelectorList((SimpleSelector(base=("name", "IndexShard")),))


def test_parse_kind_and_universal() -> None:
    assert parse(".method").selectors[0].base == ("kind", "method")
    assert parse("*").selectors[0].base == ("universal", "")


def test_parse_pseudo_calls_with_nested_selector() -> None:
    sl = parse(".method:calls(#IndexShard)")
    simple = sl.selectors[0]
    assert simple.base == ("kind", "method")
    assert len(simple.pseudo_classes) == 1
    pc = simple.pseudo_classes[0]
    assert pc.name == "calls"
    assert isinstance(pc.arg, SelectorList)
    assert pc.arg.selectors[0].base == ("name", "IndexShard")


def test_parse_attribute_filter() -> None:
    sl = parse(".function[file=src/lib.rs]")
    attrs = sl.selectors[0].attributes
    assert attrs == (AttributeSelector(name="file", value="src/lib.rs"),)


def test_parse_nth_child_number_arg() -> None:
    pc = parse(".method:nth-child(2)").selectors[0].pseudo_classes[0]
    assert pc.name == "nth-child" and pc.arg == 2


def test_parse_in_path_arg() -> None:
    pc = parse(".function:in(tests/)").selectors[0].pseudo_classes[0]
    assert pc.name == "in" and pc.arg == "tests/"


def test_parse_child_combinator() -> None:
    sl = parse("#Foo > .method")
    sel = sl.selectors[0]
    assert isinstance(sel, Combined)
    assert sel.combinator == ">"
    assert sel.left.base == ("name", "Foo")
    assert sel.right.base == ("kind", "method")


def test_parse_descendant_combinator() -> None:
    sel = parse(".struct .method").selectors[0]
    assert isinstance(sel, Combined)
    assert sel.combinator == " "


def test_parse_selector_list_union() -> None:
    sl = parse("#A, #B")
    assert len(sl.selectors) == 2
    assert sl.selectors[0].base == ("name", "A")
    assert sl.selectors[1].base == ("name", "B")


def test_parse_not_pseudo() -> None:
    pc = parse(".function:not(#logout)").selectors[0].pseudo_classes[0]
    assert pc.name == "not"
    assert isinstance(pc.arg, SelectorList)


def test_parse_error_on_garbage() -> None:
    with pytest.raises(HyphaeSyntaxError):
        parse("> #orphan")


# ===========================================================================
# Step 10: DepthQuantifier parsing tests (hyphae/parser.py lines 185-201)
# ===========================================================================

def test_parse_depth_quantifier_exact() -> None:
    """{2} sets depth_min == depth_max == 2."""
    pc = parse(".method:calls(#x){2}").selectors[0].pseudo_classes[0]
    assert pc.depth_min == 2
    assert pc.depth_max == 2


def test_parse_depth_quantifier_range() -> None:
    """{1,3} sets depth_min=1 and depth_max=3."""
    pc = parse(".method:calls(#x){1,3}").selectors[0].pseudo_classes[0]
    assert pc.depth_min == 1
    assert pc.depth_max == 3


def test_parse_depth_quantifier_single_clamps_to_max() -> None:
    """{100} clamps to _MAX_DEPTH_QUANTIFIER (50)."""
    pc = parse(".method:calls(#x){100}").selectors[0].pseudo_classes[0]
    assert pc.depth_min == 50
    assert pc.depth_max == 50


def test_parse_depth_quantifier_range_clamps_max() -> None:
    """{1,200} clamps the upper bound to 50."""
    pc = parse(".method:calls(#x){1,200}").selectors[0].pseudo_classes[0]
    assert pc.depth_min == 1
    assert pc.depth_max == 50


def test_parse_depth_quantifier_range_on_callees() -> None:
    """{2,4} works on :callees pseudo-class."""
    pc = parse(".function:callees(#y){2,4}").selectors[0].pseudo_classes[0]
    assert pc.depth_min == 2
    assert pc.depth_max == 4


def test_parse_depth_quantifier_on_in_pseudo() -> None:
    """:in(src){1,2} — parser stores depth values on PseudoClass (evaluator ignores them)."""
    pc = parse(".function:in(src){1,2}").selectors[0].pseudo_classes[0]
    assert pc.name == "in"
    # The parser stores depth quantifiers on any pseudo-class; values are set.
    assert pc.depth_min == 1
    assert pc.depth_max == 2
