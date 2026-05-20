"""Direct coverage for SQL procedure extraction helpers."""

from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages.sql_plugin.procedure_extractor import (
    _extract_procedure_dependencies,
    extract_legacy_procedures,
    extract_procedure_parameters,
    extract_sql_procedures,
)
from tree_sitter_analyzer.models import Function, SQLParameter, SQLProcedure


@dataclass
class FakePoint:
    row: int
    column: int = 0

    def __getitem__(self, index: int) -> int:
        return (self.row, self.column)[index]


@dataclass
class FakeNode:
    type: str
    text: str = ""
    children: list["FakeNode"] = field(default_factory=list)
    start_point: FakePoint = field(default_factory=lambda: FakePoint(0))
    end_point: FakePoint = field(default_factory=lambda: FakePoint(0))


def _traverse(node: FakeNode):
    yield node
    for child in node.children:
        yield from _traverse(child)


def _node_text(node: FakeNode) -> str:
    return node.text


def test_extract_sql_procedures_from_source_lines() -> None:
    root = FakeNode("program")
    sql = """CREATE PROCEDURE refresh_user(IN user_id INT, OUT total DECIMAL(10,2))
BEGIN
    SELECT COUNT(*) INTO total FROM orders WHERE orders.user_id = user_id;
END;"""
    elements: list[Any] = []

    extract_sql_procedures(root, _traverse, _node_text, sql, elements)

    assert len(elements) == 1
    procedure = elements[0]
    assert isinstance(procedure, SQLProcedure)
    assert procedure.name == "refresh_user"
    assert procedure.start_line == 1
    assert procedure.end_line == 4
    assert [param.name for param in procedure.parameters] == ["user_id", "total"]
    assert [param.direction for param in procedure.parameters] == ["IN", "OUT"]


def test_extract_procedure_parameters_filters_keywords_and_detects_inout() -> None:
    parameters: list[SQLParameter] = []
    proc_text = """
    CREATE PROCEDURE sync_user(INOUT user_id INT, IN state_value VARCHAR(20), OUT NAME TEXT)
    BEGIN
        SELECT 1;
    END;
    """

    extract_procedure_parameters(proc_text, parameters)

    assert [(param.name, param.data_type, param.direction) for param in parameters] == [
        ("user_id", "INT", "INOUT"),
        ("state_value", "VARCHAR(20)", "IN"),
    ]


def test_extract_sql_procedures_fallback_skips_duplicates() -> None:
    error_node = FakeNode(
        "ERROR",
        "CREATE PROCEDURE fallback_proc()\nBEGIN\nEND;",
        children=[FakeNode("keyword_create")],
        start_point=FakePoint(4),
        end_point=FakePoint(6),
    )
    root = FakeNode("program", children=[error_node])
    elements: list[Any] = []

    extract_sql_procedures(root, _traverse, _node_text, "", elements)
    extract_sql_procedures(root, _traverse, _node_text, "", elements)

    assert [element.name for element in elements] == ["fallback_proc"]
    assert elements[0].start_line == 5
    assert elements[0].end_line == 7


def test_extract_legacy_procedures_from_error_node() -> None:
    error_node = FakeNode(
        "ERROR",
        "CREATE PROCEDURE legacy_proc()\nBEGIN\nEND;",
        children=[FakeNode("keyword_create")],
        start_point=FakePoint(2),
        end_point=FakePoint(4),
    )
    functions: list[Function] = []

    extract_legacy_procedures(error_node, functions, _traverse, _node_text)

    assert len(functions) == 1
    assert functions[0].name == "legacy_proc"
    assert functions[0].start_line == 3
    assert functions[0].end_line == 5


def test_extract_procedure_dependencies_deduplicates_object_references() -> None:
    proc_node = FakeNode(
        "procedure",
        children=[
            FakeNode(
                "object_reference",
                children=[
                    FakeNode("identifier", "orders"),
                    FakeNode("identifier", "orders"),
                ],
            ),
            FakeNode(
                "object_reference",
                children=[FakeNode("identifier", "users")],
            ),
        ],
    )
    dependencies: list[str] = []

    _extract_procedure_dependencies(proc_node, dependencies, _traverse, _node_text)

    assert dependencies == ["orders", "users"]
