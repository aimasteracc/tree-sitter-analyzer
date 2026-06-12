#!/usr/bin/env python3
"""Scala expression-body defs must not claim ``Unit`` (issue #594).

``def get(key: String) = "legacy"`` used to extract ``return_type="Unit"``.
The expression body infers ``String``; claiming ``Unit`` is actively wrong.
Same family as the Kotlin fix for #591/#593 — the contract mirrors
``test_kotlin_expression_body_return.py`` exactly:

* explicit return type → use it (unchanged)
* block body ``{ ... }`` with no explicit type → ``Unit`` (correct, kept)
* expression body ``= <expr>`` with no explicit type:
  - trivial literal → its pinned type (String / Int / Boolean / Double)
  - anything else (calls, suffixed/hex numbers, null, blocks) → ``""``
    (empty = unknown; matches the Go plugin's absent-return-type
    convention in ``_go_common_helpers.extract_return_type``)

Live-verified Scala node shapes (tree-sitter-scala): expression body is a
direct ``=`` child followed by the expression node; ``string`` covers both
``"x"`` and raw ``\"\"\"x\"\"\"``; ``integer_literal`` covers ``42``/``42L``/
``0xFF``; floats are ``floating_point_literal``.
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_scala

from tree_sitter_analyzer.languages.scala_plugin import ScalaElementExtractor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(source: str) -> tree_sitter.Tree:
    lang = tree_sitter.Language(tree_sitter_scala.language())
    parser = tree_sitter.Parser(lang)
    return parser.parse(source.encode("utf-8"))


def _functions(source: str) -> dict[str, object]:
    """Return a name→Function dict parsed from *source*."""
    extractor = ScalaElementExtractor()
    return {fn.name: fn for fn in extractor.extract_functions(_parse(source), source)}


_SRC = """\
def str() = "legacy"
def integer = 42
def truthy = true
def falsy = false
def dbl = 3.14
def call = compute()
def longLit = 42L
def hexLit = 0xFF
def nullLit = null
def exprBlock = { 1 }
def explicit: String = "x"
def block() { println("hi") }
def blockTyped(): Int = { 1 }
"""

_FUNCS = _functions(_SRC)


# ---------------------------------------------------------------------------
# Expression body, trivial literal → pinned literal type
# ---------------------------------------------------------------------------


def test_expression_body_string_literal_is_string() -> None:
    assert _FUNCS["str"].return_type == "String"


def test_expression_body_integer_literal_is_int() -> None:
    assert _FUNCS["integer"].return_type == "Int"


def test_expression_body_true_is_boolean() -> None:
    assert _FUNCS["truthy"].return_type == "Boolean"


def test_expression_body_false_is_boolean() -> None:
    assert _FUNCS["falsy"].return_type == "Boolean"


def test_expression_body_float_literal_is_double() -> None:
    assert _FUNCS["dbl"].return_type == "Double"


def test_expression_body_raw_string_is_string() -> None:
    # Codex P2 on the Kotlin twin (#593): raw/multiline strings are the
    # same trivial String case. In Scala both share the ``string`` node.
    funcs = _functions('def raw = """x"""')
    assert funcs["raw"].return_type == "String"


# ---------------------------------------------------------------------------
# Expression body, non-trivial → "" (unknown), never Unit
# ---------------------------------------------------------------------------


def test_expression_body_call_is_unknown_not_unit() -> None:
    assert _FUNCS["call"].return_type == ""


def test_expression_body_long_suffix_is_unknown() -> None:
    # 42L is an integer_literal but NOT an Int; honesty: emit unknown.
    assert _FUNCS["longLit"].return_type == ""


def test_expression_body_hex_literal_is_unknown() -> None:
    assert _FUNCS["hexLit"].return_type == ""


def test_expression_body_null_is_unknown() -> None:
    assert _FUNCS["nullLit"].return_type == ""


def test_expression_body_block_expr_is_unknown() -> None:
    # ``def f = { 1 }`` — expression body whose expr is a block; not a
    # trivial literal, so unknown (and definitely not Unit).
    assert _FUNCS["exprBlock"].return_type == ""


# ---------------------------------------------------------------------------
# Unchanged behavior: explicit type and block body
# ---------------------------------------------------------------------------


def test_explicit_return_type_unchanged() -> None:
    assert _FUNCS["explicit"].return_type == "String"


def test_block_body_without_type_stays_unit() -> None:
    # Scala 2 procedure syntax ``def block() { ... }`` → Unit (correct).
    assert _FUNCS["block"].return_type == "Unit"


def test_block_body_with_explicit_type_unchanged() -> None:
    assert _FUNCS["blockTyped"].return_type == "Int"


def test_abstract_def_without_body_stays_unit() -> None:
    # No ``=`` and no block (trait member) → Unit default kept.
    funcs = _functions("trait I { def render(): Unit; def bare() }")
    assert funcs["bare"].return_type == "Unit"


# ---------------------------------------------------------------------------
# Issue #594 reproducer: the exact sample from the report
# ---------------------------------------------------------------------------


def test_issue_594_reproducer_class_method() -> None:
    funcs = _functions(
        """\
class LegacyUserManager {
  def get(key: String) = "legacy"
}
"""
    )
    assert funcs["get"].return_type == "String"


def test_malformed_expression_body_returns_unknown() -> None:
    # Defensive: ``=`` as the last child (no expression after it). Real
    # parses turn this into an ERROR node, so drive the helper directly
    # with explicit stub nodes (never MagicMock — unbounded attr chains).
    class _Stub:
        def __init__(self, type_: str, children: list) -> None:
            self.type = type_
            self.children = children
            self.child_count = len(children)
            self.parent = None

    eq = _Stub("=", [])
    fn = _Stub("function_definition", [_Stub("def", []), _Stub("identifier", []), eq])
    extractor = ScalaElementExtractor()
    assert extractor._scala_expression_body_type(fn) == ""
