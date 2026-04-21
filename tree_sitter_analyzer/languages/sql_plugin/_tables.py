"""SQL element extraction mixin — tables."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import (
    Class,
    SQLColumn,
    SQLConstraint,
    SQLElement,
    SQLTable,
)
from ...utils import log_debug
from ._base import _SQLExtractorBase


class TablesMixin(_SQLExtractorBase):

    def _extract_tables(
        self, root_node: tree_sitter.Node, classes: list[Class]
    ) -> None:
        """
        Extract CREATE TABLE statements from SQL AST.

        Searches for create_table nodes and identifies table names from
        object_reference.identifier, supporting both simple identifiers
        and qualified names (schema.table).

        Args:
            root_node: Root node of the SQL AST
            classes: List to append extracted table Class elements to
        """
        for node in self._traverse_nodes(root_node):
            if node.type == "create_table":
                # Look for object_reference within create_table
                table_name = None
                for child in node.children:
                    if child.type == "object_reference":
                        # object_reference contains identifier
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                table_name = self._get_node_text(subchild).strip()
                                # Validate table name
                                if table_name and self._is_valid_identifier(table_name):
                                    break
                                else:
                                    table_name = None
                        if table_name:
                            break

                if table_name:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = self._get_node_text(node)

                        cls = Class(
                            name=table_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                        )
                        classes.append(cls)
                    except Exception as e:
                        log_debug(f"Failed to extract table: {e}")

    def _extract_sql_tables(
        self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]
    ) -> None:
        """
        Extract CREATE TABLE statements with enhanced metadata.

        Extracts table information including columns, data types, constraints,
        and dependencies for comprehensive table analysis.
        """
        for node in self._traverse_nodes(root_node):
            if node.type == "create_table":
                table_name = None

                columns: list[SQLColumn] = []
                constraints: list[SQLConstraint] = []

                # Extract table name
                for child in node.children:
                    if child.type == "object_reference":
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                table_name = self._get_node_text(subchild).strip()
                                # Validate table name - should be a simple identifier
                                if table_name and self._is_valid_identifier(table_name):
                                    break
                                else:
                                    table_name = None
                        if table_name:
                            break

                # Extract column definitions
                self._extract_table_columns(node, columns, constraints)

                if table_name:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = self._get_node_text(node)

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

    def _extract_table_columns(
        self,
        table_node: tree_sitter.Node,
        columns: list[SQLColumn],
        constraints: list[SQLConstraint],
    ) -> None:
        """Extract column definitions from CREATE TABLE statement."""
        # Use a more robust approach to extract columns
        table_text = self._get_node_text(table_node)

        # Parse the table definition using regex as fallback
        import re

        # Extract the content between parentheses
        table_content_match = re.search(
            r"\(\s*(.*?)\s*\)(?:\s*;)?$", table_text, re.DOTALL
        )
        if table_content_match:
            table_content = table_content_match.group(1)

            # Split by commas, but be careful with nested parentheses
            column_definitions = self._split_column_definitions(table_content)

            for col_def in column_definitions:
                col_def = col_def.strip()
                if not col_def or col_def.upper().startswith(
                    ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "INDEX", "KEY")
                ):
                    continue

                # Parse individual column definition
                column = self._parse_column_definition(col_def)
                if column:
                    columns.append(column)

        # Also try tree-sitter approach as backup
        for node in self._traverse_nodes(table_node):
            if node.type == "column_definition":
                column_name = None
                data_type = None
                nullable = True
                is_primary_key = False

                # Extract column name and type
                for child in node.children:
                    if child.type == "identifier" and column_name is None:
                        column_name = self._get_node_text(child).strip()
                    elif child.type in ["data_type", "type_name"]:
                        data_type = self._get_node_text(child).strip()
                    elif (
                        child.type == "not_null"
                        or "NOT NULL" in self._get_node_text(child).upper()
                    ):
                        nullable = False
                    elif (
                        child.type == "primary_key"
                        or "PRIMARY KEY" in self._get_node_text(child).upper()
                    ):
                        is_primary_key = True

                if column_name and data_type:
                    # Check if this column is already added by regex parsing
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

    def _split_column_definitions(self, content: str) -> list[str]:
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

    def _parse_column_definition(self, col_def: str) -> SQLColumn | None:
        """Parse a single column definition string."""
        import re

        # Basic pattern: column_name data_type [constraints]
        match = re.match(
            r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+([A-Z]+(?:\([^)]*\))?)",
            col_def,
            re.IGNORECASE,
        )
        if not match:
            return None

        column_name = match.group(1)
        data_type = match.group(2)

        # Check for constraints
        col_def_upper = col_def.upper()
        nullable = "NOT NULL" not in col_def_upper
        is_primary_key = (
            "PRIMARY KEY" in col_def_upper or "AUTO_INCREMENT" in col_def_upper
        )
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
