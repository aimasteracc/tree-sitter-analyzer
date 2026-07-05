#!/usr/bin/env python3
"""
JavaScript Language Plugin

Enhanced JavaScript-specific parsing and element extraction functionality.
Provides comprehensive support for modern JavaScript features including ES6+,
async/await, classes, modules, JSX, and framework-specific patterns.
Equivalent to Java plugin capabilities for consistent language support.
"""

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import tree_sitter

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ...encoding_utils import extract_text_slice, safe_encode
from ...models import Class, Variable
from ...plugins.base import ElementExtractor
from ...utils import log_debug
from ..shared.traversal import node_range
from ._class import extract_class
from ._function_mixin import JavaScriptFunctionExtractionMixin
from ._import_export_mixin import JavaScriptImportExportMixin
from ._public_extraction_mixin import JavaScriptPublicExtractionMixin
from ._text import get_node_text_optimized
from ._traversal import traverse_and_extract_iterative
from ._utility_mixin import JavaScriptUtilityMixin
from ._variable import parse_variable_declarator


class JavaScriptElementExtractor(
    JavaScriptPublicExtractionMixin,
    JavaScriptImportExportMixin,
    JavaScriptUtilityMixin,
    JavaScriptFunctionExtractionMixin,
    ElementExtractor,
):
    """Enhanced JavaScript-specific element extractor with comprehensive feature support"""

    def __init__(self) -> None:
        """Initialize the JavaScript element extractor."""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.imports: list[str] = []
        self.exports: list[dict[str, Any]] = []

        # Performance optimization caches - use position-based keys for deterministic caching
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None
        self._jsdoc_cache: dict[int, str] = {}
        self._complexity_cache: dict[int, int] = {}

        # JavaScript-specific tracking
        self.is_module: bool = False
        self.is_jsx: bool = False
        self.framework_type: str = ""  # react, vue, angular, etc.

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        self._jsdoc_cache.clear()
        self._complexity_cache.clear()

    def _detect_file_characteristics(self) -> None:
        """Detect JavaScript file characteristics"""
        # Check if it's a module
        self.is_module = "import " in self.source_code or "export " in self.source_code

        # Check if it contains JSX
        self.is_jsx = "</" in self.source_code and "jsx" in self.current_file.lower()

        # Detect framework
        if "react" in self.source_code.lower() or "jsx" in self.source_code:
            self.framework_type = "react"
        elif "vue" in self.source_code.lower():
            self.framework_type = "vue"
        elif "angular" in self.source_code.lower():
            self.framework_type = "angular"

    def _traverse_and_extract_iterative(
        self,
        root_node: Optional["tree_sitter.Node"],
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """Iterative node traversal and extraction with caching"""
        traverse_and_extract_iterative(
            root_node,
            extractors,
            results,
            element_type,
            self._processed_nodes,
            self._element_cache,
        )

    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """Get node text with optimized caching using position-based keys"""
        return get_node_text_optimized(
            node,
            self.content_lines,
            self._file_encoding,
            self._node_text_cache,
            extract_text_slice,
            safe_encode,
        )

    def _extract_class_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class information with detailed metadata"""
        return extract_class(
            node,
            self._get_node_text_optimized,
            self._extract_jsdoc_for_line,
            self._is_react_component,
            self._is_exported_class,
            self.framework_type,
        )

    def _extract_variable_optimized(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract var declaration variables"""
        return self._extract_variables_from_declaration(node, "var")

    def _extract_lexical_variable_optimized(
        self, node: "tree_sitter.Node"
    ) -> list[Variable]:
        """Extract let/const declaration variables"""
        # Determine if it's let or const
        node_text = self._get_node_text_optimized(node)
        kind = "let" if node_text.strip().startswith("let") else "const"
        return self._extract_variables_from_declaration(node, kind)

    def _extract_property_optimized(self, node: "tree_sitter.Node") -> Variable | None:
        """Extract class property definition"""
        try:
            start_line, end_line = node_range(node)

            # Extract property name
            prop_name = None
            prop_value = None
            is_static = False

            for child in node.children:
                if child.type == "property_identifier":
                    prop_name = self._get_node_text_optimized(child)
                elif child.type in ["string", "number", "true", "false", "null"]:
                    prop_value = self._get_node_text_optimized(child)

            # Check if static (would be in parent modifiers)
            parent = node.parent
            if parent:
                parent_text = self._get_node_text_optimized(parent)
                is_static = "static" in parent_text

            if not prop_name:
                return None

            # Find parent class (currently not used but may be needed for future enhancements)
            # class_name = self._find_parent_class_name(node)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Variable(
                name=prop_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="javascript",
                variable_type=self._infer_type_from_value(prop_value),
                is_static=is_static,
                is_constant=False,  # Class properties are not const
                initializer=prop_value,
            )
        except Exception as e:
            log_debug(f"Failed to extract property info: {e}")
            return None

    def _extract_field_definition_optimized(
        self, node: "tree_sitter.Node"
    ) -> Variable | None:
        """Extract class field declaration (public and private, not arrow methods)."""
        try:
            start_line, end_line = node_range(node)

            field_name = None
            field_value = None
            has_arrow_value = False
            is_static = False

            is_private_field = False
            found_assignment = False  # True once we pass the '=' separator
            for child in node.children:
                if child.type == "=":
                    # Everything after '=' is the value, not the key.
                    found_assignment = True
                elif not found_assignment:
                    # Key section: pick up the name node before the '='.
                    if child.type == "static":
                        is_static = True
                    elif child.type == "private_property_identifier":
                        field_name = self._get_node_text_optimized(child)
                        is_private_field = True
                    elif child.type == "property_identifier":
                        field_name = self._get_node_text_optimized(child)
                    elif child.type in ("string", "number"):
                        # Issue #892: string-literal keys ('key' = val) and
                        # numeric keys (0 = 'zero') — strip surrounding quotes.
                        raw = self._get_node_text_optimized(child)
                        field_name = raw.strip("'\"") if child.type == "string" else raw
                    elif child.type == "computed_property_name":
                        # Issue #892: computed property names (['x'] = val).
                        # Use the full bracket text, e.g. "['x']".
                        field_name = self._get_node_text_optimized(child)
                else:
                    # Value section: only detect arrow function values.
                    if child.type == "arrow_function":
                        has_arrow_value = True

            # Arrow function class fields are captured in the function extraction pass
            # (via field_definition in container_node_types + _arrow_function_name fix).
            if has_arrow_value:
                return None

            if not field_name:
                return None

            # Use the named "value" field for the initializer so non-primitive RHS
            # expressions (objects, arrays, calls, identifiers) are preserved
            # intact instead of being silently dropped (Codex P2 on #746).
            value_node = node.child_by_field_name("value")
            if value_node is not None:
                field_value = self._get_node_text_optimized(value_node)

            raw_text = self._get_node_text_optimized(node)
            # Private fields (#name) are private; all others are public (Codex P2 #746).
            visibility = "private" if is_private_field else "public"

            return Variable(
                name=field_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="javascript",
                variable_type=self._infer_type_from_value(field_value),
                is_static=is_static,
                is_constant=False,
                initializer=field_value,
                visibility=visibility,
            )
        except Exception as e:
            log_debug(f"Failed to extract field definition: {e}")
            return None

    def _extract_variables_from_declaration(
        self, node: "tree_sitter.Node", kind: str
    ) -> list[Variable]:
        """Extract variables from declaration node"""
        variables: list[Variable] = []

        try:
            start_line, end_line = node_range(node)

            # Find variable declarators
            for child in node.children:
                if child.type == "variable_declarator":
                    var_info = self._parse_variable_declarator(
                        child, kind, start_line, end_line
                    )
                    if var_info:
                        variables.append(var_info)

        except Exception as e:
            log_debug(f"Failed to extract variables from declaration: {e}")

        return variables

    def _parse_variable_declarator(
        self, node: "tree_sitter.Node", kind: str, start_line: int, end_line: int
    ) -> Variable | None:
        """Parse individual variable declarator"""
        return parse_variable_declarator(
            node,
            kind,
            start_line,
            end_line,
            self._get_node_text_optimized,
            self._infer_type_from_value,
            self._extract_jsdoc_for_line,
        )
