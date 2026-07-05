"""Branch-level unit tests for the Go receiver-parsing helpers (#964).

The full-parser tests in ``test_go_bugs_749_750.py`` exercise the common
(AST) path, but several helper branches are only reachable from synthetic
inputs:

* ``_strip_generic_suffix`` — unbalanced brackets, the ``start is None``
  fall-through, the empty-base case, and trailing whitespace.
* ``_extract_receiver_from_text`` — the lightweight fake-node text fallback
  (unnamed receiver, malformed/empty input, no-space type).
* ``_extract_receiver_parts`` — the ``qualified_type`` branch and the
  no-type-found ``return None, None``.
* ``find_receiver_type_go`` / ``_normalize_go_receiver_type_for_graph`` —
  the bracket-depth stripping branches, the pointer strip, and the
  unbalanced/empty fall-throughs.

All assertions pin exact return values (== / is), never loose bounds.
"""

from __future__ import annotations

from typing import Any

from tree_sitter_analyzer.function_extraction import (
    _normalize_go_receiver_type_for_graph,
    find_receiver_type_go,
)
from tree_sitter_analyzer.languages._go_common import (
    _extract_receiver_from_text,
    _extract_receiver_parts,
    _strip_generic_suffix,
    extract_method_receiver,
)


# ---------------------------------------------------------------------------
# Lightweight fake tree-sitter nodes (text-only) for the fallback paths.
# ---------------------------------------------------------------------------
class _FakeNode:
    def __init__(
        self, text: str, ntype: str = "x", children: list[_FakeNode] | None = None
    ) -> None:
        self._text = text
        self.type = ntype
        self.children = children or []

    @property
    def text(self) -> bytes:
        return self._text.encode()


class _FakeMethod:
    """Minimal stand-in for a method_declaration node."""

    def __init__(self, receiver_node: Any) -> None:
        self._receiver = receiver_node
        self.type = "method_declaration"

    def child_by_field_name(self, name: str) -> Any:
        return self._receiver if name == "receiver" else None


def _gnt(node: Any) -> str:
    text = node.text
    return text.decode("utf-8") if isinstance(text, bytes) else str(text)


# ---------------------------------------------------------------------------
# _strip_generic_suffix
# ---------------------------------------------------------------------------
class TestStripGenericSuffix:
    def test_plain_type_unchanged(self) -> None:
        assert _strip_generic_suffix("T") == "T"

    def test_pointer_generic_strips_param(self) -> None:
        assert _strip_generic_suffix("*Stack[T]") == "*Stack"

    def test_two_type_params_stripped(self) -> None:
        assert _strip_generic_suffix("Pair[A, B]") == "Pair"
        assert _strip_generic_suffix("Map[K,V]") == "Map"

    def test_trailing_space_stripped(self) -> None:
        # "T[K] " — trailing whitespace is skipped before the closing ']'.
        assert _strip_generic_suffix("T[K] ") == "T"

    def test_unbalanced_open_bracket_returned_verbatim(self) -> None:
        # "T[" does not end in ']' -> early return of the raw text.
        assert _strip_generic_suffix("T[") == "T["

    def test_only_brackets_yields_none(self) -> None:
        # "[T]" — matching '[' is at index 0, base becomes "" -> None.
        assert _strip_generic_suffix("[T]") is None

    def test_empty_input_yields_none(self) -> None:
        assert _strip_generic_suffix("") is None

    def test_no_bracket_close_only_returns_verbatim(self) -> None:
        # "T]" / "Stack]]" have no '[' at all -> early "[" not in text return.
        assert _strip_generic_suffix("T]") == "T]"
        assert _strip_generic_suffix("Stack]]") == "Stack]]"

    def test_unbalanced_start_none_fallthrough(self) -> None:
        # "T[]]" has '[' and ends in ']' but the reverse scan never returns to
        # depth 0 at the '[' -> ``start is None`` fall-through.
        assert _strip_generic_suffix("T[]]") == "T[]]"


# ---------------------------------------------------------------------------
# _extract_receiver_from_text (the fake-node text fallback)
# ---------------------------------------------------------------------------
class TestExtractReceiverFromText:
    def test_named_pointer_generic(self) -> None:
        assert _extract_receiver_from_text("(p *Stack[T])") == ("p", "*Stack")

    def test_unnamed_pointer_generic(self) -> None:
        # "(*Stack[T])" — no receiver name, type only.
        assert _extract_receiver_from_text("(*Stack[T])") == (None, "*Stack")

    def test_empty_string(self) -> None:
        assert _extract_receiver_from_text("") == (None, None)

    def test_only_parens_whitespace(self) -> None:
        assert _extract_receiver_from_text("(   )") == (None, None)

    def test_without_surrounding_parens(self) -> None:
        assert _extract_receiver_from_text("p *Stack[T]") == ("p", "*Stack")

    def test_single_token_no_space(self) -> None:
        # No space at depth 0 -> falls through to (None, stripped-type).
        assert _extract_receiver_from_text("(noSpaceType)") == (None, "noSpaceType")

    def test_two_param_generic_named(self) -> None:
        assert _extract_receiver_from_text("( s Pair[A, B] )") == ("s", "Pair")


# ---------------------------------------------------------------------------
# extract_method_receiver — drives the fallback + None-receiver branches
# ---------------------------------------------------------------------------
class TestExtractMethodReceiver:
    def test_none_receiver_node(self) -> None:
        assert extract_method_receiver(_FakeMethod(None), _gnt) == (None, None)

    def test_text_fallback_when_no_parameter_declaration_child(self) -> None:
        # receiver node has only non-parameter_declaration children -> fallback.
        rn = _FakeNode("(p *Stack[T])", ntype="parameter_list", children=[])
        assert extract_method_receiver(_FakeMethod(rn), _gnt) == ("p", "*Stack")

    def test_parameter_declaration_qualified_type(self) -> None:
        # child_by_field_name -> a receiver node whose parameter_declaration
        # child carries a qualified_type -> _extract_receiver_parts path.
        qualified = _FakeNode("pkg.T", ntype="qualified_type")
        ident = _FakeNode("s", ntype="identifier")
        param = _FakeNode(
            "s pkg.T", ntype="parameter_declaration", children=[ident, qualified]
        )
        rn = _FakeNode("(s pkg.T)", ntype="parameter_list", children=[param])
        assert extract_method_receiver(_FakeMethod(rn), _gnt) == ("s", "pkg.T")


# ---------------------------------------------------------------------------
# _extract_receiver_parts — direct (qualified_type + no-type-found)
# ---------------------------------------------------------------------------
class TestExtractReceiverParts:
    def test_qualified_type_with_generic_suffix_stripped(self) -> None:
        ident = _FakeNode("s", ntype="identifier")
        gen = _FakeNode("pkg.T[K]", ntype="generic_type")
        param = _FakeNode(
            "s pkg.T[K]", ntype="parameter_declaration", children=[ident, gen]
        )
        assert _extract_receiver_parts(param, _gnt) == ("s", "pkg.T")

    def test_no_recognized_type_returns_none_none(self) -> None:
        # Only an identifier, no type node -> receiver_type stays None.
        ident = _FakeNode("s", ntype="identifier")
        param = _FakeNode("s", ntype="parameter_declaration", children=[ident])
        assert _extract_receiver_parts(param, _gnt) == (None, None)

    def test_unrelated_child_is_skipped(self) -> None:
        # A non-identifier, non-type child (e.g. a comment) is skipped, then the
        # real type is picked up -> exercises the type-check ``in`` False branch.
        comment = _FakeNode("/*x*/", ntype="comment")
        ident = _FakeNode("s", ntype="identifier")
        ti = _FakeNode("Counter", ntype="type_identifier")
        param = _FakeNode(
            "s Counter",
            ntype="parameter_declaration",
            children=[comment, ident, ti],
        )
        assert _extract_receiver_parts(param, _gnt) == ("s", "Counter")


# ---------------------------------------------------------------------------
# _normalize_go_receiver_type_for_graph
# ---------------------------------------------------------------------------
class TestNormalizeReceiverTypeForGraph:
    def test_none_input(self) -> None:
        assert _normalize_go_receiver_type_for_graph(None) is None

    def test_empty_string(self) -> None:
        assert _normalize_go_receiver_type_for_graph("") is None

    def test_pointer_generic_strips_pointer_and_param(self) -> None:
        # graph normalization also strips the leading '*'.
        assert _normalize_go_receiver_type_for_graph("*Stack[T]") == "Stack"

    def test_two_type_params(self) -> None:
        assert _normalize_go_receiver_type_for_graph("Map[K,V]") == "Map"

    def test_plain_type(self) -> None:
        assert _normalize_go_receiver_type_for_graph("T") == "T"

    def test_pointer_only(self) -> None:
        assert _normalize_go_receiver_type_for_graph("*T") == "T"

    def test_only_brackets_yields_none(self) -> None:
        # "[T]" -> after stripping, base is empty -> None.
        assert _normalize_go_receiver_type_for_graph("[T]") is None

    def test_trailing_space(self) -> None:
        assert _normalize_go_receiver_type_for_graph("Stack[T] ") == "Stack"

    def test_unbalanced_open_bracket_returns_base(self) -> None:
        # "Unbal[T" does not end in ']' -> base returned verbatim.
        assert _normalize_go_receiver_type_for_graph("Unbal[T") == "Unbal[T"

    def test_no_bracket_close_only_returns_base(self) -> None:
        # "Stack]" has no '[' -> early "[" not in base return.
        assert _normalize_go_receiver_type_for_graph("Stack]") == "Stack]"

    def test_pointer_only_yields_none(self) -> None:
        # "*" -> base empty after lstrip('*') -> None.
        assert _normalize_go_receiver_type_for_graph("*") is None

    def test_unbalanced_start_none_fallthrough(self) -> None:
        # "T[]]" has '[' and ends in ']' but the reverse scan never balances
        # to depth 0 -> final ``return base``.
        assert _normalize_go_receiver_type_for_graph("T[]]") == "T[]]"


# ---------------------------------------------------------------------------
# find_receiver_type_go — non-method node + None guards
# ---------------------------------------------------------------------------
class TestFindReceiverTypeGo:
    def test_none_node(self) -> None:
        assert find_receiver_type_go(None) is None

    def test_non_method_node(self) -> None:
        assert (
            find_receiver_type_go(_FakeNode("x", ntype="function_declaration")) is None
        )

    def test_no_receiver_field(self) -> None:
        assert find_receiver_type_go(_FakeMethod(None)) is None

    def test_qualified_type_receiver(self) -> None:
        # parameter_declaration with a direct qualified_type sub -> normalized.
        qualified = _FakeNode("pkg.T", ntype="qualified_type")
        param = _FakeNode(
            "s pkg.T", ntype="parameter_declaration", children=[qualified]
        )
        rn = _FakeNode("(s pkg.T)", ntype="parameter_list", children=[param])
        assert find_receiver_type_go(_FakeMethod(rn)) == "pkg.T"

    def test_generic_pointer_receiver_strips_pointer_and_param(self) -> None:
        ptr = _FakeNode("*Stack[T]", ntype="pointer_type")
        param = _FakeNode("s *Stack[T]", ntype="parameter_declaration", children=[ptr])
        rn = _FakeNode("(s *Stack[T])", ntype="parameter_list", children=[param])
        assert find_receiver_type_go(_FakeMethod(rn)) == "Stack"

    def test_nested_leaf_type_identifier(self) -> None:
        # sub node is not itself a type, but has a type_identifier leaf.
        leaf = _FakeNode("Counter", ntype="type_identifier")
        wrapper = _FakeNode("Counter", ntype="some_wrapper", children=[leaf])
        param = _FakeNode(
            "c Counter", ntype="parameter_declaration", children=[wrapper]
        )
        rn = _FakeNode("(c Counter)", ntype="parameter_list", children=[param])
        assert find_receiver_type_go(_FakeMethod(rn)) == "Counter"

    def test_no_parameter_declaration_returns_none(self) -> None:
        rn = _FakeNode("()", ntype="parameter_list", children=[])
        assert find_receiver_type_go(_FakeMethod(rn)) is None

    def test_parameter_declaration_without_type_returns_none(self) -> None:
        # parameter_declaration whose subs are neither types nor carry type
        # leaves -> type_text stays None -> normalize(None) -> None -> next loop.
        only_ident = _FakeNode("s", ntype="identifier")
        param = _FakeNode("s", ntype="parameter_declaration", children=[only_ident])
        rn = _FakeNode("(s)", ntype="parameter_list", children=[param])
        assert find_receiver_type_go(_FakeMethod(rn)) is None

    def test_non_matching_leaf_is_skipped(self) -> None:
        # First sub has only a non-type leaf (skipped), second sub is the type.
        bad_leaf = _FakeNode("x", ntype="comment")
        wrapper = _FakeNode("x", ntype="some_wrapper", children=[bad_leaf])
        ti = _FakeNode("Counter", ntype="type_identifier")
        param = _FakeNode(
            "c Counter",
            ntype="parameter_declaration",
            children=[wrapper, ti],
        )
        rn = _FakeNode("(c Counter)", ntype="parameter_list", children=[param])
        assert find_receiver_type_go(_FakeMethod(rn)) == "Counter"

    def test_first_param_decl_none_then_second_resolves(self) -> None:
        # First parameter_declaration yields no type (normalized None) -> the
        # outer loop continues to the second, which resolves.
        empty_param = _FakeNode("", ntype="parameter_declaration", children=[])
        ti = _FakeNode("Counter", ntype="type_identifier")
        good_param = _FakeNode(
            "c Counter", ntype="parameter_declaration", children=[ti]
        )
        rn = _FakeNode(
            "(c Counter)",
            ntype="parameter_list",
            children=[empty_param, good_param],
        )
        assert find_receiver_type_go(_FakeMethod(rn)) == "Counter"
