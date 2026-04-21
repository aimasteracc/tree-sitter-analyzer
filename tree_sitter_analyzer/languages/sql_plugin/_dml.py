"""SQL element extraction mixin — dml."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import (
    Expression,
    Import,
)
from ...utils import log_debug
from ._base import _SQLExtractorBase


class DmlMixin(_SQLExtractorBase):

    def _extract_dml_statements(
        self, root_node: tree_sitter.Node, elements: list[Expression]
    ) -> None:
        """
        Extract DML statements (INSERT, UPDATE, DELETE) for grammar coverage.

        This method creates Expression elements for DML statements to ensure
        all DML-related node types are covered.

        Args:
            root_node: Root node of the tree
            elements: List to append extracted elements to
        """
        stack: list[tree_sitter.Node] = [root_node]

        while stack:
            node = stack.pop()

            # Extract DML statements
            if node.type in ("insert", "update", "delete"):
                try:
                    raw_text = self._get_node_text(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    elements.append(
                        Expression(
                            name=f"{node.type.upper()}_statement",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text[:200] if len(raw_text) > 200 else raw_text,
                            language="sql",
                            expression_kind=node.type,
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting {node.type}: {e}")

            # Add children to stack
            stack.extend(reversed(node.children))

    def _extract_expressions(
        self, root_node: tree_sitter.Node, elements: list[Expression]
    ) -> None:
        """
        Extract expressions (CASE, CAST, BETWEEN, EXISTS, etc.) for grammar coverage.

        This method creates Expression elements for various SQL expressions to ensure
        all expression-related node types are covered.

        Args:
            root_node: Root node of the tree
            elements: List to append extracted elements to
        """
        expression_types = {
            "case",
            "cast",
            "between_expression",
            "exists",
            "parenthesized_expression",
            "unary_expression",
        }

        stack: list[tree_sitter.Node] = [root_node]

        while stack:
            node = stack.pop()

            if node.type in expression_types:
                try:
                    raw_text = self._get_node_text(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    elements.append(
                        Expression(
                            name=f"{node.type}_expr",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text[:200] if len(raw_text) > 200 else raw_text,
                            language="sql",
                            expression_kind=node.type,
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting expression {node.type}: {e}")

            stack.extend(reversed(node.children))

    def _extract_query_clauses(
        self, root_node: tree_sitter.Node, elements: list[Expression]
    ) -> None:
        """
        Extract query clauses (ORDER BY, LIMIT, OFFSET, CTE, etc.) for grammar coverage.

        This method creates Expression elements for query clauses to ensure
        all clause-related node types are covered.

        Args:
            root_node: Root node of the tree
            elements: List to append extracted elements to
        """
        clause_types = {
            "order_by",
            "order_target",
            "direction",
            "limit",
            "offset",
            "cte",
            "set_operation",
            "returning",
            "assignment",
        }

        stack: list[tree_sitter.Node] = [root_node]

        while stack:
            node = stack.pop()

            if node.type in clause_types:
                try:
                    raw_text = self._get_node_text(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    elements.append(
                        Expression(
                            name=f"{node.type}_clause",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text[:200] if len(raw_text) > 200 else raw_text,
                            language="sql",
                            expression_kind=node.type,
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting clause {node.type}: {e}")

            stack.extend(reversed(node.children))

    def _extract_window_functions(
        self, root_node: tree_sitter.Node, elements: list[Expression]
    ) -> None:
        """
        Extract window functions and specifications for grammar coverage.

        This method creates Expression elements for window functions to ensure
        all window-related node types are covered.

        Args:
            root_node: Root node of the tree
            elements: List to append extracted elements to
        """
        window_types = {
            "window_function",
            "window_specification",
            "window_frame",
            "partition_by",
            "frame_definition",
        }

        stack: list[tree_sitter.Node] = [root_node]

        while stack:
            node = stack.pop()

            if node.type in window_types:
                try:
                    raw_text = self._get_node_text(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    elements.append(
                        Expression(
                            name=f"{node.type}_window",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text[:200] if len(raw_text) > 200 else raw_text,
                            language="sql",
                            expression_kind=node.type,
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting window {node.type}: {e}")

            stack.extend(reversed(node.children))

    def _extract_transactions(
        self, root_node: tree_sitter.Node, elements: list[Expression]
    ) -> None:
        """
        Extract transaction statements for grammar coverage.

        This method creates Expression elements for transaction statements to ensure
        all transaction-related node types are covered.

        Args:
            root_node: Root node of the tree
            elements: List to append extracted elements to
        """
        stack: list[tree_sitter.Node] = [root_node]

        while stack:
            node = stack.pop()

            if node.type == "transaction":
                try:
                    raw_text = self._get_node_text(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    elements.append(
                        Expression(
                            name="transaction_stmt",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text[:200] if len(raw_text) > 200 else raw_text,
                            language="sql",
                            expression_kind="transaction",
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting transaction: {e}")

            stack.extend(reversed(node.children))

    def _extract_comments(
        self, root_node: tree_sitter.Node, elements: list[Expression]
    ) -> None:
        """
        Extract comments for grammar coverage.

        This method creates Expression elements for comments to ensure
        all comment nodes are covered.

        Args:
            root_node: Root node of the tree
            elements: List to append extracted elements to
        """
        stack: list[tree_sitter.Node] = [root_node]

        while stack:
            node = stack.pop()

            if node.type == "comment":
                try:
                    raw_text = self._get_node_text(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    elements.append(
                        Expression(
                            name="comment",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text[:200] if len(raw_text) > 200 else raw_text,
                            language="sql",
                            expression_kind="comment",
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting comment: {e}")

            stack.extend(reversed(node.children))

    def _extract_select_statements(
        self, root_node: tree_sitter.Node, elements: list[Expression]
    ) -> None:
        """
        Extract standalone SQL statements for grammar coverage.

        This method creates Expression elements for SQL statements to ensure
        all statement-related constructs and keywords are covered.

        Args:
            root_node: Root node of the tree
            elements: List to append extracted elements to
        """
        stack: list[tree_sitter.Node] = [root_node]

        while stack:
            node = stack.pop()

            # Extract statement nodes (these span full queries including HAVING, JOIN, etc.)
            if node.type == "statement":
                try:
                    raw_text = self._get_node_text(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    elements.append(
                        Expression(
                            name="SQL_statement",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text[:200] if len(raw_text) > 200 else raw_text,
                            language="sql",
                            expression_kind="statement",
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting statement: {e}")

            stack.extend(reversed(node.children))

    def _extract_schema_references(
        self, root_node: tree_sitter.Node, imports: list[Import]
    ) -> None:
        """Extract schema references (e.g., FROM schema.table)."""
        # This is a simplified implementation
        # In a full implementation, we would extract schema.table references
        # For now, we'll extract qualified names that might represent schema references
        for node in self._traverse_nodes(root_node):
            if node.type == "qualified_name":
                # Check if this looks like a schema reference
                text = self._get_node_text(node)
                if "." in text and len(text.split(".")) == 2:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = text

                        imp = Import(
                            name=text,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                        )
                        imports.append(imp)
                    except Exception as e:
                        log_debug(f"Failed to extract schema reference: {e}")
