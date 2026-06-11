#!/usr/bin/env python3
"""
TypeScript Language Plugin

Enhanced TypeScript-specific parsing and element extraction functionality.
Provides comprehensive support for TypeScript features including interfaces,
type aliases, enums, generics, decorators, and modern JavaScript features.
Equivalent to JavaScript plugin capabilities with TypeScript-specific enhancements.
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
from ...language_loader import loader  # noqa: F401
from ...models import Class, CodeElement, Function, Import, Variable
from ...plugins.base import ElementExtractor
from ...utils import log_debug
from ._class_helpers import (
    extract_class,
    extract_enum,
    extract_interface,
    extract_namespace,
    extract_type_alias,
)
from ._function_helpers import (
    extract_abstract_method_signature,
    extract_arrow_function,
    extract_function,
    extract_generator_function,
    extract_method,
    extract_method_signature,
)
from ._import_info_helpers import extract_import_info_simple
from ._parameter_helpers import extract_parameters_with_types
from ._signature_helpers import (
    parse_function_signature,
    parse_method_signature,
)
from ._text_helpers import calculate_complexity, get_node_text_optimized
from ._traversal_helpers import traverse_and_extract_iterative
from ._tsdoc_helpers import clean_tsdoc, extract_tsdoc_for_line
from ._variable_helpers import (
    extract_property,
    extract_property_signature,
    extract_variables_from_declaration,
    infer_type_from_value,
    is_exported_class,
    is_framework_component,
    parse_variable_declarator,
)
from .import_extractor import (
    _extract_commonjs_requires as _commonjs_requires_standalone,
)
from .import_extractor import (
    _extract_dynamic_import as _dynamic_import_standalone,
)
from .import_extractor import (
    _extract_import_names as _import_names_standalone,
)
from .import_extractor import (
    extract_ts_imports as _extract_ts_imports_standalone,
)


class TypeScriptElementExtractor(ElementExtractor):
    """Enhanced TypeScript-specific element extractor with comprehensive feature support"""

    def __init__(self) -> None:
        """Initialize the TypeScript element extractor."""
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
        self._tsdoc_cache: dict[int, str] = {}
        self._complexity_cache: dict[int, int] = {}

        # TypeScript-specific tracking
        self.is_module: bool = False
        self.is_tsx: bool = False
        self.framework_type: str = ""  # react, angular, vue, etc.
        self.typescript_version: str = "4.0"  # default

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract TypeScript function definitions with comprehensive details"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()
        self._detect_file_characteristics()

        functions: list[Function] = []

        # Use optimized traversal for multiple function types
        extractors = {
            "function_declaration": self._extract_function_optimized,
            "function_expression": self._extract_function_optimized,
            "arrow_function": self._extract_arrow_function_optimized,
            "method_definition": self._extract_method_optimized,
            "generator_function_declaration": self._extract_generator_function_optimized,
            "method_signature": self._extract_method_signature_optimized,
            # Issue #459 (Theme I): abstract methods inside abstract classes use
            # a distinct node type.  Visibility (public/protected/private) must
            # be preserved so we use a dedicated handler.
            "abstract_method_signature": self._extract_abstract_method_signature_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, functions, "function"
        )

        log_debug(f"Extracted {len(functions)} TypeScript functions")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract TypeScript class and interface definitions with detailed information"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        # Extract classes, interfaces, and type aliases
        extractors = {
            "class_declaration": self._extract_class_optimized,
            "interface_declaration": self._extract_interface_optimized,
            "type_alias_declaration": self._extract_type_alias_optimized,
            "enum_declaration": self._extract_enum_optimized,
            "abstract_class_declaration": self._extract_class_optimized,
            # Theme-I (2026-06-10): namespace/module containers were invisible
            # (and everything inside them lost — see _traversal_helpers).
            "internal_module": self._extract_namespace_optimized,
            "module": self._extract_namespace_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, classes, "class"
        )

        log_debug(f"Extracted {len(classes)} TypeScript classes/interfaces/types")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract TypeScript variable definitions with type annotations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        # Handle all TypeScript variable declaration types
        extractors = {
            "variable_declaration": self._extract_variable_optimized,
            "lexical_declaration": self._extract_lexical_variable_optimized,
            "property_definition": self._extract_property_optimized,
            "property_signature": self._extract_property_signature_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, variables, "variable"
        )

        log_debug(f"Extracted {len(variables)} TypeScript variables")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract TypeScript import statements with ES6+ and type import support"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        return _extract_ts_imports_standalone(
            tree, source_code, self._get_node_text_optimized
        )

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        self._tsdoc_cache.clear()
        self._complexity_cache.clear()

    def _detect_file_characteristics(self) -> None:
        """Detect TypeScript file characteristics"""
        # Check if it's a module
        self.is_module = "import " in self.source_code or "export " in self.source_code

        # Check if it contains TSX/JSX
        self.is_tsx = "</" in self.source_code and self.current_file.lower().endswith(
            (".tsx", ".jsx")
        )

        # Detect framework
        if "react" in self.source_code.lower() or "jsx" in self.source_code:
            self.framework_type = "react"
        elif "angular" in self.source_code.lower() or "@angular" in self.source_code:
            self.framework_type = "angular"
        elif "vue" in self.source_code.lower():
            self.framework_type = "vue"

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

    def _extract_function_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract regular function information with detailed metadata"""
        return extract_function(
            node,
            self._parse_function_signature_optimized,
            self._extract_tsdoc_for_line,
            self._calculate_complexity_optimized,
            self.content_lines,
            self.framework_type,
        )

    def _extract_arrow_function_optimized(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract arrow function information"""
        return extract_arrow_function(
            node,
            self._get_node_text_optimized,
            self._extract_parameters_with_types,
            self._extract_tsdoc_for_line,
            self._calculate_complexity_optimized,
            self.framework_type,
        )

    def _extract_method_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract method information from class"""
        return extract_method(
            node,
            self._parse_method_signature_optimized,
            self._extract_tsdoc_for_line,
            self._calculate_complexity_optimized,
            self._get_node_text_optimized,
            self.framework_type,
        )

    def _extract_method_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract method signature information from interfaces"""
        return extract_method_signature(
            node,
            self._parse_method_signature_optimized,
            self._extract_tsdoc_for_line,
            self._get_node_text_optimized,
            self.framework_type,
        )

    def _extract_abstract_method_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract abstract method signature from an abstract class (preserves visibility)."""
        return extract_abstract_method_signature(
            node,
            self._parse_method_signature_optimized,
            self._extract_tsdoc_for_line,
            self._get_node_text_optimized,
            self.framework_type,
        )

    def _extract_generator_function_optimized(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract generator function information"""
        return extract_generator_function(
            node,
            self._parse_function_signature_optimized,
            self._extract_tsdoc_for_line,
            self._calculate_complexity_optimized,
            self._get_node_text_optimized,
            self.framework_type,
        )

    def _extract_class_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class information with detailed metadata"""
        return extract_class(
            node,
            self._get_node_text_optimized,
            self._extract_generics,
            self._extract_tsdoc_for_line,
            self._is_framework_component,
            self._is_exported_class,
            self.framework_type,
        )

    def _extract_interface_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract interface information"""
        return extract_interface(
            node,
            self._get_node_text_optimized,
            self._extract_generics,
            self._extract_tsdoc_for_line,
            self._is_exported_class,
            self.framework_type,
        )

    def _extract_type_alias_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract type alias information"""
        return extract_type_alias(
            node,
            self._get_node_text_optimized,
            self._extract_generics,
            self._extract_tsdoc_for_line,
            self._is_exported_class,
            self.framework_type,
        )

    def _extract_enum_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract enum information"""
        return extract_enum(
            node,
            self._get_node_text_optimized,
            self._extract_tsdoc_for_line,
            self._is_exported_class,
            self.framework_type,
        )

    def _extract_namespace_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract namespace/module container information"""
        return extract_namespace(
            node,
            self._get_node_text_optimized,
            self._extract_tsdoc_for_line,
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
        return extract_property(node, self._get_node_text_optimized)

    def _extract_property_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> Variable | None:
        """Extract property signature from interface"""
        return extract_property_signature(node, self._get_node_text_optimized)

    def _extract_variables_from_declaration(
        self, node: "tree_sitter.Node", kind: str
    ) -> list[Variable]:
        """Extract variables from declaration node"""
        return extract_variables_from_declaration(
            node,
            kind,
            self._get_node_text_optimized,
            self._parse_variable_declarator,
            self._extract_tsdoc_for_line,
        )

    def _parse_variable_declarator(
        self, node: "tree_sitter.Node", kind: str, start_line: int, end_line: int
    ) -> Variable | None:
        """Parse individual variable declarator with TypeScript type annotations"""
        return parse_variable_declarator(
            node,
            kind,
            start_line,
            end_line,
            self._get_node_text_optimized,
            self._infer_type_from_value,
            self._extract_tsdoc_for_line,
        )

    def _parse_function_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str | None, list[str], bool, bool, str | None, list[str]] | None:
        """Parse function signature for TypeScript functions"""
        return parse_function_signature(
            node,
            self._get_node_text_optimized,
            self._extract_parameters_with_types,
            self._extract_generics,
        )

    def _parse_method_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> (
        tuple[
            str | None,
            list[str],
            bool,
            bool,
            bool,
            bool,
            bool,
            str | None,
            str,
            list[str],
        ]
        | None
    ):
        """Parse method signature for TypeScript class methods"""
        return parse_method_signature(
            node,
            self._get_node_text_optimized,
            self._extract_parameters_with_types,
            self._extract_generics,
        )

    def _extract_parameters_with_types(
        self, params_node: "tree_sitter.Node"
    ) -> list[str]:
        """Extract function parameters with TypeScript type annotations"""
        return extract_parameters_with_types(params_node, self._get_node_text_optimized)

    def _extract_generics(self, type_params_node: "tree_sitter.Node") -> list[str]:
        """Extract generic type parameters"""
        generics = []

        for child in type_params_node.children:
            if child.type == "type_parameter":
                generic_text = self._get_node_text_optimized(child)
                generics.append(generic_text)

        return generics

    def _extract_import_info_simple(self, node: "tree_sitter.Node") -> Import | None:
        """Extract import information from an import_statement node."""
        return extract_import_info_simple(
            node,
            self._get_node_text_optimized,
            self._extract_import_names,
        )

    def _extract_import_names(
        self, import_clause_node: "tree_sitter.Node", import_text: str = ""
    ) -> list[str]:
        return _import_names_standalone(
            import_clause_node, self.source_code, self._get_node_text_optimized
        )

    def _extract_dynamic_import(self, node: "tree_sitter.Node") -> Import | None:
        return _dynamic_import_standalone(node, self._get_node_text_optimized)

    def _extract_commonjs_requires(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        return _commonjs_requires_standalone(
            tree, source_code, self._get_node_text_optimized
        )

    def _is_framework_component(
        self, node: "tree_sitter.Node", class_name: str
    ) -> bool:
        """Check if class is a framework component"""
        return is_framework_component(
            self.framework_type, self.source_code, self._get_node_text_optimized, node
        )

    def _is_exported_class(self, class_name: str) -> bool:
        """Check if class is exported"""
        return is_exported_class(class_name, self.source_code)

    def _infer_type_from_value(self, value: str | None) -> str:
        """Infer TypeScript type from value"""
        return infer_type_from_value(value)

    def _extract_tsdoc_for_line(self, target_line: int) -> str | None:
        """Extract TSDoc comment immediately before the specified line"""
        return extract_tsdoc_for_line(
            self.content_lines,
            target_line,
            self._tsdoc_cache,
            self._clean_tsdoc,
        )

    def _clean_tsdoc(self, tsdoc_text: str) -> str:
        """Clean TSDoc text by removing comment markers"""
        return clean_tsdoc(tsdoc_text)

    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        """Calculate cyclomatic complexity efficiently"""
        return calculate_complexity(
            node, self._get_node_text_optimized, self._complexity_cache
        )

    def extract_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Legacy method for backward compatibility with tests"""
        all_elements: list[CodeElement] = []

        # Extract all types of elements
        all_elements.extend(self.extract_functions(tree, source_code))
        all_elements.extend(self.extract_classes(tree, source_code))
        all_elements.extend(self.extract_variables(tree, source_code))
        all_elements.extend(self.extract_imports(tree, source_code))

        return all_elements
