"""SQL element extraction mixin — indexes."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import (
    SQLElement,
    SQLIndex,
    Variable,
)
from ...utils import log_debug
from ._base import _SQLExtractorBase


class IndexesMixin(_SQLExtractorBase):

    def _extract_indexes(
        self, root_node: tree_sitter.Node, variables: list[Variable]
    ) -> None:
        """
        Extract CREATE INDEX statements from SQL AST.

        Searches for create_index nodes and extracts index names from
        identifier child nodes.

        Args:
            root_node: Root node of the SQL AST
            variables: List to append extracted index Variable elements to
        """
        for node in self._traverse_nodes(root_node):
            if node.type == "create_index":
                # Index name is directly in identifier child
                index_name = None
                for child in node.children:
                    if child.type == "identifier":
                        index_name = self._get_node_text(child).strip()
                        break

                if index_name:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = self._get_node_text(node)

                        var = Variable(
                            name=index_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                        )
                        variables.append(var)
                    except Exception as e:
                        log_debug(f"Failed to extract index: {e}")

    def _extract_sql_indexes(
        self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]
    ) -> None:
        """Extract CREATE INDEX statements with enhanced metadata."""
        processed_indexes = set()  # Track processed indexes to avoid duplicates

        # First try tree-sitter parsing
        for node in self._traverse_nodes(root_node):
            if node.type == "create_index":
                index_name = None

                # Use regex to extract index name from raw text for better accuracy
                import re

                raw_text = self._get_node_text(node)
                # Pattern: CREATE [UNIQUE] INDEX index_name ON table_name
                index_pattern = re.search(
                    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+ON",
                    raw_text,
                    re.IGNORECASE,
                )
                if index_pattern:
                    extracted_name = index_pattern.group(1)
                    # Validate index name
                    if self._is_valid_identifier(extracted_name):
                        index_name = extracted_name

                if index_name and index_name not in processed_indexes:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = self._get_node_text(node)

                        # Create index object first
                        index = SQLIndex(
                            name=index_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                            table_name=None,
                            indexed_columns=[],
                            is_unique=False,
                            dependencies=[],
                        )

                        # Extract metadata and populate the index object
                        self._extract_index_metadata(node, index)

                        sql_elements.append(index)
                        processed_indexes.add(index_name)
                        log_debug(
                            f"Extracted index: {index_name} on table {index.table_name}"
                        )
                    except Exception as e:
                        log_debug(f"Failed to extract enhanced index {index_name}: {e}")

        # Add regex-based fallback for indexes that tree-sitter might miss
        self._extract_indexes_with_regex(sql_elements, processed_indexes)

    def _extract_index_metadata(
        self,
        index_node: tree_sitter.Node,
        index: SQLIndex,
    ) -> None:
        """Extract index metadata including target table and columns."""
        index_text = self._get_node_text(index_node)

        # Check for UNIQUE keyword
        if "UNIQUE" in index_text.upper():
            index.is_unique = True

        # Extract table name
        import re

        table_match = re.search(
            r"ON\s+([a-zA-Z_][a-zA-Z0-9_]*)", index_text, re.IGNORECASE
        )
        if table_match:
            index.table_name = table_match.group(1)
            # Update dependencies
            if index.table_name and index.table_name not in index.dependencies:
                index.dependencies.append(index.table_name)

        # Extract column names
        columns_match = re.search(r"\(([^)]+)\)", index_text)
        if columns_match:
            columns_str = columns_match.group(1)
            columns = [col.strip() for col in columns_str.split(",")]
            index.indexed_columns.extend(columns)

    def _extract_indexes_with_regex(
        self, sql_elements: list[SQLElement], processed_indexes: set[str]
    ) -> None:
        """Extract CREATE INDEX statements using regex as fallback."""
        import re

        # Split source code into lines for line number tracking
        lines = self.source_code.split("\n")

        # Pattern to match CREATE INDEX statements
        index_pattern = re.compile(
            r"^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+ON\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]+)\)",
            re.IGNORECASE | re.MULTILINE,
        )

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line.upper().startswith("CREATE") or "INDEX" not in line.upper():
                continue

            match = index_pattern.match(line)
            if match:
                is_unique = match.group(1) is not None
                index_name = match.group(2)
                table_name = match.group(3)
                columns_str = match.group(4)

                # Skip if already processed
                if index_name in processed_indexes:
                    continue

                # Parse columns
                columns = [col.strip() for col in columns_str.split(",")]

                try:
                    index = SQLIndex(
                        name=index_name,
                        start_line=line_num,
                        end_line=line_num,
                        raw_text=line,
                        language="sql",
                        table_name=table_name,
                        indexed_columns=columns,
                        is_unique=is_unique,
                        dependencies=[table_name] if table_name else [],
                    )

                    sql_elements.append(index)
                    processed_indexes.add(index_name)
                    log_debug(
                        f"Regex extracted index: {index_name} on table {table_name}"
                    )

                except Exception as e:
                    log_debug(
                        f"Failed to create regex-extracted index {index_name}: {e}"
                    )
