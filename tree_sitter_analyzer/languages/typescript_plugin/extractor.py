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
from ._class_helpers import extract_class, extract_interface
from ._function_helpers import (
    extract_arrow_function,
    extract_function,
    extract_method,
    extract_method_signature,
)
from ._import_info_helpers import extract_import_info_simple
from ._parameter_helpers import extract_parameters_with_types
from ._signature_helpers import (
    parse_function_signature,
    parse_method_signature,
)
from ._text_helpers import get_node_text_optimized
from ._traversal_helpers import traverse_and_extract_iterative
from ._tsdoc_helpers import clean_tsdoc, extract_tsdoc_for_line
from ._variable_helpers import extract_property, parse_variable_declarator
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

    # Extract elements from AST: extract_functions
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
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, functions, "function"
        )

        log_debug(f"Extracted {len(functions)} TypeScript functions")
        return functions

    # Extract elements from AST: extract_classes
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
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, classes, "class"
        )

        log_debug(f"Extracted {len(classes)} TypeScript classes/interfaces/types")
        return classes

    # Extract elements from AST: extract_variables
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

    # Extract elements from AST: extract_imports
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

    # Detect patterns in source code: _detect_file_characteristics
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

    # Extract elements from AST: _traverse_and_extract_iterative
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

    # Extract elements from AST: _extract_function_optimized
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

    # Extract elements from AST: _extract_arrow_function_optimized
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

    # Extract elements from AST: _extract_method_optimized
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

    # Extract elements from AST: _extract_method_signature_optimized
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

    # Extract elements from AST: _extract_generator_function_optimized
    def _extract_generator_function_optimized(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract generator function information"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract function details
            function_info = self._parse_function_signature_optimized(node)
            if not function_info:
                return None

            name, parameters, is_async, _, return_type, generics = function_info

            # Skip if no name found
            if name is None:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Calculate complexity
            complexity_score = self._calculate_complexity_optimized(node)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                parameters=parameters,
                return_type=return_type or "Generator",
                is_async=is_async,
                is_generator=True,
                docstring=tsdoc,
                complexity_score=complexity_score,
                # TypeScript-specific properties
                is_arrow=False,
                is_method=False,
                framework_type=self.framework_type,
                # TypeScript-specific properties handled above
            )
        except Exception as e:
            log_debug(f"Failed to extract generator function info: {e}")
            return None

    # Extract elements from AST: _extract_class_optimized
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

    # Extract elements from AST: _extract_interface_optimized
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

    # Extract elements from AST: _extract_type_alias_optimized
    def _extract_type_alias_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract type alias information"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract type alias name
            type_name = None
            # generics = []  # Commented out as not used yet

            for child in node.children:
                if child.type == "type_identifier":
                    type_name = child.text.decode("utf8") if child.text else None
                elif child.type == "type_parameters":
                    self._extract_generics(child)

            if not type_name:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Class(
                name=type_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                class_type="type",
                docstring=tsdoc,
                # TypeScript-specific properties
                framework_type=self.framework_type,
                is_exported=self._is_exported_class(type_name),
                # TypeScript-specific properties handled above
            )
        except Exception as e:
            log_debug(f"Failed to extract type alias info: {e}")
            return None

    # Extract elements from AST: _extract_enum_optimized
    def _extract_enum_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract enum information"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract enum name
            enum_name = None

            for child in node.children:
                if child.type == "identifier":
                    enum_name = child.text.decode("utf8") if child.text else None

            if not enum_name:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Class(
                name=enum_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                class_type="enum",
                docstring=tsdoc,
                # TypeScript-specific properties
                framework_type=self.framework_type,
                is_exported=self._is_exported_class(enum_name),
                # TypeScript-specific properties handled above
            )
        except Exception as e:
            log_debug(f"Failed to extract enum info: {e}")
            return None

    # Extract elements from AST: _extract_variable_optimized
    def _extract_variable_optimized(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract var declaration variables"""
        return self._extract_variables_from_declaration(node, "var")

    # Extract elements from AST: _extract_lexical_variable_optimized
    def _extract_lexical_variable_optimized(
        self, node: "tree_sitter.Node"
    ) -> list[Variable]:
        """Extract let/const declaration variables"""
        # Determine if it's let or const
        node_text = self._get_node_text_optimized(node)
        kind = "let" if node_text.strip().startswith("let") else "const"
        return self._extract_variables_from_declaration(node, kind)

    # Extract elements from AST: _extract_property_optimized
    def _extract_property_optimized(self, node: "tree_sitter.Node") -> Variable | None:
        """Extract class property definition"""
        return extract_property(node, self._get_node_text_optimized)

    # Extract elements from AST: _extract_property_signature_optimized
    def _extract_property_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> Variable | None:
        """Extract property signature from interface"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract property signature name and type
            prop_name = None
            prop_type = None
            # is_optional = False  # Commented out as not used yet

            for child in node.children:
                if child.type == "property_identifier":
                    prop_name = self._get_node_text_optimized(child)
                elif child.type == "type_annotation":
                    prop_type = self._get_node_text_optimized(child).lstrip(": ")

            # Check for optional property
            # node_text = self._get_node_text_optimized(node)  # Commented out as not used yet
            # Check for optional property (not used but kept for future reference)
            # is_optional = "?" in node_text

            if not prop_name:
                return None

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Variable(
                name=prop_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                variable_type=prop_type or "any",
                is_constant=False,
                # TypeScript-specific properties
                visibility="public",  # Interface properties are always public
            )
        except Exception as e:
            log_debug(f"Failed to extract property signature info: {e}")
            return None

    # Extract elements from AST: _extract_variables_from_declaration
    def _extract_variables_from_declaration(
        self, node: "tree_sitter.Node", kind: str
    ) -> list[Variable]:
        """Extract variables from declaration node"""
        variables: list[Variable] = []

        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

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

    # Parse input into structured data: _parse_variable_declarator
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

    # Parse input into structured data: _parse_function_signature_optimized
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

    # Parse input into structured data: _parse_method_signature_optimized
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

    # Extract elements from AST: _extract_parameters_with_types
    def _extract_parameters_with_types(
        self, params_node: "tree_sitter.Node"
    ) -> list[str]:
        """Extract function parameters with TypeScript type annotations"""
        return extract_parameters_with_types(params_node, self._get_node_text_optimized)

    # Extract elements from AST: _extract_generics
    def _extract_generics(self, type_params_node: "tree_sitter.Node") -> list[str]:
        """Extract generic type parameters"""
        generics = []

        for child in type_params_node.children:
            if child.type == "type_parameter":
                generic_text = self._get_node_text_optimized(child)
                generics.append(generic_text)

        return generics

    # Extract elements from AST: _extract_import_info_simple
    def _extract_import_info_simple(self, node: "tree_sitter.Node") -> Import | None:
        """Extract import information from an import_statement node."""
        return extract_import_info_simple(
            node,
            self._get_node_text_optimized,
            self._extract_import_names,
        )

    # Extract elements from AST: _extract_import_names
    def _extract_import_names(
        self, import_clause_node: "tree_sitter.Node", import_text: str = ""
    ) -> list[str]:
        return _import_names_standalone(
            import_clause_node, self.source_code, self._get_node_text_optimized
        )

    # Extract elements from AST: _extract_dynamic_import
    def _extract_dynamic_import(self, node: "tree_sitter.Node") -> Import | None:
        return _dynamic_import_standalone(node, self._get_node_text_optimized)

    # Extract elements from AST: _extract_commonjs_requires
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
        if self.framework_type == "react":
            # Check if extends React.Component or Component
            node_text = self._get_node_text_optimized(node)
            return "extends" in node_text and (
                "Component" in node_text or "PureComponent" in node_text
            )
        elif self.framework_type == "angular":
            # Check for Angular component decorator
            return "@Component" in self.source_code
        elif self.framework_type == "vue":
            # Check for Vue component patterns
            return "Vue" in self.source_code or "@Component" in self.source_code
        return False

    def _is_exported_class(self, class_name: str) -> bool:
        """Check if class is exported"""
        # Simple check for export statements
        return (
            f"export class {class_name}" in self.source_code
            or f"export default {class_name}" in self.source_code
        )

    def _infer_type_from_value(self, value: str | None) -> str:
        """Infer TypeScript type from value"""
        if not value:
            return "any"

        value = value.strip()

        if value.startswith('"') or value.startswith("'") or value.startswith("`"):
            return "string"
        if value in ["true", "false"]:
            return "boolean"
        if value == "null":
            return "null"
        if value == "undefined":
            return "undefined"
        if value.startswith("[") and value.endswith("]"):
            return "array"
        if value.startswith("{") and value.endswith("}"):
            return "object"
        if value.replace(".", "").replace("-", "").isdigit():
            return "number"
        if "function" in value or "=>" in value:
            return "function"
        return "any"

    # Extract elements from AST: _extract_tsdoc_for_line
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
        node_id = id(node)
        if node_id in self._complexity_cache:
            return self._complexity_cache[node_id]

        complexity = 1
        try:
            node_text = self._get_node_text_optimized(node).lower()
            keywords = [
                "if",
                "else if",
                "while",
                "for",
                "catch",
                "case",
                "switch",
                "&&",
                "||",
                "?",
            ]
            for keyword in keywords:
                complexity += node_text.count(keyword)
        except Exception as e:
            log_debug(f"Failed to calculate complexity: {e}")

        self._complexity_cache[node_id] = complexity
        return complexity

    # Extract elements from AST: extract_elements
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
