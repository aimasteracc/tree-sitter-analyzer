"""Focused coverage for SQL function extraction helpers."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages.sql_plugin.function_extractor import (
    extract_legacy_functions,
    extract_sql_functions_enhanced,
)
from tree_sitter_analyzer.models import Function, SQLFunction


@dataclass
class FakeNode:
    type: str
    text: str = ""
    children: list["FakeNode"] = field(default_factory=list)
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (0, 0)


def _walk(node: FakeNode) -> Iterator[FakeNode]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _node_text(node: FakeNode) -> str:
    return node.text


def test_extract_sql_functions_enhanced_from_source_text() -> None:
    source_code = """\
CREATE FUNCTION calc_bonus(salary DECIMAL(10,2)) RETURNS DECIMAL(10,2)
BEGIN
    -- comment lines should not close the function
    RETURN salary * 0.1;
END;
"""
    sql_elements: list[Any] = []

    extract_sql_functions_enhanced(
        FakeNode("program"),
        lambda _node: iter(()),
        _node_text,
        source_code,
        sql_elements,
    )

    functions = [
        element for element in sql_elements if isinstance(element, SQLFunction)
    ]
    assert len(functions) == 1
    assert functions[0].name == "calc_bonus"
    assert functions[0].return_type == "DECIMAL(10,2)"
    assert [parameter.name for parameter in functions[0].parameters] == ["salary"]


def test_extract_sql_functions_enhanced_skips_invalid_identifier() -> None:
    sql_elements: list[Any] = []

    extract_sql_functions_enhanced(
        FakeNode("program"),
        lambda _node: iter(()),
        _node_text,
        "CREATE FUNCTION select() RETURNS INT\nBEGIN\nRETURN 1;\nEND;",
        sql_elements,
    )

    assert not [element for element in sql_elements if isinstance(element, SQLFunction)]


def test_extract_sql_functions_enhanced_uses_ast_fallback() -> None:
    identifier = FakeNode("identifier", text="from_ast")
    object_reference = FakeNode("object_reference", children=[identifier])
    function_node = FakeNode(
        "create_function",
        text="CREATE FUNCTION from_ast() RETURNS INT BEGIN RETURN 1; END;",
        children=[object_reference],
        start_point=(4, 0),
        end_point=(4, 56),
    )
    sql_elements: list[Any] = []

    extract_sql_functions_enhanced(
        function_node,
        _walk,
        _node_text,
        "",
        sql_elements,
    )

    functions = [
        element for element in sql_elements if isinstance(element, SQLFunction)
    ]
    assert len(functions) == 1
    assert functions[0].name == "from_ast"
    assert functions[0].start_line == 5


def test_extract_legacy_functions_uses_children_and_text_fallback() -> None:
    child_named = FakeNode(
        "create_function",
        text="ignored",
        children=[
            FakeNode(
                "object_reference",
                children=[FakeNode("identifier", text="from_child")],
            )
        ],
        start_point=(1, 0),
        end_point=(2, 0),
    )
    text_named = FakeNode(
        "create_function",
        text="CREATE FUNCTION from_text() RETURNS INT BEGIN RETURN 1; END;",
        start_point=(5, 0),
        end_point=(5, 56),
    )
    root = FakeNode("program", children=[child_named, text_named])
    functions: list[Function] = []

    extract_legacy_functions(root, functions, _walk, _node_text)

    assert [function.name for function in functions] == ["from_child", "from_text"]
