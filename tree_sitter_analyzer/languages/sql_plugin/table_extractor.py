"""Enhanced SQL table extraction — extracted from sql_plugin/extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import SQLColumn, SQLConstraint, SQLTable
from ...utils import log_debug
from .identifier_validator import is_valid_identifier


def extract_sql_tables(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    sql_elements: list[Any],
) -> None:
    """Extract CREATE TABLE statements with enhanced metadata."""
    for node in traverse_nodes(root_node):
        if node.type == "create_table":
            table_name = None
            columns: list[SQLColumn] = []
            constraints: list[SQLConstraint] = []

            for child in node.children:
                if child.type == "object_reference":
                    for subchild in child.children:
                        if subchild.type == "identifier":
                            table_name = get_node_text(subchild).strip()
                            if table_name and is_valid_identifier(table_name):
                                break
                            else:
                                table_name = None
                    if table_name:
                        break

            extract_table_columns(
                node, columns, constraints, traverse_nodes, get_node_text
            )

            if table_name:
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = get_node_text(node)

                    table = SQLTable(
                        name=table_name,
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        language="sql",
                        columns=columns,
                        constraints=constraints,
                    )
                    sql_elements.append(table)
                except Exception as e:
                    log_debug(f"Failed to extract enhanced table: {e}")


def extract_table_columns(
    table_node: "tree_sitter.Node",
    columns: list[SQLColumn],
    constraints: list[SQLConstraint],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
) -> None:
    """Extract column definitions from CREATE TABLE statement."""
    table_text = get_node_text(table_node)

    # Parse the table definition using regex as fallback
    table_content_match = re.search(r"\(\s*(.*?)\s*\)(?:\s*;)?$", table_text, re.DOTALL)
    if table_content_match:
        table_content = table_content_match.group(1)
        column_definitions = _split_column_definitions(table_content)

        for col_def in column_definitions:
            col_def = col_def.strip()
            if not col_def or col_def.upper().startswith(
                ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "INDEX", "KEY")
            ):
                continue

            column = _parse_column_definition(col_def)
            if column:
                columns.append(column)

    # Also try tree-sitter approach as backup
    for node in traverse_nodes(table_node):
        if node.type == "column_definition":
            column_name = None
            data_type = None
            nullable = True
            is_primary_key = False

            for child in node.children:
                if child.type == "identifier" and column_name is None:
                    column_name = get_node_text(child).strip()
                elif child.type in ["data_type", "type_name"]:
                    data_type = get_node_text(child).strip()
                elif (
                    child.type == "not_null"
                    or "NOT NULL" in get_node_text(child).upper()
                ):
                    nullable = False
                elif (
                    child.type == "primary_key"
                    or "PRIMARY KEY" in get_node_text(child).upper()
                ):
                    is_primary_key = True

            if column_name and data_type:
                existing_column = next(
                    (c for c in columns if c.name == column_name), None
                )
                if not existing_column:
                    column = SQLColumn(
                        name=column_name,
                        data_type=data_type,
                        nullable=nullable,
                        is_primary_key=is_primary_key,
                    )
                    columns.append(column)


def _split_column_definitions(content: str) -> list[str]:
    """Split column definitions by commas, handling nested parentheses."""
    definitions = []
    current_def = ""
    paren_count = 0

    for char in content:
        if char == "(":
            paren_count += 1
        elif char == ")":
            paren_count -= 1
        elif char == "," and paren_count == 0:
            if current_def.strip():
                definitions.append(current_def.strip())
            current_def = ""
            continue

        current_def += char

    if current_def.strip():
        definitions.append(current_def.strip())

    return definitions


def _parse_column_definition(col_def: str) -> SQLColumn | None:
    """Parse a single column definition string."""
    match = re.match(
        r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+([A-Z]+(?:\([^)]*\))?)",
        col_def,
        re.IGNORECASE,
    )
    if not match:
        return None

    column_name = match.group(1)
    data_type = match.group(2)

    col_def_upper = col_def.upper()
    nullable = "NOT NULL" not in col_def_upper
    is_primary_key = "PRIMARY KEY" in col_def_upper or "AUTO_INCREMENT" in col_def_upper
    is_foreign_key = "REFERENCES" in col_def_upper

    foreign_key_reference = None
    if is_foreign_key:
        ref_match = re.search(
            r"REFERENCES\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]+)\)",
            col_def,
            re.IGNORECASE,
        )
        if ref_match:
            foreign_key_reference = f"{ref_match.group(1)}({ref_match.group(2)})"

    return SQLColumn(
        name=column_name,
        data_type=data_type,
        nullable=nullable,
        is_primary_key=is_primary_key,
        is_foreign_key=is_foreign_key,
        foreign_key_reference=foreign_key_reference,
    )
