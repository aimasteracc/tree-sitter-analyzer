"""Boundary coverage for causal-envelope symbol projections."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.cache import _symbol_walker as walker_module
from tree_sitter_analyzer.cache._symbol_walker import (
    _python_dynamic_loader_analysis,
    _SymbolWalker,
)


def test_python_loader_analysis_fails_closed_on_invalid_module() -> None:
    names, complete = _python_dynamic_loader_analysis("if (")

    assert names == frozenset({"__import__", "importlib.import_module"})
    assert complete is False


def test_python_loader_analysis_tracks_module_alias_chains() -> None:
    source = """
import importlib as il
from importlib import import_module, invalidate_caches
loader: object = il.import_module
later = loader
annotation_only: object
"""

    names, complete = _python_dynamic_loader_analysis(source)

    assert names == frozenset(
        {
            "__import__",
            "importlib.import_module",
            "il.import_module",
            "import_module",
            "loader",
            "later",
        }
    )
    assert complete is True


def test_python_loader_analysis_rejects_nested_bindings_and_aliases() -> None:
    source = """
import importlib

def load(positional, /, regular, *items, keyword, **options):
    nested = importlib.import_module
    holder.loader = importlib.import_module
    annotated: object = importlib.import_module
    import importlib as nested_importlib
    from importlib import import_module as nested_load
"""

    names, complete = _python_dynamic_loader_analysis(source)

    assert "importlib.import_module" in names
    assert complete is False


@pytest.mark.parametrize(
    ("language", "node_type", "enclosed"),
    [
        ("python", "class_definition", False),
        ("scala", "identifier", False),
        ("scala", "object_definition", True),
    ],
)
def test_scala_projection_rejects_non_top_level_class_like_nodes(
    language: str, node_type: str, enclosed: bool
) -> None:
    walker = _SymbolWalker("", [], language, None)
    node = SimpleNamespace(type=node_type)

    assert walker._append_scala(node, enclosed) is False


def test_scala_projection_handles_empty_and_present_symbols(monkeypatch) -> None:
    walker = _SymbolWalker("", [], "scala", None)
    node = SimpleNamespace(type="object_definition")
    monkeypatch.setattr(walker_module, "_scala_symbol_from_node", lambda *_: None)

    assert walker._append_scala(node, False) is True
    assert walker.symbols == []

    expected = {"kind": "class", "name": "User"}
    monkeypatch.setattr(walker_module, "_scala_symbol_from_node", lambda *_: expected)
    assert walker._append_scala(node, False) is True
    assert walker.symbols == [expected]


def test_class_projection_covers_empty_fallback_and_parents(monkeypatch) -> None:
    empty_name = SimpleNamespace(type="identifier", start_byte=0, end_byte=0)
    node = SimpleNamespace(
        type="class_definition",
        children=[SimpleNamespace(type="comment"), empty_name],
        start_point=(0, 0),
        end_point=(0, 0),
    )
    walker = _SymbolWalker("", [], "python", None)

    assert walker._class_name_node(node, object()) is not None
    assert walker._class_name_node(node, None) is empty_name
    assert (
        walker._class_name_node(
            SimpleNamespace(children=[SimpleNamespace(type="comment")]), None
        )
        is None
    )
    walker._append_class(node, None)
    assert walker.symbols == []

    monkeypatch.setattr(walker_module, "_node_text", lambda *_: "Child")
    monkeypatch.setattr(walker_module, "_extract_parent_classes", lambda *_: ["Base"])
    monkeypatch.setattr(walker_module, "_python_docstring", lambda *_: None)
    walker._append_class(node, None)
    assert walker.symbols == [
        {
            "kind": "class",
            "name": "Child",
            "line": 1,
            "end_line": 1,
            "language": "python",
            "parents": ["Base"],
        }
    ]
