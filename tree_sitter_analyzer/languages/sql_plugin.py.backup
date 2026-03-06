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
from ..platform_compat.adapter import CompatibilityAdapter
from ..platform_compat.detector import PlatformDetector
from ..platform_compat.profiles import BehaviorProfile
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

                # Apply platform compatibility adapter if available
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

                log_debug(f"Extracted {len(sql_elements)} SQL elements with metadata")
            except Exception as e:
                log_error(
                    f"Error during enhanced SQL extraction on {self.platform_info}: {e}"
                )
                log_error(
                    "Suggestion: Check platform compatibility documentation or enable diagnostic mode for more details."
                )
                # Return empty list or partial results to allow other languages to continue
                if not sql_elements:
                    sql_elements = []

        return sql_elements

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
                    # Use finditer to find ALL procedures in the ERROR node
                    import re

                    matches = re.finditer(
                        r"CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        node_text,
                        re.IGNORECASE,
                    )

                    for match in matches:
                        proc_name = match.group(1)

                        if proc_name:
                            try:
                                # Calculate start line based on match position
                                newlines_before = node_text[: match.start()].count("\n")
                                start_line = node.start_point[0] + 1 + newlines_before
                                end_line = node.end_point[0] + 1

                                # Use specific text for this procedure if possible,
                                # but for legacy extraction we often just use the whole node text
                                # or we could slice it. For now, keeping whole node text is safer for legacy
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
                # Since multiple triggers might be lumped into one ERROR node,
                # we need to scan all children or use regex.
                # Using regex on the node text is more robust for ERROR nodes.

                node_text = self._get_node_text(node)
                if not node_text:
                    continue

                node_text_upper = node_text.upper()
                if "CREATE" in node_text_upper and "TRIGGER" in node_text_upper:
                    import re

                    # Regex to find CREATE TRIGGER statements
                    # Matches: CREATE TRIGGER [IF NOT EXISTS] trigger_name
                    matches = re.finditer(
                        r"CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
                        node_text,
                        re.IGNORECASE,
                    )

                    for match in matches:
                        trigger_name = match.group(1)

                        if trigger_name and self._is_valid_identifier(trigger_name):
                            # Skip common SQL keywords
                            if trigger_name.upper() in (
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
                                "CONSTRAINT",
                                "CHECK",
                                "DEFAULT",
                                "REFERENCES",
                                "ON",
                                "UPDATE",
                                "DELETE",
                                "INSERT",
                                "BEFORE",
                                "AFTER",
                                "INSTEAD",
                                "OF",
                            ):
                                continue

                            try:
                                # Calculate start line based on match position
                                newlines_before = node_text[: match.start()].count("\n")
                                start_line = node.start_point[0] + 1 + newlines_before
                                end_line = node.end_point[0] + 1

                                # Use the whole error node text as raw text for now
                                raw_text = node_text

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
                from ..models import SQLColumn, SQLConstraint

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
        self, view_node: "tree_sitter.Node", source_tables: list[str]
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

                    from ..models import SQLParameter

                    proc_parameters: list[SQLParameter] = []
                    proc_dependencies: list[str] = []

                    # Extract parameters and dependencies from the text
                    self._extract_procedure_parameters(raw_text, proc_parameters)

                    try:
                        procedure = SQLProcedure(
                            name=proc_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                            parameters=proc_parameters,
                            dependencies=proc_dependencies,
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
                    # Extract procedure name
                    # Use finditer to find ALL procedures in the ERROR node
                    matches = re.finditer(
                        r"CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        node_text,
                        re.IGNORECASE,
                    )

                    for match in matches:
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
                            # Note: This extracts parameters from the WHOLE node text, which might be wrong
                            # if there are multiple procedures. Ideally we should slice the text.
                            # But _extract_procedure_parameters parses the whole text.
                            # For now, we use the text starting from the match.
                            current_proc_text = node_text[match.start() :]

                            # Reset parameters and dependencies for each procedure
                            iteration_parameters: list[SQLParameter] = []
                            iteration_dependencies: list[str] = []

                            self._extract_procedure_parameters(
                                current_proc_text, iteration_parameters
                            )

                            # Extract dependencies (table references)
                            # This still uses the whole node for dependencies, which is hard to fix without
                            # proper parsing, but acceptable for fallback.
                            self._extract_procedure_dependencies(
                                node, iteration_dependencies
                            )

                            try:
                                # Calculate start line
                                newlines_before = node_text[: match.start()].count("\n")
                                start_line = node.start_point[0] + 1 + newlines_before
                                end_line = node.end_point[0] + 1

                                # Use current_proc_text as raw_text
                                raw_text = current_proc_text

                                procedure = SQLProcedure(
                                    name=proc_name,
                                    start_line=start_line,
                                    end_line=end_line,
                                    raw_text=raw_text,
                                    language="sql",
                                    parameters=iteration_parameters,
                                    dependencies=iteration_dependencies,
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
        # Ensure IN/OUT/INOUT is followed by space to avoid ambiguity
        param_matches = re.findall(
            r"(?:(?:IN|OUT|INOUT)\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+([A-Z]+(?:\([^)]*\))?)",
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

        # Pattern to match CREATE FUNCTION statements - requires opening parenthesis
        function_pattern = re.compile(
            r"^\s*CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            re.IGNORECASE,
        )

        i = 0
        inside_function = False

        while i < len(lines):
            # Skip lines if we're inside a function body
            if inside_function:
                if lines[i].strip().upper() in ["END;", "END$"] or lines[
                    i
                ].strip().upper().startswith("END;"):
                    inside_function = False
                i += 1
                continue

            # Only check for CREATE FUNCTION when not inside a function
            match = function_pattern.match(lines[i])
            if match:
                func_name = match.group(1)

                # Validate the function name using the centralized validation method
                if not self._is_valid_identifier(func_name):
                    i += 1
                    continue

                start_line = i + 1
                inside_function = True

                # Find the end of the function (look for END; or END$$)
                end_line = start_line
                nesting_level = 0

                for j in range(i + 1, len(lines)):
                    line_stripped = lines[j].strip().upper()

                    # Skip comments to avoid false positives
                    if line_stripped.startswith("--") or line_stripped.startswith("#"):
                        continue

                    # Handle nesting of BEGIN ... END blocks
                    # This is a heuristic: if we see BEGIN, we expect a matching END;
                    # We use word boundaries to avoid matching BEGIN in other contexts if possible
                    if re.search(r"\bBEGIN\b", line_stripped):
                        nesting_level += 1

                    is_end = False
                    if line_stripped in ["END;", "END$", "END"]:
                        is_end = True
                    elif line_stripped.startswith("END;"):
                        is_end = True

                    if is_end:
                        if nesting_level > 0:
                            nesting_level -= 1

                        if nesting_level == 0:
                            end_line = j + 1
                            inside_function = False
                            break

                # Extract the full function text
                func_lines = lines[i:end_line]
                raw_text = "\n".join(func_lines)

                from ..models import SQLParameter

                parameters: list[SQLParameter] = []
                dependencies: list[str] = []
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

        # Also try the original tree-sitter approach as fallback
        for node in self._traverse_nodes(root_node):
            if node.type == "create_function":
                func_name = None
                return_type = None

                # Extract function name - only from the FIRST object_reference child
                # This should be the function name, not references within the function body
                found_first_object_ref = False
                for child in node.children:
                    if child.type == "object_reference" and not found_first_object_ref:
                        found_first_object_ref = True
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                func_name = self._get_node_text(subchild).strip()
                                # Validate function name using centralized validation
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
        import re

        # Use self.source_code which is set by parent method _extract_sql_elements
        # This is more reliable than _get_node_text(root_node) which may fail
        # on some platforms due to encoding or byte offset issues
        source_code = self.source_code

        if not source_code:
            log_debug("WARNING: source_code is empty in _extract_sql_triggers")
            return

        # Track processed triggers by name to avoid duplicates
        processed_triggers = set()

        # Use regex on the full source to find all triggers with accurate positions
        trigger_pattern = re.compile(
            r"CREATE\s+TRIGGER\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE | re.MULTILINE
        )

        trigger_matches = list(trigger_pattern.finditer(source_code))
        log_debug(f"Found {len(trigger_matches)} CREATE TRIGGER statements in source")

        for match in trigger_matches:
            trigger_name = match.group(1)

            # Skip if already processed
            if trigger_name in processed_triggers:
                continue

            if not self._is_valid_identifier(trigger_name):
                continue

            # Skip invalid trigger names (too short or common SQL keywords)
            if len(trigger_name) <= 2:
                continue

            # Skip common SQL keywords that might be incorrectly identified
            if trigger_name.upper() in (
                "KEY",
                "AUTO_INCREMENT",
                "PRIMARY",
                "FOREIGN",
                "INDEX",
                "UNIQUE",
            ):
                continue

            # Mark as processed
            processed_triggers.add(trigger_name)

            # Calculate start line (1-indexed)
            start_line = source_code[: match.start()].count("\n") + 1

            # Find the end of this trigger statement (looking for the END keyword followed by semicolon)
            trigger_start_pos = match.start()
            # Search for END; after the trigger definition
            end_pattern = re.compile(r"\bEND\s*;", re.IGNORECASE)
            end_match = end_pattern.search(source_code, trigger_start_pos)

            if end_match:
                end_line = source_code[: end_match.end()].count("\n") + 1
                trigger_text = source_code[trigger_start_pos : end_match.end()]
            else:
                # Fallback: use a reasonable default
                end_line = start_line + 20
                trigger_text = source_code[trigger_start_pos : trigger_start_pos + 500]

            # Extract trigger metadata from the extracted text
            trigger_timing, trigger_event, table_name = self._extract_trigger_metadata(
                trigger_text
            )

            try:
                trigger = SQLTrigger(
                    name=trigger_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=trigger_text,
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
    ) -> tuple[str | None, str | None, str | None]:
        """Extract trigger timing, event, and target table."""
        import re

        timing = None
        event = None
        table_name = None

        # Extract timing (BEFORE/AFTER)
        timing_match = re.search(r"(BEFORE|AFTER)", trigger_text, re.IGNORECASE)
        if timing_match:
            timing = timing_match.group(1).upper()

        # Extract event (INSERT/UPDATE/DELETE)
        event_match = re.search(r"(INSERT|UPDATE|DELETE)", trigger_text, re.IGNORECASE)
        if event_match:
            event = event_match.group(1).upper()

        # Extract target table
        table_match = re.search(
            r"ON\s+([a-zA-Z_][a-zA-Z0-9_]*)", trigger_text, re.IGNORECASE
        )
        if table_match:
            table_name = table_match.group(1)

        return timing, event, table_name

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

    def __init__(self, diagnostic_mode: bool = False) -> None:
        """
        Initialize the SQL language plugin.

        Sets up the extractor instance and caches for tree-sitter language
        loading. The plugin supports .sql file extensions.
        """
        super().__init__()
        self.diagnostic_mode = diagnostic_mode
        self.extractor = SQLElementExtractor(diagnostic_mode=diagnostic_mode)
        self.language = "sql"  # Add language property for test compatibility
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None  # Cache for tree-sitter language

        # Platform compatibility initialization
        self.platform_info = None
        try:
            self.platform_info = PlatformDetector.detect()
            from ..plugins.base import ElementExtractor

            if isinstance(self.extractor, ElementExtractor):
                self.extractor.platform_info = self.platform_info

            platform_info = self.platform_info
            profile = BehaviorProfile.load(platform_info.platform_key)

            if self.diagnostic_mode:
                log_debug(f"Diagnostic: Platform detected: {platform_info}")
                if profile:
                    log_debug(
                        f"Diagnostic: Loaded SQL behavior profile for {platform_info.platform_key}"
                    )
                    log_debug(f"Diagnostic: Profile rules: {profile.adaptation_rules}")
                else:
                    log_debug(
                        f"Diagnostic: No SQL behavior profile found for {platform_info.platform_key}"
                    )
            elif profile:
                log_debug(
                    f"Loaded SQL behavior profile for {platform_info.platform_key}"
                )
            else:
                log_debug(
                    f"No SQL behavior profile found for {platform_info.platform_key}, using defaults"
                )

            self.adapter = CompatibilityAdapter(profile)
            self.extractor.set_adapter(self.adapter)
        except Exception as e:
            log_error(f"Failed to initialize SQL platform compatibility: {e}")
            self.adapter = CompatibilityAdapter(None)  # Use default adapter
            self.extractor.set_adapter(self.adapter)

    def get_tree_sitter_language(self) -> Any:
        """
        Get the tree-sitter language object for SQL.

        Returns:
            The tree-sitter language object.

        Raises:
            RuntimeError: If tree-sitter-sql is not installed.
        """
        if self._cached_language:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_sql

            self._cached_language = tree_sitter.Language(tree_sitter_sql.language())
            return self._cached_language
        except ImportError as e:
            raise RuntimeError(
                "tree-sitter-sql is required for SQL analysis but not installed."
            ) from e

    def get_language_name(self) -> str:
        """Get the language name."""
        return "sql"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".sql"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return SQLElementExtractor()

    def extract_elements(self, tree: Any, source_code: str) -> dict[str, list[Any]]:
        """
        Legacy method for extracting elements.
        Maintained for backward compatibility and testing.

        Args:
            tree: Tree-sitter AST tree
            source_code: Source code string

        Returns:
            Dictionary with keys 'functions', 'classes', 'variables', 'imports'
        """
        elements = self.extractor.extract_sql_elements(tree, source_code)

        result: dict[str, Any] = {
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
        }

        for element in elements:
            if element.element_type in ["function", "procedure", "trigger"]:
                result["functions"].append(element)
            elif element.element_type in ["class", "table", "view"]:
                result["classes"].append(element)
            elif element.element_type in ["variable", "index"]:
                result["variables"].append(element)
            elif element.element_type == "import":
                result["imports"].append(element)

        return result

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """
        Analyze SQL file and return structured results.

        Parses the SQL file using tree-sitter-sql, extracts database elements
        (tables, views, procedures, functions, triggers, indexes), and returns
        an AnalysisResult with all extracted information.

        Args:
            file_path: Path to the file to analyze
            request: Analysis request object

        Returns:
            AnalysisResult object containing extracted elements
        """
        from ..core.parser import Parser
        from ..models import AnalysisResult

        try:
            # Read file content
            with open(file_path, encoding="utf-8") as f:
                source_code = f.read()

            # Parse using core parser
            parser = Parser()
            parse_result = parser.parse_code(source_code, "sql", file_path)

            if not parse_result.success:
                return AnalysisResult(
                    file_path=file_path,
                    language="sql",
                    line_count=len(source_code.splitlines()),
                    elements=[],
                    node_count=0,
                    query_results={},
                    source_code=source_code,
                    success=False,
                    error_message=parse_result.error_message,
                )

            # Extract elements
            elements = []
            if parse_result.tree:
                elements = self.extractor.extract_sql_elements(
                    parse_result.tree, source_code
                )

            # Create result
            return AnalysisResult(
                file_path=file_path,
                language="sql",
                line_count=len(source_code.splitlines()),
                elements=elements,
                node_count=(
                    parse_result.tree.root_node.end_byte if parse_result.tree else 0
                ),
                query_results={},
                source_code=source_code,
                success=True,
                error_message=None,
            )

        except Exception as e:
            log_error(f"Failed to analyze SQL file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message=str(e),
            )
