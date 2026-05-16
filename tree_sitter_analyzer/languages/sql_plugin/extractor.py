#!/usr/bin/env python3
"""
SQL Language Plugin

Provides SQL-specific parsing and element extraction functionality.
Supports extraction of tables, views, stored procedures, functions, triggers, and indexes.
"""

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter


try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


from ...encoding_utils import extract_text_slice, safe_encode
from ...models import (
    Class,
    Function,
    Import,
    SQLElement,
    SQLIndex,
    SQLTrigger,
    Variable,
)
from ...platform_compat.adapter import CompatibilityAdapter
from ...platform_compat.detector import PlatformDetector  # noqa: F401
from ...plugins.base import ElementExtractor
from ...utils import log_debug, log_error
from .element_validator import validate_and_fix_elements
from .function_extractor import (
    _extract_function_metadata,
    extract_sql_functions_enhanced,
)
from .identifier_validator import is_valid_identifier as _is_valid_identifier_external
from .index_extractor import extract_sql_indexes
from .procedure_extractor import extract_procedure_parameters, extract_sql_procedures
from .table_extractor import (
    _parse_column_definition,
    _split_column_definitions,
    extract_sql_tables,
)
from .view_extractor import extract_sql_views


# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
# Section: module imports and setup
# Section: class definitions
# Section: public API methods
# Section: internal helper methods
# Section: data processing pipeline
# Section: output formatting
# Section: error handling
class SQLElementExtractor(ElementExtractor):
    """
    SQL-specific element extractor.

    This extractor parses SQL AST and extracts database elements, mapping them
    to the unified element model:
    - Tables and Views → Class elements
    - Stored Procedures, Functions, Triggers → Function elements
    - Indexes → Variable elements
    - Schema references → Import elements
    """

    def __init__(self, diagnostic_mode: bool = False) -> None:
        super().__init__()
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.diagnostic_mode = diagnostic_mode
        self.platform_info = None

        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[int] = set()
        self._file_encoding: str | None = None

        self.adapter: CompatibilityAdapter | None = None

    # Process: set_adapter
    def set_adapter(self, adapter: CompatibilityAdapter) -> None:
        """Set the compatibility adapter."""
        self.adapter = adapter

    # Extract elements from AST: extract_sql_elements
    def extract_sql_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[SQLElement]:
        """Extract all SQL elements with enhanced metadata."""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        sql_elements: list[SQLElement] = []

        if tree is not None and tree.root_node is not None:
            try:
                self._extract_sql_tables(tree.root_node, sql_elements)
                self._extract_sql_views(tree.root_node, sql_elements)
                self._extract_sql_procedures(tree.root_node, sql_elements)
                self._extract_sql_functions_enhanced(tree.root_node, sql_elements)
                self._extract_sql_triggers(tree.root_node, sql_elements)
                self._extract_sql_indexes(tree.root_node, sql_elements)

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

                sql_elements = self._validate_and_fix_elements(sql_elements)

                log_debug(f"Extracted {len(sql_elements)} SQL elements with metadata")
            except Exception as e:
                log_error(
                    f"Error during enhanced SQL extraction on {self.platform_info}: {e}"
                )
                log_error(
                    "Suggestion: Check platform compatibility documentation or enable diagnostic mode for more details."
                )
                if not sql_elements:
                    sql_elements = []

        return sql_elements

    # Process: _validate_and_fix_elements
    def _validate_and_fix_elements(
        self, elements: list[SQLElement]
    ) -> list[SQLElement]:
        return validate_and_fix_elements(elements, self.source_code)

    # Extract elements from AST: extract_functions
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract stored procedures, functions, and triggers from SQL code."""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        if tree is not None and tree.root_node is not None:
            try:
                self._extract_procedures(tree.root_node, functions)
                self._extract_sql_functions(tree.root_node, functions)
                self._extract_triggers(tree.root_node, functions)
                log_debug(
                    f"Extracted {len(functions)} SQL functions/procedures/triggers"
                )
            except Exception as e:
                log_debug(f"Error during function extraction: {e}")

        return functions

    # Extract elements from AST: extract_classes
    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract tables and views from SQL code."""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        if tree is not None and tree.root_node is not None:
            try:
                self._extract_tables(tree.root_node, classes)
                self._extract_views(tree.root_node, classes)
                log_debug(f"Extracted {len(classes)} SQL tables/views")
            except Exception as e:
                log_debug(f"Error during class extraction: {e}")

        return classes

    # Extract elements from AST: extract_variables
    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract indexes from SQL code."""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                self._extract_indexes(tree.root_node, variables)
                log_debug(f"Extracted {len(variables)} SQL indexes")
            except Exception as e:
                log_debug(f"Error during variable extraction: {e}")

        # Return result
        return variables

    # Extract elements from AST: extract_imports
    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract schema references and dependencies from SQL code."""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        imports: list[Import] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                self._extract_schema_references(tree.root_node, imports)
                log_debug(f"Extracted {len(imports)} SQL schema references")
            except Exception as e:
                log_debug(f"Error during import extraction: {e}")

        # Return result
        return imports

    # ---------------------------------------------------------------
    # Core utilities
    # ---------------------------------------------------------------

    def _reset_caches(self) -> None:
        self._node_text_cache.clear()
        self._processed_nodes.clear()

    # Process: _get_node_text
    def _get_node_text(self, node: "tree_sitter.Node") -> str:
        """Get text content from a tree-sitter node with caching."""
        cache_key = (node.start_byte, node.end_byte)

        # Check: cache_key in self._node_text_cache
        if cache_key in self._node_text_cache:
            # Return result
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte
            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)

            # Check: text
            if text:
                self._node_text_cache[cache_key] = text
                # Return result
                return text
        except Exception as e:
            log_debug(f"Error in _get_node_text: {e}")

        # Fallback to line-based extraction
        try:
            start_point = node.start_point
            end_point = node.end_point

            # Check: start_point[0] < 0 or start_point[0] >=
            if start_point[0] < 0 or start_point[0] >= len(self.content_lines):
                # Return result
                return ""

            # Check: end_point[0] < 0 or end_point[0] >= len(
            if end_point[0] < 0 or end_point[0] >= len(self.content_lines):
                # Return result
                return ""

            # Check: start_point[0] == end_point[0]
            if start_point[0] == end_point[0]:
                line = self.content_lines[start_point[0]]
                start_col = max(0, min(start_point[1], len(line)))
                end_col = max(start_col, min(end_point[1], len(line)))
                result: str = line[start_col:end_col]
                self._node_text_cache[cache_key] = result
                # Return result
                return result
            else:
                lines = []
                for i in range(
                    start_point[0], min(end_point[0] + 1, len(self.content_lines))
                ):
                    # Check: i < len(self.content_lines)
                    if i < len(self.content_lines):
                        line = self.content_lines[i]
                        # Check: i == start_point[0] and i == end_point[0
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
                # Return result
                return result
        except Exception as fallback_error:
            log_debug(f"Fallback text extraction also failed: {fallback_error}")
            # Return result
            return ""

    # Process: _traverse_nodes
    def _traverse_nodes(self, node: "tree_sitter.Node") -> Iterator["tree_sitter.Node"]:
        yield node
        # Check: hasattr(node, "children")
        if hasattr(node, "children"):
            # Iterate over child
            for child in node.children:
                yield from self._traverse_nodes(child)

    # Process: _is_valid_identifier
    def _is_valid_identifier(self, name: str) -> bool:
        # Return result
        return _is_valid_identifier_external(name)

    # ---------------------------------------------------------------
    # Enhanced extraction delegates (backward-compatible test surface)
    # ---------------------------------------------------------------

    def _extract_sql_tables(
        self, root_node: "tree_sitter.Node", sql_elements: list[Any]
    ) -> None:
        """Extract enhanced SQL table elements."""
        extract_sql_tables(
            root_node,
            self._traverse_nodes,
            self._get_node_text,
            sql_elements,
        )

    def _extract_sql_views(
        self, root_node: "tree_sitter.Node", sql_elements: list[Any]
    ) -> None:
        """Extract enhanced SQL view elements."""
        extract_sql_views(
            root_node,
            self._traverse_nodes,
            self._get_node_text,
            self.source_code,
            self.content_lines,
            sql_elements,
        )

    def _extract_sql_procedures(
        self, root_node: "tree_sitter.Node", sql_elements: list[Any]
    ) -> None:
        """Extract enhanced SQL procedure elements."""
        extract_sql_procedures(
            root_node,
            self._traverse_nodes,
            self._get_node_text,
            self.source_code,
            sql_elements,
        )

    def _extract_sql_functions_enhanced(
        self, root_node: "tree_sitter.Node", sql_elements: list[Any]
    ) -> None:
        """Extract enhanced SQL function elements."""
        extract_sql_functions_enhanced(
            root_node,
            self._traverse_nodes,
            self._get_node_text,
            self.source_code,
            sql_elements,
        )

    def _extract_function_metadata(
        self,
        func_node: "tree_sitter.Node",
        parameters: list[Any],
        return_type: str | None,
        dependencies: list[str],
    ) -> None:
        """Extract function metadata using this extractor's node text helper."""
        _extract_function_metadata(
            func_node,
            parameters,
            return_type,
            dependencies,
            self._get_node_text,
        )

    def _extract_procedure_parameters(
        self, proc_text: str, parameters: list[Any]
    ) -> None:
        """Extract procedure parameters."""
        extract_procedure_parameters(proc_text, parameters)

    def _extract_sql_triggers(
        self, root_node: "tree_sitter.Node", sql_elements: list[Any]
    ) -> None:
        """Extract enhanced SQL trigger elements."""
        if not self.source_code:
            log_debug("WARNING: source_code is empty in _extract_sql_triggers")
            return

        processed_triggers: set[str] = set()
        trigger_pattern = re.compile(
            r"CREATE\s+TRIGGER\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            re.IGNORECASE | re.MULTILINE,
        )

        for match in trigger_pattern.finditer(self.source_code):
            trigger_name = match.group(1)
            if (
                trigger_name in processed_triggers
                or not self._is_valid_identifier(trigger_name)
                or len(trigger_name) <= 2
                or trigger_name.upper()
                in {"KEY", "AUTO_INCREMENT", "PRIMARY", "FOREIGN", "INDEX", "UNIQUE"}
            ):
                continue

            processed_triggers.add(trigger_name)
            start_line = self.source_code[: match.start()].count("\n") + 1
            trigger_start = match.start()
            end_match = re.search(
                r"\bEND\s*;", self.source_code[trigger_start:], re.IGNORECASE
            )
            if end_match:
                trigger_end = trigger_start + end_match.end()
                end_line = self.source_code[:trigger_end].count("\n") + 1
                trigger_text = self.source_code[trigger_start:trigger_end]
            else:
                end_line = start_line + 20
                trigger_text = self.source_code[trigger_start : trigger_start + 500]

            timing_match = re.search(r"(BEFORE|AFTER)", trigger_text, re.IGNORECASE)
            event_match = re.search(
                r"(INSERT|UPDATE|DELETE)", trigger_text, re.IGNORECASE
            )
            table_match = re.search(
                r"ON\s+([a-zA-Z_][a-zA-Z0-9_]*)", trigger_text, re.IGNORECASE
            )
            table_name = table_match.group(1) if table_match else None

            try:
                sql_elements.append(
                    SQLTrigger(
                        name=trigger_name,
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=trigger_text,
                        language="sql",
                        table_name=table_name,
                        trigger_timing=timing_match.group(1).upper()
                        if timing_match
                        else None,
                        trigger_event=event_match.group(1).upper()
                        if event_match
                        else None,
                        dependencies=[table_name] if table_name else [],
                    )
                )
            except Exception as e:
                log_debug(f"Failed to extract enhanced trigger: {e}")

    def _extract_sql_indexes(
        self, root_node: "tree_sitter.Node", sql_elements: list[Any]
    ) -> None:
        """Extract enhanced SQL index elements."""
        extract_sql_indexes(
            root_node,
            self._traverse_nodes,
            self._get_node_text,
            self.source_code,
            sql_elements,
        )

    def _extract_indexes_with_regex(
        self, sql_elements: list[Any], processed_indexes: set[str]
    ) -> None:
        """Extract CREATE INDEX statements using regex as fallback."""
        index_pattern = re.compile(
            r"^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+ON\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]+)\)",
            re.IGNORECASE | re.MULTILINE,
        )

        for line_num, line in enumerate(self.source_code.split("\n"), 1):
            stripped = line.strip()
            if (
                not stripped.upper().startswith("CREATE")
                or "INDEX" not in stripped.upper()
            ):
                continue

            match = index_pattern.match(stripped)
            if not match:
                continue

            index_name = match.group(2)
            if index_name in processed_indexes:
                continue

            table_name = match.group(3)
            columns = [col.strip() for col in match.group(4).split(",")]

            try:
                sql_elements.append(
                    SQLIndex(
                        name=index_name,
                        start_line=line_num,
                        end_line=line_num,
                        raw_text=stripped,
                        language="sql",
                        table_name=table_name,
                        indexed_columns=columns,
                        is_unique=match.group(1) is not None,
                        dependencies=[table_name] if table_name else [],
                    )
                )
                processed_indexes.add(index_name)
            except Exception as e:
                log_debug(f"Failed to create regex-extracted index {index_name}: {e}")

    # ---------------------------------------------------------------
    # Legacy extraction methods (used by extract_classes/functions/etc.)
    # ---------------------------------------------------------------

    def _extract_tables(
        self, root_node: "tree_sitter.Node", classes: list[Class]
    ) -> None:
        """Extract CREATE TABLE statements from SQL AST."""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "create_table"
            if node.type == "create_table":
                table_name = None
                # Iterate over child
                for child in node.children:
                    # Check: child.type == "object_reference"
                    if child.type == "object_reference":
                        # Iterate over subchild
                        for subchild in child.children:
                            # Check: subchild.type == "identifier"
                            if subchild.type == "identifier":
                                table_name = self._get_node_text(subchild).strip()
                                # Check: table_name and self._is_valid_identifier
                                if table_name and self._is_valid_identifier(table_name):
                                    break
                                else:
                                    table_name = None
                        # Check: table_name
                        if table_name:
                            break

                # Check: table_name
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

    # Extract elements from AST: _extract_views
    def _extract_views(
        self, root_node: "tree_sitter.Node", classes: list[Class]
    ) -> None:
        """Extract CREATE VIEW statements from SQL AST."""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "create_view"
            if node.type == "create_view":
                raw_text = self._get_node_text(node)
                view_name = None

                # Check: raw_text
                if raw_text:
                    view_match = re.search(
                        r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
                        raw_text,
                        re.IGNORECASE,
                    )
                    # Check: view_match
                    if view_match:
                        potential_name = view_match.group(1).strip()
                        # Check: self._is_valid_identifier(potential_name
                        if self._is_valid_identifier(potential_name):
                            view_name = potential_name

                # Check: not view_name
                if not view_name:
                    # Iterate over child
                    for child in node.children:
                        # Check: child.type == "object_reference"
                        if child.type == "object_reference":
                            # Iterate over subchild
                            for subchild in child.children:
                                # Check: subchild.type == "identifier"
                                if subchild.type == "identifier":
                                    potential_name = self._get_node_text(subchild)
                                    # Check: potential_name
                                    if potential_name:
                                        potential_name = potential_name.strip()
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
                            # Check: view_name
                            if view_name:
                                break

                # Check: view_name
                if view_name:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        # Check: start_line == end_line and self.source_c
                        if start_line == end_line and self.source_code:
                            current_line_idx = start_line - 1
                            found_end = False
                            # Iterate over i
                            for i in range(current_line_idx, len(self.content_lines)):
                                line = self.content_lines[i]
                                # Check: ";" in line
                                if ";" in line:
                                    end_line = i + 1
                                    found_end = True
                                    break

                            # Check: not found_end
                            if not found_end:
                                for i in range(
                                    current_line_idx + 1,
                                    min(len(self.content_lines), current_line_idx + 50),
                                ):
                                    line = self.content_lines[i].strip()
                                    # Check: not line or line.upper().startswith("CRE
                                    if not line or line.upper().startswith("CREATE "):
                                        end_line = i
                                        found_end = True
                                        break

                            # Check: found_end and end_line > start_line
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

    # Extract elements from AST: _extract_procedures
    def _extract_procedures(
        self, root_node: "tree_sitter.Node", functions: list[Function]
    ) -> None:
        """Extract CREATE PROCEDURE statements from SQL AST."""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "ERROR"
            if node.type == "ERROR":
                has_create = False
                node_text = self._get_node_text(node)
                node_text_upper = node_text.upper()

                # Iterate over child
                for child in node.children:
                    # Check: child.type == "keyword_create"
                    if child.type == "keyword_create":
                        has_create = True
                        break

                # Check: has_create and "PROCEDURE" in node_text_
                if has_create and "PROCEDURE" in node_text_upper:
                    matches = re.finditer(
                        r"CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        node_text,
                        re.IGNORECASE,
                    )

                    # Iterate over match
                    for match in matches:
                        proc_name = match.group(1)

                        # Check: proc_name
                        if proc_name:
                            try:
                                newlines_before = node_text[: match.start()].count("\n")
                                start_line = node.start_point[0] + 1 + newlines_before
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

    # Extract elements from AST: _extract_sql_functions
    def _extract_sql_functions(
        self, root_node: "tree_sitter.Node", functions: list[Function]
    ) -> None:
        """Extract CREATE FUNCTION statements from SQL AST."""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "create_function"
            if node.type == "create_function":
                func_name = None
                # Iterate over child
                for child in node.children:
                    # Check: child.type == "object_reference"
                    if child.type == "object_reference":
                        # Iterate over subchild
                        for subchild in child.children:
                            # Check: subchild.type == "identifier"
                            if subchild.type == "identifier":
                                func_name = self._get_node_text(subchild).strip()
                                # Check: func_name and self._is_valid_identifier(
                                if func_name and self._is_valid_identifier(func_name):
                                    break
                                else:
                                    func_name = None
                        break

                # Check: not func_name
                if not func_name:
                    raw_text = self._get_node_text(node)
                    match = re.search(
                        r"CREATE\s+FUNCTION\s+(\w+)\s*\(", raw_text, re.IGNORECASE
                    )
                    # Check: match
                    if match:
                        potential_name = match.group(1).strip()
                        # Check: self._is_valid_identifier(potential_name
                        if self._is_valid_identifier(potential_name):
                            func_name = potential_name

                # Check: func_name
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

    # Extract elements from AST: _extract_triggers
    def _extract_triggers(
        self, root_node: "tree_sitter.Node", functions: list[Function]
    ) -> None:
        """Extract CREATE TRIGGER statements from SQL AST."""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "ERROR"
            if node.type == "ERROR":
                node_text = self._get_node_text(node)
                # Check: not node_text
                if not node_text:
                    continue

                node_text_upper = node_text.upper()
                # Check: "CREATE" in node_text_upper and "TRIGGER
                if "CREATE" in node_text_upper and "TRIGGER" in node_text_upper:
                    matches = re.finditer(
                        r"CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
                        node_text,
                        re.IGNORECASE,
                    )

                    # Iterate over match
                    for match in matches:
                        trigger_name = match.group(1)

                        # Check: trigger_name and self._is_valid_identifi
                        if trigger_name and self._is_valid_identifier(trigger_name):
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
                                newlines_before = node_text[: match.start()].count("\n")
                                start_line = node.start_point[0] + 1 + newlines_before
                                end_line = node.end_point[0] + 1
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

    # Extract elements from AST: _extract_indexes
    def _extract_indexes(
        self, root_node: "tree_sitter.Node", variables: list[Variable]
    ) -> None:
        """Extract CREATE INDEX statements from SQL AST."""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "create_index"
            if node.type == "create_index":
                index_name = None
                # Iterate over child
                for child in node.children:
                    # Check: child.type == "identifier"
                    if child.type == "identifier":
                        index_name = self._get_node_text(child).strip()
                        break

                # Check: index_name
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

    # Extract elements from AST: _extract_schema_references
    def _extract_schema_references(
        self, root_node: "tree_sitter.Node", imports: list[Import]
    ) -> None:
        """Extract schema references (e.g., FROM schema.table)."""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "qualified_name"
            if node.type == "qualified_name":
                text = self._get_node_text(node)
                # Check: "." in text and len(text.split(".")) ==
                if "." in text and len(text.split(".")) == 2:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        imp = Import(
                            name=text,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=text,
                            language="sql",
                        )
                        imports.append(imp)
                    except Exception as e:
                        log_debug(f"Failed to extract schema reference: {e}")

    # Backward-compatible delegates for tests
    def _parse_column_definition(self, col_def: str) -> Any:
        # Return result
        return _parse_column_definition(col_def)

    # Process: _split_column_definitions
    def _split_column_definitions(self, content: str) -> list[str]:
        # Return result
        return _split_column_definitions(content)
