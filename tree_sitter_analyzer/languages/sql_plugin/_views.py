"""SQL element extraction mixin — views."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import (
    Class,
    SQLElement,
    SQLView,
)
from ...utils import log_debug
from ._base import _SQLExtractorBase


class ViewsMixin(_SQLExtractorBase):

    def _extract_views(
        self, root_node: tree_sitter.Node, classes: list[Class]
    ) -> None:
        """
        Extract CREATE VIEW statements from SQL AST.

        Searches for create_view nodes and extracts view names from
        object_reference.identifier, supporting qualified names.

        Args:
            root_node: Root node of the SQL AST
            classes: List to append extracted view Class elements to
        """
        import re

        for node in self._traverse_nodes(root_node):
            if node.type == "create_view":
                # Get raw text first for fallback regex
                raw_text = self._get_node_text(node)
                view_name = None

                # FIRST: Try regex parsing (most reliable for CREATE VIEW)
                if raw_text:
                    # Pattern: CREATE VIEW [IF NOT EXISTS] view_name
                    view_match = re.search(
                        r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
                        raw_text,
                        re.IGNORECASE,
                    )
                    if view_match:
                        potential_name = view_match.group(1).strip()
                        if self._is_valid_identifier(potential_name):
                            view_name = potential_name

                # Fallback: Try AST parsing if regex didn't work
                if not view_name:
                    for child in node.children:
                        if child.type == "object_reference":
                            # object_reference contains identifier
                            for subchild in child.children:
                                if subchild.type == "identifier":
                                    potential_name = self._get_node_text(subchild)
                                    if potential_name:
                                        potential_name = potential_name.strip()
                                        # Validate view name - exclude SQL keywords
                                        if (
                                            potential_name
                                            and self._is_valid_identifier(
                                                potential_name
                                            )
                                            and potential_name.upper()
                                            not in (
                                                "SELECT",
                                                "FROM",
                                                "WHERE",
                                                "AS",
                                                "IF",
                                                "NOT",
                                                "EXISTS",
                                                "NULL",
                                                "CURRENT_TIMESTAMP",
                                                "NOW",
                                                "SYSDATE",
                                            )
                                        ):
                                            view_name = potential_name
                                            break
                            if view_name:
                                break

                if view_name:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        # Fix for truncated view definitions (single-line misparsing)
                        # When tree-sitter misparses a view as a single line (e.g. lines 47-47),
                        # we need to expand the range to include the actual query definition.
                        # We look for the next semicolon or empty line to find the true end.
                        if start_line == end_line and self.source_code:
                            # This logic is similar to the recovery logic in _validate_and_fix_elements
                            # Find where the view definition actually ends
                            current_line_idx = start_line - 1

                            # Scan forward for semicolon to find end of statement
                            found_end = False
                            for i in range(current_line_idx, len(self.content_lines)):
                                line = self.content_lines[i]
                                if ";" in line:
                                    end_line = i + 1
                                    found_end = True
                                    break

                            # If no semicolon found within reasonable range, use a fallback
                            if not found_end:
                                # Look for empty line as separator or next CREATE statement
                                for i in range(
                                    current_line_idx + 1,
                                    min(len(self.content_lines), current_line_idx + 50),
                                ):
                                    line = self.content_lines[i].strip()
                                    if not line or line.upper().startswith("CREATE "):
                                        end_line = i  # End before this line
                                        found_end = True
                                        break

                            # Update raw_text to cover the full range
                            # Re-extract text for the corrected range
                            if found_end and end_line > start_line:
                                raw_text = "\n".join(
                                    self.content_lines[current_line_idx:end_line]
                                )
                                log_debug(
                                    f"Corrected view span for {view_name}: {start_line}-{end_line}"
                                )

                        cls = Class(
                            name=view_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                        )
                        classes.append(cls)
                    except Exception as e:
                        log_debug(f"Failed to extract view: {e}")

    def _extract_sql_views(
        self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]
    ) -> None:
        """Extract CREATE VIEW statements with enhanced metadata."""
        for node in self._traverse_nodes(root_node):
            if node.type == "ERROR":
                # Handle views inside ERROR nodes (common in some environments)
                raw_text = self._get_node_text(node)
                if not raw_text:
                    continue

                import re

                # Find all views in this error node
                view_matches = re.finditer(
                    r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
                    raw_text,
                    re.IGNORECASE,
                )

                for match in view_matches:
                    view_name = match.group(1).strip()
                    if not self._is_valid_identifier(view_name):
                        continue

                    # Avoid duplicates
                    if any(
                        e.name == view_name and isinstance(e, SQLView)
                        for e in sql_elements
                    ):
                        continue

                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    # Extract source tables from context following the view definition
                    view_context = raw_text[match.end() :]
                    semicolon_match = re.search(r";", view_context)
                    if semicolon_match:
                        view_context = view_context[: semicolon_match.end()]

                    source_tables = []
                    # Simple extraction for source tables
                    table_matches = re.findall(
                        r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        view_context,
                        re.IGNORECASE,
                    )
                    source_tables.extend(table_matches)

                    view = SQLView(
                        name=view_name,
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=f"CREATE VIEW {view_name} ...",
                        language="sql",
                        source_tables=sorted(set(source_tables)),
                        dependencies=sorted(set(source_tables)),
                    )
                    sql_elements.append(view)

            elif node.type == "create_view":
                view_name = None
                source_tables = []

                # Get raw text for regex parsing
                raw_text = self._get_node_text(node)

                # FIRST: Try regex parsing (most reliable for CREATE VIEW)
                if raw_text:
                    # Pattern: CREATE VIEW [IF NOT EXISTS] view_name AS
                    import re

                    view_match = re.search(
                        r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
                        raw_text,
                        re.IGNORECASE,
                    )
                    if view_match:
                        potential_name = view_match.group(1).strip()
                        if self._is_valid_identifier(potential_name):
                            view_name = potential_name

                # Fallback: Try AST parsing if regex didn't work
                if not view_name:
                    for child in node.children:
                        if child.type == "object_reference":
                            for subchild in child.children:
                                if subchild.type == "identifier":
                                    potential_name = self._get_node_text(
                                        subchild
                                    ).strip()
                                    # Validate view name more strictly - exclude SQL keywords
                                    if (
                                        potential_name
                                        and self._is_valid_identifier(potential_name)
                                        and potential_name.upper()
                                        not in (
                                            "SELECT",
                                            "FROM",
                                            "WHERE",
                                            "AS",
                                            "IF",
                                            "NOT",
                                            "EXISTS",
                                            "NULL",
                                            "CURRENT_TIMESTAMP",
                                            "NOW",
                                            "SYSDATE",
                                            "COUNT",
                                            "SUM",
                                            "AVG",
                                            "MAX",
                                            "MIN",
                                        )
                                    ):
                                        view_name = potential_name
                                        break
                            if view_name:
                                break

                # Extract source tables from SELECT statement
                self._extract_view_sources(node, source_tables)

                if view_name:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = self._get_node_text(node)

                        view = SQLView(
                            name=view_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                            source_tables=source_tables,
                            dependencies=source_tables,
                        )
                        sql_elements.append(view)
                    except Exception as e:
                        log_debug(f"Failed to extract enhanced view: {e}")

    def _extract_view_sources(
        self, view_node: tree_sitter.Node, source_tables: list[str]
    ) -> None:
        """Extract source tables from view definition."""
        for node in self._traverse_nodes(view_node):
            if node.type == "from_clause":
                for child in self._traverse_nodes(node):
                    if child.type == "object_reference":
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                table_name = self._get_node_text(child).strip()
                                if table_name and table_name not in source_tables:
                                    source_tables.append(table_name)
