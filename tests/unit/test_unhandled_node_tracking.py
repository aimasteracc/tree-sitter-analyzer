"""Tests for the walker's terminal fall-through observability.

Every silent data-loss defect in the symbol walker's history (extractor
versions v3..v17) had one shape: a node type nobody had listed in a set
reached the end of the dispatch chain and was dropped without a trace.
``cache/unhandled_nodes`` is the feedback channel that makes that visible;
these tests pin its contract.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.cache import unhandled_nodes as un
from tree_sitter_analyzer.cache.extraction import _extract_symbols
from tree_sitter_analyzer.core.parser import Parser


def _symbols(source: str, language: str):
    result = Parser().parse_code(source, language)
    assert result.success and result.tree is not None
    return _extract_symbols(result.tree, source, language)


# ---------------------------------------------------------------------------
# Default-off contract
# ---------------------------------------------------------------------------


def test_tracking_is_off_by_default() -> None:
    """The hot path must not pay for diagnostics nobody asked for."""
    un.reset_unhandled()
    _symbols("def f():\n    return 1\n", "python")
    assert un.get_unhandled() == {}


def test_tracking_context_restores_previous_state() -> None:
    before = un.ENABLED
    with un.tracking_enabled():
        assert un.ENABLED is True
    assert un.ENABLED is before


def test_reset_clears_counts() -> None:
    with un.tracking_enabled():
        _symbols("x = [1, 2, 3]\n", "python")
        assert un.get_unhandled()
        un.reset_unhandled()
        assert un.get_unhandled() == {}


# ---------------------------------------------------------------------------
# Recording behaviour
# ---------------------------------------------------------------------------


def test_unhandled_nodes_are_recorded_when_enabled() -> None:
    with un.tracking_enabled():
        _symbols("x = [1, 2, 3]\n", "python")
        recorded = un.get_unhandled()
    assert recorded, "expected the walker to report unhandled node types"
    assert all(lang == "python" for lang, _ in recorded)


def test_handled_node_types_are_not_recorded() -> None:
    """A node the walker turns into a symbol must not appear as unhandled."""
    with un.tracking_enabled():
        payload = _symbols("def handled():\n    return 1\n", "python")
        recorded = {node_type for _, node_type in un.get_unhandled()}

    assert any(s.get("name") == "handled" for s in payload["symbols"])
    assert "function_definition" not in recorded


def test_anonymous_nodes_are_not_recorded() -> None:
    """Punctuation and keyword tokens are noise, not missing coverage."""
    with un.tracking_enabled():
        _symbols("def f(a, b):\n    return a\n", "python")
        recorded = {node_type for _, node_type in un.get_unhandled()}
    for token in ("def", "(", ")", ":", ","):
        assert token not in recorded


# ---------------------------------------------------------------------------
# Triage filter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "node_type",
    [
        "property_declaration",
        "enum_item",
        "mod_item",
        "namespace_definition",
        "const_spec",
        "field_declaration",
    ],
)
def test_declaration_like_accepts_real_declarations(node_type: str) -> None:
    assert un.is_declaration_like(node_type)


@pytest.mark.parametrize(
    "node_type",
    [
        "identifier",
        "comment",
        "string_literal",
        "integer_literal",
        "abstract_pointer_declarator",
        "parameter_declaration",
        "type_declaration_list",
        "attribute_declaration",
        "storage_class_specifier",
    ],
)
def test_declaration_like_rejects_noise(node_type: str) -> None:
    assert not un.is_declaration_like(node_type)


def test_get_suspicious_is_a_subset_of_get_unhandled() -> None:
    with un.tracking_enabled():
        _symbols("class C:\n    x = 1\n\n    def m(self):\n        pass\n", "python")
        everything = un.get_unhandled()
        suspicious = un.get_suspicious()

    assert set(suspicious) <= set(everything)
    assert all(un.is_declaration_like(nt) for _, nt in suspicious)


def test_suspicious_filter_removes_the_bulk_of_the_noise() -> None:
    """The report must be short enough for a human to actually read."""
    src = (
        "import os\n"
        "from typing import Any\n\n"
        "CONST = 1\n\n"
        "class Widget:\n"
        "    attr: int = 0\n\n"
        "    def method(self, value: Any) -> str:\n"
        "        local = value + 1\n"
        "        return str(local)\n"
    )
    with un.tracking_enabled():
        _symbols(src, "python")
        everything = un.get_unhandled()
        suspicious = un.get_suspicious()

    assert len(everything) > len(suspicious)


# ---------------------------------------------------------------------------
# The defect class this exists to catch
# ---------------------------------------------------------------------------


def test_rust_enum_item_surfaces_as_suspicious() -> None:
    """`enum Direction` is dropped by the index — the tool must say so.

    ``_ENUM_LIKE`` carries Java's ``enum_declaration`` but not Rust's
    ``enum_item``, so Rust enums never reach ast_symbol_rows. This test
    documents the live gap and will fail loudly once it is closed, at
    which point the assertion should be inverted rather than deleted.
    """
    with un.tracking_enabled():
        payload = _symbols("enum Direction { North, South }\n", "rust")
        suspicious = {nt for _, nt in un.get_suspicious()}

    names = {s.get("name") for s in payload["symbols"]}
    assert "Direction" not in names, (
        "Rust enums are now indexed — flip this test to assert coverage"
    )
    assert "enum_item" in suspicious
