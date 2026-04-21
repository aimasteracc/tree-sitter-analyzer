"""SQL element extraction — core utilities and entry point."""
from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter


from ...encoding_utils import extract_text_slice, safe_encode
from ...models import (
    Class,
    Expression,
    Function,
    Import,
    SQLElement,
    SQLView,
    Variable,
)
from ...platform_compat.adapter import CompatibilityAdapter
from ...plugins.base import ElementExtractor
from ...utils import log_debug, log_error
from ._base import _SQLExtractorBase


class CoreMixin(_SQLExtractorBase, ElementExtractor):

    def __init__(self, diagnostic_mode: bool = False) -> None:
        """
        Initialize the SQL element extractor.

        Sets up internal state for source code processing and performance
        optimization caches for node text extraction.
        """
        super().__init__()
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.diagnostic_mode = diagnostic_mode
        self.platform_info = None

        # Performance optimization caches - use position-based keys for deterministic caching
        # Cache node text to avoid repeated extraction
        self._node_text_cache: dict[tuple[int, int], str] = {}
        # Track processed nodes to avoid duplicate processing
        self._processed_nodes: set[int] = set()
        # File encoding for safe text extraction
        self._file_encoding: str | None = None

        # Platform compatibility
        self.adapter: CompatibilityAdapter | None = None

    def set_adapter(self, adapter: CompatibilityAdapter) -> None:
        """Set the compatibility adapter."""
        self.adapter = adapter

    def extract_sql_elements(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[SQLElement | Expression]:
        """
        Extract all SQL elements with enhanced metadata.

        This is the new enhanced extraction method that returns SQL-specific
        element types with detailed metadata including columns, constraints,
        parameters, and dependencies, plus Expression elements for comprehensive
        grammar coverage.

        Args:
            tree: Tree-sitter AST tree parsed from SQL source
            source_code: Original SQL source code as string

        Returns:
            List of SQLElement and Expression objects
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        sql_elements: list[SQLElement] = []
        expression_elements: list[Expression] = []

        if tree is not None and tree.root_node is not None:
            try:
                # Extract all SQL element types with enhanced metadata
                self._extract_sql_tables(tree.root_node, sql_elements)
                self._extract_sql_views(tree.root_node, sql_elements)
                self._extract_sql_procedures(tree.root_node, sql_elements)
                self._extract_sql_functions_enhanced(tree.root_node, sql_elements)
                self._extract_sql_triggers(tree.root_node, sql_elements)
                self._extract_sql_indexes(tree.root_node, sql_elements)

                # Extract additional elements for grammar coverage
                self._extract_dml_statements(tree.root_node, expression_elements)
                self._extract_expressions(tree.root_node, expression_elements)
                self._extract_query_clauses(tree.root_node, expression_elements)
                self._extract_window_functions(tree.root_node, expression_elements)
                self._extract_transactions(tree.root_node, expression_elements)
                self._extract_comments(tree.root_node, expression_elements)
                self._extract_select_statements(tree.root_node, expression_elements)
                # _extract_keywords_and_others removed — it was a no-op traversal

                # Apply platform compatibility adapter if available (SQL elements only)
                if self.adapter:
                    if self.diagnostic_mode:
                        log_debug(
                            f"Diagnostic: Before adaptation: {[e.name for e in sql_elements]}"
                        )

                    sql_elements = self.adapter.adapt_elements(
                        sql_elements, self.source_code
                    )

                    if self.diagnostic_mode:
                        log_debug(
                            f"Diagnostic: After adaptation: {[e.name for e in sql_elements]}"
                        )

                # Post-process to fix platform-specific parsing errors
                sql_elements = self._validate_and_fix_elements(sql_elements)

                log_debug(
                    f"Extracted {len(sql_elements)} SQL elements + "
                    f"{len(expression_elements)} expression elements"
                )
            except Exception as e:
                log_error(
                    f"Error during enhanced SQL extraction on {self.platform_info}: {e}"
                )
                log_error(
                    "Suggestion: Check platform compatibility documentation or enable diagnostic mode for more details."
                )
                # Return empty list or partial results to allow other languages to continue
                if not sql_elements and not expression_elements:
                    return []

        # Combine SQL elements and expression elements
        all_elements: list[SQLElement | Expression] = []
        all_elements.extend(sql_elements)
        all_elements.extend(expression_elements)
        return all_elements

    def _validate_and_fix_elements(
        self, elements: list[SQLElement]
    ) -> list[SQLElement]:
        """
        Post-process elements to fix parsing errors caused by platform-specific
        tree-sitter behavior (e.g. ERROR nodes misidentifying triggers).
        """
        import re

        validated = []
        seen_names = set()

        for elem in elements:
            elem_type = getattr(elem, "sql_element_type", None)

            # 1. Check for Phantom Elements (Mismatch between Type and Content)
            if elem_type and elem.raw_text:
                raw_text_stripped = elem.raw_text.strip()
                is_valid = True

                # Fix Ubuntu 3.12 phantom trigger issue (Trigger type but Function content)
                if elem_type.value == "trigger":
                    # Must start with CREATE TRIGGER (allow comments/whitespace)
                    if not re.search(
                        r"CREATE\s+TRIGGER", raw_text_stripped, re.IGNORECASE
                    ):
                        log_debug(
                            f"Removing phantom trigger: {elem.name} (content mismatch)"
                        )
                        is_valid = False

                # Fix phantom functions
                elif elem_type.value == "function":
                    if not re.search(
                        r"CREATE\s+FUNCTION", raw_text_stripped, re.IGNORECASE
                    ):
                        log_debug(
                            f"Removing phantom function: {elem.name} (content mismatch)"
                        )
                        is_valid = False

                if not is_valid:
                    continue

            # 2. Fix Names
            if elem_type and elem.raw_text:
                # Fix Trigger name issues (e.g. macOS "description" bug)
                if elem_type.value == "trigger":
                    trigger_match = re.search(
                        r"CREATE\s+TRIGGER\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        elem.raw_text,
                        re.IGNORECASE,
                    )
                    if trigger_match:
                        correct_name = trigger_match.group(1)
                        if elem.name != correct_name and self._is_valid_identifier(
                            correct_name
                        ):
                            log_debug(
                                f"Fixing trigger name: {elem.name} -> {correct_name}"
                            )
                            elem.name = correct_name

                # Fix Function name issues (e.g. Windows/Ubuntu "AUTO_INCREMENT" bug)
                elif elem_type.value == "function":
                    # Filter out obvious garbage names if they match keywords
                    if elem.name and elem.name.upper() in (
                        "AUTO_INCREMENT",
                        "KEY",
                        "PRIMARY",
                        "FOREIGN",
                    ):
                        # Try to recover correct name
                        func_match = re.search(
                            r"CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                            elem.raw_text,
                            re.IGNORECASE,
                        )
                        if func_match:
                            correct_name = func_match.group(1)
                            log_debug(
                                f"Fixing garbage function name: {elem.name} -> {correct_name}"
                            )
                            elem.name = correct_name
                        else:
                            log_debug(f"Removing garbage function name: {elem.name}")
                            continue

                    # General name verification
                    gen_match = re.search(
                        r"CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        elem.raw_text,
                        re.IGNORECASE,
                    )
                    if gen_match:
                        correct_name = gen_match.group(1)
                        if elem.name != correct_name and self._is_valid_identifier(
                            correct_name
                        ):
                            log_debug(
                                f"Fixing function name: {elem.name} -> {correct_name}"
                            )
                            elem.name = correct_name

            # Deduplication
            key = (getattr(elem, "sql_element_type", None), elem.name, elem.start_line)
            if key in seen_names:
                continue
            seen_names.add(key)

            validated.append(elem)

        # Recover missing Views (often missed in ERROR nodes on some platforms)
        # This is a fallback scan of the entire source code
        if self.source_code:
            existing_views = {
                e.name
                for e in validated
                if hasattr(e, "sql_element_type") and e.sql_element_type.value == "view"
            }

            view_matches = re.finditer(
                r"^\s*CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
                self.source_code,
                re.IGNORECASE | re.MULTILINE,
            )

            for match in view_matches:
                view_name = match.group(1)
                if view_name not in existing_views and self._is_valid_identifier(
                    view_name
                ):
                    log_debug(f"Recovering missing view: {view_name}")

                    # Calculate approximate line numbers
                    start_pos = match.start()
                    # Count newlines before start_pos
                    start_line = self.source_code.count("\n", 0, start_pos) + 1

                    # Estimate end line (until next semicolon or empty line)
                    view_context = self.source_code[start_pos:]
                    semicolon_match = re.search(r";", view_context)
                    if semicolon_match:
                        end_pos = start_pos + semicolon_match.end()
                        end_line = self.source_code.count("\n", 0, end_pos) + 1
                    else:
                        end_line = start_line + 5  # Fallback estimate

                    # Extract source tables roughly
                    source_tables = []
                    table_matches = re.findall(
                        r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        view_context[
                            : semicolon_match.end() if semicolon_match else 500
                        ],
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
                    validated.append(view)
                    existing_views.add(view_name)

        return validated

    def extract_functions(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """
        Extract stored procedures, functions, and triggers from SQL code.

        Maps SQL executable units to Function elements:
        - CREATE PROCEDURE statements → Function
        - CREATE FUNCTION statements → Function
        - CREATE TRIGGER statements → Function

        Args:
            tree: Tree-sitter AST tree parsed from SQL source
            source_code: Original SQL source code as string

        Returns:
            List of Function elements representing procedures, functions, and triggers
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        if tree is not None and tree.root_node is not None:
            try:
                # Extract procedures, functions, and triggers
                self._extract_procedures(tree.root_node, functions)
                self._extract_sql_functions(tree.root_node, functions)
                self._extract_triggers(tree.root_node, functions)
                log_debug(
                    f"Extracted {len(functions)} SQL functions/procedures/triggers"
                )
            except Exception as e:
                log_debug(f"Error during function extraction: {e}")

        return functions

    def extract_classes(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Class]:
        """
        Extract tables and views from SQL code.

        Maps SQL structural definitions to Class elements:
        - CREATE TABLE statements → Class
        - CREATE VIEW statements → Class

        Args:
            tree: Tree-sitter AST tree parsed from SQL source
            source_code: Original SQL source code as string

        Returns:
            List of Class elements representing tables and views
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        if tree is not None and tree.root_node is not None:
            try:
                # Extract tables and views
                self._extract_tables(tree.root_node, classes)
                self._extract_views(tree.root_node, classes)
                log_debug(f"Extracted {len(classes)} SQL tables/views")
            except Exception as e:
                log_debug(f"Error during class extraction: {e}")

        return classes

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """
        Extract indexes from SQL code.

        Maps SQL metadata definitions to Variable elements:
        - CREATE INDEX statements → Variable

        Args:
            tree: Tree-sitter AST tree parsed from SQL source
            source_code: Original SQL source code as string

        Returns:
            List of Variable elements representing indexes
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        if tree is not None and tree.root_node is not None:
            try:
                # Extract indexes
                self._extract_indexes(tree.root_node, variables)
                log_debug(f"Extracted {len(variables)} SQL indexes")
            except Exception as e:
                log_debug(f"Error during variable extraction: {e}")

        return variables

    def extract_imports(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Import]:
        """
        Extract schema references and dependencies from SQL code.

        Extracts qualified names (schema.table) that represent cross-schema
        dependencies, mapping them to Import elements.

        Args:
            tree: Tree-sitter AST tree parsed from SQL source
            source_code: Original SQL source code as string

        Returns:
            List of Import elements representing schema references
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        imports: list[Import] = []

        if tree is not None and tree.root_node is not None:
            try:
                # Extract schema references (e.g., FROM schema.table)
                self._extract_schema_references(tree.root_node, imports)
                log_debug(f"Extracted {len(imports)} SQL schema references")
            except Exception as e:
                log_debug(f"Error during import extraction: {e}")

        return imports

    def _reset_caches(self) -> None:
        """Reset performance caches."""
        self._node_text_cache.clear()
        self._processed_nodes.clear()

    def _get_node_text(self, node: tree_sitter.Node) -> str:
        """
        Get text content from a tree-sitter node with caching.

        Uses byte-based extraction first, falls back to line-based extraction
        if byte extraction fails. Results are cached for performance.

        Args:
            node: Tree-sitter node to extract text from

        Returns:
            Text content of the node, or empty string if extraction fails
        """
        # Use position-based cache key for deterministic behavior
        cache_key = (node.start_byte, node.end_byte)

        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte
            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)

            if text:
                self._node_text_cache[cache_key] = text
                return text
        except Exception as e:
            log_debug(f"Error in _get_node_text: {e}")

        # Fallback to line-based extraction
        try:
            start_point = node.start_point
            end_point = node.end_point

            if start_point[0] < 0 or start_point[0] >= len(self.content_lines):
                return ""

            if end_point[0] < 0 or end_point[0] >= len(self.content_lines):
                return ""

            if start_point[0] == end_point[0]:
                line = self.content_lines[start_point[0]]
                start_col = max(0, min(start_point[1], len(line)))
                end_col = max(start_col, min(end_point[1], len(line)))
                result: str = line[start_col:end_col]
                self._node_text_cache[cache_key] = result
                return result
            else:
                lines = []
                for i in range(
                    start_point[0], min(end_point[0] + 1, len(self.content_lines))
                ):
                    if i < len(self.content_lines):
                        line = self.content_lines[i]
                        if i == start_point[0] and i == end_point[0]:
                            start_col = max(0, min(start_point[1], len(line)))
                            end_col = max(start_col, min(end_point[1], len(line)))
                            lines.append(line[start_col:end_col])
                        elif i == start_point[0]:
                            start_col = max(0, min(start_point[1], len(line)))
                            lines.append(line[start_col:])
                        elif i == end_point[0]:
                            end_col = max(0, min(end_point[1], len(line)))
                            lines.append(line[:end_col])
                        else:
                            lines.append(line)
                result = "\n".join(lines)
                self._node_text_cache[cache_key] = result
                return result
        except Exception as fallback_error:
            log_debug(f"Fallback text extraction also failed: {fallback_error}")
            return ""

    def _traverse_nodes(self, node: tree_sitter.Node) -> Iterator[tree_sitter.Node]:
        """
        Traverse tree nodes recursively in depth-first order.

        Args:
            node: Root node to start traversal from

        Yields:
            Each node in the tree, starting with the root node
        """
        yield node
        if hasattr(node, "children"):
            for child in node.children:
                yield from self._traverse_nodes(child)

    def _is_valid_identifier(self, name: str) -> bool:
        """
        Validate that a name is a valid SQL identifier.

        This prevents accepting multi-line text or SQL statements as identifiers.
        Also rejects common column names and SQL reserved keywords.

        Args:
            name: The identifier to validate

        Returns:
            True if the name is a valid identifier, False otherwise
        """
        if not name:
            return False

        # Reject if contains newlines or other control characters
        if "\n" in name or "\r" in name or "\t" in name:
            return False

        # Reject if matches SQL statement patterns (keyword followed by space)
        # This catches "CREATE TABLE" but allows "create_table" as an identifier
        name_upper = name.upper()
        sql_statement_patterns = [
            "CREATE ",
            "SELECT ",
            "INSERT ",
            "UPDATE ",
            "DELETE ",
            "DROP ",
            "ALTER ",
            "TABLE ",
            "VIEW ",
            "PROCEDURE ",
            "FUNCTION ",
            "TRIGGER ",
        ]
        if any(name_upper.startswith(pattern) for pattern in sql_statement_patterns):
            return False

        # Reject common column names that should never be function names
        # These are typical column names that might appear in SELECT statements
        common_column_names = {
            "PRICE",
            "QUANTITY",
            "TOTAL",
            "AMOUNT",
            "COUNT",
            "SUM",
            "CREATED_AT",
            "UPDATED_AT",
            "ID",
            "NAME",
            "EMAIL",
            "STATUS",
            "VALUE",
            "DATE",
            "TIME",
            "TIMESTAMP",
            "USER_ID",
            "ORDER_ID",
            "PRODUCT_ID",
        }
        if name_upper in common_column_names:
            return False

        # Reject common SQL keywords that should never be identifiers
        sql_keywords = {
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
            "AVG",
            "MAX",
            "MIN",
            "AND",
            "OR",
            "IN",
            "LIKE",
            "BETWEEN",
            "JOIN",
            "LEFT",
            "RIGHT",
            "INNER",
            "OUTER",
            "CROSS",
            "ON",
            "USING",
            "GROUP",
            "BY",
            "ORDER",
            "HAVING",
            "LIMIT",
            "OFFSET",
            "DISTINCT",
            "ALL",
            "UNION",
            "INTERSECT",
            "EXCEPT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "CREATE",
            "DROP",
            "ALTER",
            "TABLE",
            "VIEW",
            "INDEX",
            "TRIGGER",
            "PROCEDURE",
            "FUNCTION",
            "PRIMARY",
            "FOREIGN",
            "KEY",
            "UNIQUE",
            "CHECK",
            "DEFAULT",
            "REFERENCES",
            "CASCADE",
            "RESTRICT",
            "SET",
            "NO",
            "ACTION",
            "INTO",
            "VALUES",
            "BEGIN",
            "END",
            "DECLARE",
            "RETURN",
            "RETURNS",
            "READS",
            "SQL",
            "DATA",
            "DETERMINISTIC",
            "BEFORE",
            "AFTER",
            "EACH",
            "ROW",
            "FOR",
            "COALESCE",
            "CASE",
            "WHEN",
            "THEN",
            "ELSE",
        }
        if name_upper in sql_keywords:
            return False

        # Reject if contains parentheses (like "users (" or "(id")
        if "(" in name or ")" in name:
            return False

        # Reject if too long (identifiers should be reasonable length)
        if len(name) > 128:
            return False

        # Accept if it matches standard identifier pattern
        import re

        # Allow alphanumeric, underscore, and some special chars used in SQL identifiers
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
            return True

        # Also allow quoted identifiers (backticks, double quotes, square brackets)
        if re.match(r'^[`"\[].*[`"\]]$', name):
            return True

        return False
