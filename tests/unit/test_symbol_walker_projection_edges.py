"""Boundary coverage for causal-envelope symbol projections."""

from __future__ import annotations

import ast
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.cache import _symbol_walker as walker_module
from tree_sitter_analyzer.cache._symbol_walker import (
    _cpp_code_mask,
    _python_dynamic_loader_analysis,
    _python_module_scope_statements,
    _SymbolWalker,
    _walk_for_symbols,
)


@pytest.mark.parametrize(
    ("source", "visible"),
    [
        ("// comment", ""),
        ("// comment\nx", "\nx"),
        ('R"(unterminated', ""),
        ('R"12345678901234567(payload)', "R"),
        ('"a\\"b"x', "x"),
    ],
)
def test_cpp_code_mask_excludes_comments_and_literals(
    source: str, visible: str
) -> None:
    mask = _cpp_code_mask(source)

    assert (
        "".join(char for char, is_code in zip(source, mask, strict=True) if is_code)
        == visible
    )


def test_python_loader_analysis_fails_closed_on_invalid_module() -> None:
    names, complete = _python_dynamic_loader_analysis("if (")

    assert names == frozenset(
        {"__import__", "builtins.__import__", "importlib.import_module"}
    )
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
            "builtins.__import__",
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
    "body",
    [
        "for loader in values:\n        loader('pkg.util')",
        "try:\n        pass\n    except Exception as loader:\n        loader('pkg.util')",
        "if (nested := importlib.import_module):\n        nested('pkg.util')",
    ],
)
def test_python_loader_analysis_rejects_additional_lexical_bindings(
    body: str,
) -> None:
    source = (
        "import importlib\n"
        "loader = importlib.import_module\n"
        "def load(values):\n"
        f"    {body}\n"
    )

    _names, complete = _python_dynamic_loader_analysis(source)

    assert complete is False


def test_python_loader_analysis_discovers_module_control_flow_alias() -> None:
    source = """
def load_plugin():
    return load("pkg.util")

if enabled:
    from importlib import import_module as load
"""

    names, complete = _python_dynamic_loader_analysis(source)

    assert "load" in names
    assert complete is True


def test_python_loader_analysis_rejects_module_rebinding() -> None:
    source = """
from importlib import import_module as load
load = fake
load("pkg.util")
"""

    names, complete = _python_dynamic_loader_analysis(source)

    assert "load" in names
    assert complete is False


@pytest.mark.parametrize(
    "rebind",
    [
        "from helpers import load",
        "def load():\n    pass",
        "class load:\n    pass",
        "del load",
    ],
)
def test_python_loader_analysis_rejects_nonassignment_rebinding(
    rebind: str,
) -> None:
    source = (
        f"from importlib import import_module as load\n{rebind}\nload('pkg.util')\n"
    )

    names, complete = _python_dynamic_loader_analysis(source)

    assert "load" in names
    assert complete is False


def test_python_loader_analysis_tracks_builtins_alias() -> None:
    names, complete = _python_dynamic_loader_analysis(
        "import builtins as runtime\nruntime.__import__('pkg.util')\n"
    )

    assert "runtime.__import__" in names
    assert complete is True


@pytest.mark.parametrize(
    "expression",
    [
        "callback = lambda load: load('pkg.util')",
        "results = [load('pkg.util') for load in loaders]",
    ],
)
def test_python_loader_analysis_rejects_expression_scope_shadowing(
    expression: str,
) -> None:
    source = f"from importlib import import_module as load\n{expression}\n"

    names, complete = _python_dynamic_loader_analysis(source)

    assert "load" in names
    assert complete is False


def test_module_scope_statement_walk_skips_nested_function_body() -> None:
    module = ast.parse("if enabled:\n    def nested():\n        import importlib\n")

    statements = _python_module_scope_statements(module)

    assert [type(statement) for statement in statements] == [ast.If, ast.FunctionDef]


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


def test_collect_node_stops_after_scala_projection(monkeypatch) -> None:
    expected = {"kind": "object", "name": "Registry"}
    monkeypatch.setattr(walker_module, "_scala_symbol_from_node", lambda *_: expected)
    node = SimpleNamespace(
        type="object_definition", child_by_field_name=lambda _name: None
    )
    walker = _SymbolWalker("", [], "scala", None)

    walker._collect_node(node, 0, False)

    assert walker.symbols == [expected]


class _TextNode:
    def __init__(self, node_type: str, source: str) -> None:
        self.type = node_type
        self.start_byte = 0
        self.end_byte = len(source.encode())
        self.start_point = (0, 0)
        self.end_point = (0, len(source))


def test_python_loader_assignment_rejects_invalid_syntax() -> None:
    source = "if ("
    walker = _SymbolWalker(source, [], "python", None)

    assert (
        walker._append_python_loader_assignment(_TextNode("assignment", source))
        is False
    )


def test_python_loader_assignment_rejects_multiple_statements() -> None:
    source = "first = importlib.import_module\nsecond = first"
    walker = _SymbolWalker(source, [], "python", None)

    assert (
        walker._append_python_loader_assignment(_TextNode("assignment", source))
        is False
    )


def test_python_loader_assignment_accepts_annotated_alias() -> None:
    source = "loader: object = importlib.import_module"
    walker = _SymbolWalker(source, [], "python", None)

    assert (
        walker._append_python_loader_assignment(
            _TextNode("annotated_assignment", source)
        )
        is True
    )


def test_python_loader_assignment_rejects_annotation_without_value() -> None:
    source = "loader: object"
    walker = _SymbolWalker(source, [], "python", None)

    assert (
        walker._append_python_loader_assignment(
            _TextNode("annotated_assignment", source)
        )
        is False
    )


class _FieldNode(_TextNode):
    def __init__(
        self, node_type: str, source: str, fields: dict[str, _TextNode]
    ) -> None:
        super().__init__(node_type, source)
        self.fields = fields

    def child_by_field_name(self, name: str):
        return self.fields.get(name)


def test_java_reflection_rejects_missing_name() -> None:
    source = "forName()"
    node = _FieldNode(
        "method_invocation", source, {"arguments": _TextNode("arguments", source)}
    )

    assert (
        _SymbolWalker(source, [], "java", None)._append_java_reflective_load(node)
        is False
    )


def test_java_reflection_rejects_other_method_name() -> None:
    source = "load()"
    node = _FieldNode(
        "method_invocation",
        source,
        {
            "name": _TextNode("identifier", "load"),
            "arguments": _TextNode("arguments", source),
        },
    )

    assert (
        _SymbolWalker(source, [], "java", None)._append_java_reflective_load(node)
        is False
    )


def test_include_next_projection_ignores_other_preprocessor_calls() -> None:
    source = "#pragma once"
    node = _TextNode("preproc_call", source)

    assert _SymbolWalker(source, [], "cpp", None)._append_include_next(node) is False


def test_historical_walk_wrapper_delegates_to_walker() -> None:
    node = SimpleNamespace(
        type="comment", children=[], child_by_field_name=lambda _name: None
    )
    symbols: list[dict] = []

    _walk_for_symbols(node, "", symbols, "unknown")

    assert symbols == []


def test_symbol_walk_records_depth_truncation() -> None:
    truncated = [False]
    walker = _SymbolWalker("", [], "unknown", truncated)

    walker.walk(object(), depth=10_000)

    assert truncated == [True]


def test_symbol_walk_without_truncation_sink_stops_cleanly() -> None:
    walker = _SymbolWalker("", [], "unknown", None)

    walker.walk(object(), depth=10_000)

    assert walker.symbols == []


def test_php_constant_projection_appends_extracted_constants(monkeypatch) -> None:
    expected = {"kind": "constant", "name": "LIMIT"}
    monkeypatch.setattr(walker_module, "_php_constants", lambda *_: [expected])
    node = SimpleNamespace(type="const_declaration")
    walker = _SymbolWalker("", [], "php", None)

    walker._append_constant(node, None, False)

    assert walker.symbols == [expected]


def test_go_constant_projection_appends_extracted_constants(monkeypatch) -> None:
    expected = {"kind": "constant", "name": "Limit"}
    monkeypatch.setattr(walker_module, "_go_package_constants", lambda *_: [expected])
    node = SimpleNamespace(type="const_declaration")
    walker = _SymbolWalker("", [], "go", None)

    walker._append_constant(node, None, False)

    assert walker.symbols == [expected]


def test_rust_constant_projection_appends_named_constant() -> None:
    source = "LIMIT"
    name = _TextNode("identifier", source)
    node = SimpleNamespace(
        type="const_item", start_point=(0, 0), end_point=(0, len(source))
    )
    walker = _SymbolWalker(source, [], "rust", None)

    walker._append_constant(node, name, False)

    assert walker.symbols == [
        {
            "kind": "constant",
            "name": "LIMIT",
            "line": 1,
            "end_line": 1,
            "language": "rust",
        }
    ]


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
