#!/usr/bin/env python3
"""Kotlin expression-body return types must not claim ``Unit`` (issue #591).

``fun get(key: String) = "legacy"`` used to extract ``return_type="Unit"``.
The expression body infers ``String``; claiming ``Unit`` is actively wrong.

Minimum honest contract (full type inference is a NON-goal, per the
honesty-over-fabrication precedent from #537):

* explicit return type → use it (unchanged)
* block body ``{ ... }`` with no explicit type → ``Unit`` (correct, kept)
* expression body ``= <expr>`` with no explicit type:
  - trivial literal → its pinned type (String / Int / Boolean / Double)
  - anything else → ``""`` (empty = unknown; matches the Go plugin's
    absent-return-type convention in ``_go_common_helpers.extract_return_type``)
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_kotlin

from tree_sitter_analyzer.languages.kotlin_helpers import extract_kotlin_function

# ---------------------------------------------------------------------------
# Helpers (same parse harness as test_kotlin_method_receiver.py)
# ---------------------------------------------------------------------------


def _build_language() -> tree_sitter.Language:
    caps_or_lang = tree_sitter_kotlin.language()
    if hasattr(caps_or_lang, "__class__") and "Language" in str(type(caps_or_lang)):
        return caps_or_lang
    return tree_sitter.Language(caps_or_lang)


def _parse(source: str) -> tree_sitter.Tree:
    lang = _build_language()
    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(lang)
    else:
        parser = tree_sitter.Parser(lang)
    return parser.parse(source.encode("utf-8"))


def _functions(source: str) -> dict[str, object]:
    """Return a name→Function dict parsed from *source*."""
    tree = _parse(source)
    results: dict[str, object] = {}
    src_bytes = source.encode("utf-8")

    def _node_text(n: tree_sitter.Node) -> str:
        return src_bytes[n.start_byte : n.end_byte].decode("utf-8", errors="replace")

    def _visit(node: tree_sitter.Node) -> None:
        if node.type == "function_declaration":
            func = extract_kotlin_function(node, _node_text, "")
            if func:
                results[func.name] = func
        for child in node.children:
            _visit(child)

    _visit(tree.root_node)
    return results


_SRC = """\
fun str() = "legacy"
fun integer() = 42
fun truthy() = true
fun falsy() = false
fun dbl() = 3.14
fun call() = compute()
fun longLit() = 42L
fun nullLit() = null
fun explicit(): String = "x"
fun block() { println("hi") }
fun blockTyped(): Int { return 1 }
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


# ---------------------------------------------------------------------------
# Expression body, non-trivial → "" (unknown), never Unit
# ---------------------------------------------------------------------------


def test_expression_body_call_is_unknown_not_unit() -> None:
    assert _FUNCS["call"].return_type == ""


def test_expression_body_long_suffix_is_unknown() -> None:
    # 42L is a number_literal but NOT an Int; honesty: emit unknown.
    assert _FUNCS["longLit"].return_type == ""


def test_expression_body_null_is_unknown() -> None:
    assert _FUNCS["nullLit"].return_type == ""


# ---------------------------------------------------------------------------
# Unchanged behavior: explicit type and block body
# ---------------------------------------------------------------------------


def test_explicit_return_type_unchanged() -> None:
    assert _FUNCS["explicit"].return_type == "String"


def test_block_body_without_type_stays_unit() -> None:
    assert _FUNCS["block"].return_type == "Unit"


def test_block_body_with_explicit_type_unchanged() -> None:
    assert _FUNCS["blockTyped"].return_type == "Int"


# ---------------------------------------------------------------------------
# Issue #591 reproducer: the exact sample from the report
# ---------------------------------------------------------------------------


def test_abstract_fun_without_body_stays_unit() -> None:
    # No function_body child at all (interface member) → Unit default kept.
    funcs = _functions("interface I { fun render() }")
    assert funcs["render"].return_type == "Unit"


def test_malformed_expression_body_returns_unknown() -> None:
    # Defensive: a function_body holding only '=' (no expression). Real
    # parses turn this into an ERROR node, so drive the helper directly
    # with explicit stub nodes (never MagicMock — unbounded attr chains).
    from tree_sitter_analyzer.languages.kotlin_helpers import (
        _kotlin_expression_body_type,
    )

    class _Stub:
        def __init__(self, type_: str, children: list) -> None:
            self.type = type_
            self.children = children
            self.child_count = len(children)
            self.parent = None

    eq = _Stub("=", [])
    body = _Stub("function_body", [eq])
    fn = _Stub("function_declaration", [body])
    assert _kotlin_expression_body_type(fn, lambda n: "") == ""


def test_issue_591_reproducer_class_method() -> None:
    funcs = _functions(
        """\
class LegacyUserManager {
    fun get(key: String) = "legacy"
}
"""
    )
    assert funcs["get"].return_type == "String"
