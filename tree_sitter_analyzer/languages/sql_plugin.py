#!/usr/bin/env python3
"""
SQL Language Plugin

Provides SQL-specific parsing and element extraction functionality.
Supports extraction of tables, views, stored procedures, functions, triggers, and indexes.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import (
    Class,
    Function,
    Import,
    SQLColumn,
    SQLConstraint,
    SQLElement,
    SQLFunction,
    SQLIndex,
    SQLParameter,
    SQLProcedure,
    SQLTable,
    SQLTrigger,
    SQLView,
    Variable,
)
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error


class SQLElementExtractor(ElementExtractor):
    """
    SQL-specific element extractor.

    This extractor parses SQL AST and extracts database elements, mapping them
    to the unified element model:
    - Tables and Views → Class elements
    - Stored Procedures, Functions, Triggers → Function elements
    - Indexes → Variable elements
    - Schema references → Import elements

    The extractor handles standard SQL (ANSI SQL) syntax and supports
    CREATE TABLE, CREATE VIEW, CREATE PROCEDURE, CREATE FUNCTION,
    CREATE TRIGGER, and CREATE INDEX statements.
    """

    def __init__(self) -> None:
        """
        Initialize the SQL element extractor.

        Sets up internal state for source code processing and performance
        optimization caches for node text extraction.
        """
        super().__init__()
        self.source_code: str = ""
        self.content_lines: list[str] = []

        # Performance optimization caches
        # Cache node text to avoid repeated extraction
        self._node_text_cache: dict[int, str] = {}
        # Track processed nodes to avoid duplicate processing
        self._processed_nodes: set[int] = set()
        # File encoding for safe text extraction
        self._file_encoding: str | None = None

    def extract_sql_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[SQLElement]:
        """
        Extract all SQL elements with enhanced metadata.

        This is the new enhanced extraction method that returns SQL-specific
        element types with detailed metadata including columns, constraints,
        parameters, and dependencies.

        Args:
            tree: Tree-sitter AST tree parsed from SQL source
            source_code: Original SQL source code as string

        Returns:
            List of SQLElement objects with detailed metadata
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        sql_elements: list[SQLElement] = []

        if tree is not None and tree.root_node is not None:
            try:
                # Extract all SQL element types with enhanced metadata
                self._extract_sql_tables(tree.root_node, sql_elements)
                self._extract_sql_views(tree.root_node, sql_elements)
                self._extract_sql_procedures(tree.root_node, sql_elements)
                self._extract_sql_functions_enhanced(tree.root_node, sql_elements)
                self._extract_sql_triggers(tree.root_node, sql_elements)
                self._extract_sql_indexes(tree.root_node, sql_elements)
                log_debug(f"Extracted {len(sql_elements)} SQL elements with metadata")
            except Exception as e:
                log_debug(f"Error during enhanced SQL extraction: {e}")

        return sql_elements

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
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
        self, tree: "tree_sitter.Tree", source_code: str
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
        self, tree: "tree_sitter.Tree", source_code: str
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
        self, tree: "tree_sitter.Tree", source_code: str
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

    def _get_node_text(self, node: "tree_sitter.Node") -> str:
        """
        Get text content from a tree-sitter node with caching.

        Uses byte-based extraction first, falls back to line-based extraction
        if byte extraction fails. Results are cached for performance.

        Args:
            node: Tree-sitter node to extract text from

        Returns:
            Text content of the node, or empty string if extraction fails
        """
        node_id = id(node)

        if node_id in self._node_text_cache:
            return self._node_text_cache[node_id]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte
            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)

            if text:
                self._node_text_cache[node_id] = text
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
                self._node_text_cache[node_id] = result
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
                self._node_text_cache[node_id] = result
                return result
        except Exception as fallback_error:
            log_debug(f"Fallback text extraction also failed: {fallback_error}")
            return ""

    def _traverse_nodes(self, node: "tree_sitter.Node") -> Iterator["tree_sitter.Node"]:
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
            "COUNT",
            "SUM",
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

    def _extract_tables(
        self, root_node: "tree_sitter.Node", classes: list[Class]
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

    def _extract_views(
        self, root_node: "tree_sitter.Node", classes: list[Class]
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
                    # Pattern: CREATE VIEW [IF NOT EXISTS] view_name AS
                    match = re.search(
                        r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
                        raw_text,
                        re.IGNORECASE,
                    )
                    if match:
                        potential_name = match.group(1).strip()
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

    def _extract_procedures(
        self, root_node: "tree_sitter.Node", functions: list[Function]
    ) -> None:
        """
        Extract CREATE PROCEDURE statements from SQL AST.

        Since tree-sitter-sql doesn't fully support PROCEDURE syntax, these
        appear as ERROR nodes. The PROCEDURE keyword is not tokenized, so we
        need to check the raw text content of ERROR nodes that contain
        keyword_create and look for "PROCEDURE" in the text.

        Args:
            root_node: Root node of the SQL AST
            functions: List to append extracted procedure Function elements to
        """
        for node in self._traverse_nodes(root_node):
            if node.type == "ERROR":
                # Check if this ERROR node contains CREATE and PROCEDURE in text
                has_create = False
                node_text = self._get_node_text(node)
                node_text_upper = node_text.upper()

                # Look for keyword_create child
                for child in node.children:
                    if child.type == "keyword_create":
                        has_create = True
                        break

                # Check if the text contains PROCEDURE
                if has_create and "PROCEDURE" in node_text_upper:
                    # Extract procedure name from the text (preserve original case)
                    proc_name = None

                    # Try to extract from pattern: CREATE PROCEDURE name(
                    import re

                    match = re.search(
                        r"CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        node_text,
                        re.IGNORECASE,
                    )
                    if match:
                        proc_name = match.group(1)

                    if proc_name:
                        try:
                            start_line = node.start_point[0] + 1
                            end_line = node.end_point[0] + 1
                            raw_text = self._get_node_text(node)

                            func = Function(
                                name=proc_name,
                                start_line=start_line,
                                end_line=end_line,
                                raw_text=raw_text,
                                language="sql",
                            )
                            functions.append(func)
                        except Exception as e:
                            log_debug(f"Failed to extract procedure: {e}")

    def _extract_sql_functions(
        self, root_node: "tree_sitter.Node", functions: list[Function]
    ) -> None:
        """
        Extract CREATE FUNCTION statements from SQL AST.

        Functions are properly parsed as create_function nodes, so we search
        for these nodes and extract the function name from object_reference > identifier.

        Args:
            root_node: Root node of the SQL AST
            functions: List to append extracted function Function elements to
        """
        for node in self._traverse_nodes(root_node):
            if node.type == "create_function":
                func_name = None
                # Only use the FIRST object_reference as the function name
                for child in node.children:
                    if child.type == "object_reference":
                        # Only process the first object_reference
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                func_name = self._get_node_text(subchild).strip()
                                if func_name and self._is_valid_identifier(func_name):
                                    break
                                else:
                                    func_name = None
                        break  # Stop after first object_reference

                # Fallback: Parse from raw text if AST parsing failed or returned invalid name
                if not func_name:
                    raw_text = self._get_node_text(node)
                    import re

                    match = re.search(
                        r"CREATE\s+FUNCTION\s+(\w+)\s*\(", raw_text, re.IGNORECASE
                    )
                    if match:
                        potential_name = match.group(1).strip()
                        if self._is_valid_identifier(potential_name):
                            func_name = potential_name

                if func_name:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = self._get_node_text(node)
                        func = Function(
                            name=func_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                        )
                        functions.append(func)
                    except Exception as e:
                        log_debug(f"Failed to extract function: {e}")

    def _extract_triggers(
        self, root_node: "tree_sitter.Node", functions: list[Function]
    ) -> None:
        """
        Extract CREATE TRIGGER statements from SQL AST.

        Since tree-sitter-sql doesn't fully support TRIGGER syntax, these
        appear as ERROR nodes. We search for ERROR nodes containing both
        keyword_create and keyword_trigger, then extract the trigger name
        from the first object_reference > identifier that appears after
        keyword_trigger.

        Args:
            root_node: Root node of the SQL AST
            functions: List to append extracted trigger Function elements to
        """
        for node in self._traverse_nodes(root_node):
            if node.type == "ERROR":
                # Check if this ERROR node contains CREATE TRIGGER
                has_create = False
                has_trigger = False
                trigger_name = None
                found_trigger_keyword = False

                # Traverse children in order to find the trigger name right after CREATE TRIGGER
                for child in node.children:
                    if child.type == "keyword_create":
                        has_create = True
                    elif child.type == "keyword_trigger":
                        has_trigger = True
                        found_trigger_keyword = True
                    elif (
                        child.type == "object_reference"
                        and found_trigger_keyword
                        and not trigger_name
                    ):
                        # This should be the trigger name (first object_reference after TRIGGER keyword)
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                extracted_name = self._get_node_text(subchild).strip()
                                # Validate the identifier
                                if extracted_name and self._is_valid_identifier(
                                    extracted_name
                                ):
                                    trigger_name = extracted_name
                                break
                        break  # Stop after finding the first object_reference after TRIGGER

                # Skip common SQL keywords that might be incorrectly identified
                if trigger_name and trigger_name.upper() in (
                    "KEY",
                    "AUTO_INCREMENT",
                    "PRIMARY",
                    "FOREIGN",
                    "INDEX",
                    "UNIQUE",
                    "PRICE",
                    "QUANTITY",
                    "TOTAL",
                    "SUM",
                    "COUNT",
                    "AVG",
                    "MAX",
                    "MIN",
                ):
                    trigger_name = None

                # Fallback: Parse from raw text if AST parsing failed or returned suspicious name
                if (has_create and has_trigger) and not trigger_name:
                    import re

                    node_text = self._get_node_text(node)
                    # Look for pattern: CREATE TRIGGER <name>
                    match = re.search(
                        r"CREATE\s+TRIGGER\s+(\w+)", node_text, re.IGNORECASE
                    )
                    if match:
                        potential_name = match.group(1).strip()
                        if self._is_valid_identifier(
                            potential_name
                        ) and potential_name.upper() not in (
                            "ON",
                            "AFTER",
                            "BEFORE",
                            "INSERT",
                            "UPDATE",
                            "DELETE",
                            "FOR",
                            "EACH",
                            "ROW",
                        ):
                            trigger_name = potential_name

                if has_create and has_trigger and trigger_name:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = self._get_node_text(node)

                        func = Function(
                            name=trigger_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                        )
                        functions.append(func)
                    except Exception as e:
                        log_debug(f"Failed to extract trigger: {e}")

    def _extract_indexes(
        self, root_node: "tree_sitter.Node", variables: list[Variable]
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

    def _extract_schema_references(
        self, root_node: "tree_sitter.Node", imports: list[Import]
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

    def _extract_sql_tables(
        self, root_node: "tree_sitter.Node", sql_elements: list[SQLElement]
    ) -> None:
        """
        Extract CREATE TABLE statements with enhanced metadata.

        Extracts table information including columns, data types, constraints,
        and dependencies for comprehensive table analysis.
        """
        for node in self._traverse_nodes(root_node):
            if node.type == "create_table":
                table_name = None
                columns = []
                constraints = []

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
        table_node: "tree_sitter.Node",
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

    def _extract_sql_views(
        self, root_node: "tree_sitter.Node", sql_elements: list[SQLElement]
    ) -> None:
        """Extract CREATE VIEW statements with enhanced metadata."""
        for node in self._traverse_nodes(root_node):
            if node.type == "create_view":
                view_name = None
                source_tables = []

                # Get raw text for regex parsing
                raw_text = self._get_node_text(node)

                # FIRST: Try regex parsing (most reliable for CREATE VIEW)
                if raw_text:
                    # Pattern: CREATE VIEW [IF NOT EXISTS] view_name AS
                    import re

                    match = re.search(
                        r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
                        raw_text,
                        re.IGNORECASE,
                    )
                    if match:
                        potential_name = match.group(1).strip()
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
        self, view_node: "tree_sitter.Node", source_tables: list[str]
    ) -> None:
        """Extract source tables from view definition."""
        for node in self._traverse_nodes(view_node):
            if node.type == "from_clause":
                for child in self._traverse_nodes(node):
                    if child.type == "object_reference":
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                table_name = self._get_node_text(subchild).strip()
                                if table_name and table_name not in source_tables:
                                    source_tables.append(table_name)

    def _extract_sql_procedures(
        self, root_node: "tree_sitter.Node", sql_elements: list[SQLElement]
    ) -> None:
        """Extract CREATE PROCEDURE statements with enhanced metadata."""
        # Use regex-based approach to find all procedures in the source code
        import re

        lines = self.source_code.split("\n")

        # Pattern to match CREATE PROCEDURE statements
        procedure_pattern = re.compile(
            r"^\s*CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            re.IGNORECASE | re.MULTILINE,
        )

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.upper().startswith("CREATE") and "PROCEDURE" in line.upper():
                match = procedure_pattern.match(lines[i])
                if match:
                    proc_name = match.group(1)
                    start_line = i + 1

                    # Find the end of the procedure (look for END; or END$$)
                    end_line = start_line
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip().upper() in ["END;", "END$$", "END"]:
                            end_line = j + 1
                            break
                        elif lines[j].strip().upper().startswith("END;"):
                            end_line = j + 1
                            break

                    # Extract the full procedure text
                    proc_lines = lines[i:end_line]
                    raw_text = "\n".join(proc_lines)

                    parameters = []
                    dependencies = []

                    # Extract parameters and dependencies from the text
                    self._extract_procedure_parameters(raw_text, parameters)

                    try:
                        procedure = SQLProcedure(
                            name=proc_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                            parameters=parameters,
                            dependencies=dependencies,
                        )
                        sql_elements.append(procedure)
                        log_debug(
                            f"Extracted procedure: {proc_name} at lines {start_line}-{end_line}"
                        )
                    except Exception as e:
                        log_debug(f"Failed to extract enhanced procedure: {e}")

                    i = end_line
                else:
                    i += 1
            else:
                i += 1

        # Also try the original tree-sitter approach as fallback
        for node in self._traverse_nodes(root_node):
            if node.type == "ERROR":
                has_create = False
                node_text = self._get_node_text(node)
                node_text_upper = node_text.upper()

                for child in node.children:
                    if child.type == "keyword_create":
                        has_create = True
                        break

                if has_create and "PROCEDURE" in node_text_upper:
                    proc_name = None
                    parameters = []
                    dependencies = []

                    # Extract procedure name
                    match = re.search(
                        r"CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        node_text,
                        re.IGNORECASE,
                    )
                    if match:
                        proc_name = match.group(1)

                        # Check if this procedure was already extracted by regex
                        already_extracted = any(
                            hasattr(elem, "name") and elem.name == proc_name
                            for elem in sql_elements
                            if hasattr(elem, "sql_element_type")
                            and elem.sql_element_type.value == "procedure"
                        )

                        if not already_extracted:
                            # Extract parameters
                            self._extract_procedure_parameters(node_text, parameters)

                            # Extract dependencies (table references)
                            self._extract_procedure_dependencies(node, dependencies)

                            try:
                                start_line = node.start_point[0] + 1
                                end_line = node.end_point[0] + 1
                                raw_text = self._get_node_text(node)

                                procedure = SQLProcedure(
                                    name=proc_name,
                                    start_line=start_line,
                                    end_line=end_line,
                                    raw_text=raw_text,
                                    language="sql",
                                    parameters=parameters,
                                    dependencies=dependencies,
                                )
                                sql_elements.append(procedure)
                            except Exception as e:
                                log_debug(f"Failed to extract enhanced procedure: {e}")

    def _extract_procedure_parameters(
        self, proc_text: str, parameters: list[SQLParameter]
    ) -> None:
        """Extract parameters from procedure definition."""
        import re

        # First, extract the parameter section from the procedure/function definition
        # Look for the parameter list in parentheses after the procedure/function name
        param_section_match = re.search(
            r"(?:PROCEDURE|FUNCTION)\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(([^)]*)\)",
            proc_text,
            re.IGNORECASE | re.DOTALL,
        )

        if not param_section_match:
            return

        param_section = param_section_match.group(1).strip()
        if not param_section:
            return

        # Look for parameter patterns like: IN param_name TYPE
        # Only search within the parameter section to avoid SQL statement content
        param_matches = re.findall(
            r"(?:IN|OUT|INOUT)?\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+([A-Z]+(?:\([^)]*\))?)",
            param_section,
            re.IGNORECASE,
        )
        for match in param_matches:
            param_name = match[0]
            data_type = match[1]

            # Skip common SQL keywords and column names that might be incorrectly matched
            if param_name.upper() in (
                "SELECT",
                "FROM",
                "WHERE",
                "INTO",
                "VALUES",
                "SET",
                "UPDATE",
                "INSERT",
                "DELETE",
                "CREATED_AT",
                "UPDATED_AT",
                "ID",
                "NAME",
                "EMAIL",
                "STATUS",
                "IN",
                "OUT",
                "INOUT",
            ):
                continue

            # Determine direction from the original text
            direction = "IN"  # Default
            if f"OUT {param_name}" in param_section:
                direction = "OUT"
            elif f"INOUT {param_name}" in param_section:
                direction = "INOUT"

            parameter = SQLParameter(
                name=param_name,
                data_type=data_type,
                direction=direction,
            )
            parameters.append(parameter)

    def _extract_procedure_dependencies(
        self, proc_node: "tree_sitter.Node", dependencies: list[str]
    ) -> None:
        """Extract table dependencies from procedure body."""
        for node in self._traverse_nodes(proc_node):
            if node.type == "object_reference":
                for child in node.children:
                    if child.type == "identifier":
                        table_name = self._get_node_text(child).strip()
                        if table_name and table_name not in dependencies:
                            # Simple heuristic: if it's referenced in FROM, UPDATE, INSERT, etc.
                            dependencies.append(table_name)

    def _extract_sql_functions_enhanced(
        self, root_node: "tree_sitter.Node", sql_elements: list[SQLElement]
    ) -> None:
        """Extract CREATE FUNCTION statements with enhanced metadata."""
        # Use regex-based approach to find all functions in the source code
        import re

        lines = self.source_code.split("\n")

        # Pattern to match CREATE FUNCTION statements
        function_pattern = re.compile(
            r"^\s*CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            re.IGNORECASE | re.MULTILINE,
        )

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.upper().startswith("CREATE") and "FUNCTION" in line.upper():
                match = function_pattern.match(lines[i])
                if match:
                    func_name = match.group(1)

                    # Skip common column names and SQL keywords that might be incorrectly matched
                    if func_name.upper() in (
                        "CREATED_AT",
                        "UPDATED_AT",
                        "ID",
                        "NAME",
                        "EMAIL",
                        "STATUS",
                        "CURRENT_TIMESTAMP",
                        "NOW",
                        "SYSDATE",
                    ):
                        i += 1
                        continue

                    start_line = i + 1

                    # Find the end of the function (look for END; or END$$)
                    end_line = start_line
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip().upper() in ["END;", "END$$", "END"]:
                            end_line = j + 1
                            break
                        elif lines[j].strip().upper().startswith("END;"):
                            end_line = j + 1
                            break

                    # Extract the full function text
                    func_lines = lines[i:end_line]
                    raw_text = "\n".join(func_lines)

                    parameters = []
                    dependencies = []
                    return_type = None

                    # Extract parameters, return type and dependencies from the text
                    self._extract_procedure_parameters(raw_text, parameters)

                    # Extract return type
                    returns_match = re.search(
                        r"RETURNS\s+([A-Z]+(?:\([^)]*\))?)", raw_text, re.IGNORECASE
                    )
                    if returns_match:
                        return_type = returns_match.group(1)

                    try:
                        function = SQLFunction(
                            name=func_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                            parameters=parameters,
                            dependencies=dependencies,
                            return_type=return_type,
                        )
                        sql_elements.append(function)
                        log_debug(
                            f"Extracted function: {func_name} at lines {start_line}-{end_line}"
                        )
                    except Exception as e:
                        log_debug(f"Failed to extract enhanced function: {e}")

                    i = end_line
                else:
                    i += 1
            else:
                i += 1

        # Also try the original tree-sitter approach as fallback
        for node in self._traverse_nodes(root_node):
            if node.type == "create_function":
                func_name = None
                parameters = []
                return_type = None
                dependencies = []

                # Extract function name
                for child in node.children:
                    if child.type == "object_reference":
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                func_name = self._get_node_text(subchild).strip()
                                # Validate function name
                                if func_name and self._is_valid_identifier(func_name):
                                    break
                                else:
                                    func_name = None
                        if func_name:
                            break

                if func_name:
                    # Check if this function was already extracted by regex
                    already_extracted = any(
                        hasattr(elem, "name") and elem.name == func_name
                        for elem in sql_elements
                        if hasattr(elem, "sql_element_type")
                        and elem.sql_element_type.value == "function"
                    )

                    if not already_extracted:
                        # Extract return type and other metadata
                        self._extract_function_metadata(
                            node, parameters, return_type, dependencies
                        )

                        try:
                            start_line = node.start_point[0] + 1
                            end_line = node.end_point[0] + 1
                            raw_text = self._get_node_text(node)

                            function = SQLFunction(
                                name=func_name,
                                start_line=start_line,
                                end_line=end_line,
                                raw_text=raw_text,
                                language="sql",
                                parameters=parameters,
                                dependencies=dependencies,
                                return_type=return_type,
                            )
                            sql_elements.append(function)
                        except Exception as e:
                            log_debug(f"Failed to extract enhanced function: {e}")

    def _extract_function_metadata(
        self,
        func_node: "tree_sitter.Node",
        parameters: list[SQLParameter],
        return_type: str | None,
        dependencies: list[str],
    ) -> None:
        """Extract function metadata including parameters and return type."""
        func_text = self._get_node_text(func_node)

        # Extract return type
        import re

        returns_match = re.search(
            r"RETURNS\s+([A-Z]+(?:\([^)]*\))?)", func_text, re.IGNORECASE
        )
        if returns_match:
            _return_type = returns_match.group(1)  # Reserved for future use

        # Extract parameters (similar to procedure parameters)
        self._extract_procedure_parameters(func_text, parameters)

        # Extract dependencies
        self._extract_procedure_dependencies(func_node, dependencies)

    def _extract_sql_triggers(
        self, root_node: "tree_sitter.Node", sql_elements: list[SQLElement]
    ) -> None:
        """Extract CREATE TRIGGER statements with enhanced metadata."""
        for node in self._traverse_nodes(root_node):
            if node.type == "ERROR":
                has_create = False
                has_trigger = False
                trigger_name = None
                table_name = None
                trigger_timing = None
                trigger_event = None
                found_trigger_keyword = False

                for child in node.children:
                    if child.type == "keyword_create":
                        has_create = True
                    elif child.type == "keyword_trigger":
                        has_trigger = True
                        found_trigger_keyword = True
                    elif (
                        child.type == "object_reference"
                        and found_trigger_keyword
                        and not trigger_name
                    ):
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                extracted_name = self._get_node_text(subchild).strip()
                                # Validate trigger name
                                if extracted_name and self._is_valid_identifier(
                                    extracted_name
                                ):
                                    trigger_name = extracted_name
                                break
                        break

                # Use regex to extract trigger name for better accuracy
                if has_create and has_trigger and not trigger_name:
                    import re

                    trigger_text = self._get_node_text(node)
                    # First verify this really is a CREATE TRIGGER statement
                    if not re.match(
                        r"^\s*CREATE\s+TRIGGER\s+", trigger_text, re.IGNORECASE
                    ):
                        continue  # Skip if not a CREATE TRIGGER statement

                    # Pattern: CREATE TRIGGER trigger_name
                    trigger_pattern = re.search(
                        r"CREATE\s+TRIGGER\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        trigger_text,
                        re.IGNORECASE,
                    )
                    if trigger_pattern:
                        extracted_name = trigger_pattern.group(1)
                        if self._is_valid_identifier(extracted_name):
                            trigger_name = extracted_name

                # Skip invalid trigger names (too short or common SQL keywords)
                if trigger_name and len(trigger_name) <= 2:
                    trigger_name = None

                # Skip common SQL keywords that might be incorrectly identified
                if trigger_name and trigger_name.upper() in (
                    "KEY",
                    "AUTO_INCREMENT",
                    "PRIMARY",
                    "FOREIGN",
                    "INDEX",
                    "UNIQUE",
                ):
                    trigger_name = None

                # Extract trigger metadata from text
                if has_create and has_trigger and trigger_name:
                    trigger_text = self._get_node_text(node)
                    self._extract_trigger_metadata(
                        trigger_text, trigger_timing, trigger_event, table_name
                    )

                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = self._get_node_text(node)

                        trigger = SQLTrigger(
                            name=trigger_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                            table_name=table_name,
                            trigger_timing=trigger_timing,
                            trigger_event=trigger_event,
                            dependencies=[table_name] if table_name else [],
                        )
                        sql_elements.append(trigger)
                    except Exception as e:
                        log_debug(f"Failed to extract enhanced trigger: {e}")

    def _extract_trigger_metadata(
        self,
        trigger_text: str,
        timing: str | None,
        event: str | None,
        table_name: str | None,
    ) -> None:
        """Extract trigger timing, event, and target table."""
        import re

        # Extract timing (BEFORE/AFTER)
        timing_match = re.search(r"(BEFORE|AFTER)", trigger_text, re.IGNORECASE)
        if timing_match:
            _timing = timing_match.group(1).upper()  # Reserved for future use

        # Extract event (INSERT/UPDATE/DELETE)
        event_match = re.search(r"(INSERT|UPDATE|DELETE)", trigger_text, re.IGNORECASE)
        if event_match:
            _event = event_match.group(1).upper()  # Reserved for future use

        # Extract target table
        table_match = re.search(
            r"ON\s+([a-zA-Z_][a-zA-Z0-9_]*)", trigger_text, re.IGNORECASE
        )
        if table_match:
            _table_name = table_match.group(1)  # Reserved for future use

    def _extract_sql_indexes(
        self, root_node: "tree_sitter.Node", sql_elements: list[SQLElement]
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
        index_node: "tree_sitter.Node",
        index: "SQLIndex",
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


class SQLPlugin(LanguagePlugin):
    """
    SQL language plugin implementation.

    Provides SQL language support for tree-sitter-analyzer, enabling analysis
    of SQL files including database schema definitions, stored procedures,
    functions, triggers, and indexes.

    The plugin follows the standard LanguagePlugin interface and integrates
    with the plugin manager for automatic discovery. It requires the
    tree-sitter-sql package to be installed (available as optional dependency).
    """

    def __init__(self) -> None:
        """
        Initialize the SQL language plugin.

        Sets up the extractor instance and caches for tree-sitter language
        loading. The plugin supports .sql file extensions.
        """
        super().__init__()
        self.extractor = SQLElementExtractor()
        self.language = "sql"  # Add language property for test compatibility
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None  # Cache for tree-sitter language

    def get_language_name(self) -> str:
        """Get the language name."""
        return "sql"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".sql"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return SQLElementExtractor()

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """
        Analyze SQL file and return structured results.

        Parses the SQL file using tree-sitter-sql, extracts database elements
        (tables, views, procedures, functions, triggers, indexes), and returns
        an AnalysisResult with all extracted information.

        Args:
            file_path: Path to the SQL file to analyze
            request: Analysis request configuration

        Returns:
            AnalysisResult containing extracted elements, line counts, and metadata.
            Returns error result if tree-sitter-sql is not available or parsing fails.
        """
        from ..models import AnalysisResult

        if not TREE_SITTER_AVAILABLE:
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message="Tree-sitter library not available.",
            )

        try:
            # Read the file content using safe encoding detection
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            # Get tree-sitter language and parse
            language = self.get_tree_sitter_language()
            if language is None:
                # Return empty result if language loading fails
                return AnalysisResult(
                    file_path=file_path,
                    language="sql",
                    line_count=len(file_content.split("\n")),
                    elements=[],
                    source_code=file_content,
                    success=False,
                    error_message="tree-sitter-sql not available. Install with: pip install tree-sitter-analyzer[sql]",
                )

            # Parse the code
            parser = tree_sitter.Parser()

            # Set language using the appropriate method
            if hasattr(parser, "set_language"):
                parser.set_language(language)
            elif hasattr(parser, "language"):
                parser.language = language
            else:
                try:
                    parser = tree_sitter.Parser(language)
                except Exception as e:
                    log_error(f"Failed to create parser with language: {e}")
                    return AnalysisResult(
                        file_path=file_path,
                        language="sql",
                        line_count=len(file_content.split("\n")),
                        elements=[],
                        source_code=file_content,
                        error_message=f"Parser creation failed: {e}",
                        success=False,
                    )

            tree = parser.parse(file_content.encode("utf-8"))

            # Extract SQL elements using enhanced extractor
            all_elements = self.extractor.extract_sql_elements(tree, file_content)

            # Count nodes in the AST tree
            node_count = (
                self._count_tree_nodes(tree.root_node) if tree and tree.root_node else 0
            )

            return AnalysisResult(
                file_path=file_path,
                language="sql",
                line_count=len(file_content.split("\n")),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
            )

        except Exception as e:
            log_error(f"Error analyzing SQL file {file_path}: {e}")
            # Return empty result on error
            return AnalysisResult(
                file_path=file_path,
                language="sql",
                line_count=0,
                elements=[],
                source_code="",
                error_message=str(e),
                success=False,
            )

    def _count_tree_nodes(self, node: Any) -> int:
        """
        Recursively count nodes in the AST tree.

        Args:
            node: Tree-sitter node

        Returns:
            Total number of nodes
        """
        if node is None:
            return 0

        count = 1  # Count current node
        if hasattr(node, "children"):
            for child in node.children:
                count += self._count_tree_nodes(child)
        return count

    def get_tree_sitter_language(self) -> Any | None:
        """
        Get the tree-sitter language for SQL.

        Loads and caches the tree-sitter-sql language object. Returns None
        if tree-sitter-sql is not installed, allowing graceful degradation.

        Returns:
            Tree-sitter Language object for SQL, or None if not available
        """
        if self._cached_language is not None:
            return self._cached_language

        try:
            # tree-sitter-sql is an optional dependency
            import tree_sitter_sql

            # Get the language function result
            caps_or_lang = tree_sitter_sql.language()

            # Convert to proper Language object if needed
            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
                # Already a Language object
                self._cached_language = caps_or_lang
            else:
                # PyCapsule - convert to Language object
                try:
                    # Use modern tree-sitter API - PyCapsule should be passed to Language constructor
                    self._cached_language = tree_sitter.Language(caps_or_lang)
                except Exception as e:
                    log_error(f"Failed to create Language object from PyCapsule: {e}")
                    return None

            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-sql not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for SQL: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """
        Extract all elements from SQL code for test compatibility.

        Convenience method that extracts all element types and returns them
        in a dictionary format. Used primarily for testing and compatibility
        with existing test infrastructure.

        Args:
            tree: Tree-sitter AST tree, or None
            source_code: Original SQL source code

        Returns:
            Dictionary with keys: functions, classes, variables, imports
            Each value is a list of extracted elements
        """
        if tree is None:
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
            }

        return {
            "functions": self.extractor.extract_functions(tree, source_code),
            "classes": self.extractor.extract_classes(tree, source_code),
            "variables": self.extractor.extract_variables(tree, source_code),
            "imports": self.extractor.extract_imports(tree, source_code),
        }
