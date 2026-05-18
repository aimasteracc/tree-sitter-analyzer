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


try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


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
from ._class_table_extractor import extract_class_tables
from ._class_view_extractor import extract_class_views
from ._node_text import get_node_text
from .element_validator import validate_and_fix_elements
from .function_extractor import (
    _extract_function_metadata,
    extract_legacy_functions,
    extract_sql_functions_enhanced,
)
from .identifier_validator import is_valid_identifier as _is_valid_identifier_external
from .index_extractor import (
    extract_indexes_with_regex,
    extract_legacy_indexes,
    extract_sql_indexes,
)
from .procedure_extractor import (
    extract_legacy_procedures,
    extract_procedure_parameters,
    extract_sql_procedures,
)
from .schema_reference_extractor import extract_schema_references
from .table_extractor import (
    _parse_column_definition,
    _split_column_definitions,
    extract_sql_tables,
)
from .trigger_extractor import (
    extract_legacy_triggers,
    extract_sql_triggers,
)
from .view_extractor import extract_sql_views


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

        if tree is None or tree.root_node is None:
            return sql_elements

        try:
            self._extract_sql_tables(tree.root_node, sql_elements)
            self._extract_sql_views(tree.root_node, sql_elements)
            self._extract_sql_procedures(tree.root_node, sql_elements)
            self._extract_sql_functions_enhanced(tree.root_node, sql_elements)
            self._extract_sql_triggers(tree.root_node, sql_elements)
            self._extract_sql_indexes(tree.root_node, sql_elements)

            sql_elements = self._adapt_sql_elements(sql_elements)
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

    def _adapt_sql_elements(self, sql_elements: list[SQLElement]) -> list[SQLElement]:
        """Apply optional platform adapter with diagnostic logging."""
        if not self.adapter:
            return sql_elements

        if self.diagnostic_mode:
            log_debug(
                f"Diagnostic: Before adaptation: {[e.name for e in sql_elements]}"
            )

        adapted_elements = self.adapter.adapt_elements(sql_elements, self.source_code)

        if self.diagnostic_mode:
            log_debug(
                f"Diagnostic: After adaptation: {[e.name for e in adapted_elements]}"
            )

        return adapted_elements

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

        if tree is not None and tree.root_node is not None:
            try:
                self._extract_indexes(tree.root_node, variables)
                log_debug(f"Extracted {len(variables)} SQL indexes")
            except Exception as e:
                log_debug(f"Error during variable extraction: {e}")

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

        if tree is not None and tree.root_node is not None:
            try:
                self._extract_schema_references(tree.root_node, imports)
                log_debug(f"Extracted {len(imports)} SQL schema references")
            except Exception as e:
                log_debug(f"Error during import extraction: {e}")

        return imports

    # ---------------------------------------------------------------
    # Core utilities
    # ---------------------------------------------------------------

    def _reset_caches(self) -> None:
        self._node_text_cache.clear()
        self._processed_nodes.clear()

    def _get_node_text(self, node: "tree_sitter.Node") -> str:
        """Get text content from a tree-sitter node with caching."""
        return get_node_text(
            node,
            self.content_lines,
            self._node_text_cache,
            self._file_encoding,
        )

    def _traverse_nodes(self, node: "tree_sitter.Node") -> Iterator["tree_sitter.Node"]:
        yield node
        if hasattr(node, "children"):
            # Iterate over child
            for child in node.children:
                yield from self._traverse_nodes(child)

    def _is_valid_identifier(self, name: str) -> bool:
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
        extract_sql_triggers(
            self.source_code,
            sql_elements,
            trigger_factory=SQLTrigger,
            is_valid_identifier_fn=self._is_valid_identifier,
        )

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
            index_factory=SQLIndex,
        )

    def _extract_indexes_with_regex(
        self, sql_elements: list[Any], processed_indexes: set[str]
    ) -> None:
        """Extract CREATE INDEX statements using regex as fallback."""
        extract_indexes_with_regex(
            sql_elements,
            processed_indexes,
            self.source_code,
            index_factory=SQLIndex,
        )

    # ---------------------------------------------------------------
    # Legacy extraction methods (used by extract_classes/functions/etc.)
    # ---------------------------------------------------------------

    def _extract_tables(
        self, root_node: "tree_sitter.Node", classes: list[Class]
    ) -> None:
        """Extract CREATE TABLE statements from SQL AST."""
        extract_class_tables(
            root_node,
            classes,
            self._traverse_nodes,
            self._get_node_text,
            self._is_valid_identifier,
        )

    # Extract elements from AST: _extract_views
    def _extract_views(
        self, root_node: "tree_sitter.Node", classes: list[Class]
    ) -> None:
        """Extract CREATE VIEW statements from SQL AST."""
        extract_class_views(
            root_node,
            classes,
            self._traverse_nodes,
            self._get_node_text,
            self._is_valid_identifier,
            self.source_code,
            self.content_lines,
        )

    # Extract elements from AST: _extract_procedures
    def _extract_procedures(
        self, root_node: "tree_sitter.Node", functions: list[Function]
    ) -> None:
        """Extract CREATE PROCEDURE statements from SQL AST."""
        extract_legacy_procedures(
            root_node,
            functions,
            self._traverse_nodes,
            self._get_node_text,
        )

    # Extract elements from AST: _extract_sql_functions
    def _extract_sql_functions(
        self, root_node: "tree_sitter.Node", functions: list[Function]
    ) -> None:
        """Extract CREATE FUNCTION statements from SQL AST."""
        extract_legacy_functions(
            root_node,
            functions,
            self._traverse_nodes,
            self._get_node_text,
            self._is_valid_identifier,
        )

    # Extract elements from AST: _extract_triggers
    def _extract_triggers(
        self, root_node: "tree_sitter.Node", functions: list[Function]
    ) -> None:
        """Extract CREATE TRIGGER statements from SQL AST."""
        extract_legacy_triggers(
            root_node,
            functions,
            self._traverse_nodes,
            self._get_node_text,
            self._is_valid_identifier,
        )

    # Extract elements from AST: _extract_indexes
    def _extract_indexes(
        self, root_node: "tree_sitter.Node", variables: list[Variable]
    ) -> None:
        """Extract CREATE INDEX statements from SQL AST."""
        extract_legacy_indexes(
            root_node,
            variables,
            self._traverse_nodes,
            self._get_node_text,
        )

    # Extract elements from AST: _extract_schema_references
    def _extract_schema_references(
        self, root_node: "tree_sitter.Node", imports: list[Import]
    ) -> None:
        """Extract schema references (e.g., FROM schema.table)."""
        extract_schema_references(
            root_node,
            imports,
            self._traverse_nodes,
            self._get_node_text,
        )

    # Backward-compatible delegates for tests
    def _parse_column_definition(self, col_def: str) -> Any:
        return _parse_column_definition(col_def)

    def _split_column_definitions(self, content: str) -> list[str]:
        return _split_column_definitions(content)
