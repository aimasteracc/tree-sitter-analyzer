#!/usr/bin/env python3
"""
TypeScript Language Plugin

Enhanced TypeScript-specific parsing and element extraction functionality.
Provides comprehensive support for TypeScript features including interfaces,
type aliases, enums, generics, decorators, and modern JavaScript features.
Equivalent to JavaScript plugin capabilities with TypeScript-specific enhancements.
"""

import re
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import tree_sitter

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ...encoding_utils import extract_text_slice, safe_encode
from ...models import Class, CodeElement, Function, Import, Variable
from ...plugins.base import ElementExtractor
from ...utils import log_debug, log_error, log_warning
from .import_extractor import (
    _extract_commonjs_requires as _commonjs_requires_standalone,
)
from .import_extractor import (
    _extract_dynamic_import as _dynamic_import_standalone,
)
from .import_extractor import (
    _extract_import_info_simple as _import_info_standalone,
)
from .import_extractor import (
    _extract_import_names as _import_names_standalone,
)
from .import_extractor import (
    extract_ts_imports as _extract_ts_imports_standalone,
)


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

    # Process: _reset_caches
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
        if not root_node:
            return

        target_node_types = set(extractors.keys())
        container_node_types = {
            "program",
            "class_body",
            "interface_body",
            "statement_block",
            "object_type",
            "class_declaration",
            "interface_declaration",
            "function_declaration",
            "method_definition",
            "export_statement",
            "variable_declaration",
            "lexical_declaration",
            "variable_declarator",
            "assignment_expression",
            "type_alias_declaration",
            "enum_declaration",
        }

        node_stack = [(root_node, 0)]
        processed_nodes = 0
        max_depth = 50

        while node_stack:
            current_node, depth = node_stack.pop()

            if depth > max_depth:
                log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
                continue

            processed_nodes += 1
            node_type = current_node.type

            # Early termination for irrelevant nodes
            if (
                depth > 0
                and node_type not in target_node_types
                and node_type not in container_node_types
            ):
                continue

            # Process target nodes
            if node_type in target_node_types:
                node_id = id(current_node)

                if node_id in self._processed_nodes:
                    continue

                cache_key = (node_id, element_type)
                if cache_key in self._element_cache:
                    element = self._element_cache[cache_key]
                    if element:
                        if isinstance(element, list):
                            results.extend(element)
                        else:
                            results.append(element)
                    self._processed_nodes.add(node_id)
                    continue

                # Extract and cache
                extractor = extractors.get(node_type)
                if extractor:
                    element = extractor(current_node)
                    self._element_cache[cache_key] = element
                    if element:
                        if isinstance(element, list):
                            results.extend(element)
                        else:
                            results.append(element)
                    self._processed_nodes.add(node_id)

            # Add children to stack
            if current_node.children:
                for child in reversed(current_node.children):
                    node_stack.append((child, depth + 1))

        log_debug(f"Iterative traversal processed {processed_nodes} nodes")

    # Process: _get_node_text_optimized
    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """Get node text with optimized caching using position-based keys"""
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

            self._node_text_cache[cache_key] = text
            return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")
            # Fallback to simple text extraction
            try:
                start_point = node.start_point
                end_point = node.end_point

                if start_point[0] == end_point[0]:
                    line = self.content_lines[start_point[0]]
                    return str(line[start_point[1] : end_point[1]])
                else:
                    lines = []
                    for i in range(start_point[0], end_point[0] + 1):
                        if i < len(self.content_lines):
                            line = self.content_lines[i]
                            if i == start_point[0]:
                                lines.append(line[start_point[1] :])
                            elif i == end_point[0]:
                                lines.append(line[: end_point[1]])
                            else:
                                lines.append(line)
                    return "\n".join(lines)
            except Exception as fallback_error:
                log_error(f"Fallback text extraction also failed: {fallback_error}")
                return ""

    # Extract elements from AST: _extract_function_optimized
    def _extract_function_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract regular function information with detailed metadata"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract function details
            function_info = self._parse_function_signature_optimized(node)
            if not function_info:
                return None

            name, parameters, is_async, is_generator, return_type, generics = (
                function_info
            )

            # Skip if no name found
            if name is None:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Calculate complexity
            complexity_score = self._calculate_complexity_optimized(node)

            # Extract raw text
            start_line_idx = max(0, start_line - 1)
            end_line_idx = min(len(self.content_lines), end_line)
            raw_text = "\n".join(self.content_lines[start_line_idx:end_line_idx])

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                parameters=parameters,
                return_type=return_type or "any",
                is_async=is_async,
                is_generator=is_generator,
                docstring=tsdoc,
                complexity_score=complexity_score,
                # TypeScript-specific properties
                is_arrow=False,
                is_method=False,
                framework_type=self.framework_type,
            )
        except Exception as e:
            log_error(f"Failed to extract function info: {e}")
            import traceback

            traceback.print_exc()
            return None

    # Extract elements from AST: _extract_arrow_function_optimized
    def _extract_arrow_function_optimized(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract arrow function information"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # For arrow functions, we need to find the variable declaration
            parent = node.parent
            name = "anonymous"

            if parent and parent.type == "variable_declarator":
                for child in parent.children:
                    if child.type == "identifier":
                        name = self._get_node_text_optimized(child)
                        break

            # Extract parameters and return type
            parameters = []
            return_type = None
            is_async = False

            for child in node.children:
                if child.type == "formal_parameters":
                    parameters = self._extract_parameters_with_types(child)
                elif child.type == "identifier":
                    # Single parameter without parentheses
                    param_name = self._get_node_text_optimized(child)
                    parameters = [param_name]
                elif child.type == "type_annotation":
                    return_type = self._get_node_text_optimized(child).lstrip(": ")

            # Check if async
            node_text = self._get_node_text_optimized(node)
            is_async = "async" in node_text

            # Extract TSDoc (look at parent variable declaration)
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
                return_type=return_type or "any",
                is_async=is_async,
                is_generator=False,
                docstring=tsdoc,
                complexity_score=complexity_score,
                # TypeScript-specific properties
                is_arrow=True,
                is_method=False,
                framework_type=self.framework_type,
            )
        except Exception as e:
            log_debug(f"Failed to extract arrow function info: {e}")
            return None

    # Extract elements from AST: _extract_method_optimized
    def _extract_method_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract method information from class"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract method details
            method_info = self._parse_method_signature_optimized(node)
            if not method_info:
                return None

            (
                name,
                parameters,
                is_async,
                is_static,
                is_getter,
                is_setter,
                is_constructor,
                return_type,
                visibility,
                generics,
            ) = method_info

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
                return_type=return_type or "any",
                is_async=is_async,
                is_static=is_static,
                is_constructor=is_constructor,
                docstring=tsdoc,
                complexity_score=complexity_score,
                # TypeScript-specific properties
                is_arrow=False,
                is_method=True,
                framework_type=self.framework_type,
                visibility=visibility,
            )
        except Exception as e:
            log_debug(f"Failed to extract method info: {e}")
            return None

    # Extract elements from AST: _extract_method_signature_optimized
    def _extract_method_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract method signature information from interfaces"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract method signature details
            method_info = self._parse_method_signature_optimized(node)
            if not method_info:
                return None

            (
                name,
                parameters,
                is_async,
                is_static,
                is_getter,
                is_setter,
                is_constructor,
                return_type,
                visibility,
                generics,
            ) = method_info

            # Skip if no name found
            if name is None:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                parameters=parameters,
                return_type=return_type or "any",
                is_async=is_async,
                is_static=is_static,
                docstring=tsdoc,
                complexity_score=0,  # Signatures have no complexity
                # TypeScript-specific properties
                is_arrow=False,
                is_method=True,
                framework_type=self.framework_type,
            )
        except Exception as e:
            log_debug(f"Failed to extract method signature info: {e}")
            return None

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
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract class name
            class_name = None
            superclass = None
            interfaces = []
            # generics = []  # Commented out as not used yet
            is_abstract = node.type == "abstract_class_declaration"

            for child in node.children:
                if child.type == "type_identifier":
                    class_name = child.text.decode("utf8") if child.text else None
                elif child.type == "class_heritage":
                    # Extract extends and implements clauses
                    heritage_text = self._get_node_text_optimized(child)
                    extends_match = re.search(r"extends\s+(\w+)", heritage_text)
                    if extends_match:
                        superclass = extends_match.group(1)

                    implements_matches = re.findall(
                        r"implements\s+([\w,\s]+)", heritage_text
                    )
                    if implements_matches:
                        interfaces = [
                            iface.strip() for iface in implements_matches[0].split(",")
                        ]
                elif child.type == "type_parameters":
                    self._extract_generics(child)

            if not class_name:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Check if it's a framework component
            is_component = self._is_framework_component(node, class_name)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Class(
                name=class_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                class_type="abstract_class" if is_abstract else "class",
                superclass=superclass,
                interfaces=interfaces,
                docstring=tsdoc,
                # TypeScript-specific properties
                is_react_component=is_component,
                framework_type=self.framework_type,
                is_exported=self._is_exported_class(class_name),
                is_abstract=is_abstract,
                # TypeScript-specific properties handled above
            )
        except Exception as e:
            log_debug(f"Failed to extract class info: {e}")
            return None

    # Extract elements from AST: _extract_interface_optimized
    def _extract_interface_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract interface information"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract interface name
            interface_name = None
            extends_interfaces = []
            # generics = []  # Commented out as not used yet

            for child in node.children:
                if child.type == "type_identifier":
                    interface_name = child.text.decode("utf8") if child.text else None
                elif child.type == "extends_clause":
                    # Extract extends clause for interfaces
                    extends_text = self._get_node_text_optimized(child)
                    extends_matches = re.findall(r"extends\s+([\w,\s]+)", extends_text)
                    if extends_matches:
                        extends_interfaces = [
                            iface.strip() for iface in extends_matches[0].split(",")
                        ]
                elif child.type == "type_parameters":
                    self._extract_generics(child)

            if not interface_name:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Class(
                name=interface_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                class_type="interface",
                interfaces=extends_interfaces,
                docstring=tsdoc,
                # TypeScript-specific properties
                framework_type=self.framework_type,
                is_exported=self._is_exported_class(interface_name),
                # TypeScript-specific properties handled above
            )
        except Exception as e:
            log_debug(f"Failed to extract interface info: {e}")
            return None

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
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract property name and type
            prop_name = None
            prop_type = None
            prop_value = None
            is_static = False
            visibility = "public"

            # Handle children if they exist
            if hasattr(node, "children") and node.children:
                for child in node.children:
                    if hasattr(child, "type"):
                        if child.type == "property_identifier":
                            prop_name = self._get_node_text_optimized(child)
                        elif child.type == "type_annotation":
                            prop_type = self._get_node_text_optimized(child).lstrip(
                                ": "
                            )
                        elif child.type in [
                            "string",
                            "number",
                            "true",
                            "false",
                            "null",
                        ]:
                            prop_value = self._get_node_text_optimized(child)

            # Check modifiers from parent or node text
            node_text = self._get_node_text_optimized(node)
            is_static = "static" in node_text
            if "private" in node_text:
                visibility = "private"
            elif "protected" in node_text:
                visibility = "protected"

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
                initializer=prop_value,
                is_static=is_static,
                is_constant=False,  # Class properties are not const
                # TypeScript-specific properties
                visibility=visibility,
            )
        except Exception as e:
            log_debug(f"Failed to extract property info: {e}")
            return None

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
        try:
            var_name = None
            var_type = None
            var_value = None

            # Find identifier, type annotation, and value in children
            for child in node.children:
                if child.type == "identifier":
                    var_name = self._get_node_text_optimized(child)
                elif child.type == "type_annotation":
                    var_type = self._get_node_text_optimized(child).lstrip(": ")
                elif child.type == "=" and child.next_sibling:
                    # Get the value after the assignment operator
                    value_node = child.next_sibling
                    var_value = self._get_node_text_optimized(value_node)

            if not var_name:
                return None

            # Skip variables that are arrow functions (handled by function extractor)
            for child in node.children:
                if child.type == "arrow_function":
                    return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Variable(
                name=var_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                variable_type=var_type or self._infer_type_from_value(var_value),
                is_static=False,
                is_constant=(kind == "const"),
                docstring=tsdoc,
                initializer=var_value,
                # TypeScript-specific properties
                visibility="public",  # Variables are typically public in TypeScript
            )
        except Exception as e:
            log_debug(f"Failed to parse variable declarator: {e}")
            return None

    # Parse input into structured data: _parse_function_signature_optimized
    def _parse_function_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str | None, list[str], bool, bool, str | None, list[str]] | None:
        """Parse function signature for TypeScript functions"""
        try:
            name = None
            parameters = []
            is_async = False
            is_generator = False
            return_type = None
            generics = []

            # Check for async/generator keywords
            node_text = self._get_node_text_optimized(node)
            is_async = "async" in node_text
            is_generator = node.type == "generator_function_declaration"

            for child in node.children:
                if child.type == "identifier":
                    name = child.text.decode("utf8") if child.text else None
                elif child.type == "formal_parameters":
                    parameters = self._extract_parameters_with_types(child)
                elif child.type == "type_annotation":
                    return_type = self._get_node_text_optimized(child).lstrip(": ")
                elif child.type == "type_parameters":
                    generics = self._extract_generics(child)

            return name, parameters, is_async, is_generator, return_type, generics
        except Exception:
            return None

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
        try:
            name = None
            parameters = []
            is_async = False
            is_static = False
            is_getter = False
            is_setter = False
            is_constructor = False
            return_type = None
            visibility = "public"
            generics = []

            # Check for method type
            node_text = self._get_node_text_optimized(node)
            is_async = "async" in node_text
            is_static = "static" in node_text

            # Check visibility
            if "private" in node_text:
                visibility = "private"
            elif "protected" in node_text:
                visibility = "protected"

            for child in node.children:
                if child.type in ["property_identifier", "identifier"]:
                    name = self._get_node_text_optimized(child)
                    # Fallback to direct text attribute if _get_node_text_optimized returns empty
                    if not name and hasattr(child, "text") and child.text:
                        name = (
                            child.text.decode("utf-8")
                            if isinstance(child.text, bytes)
                            else str(child.text)
                        )
                    is_constructor = name == "constructor"
                elif child.type == "formal_parameters":
                    parameters = self._extract_parameters_with_types(child)
                elif child.type == "type_annotation":
                    return_type = self._get_node_text_optimized(child).lstrip(": ")
                elif child.type == "type_parameters":
                    generics = self._extract_generics(child)

            # If name is still None, try to extract from node text
            if name is None:
                node_text = self._get_node_text_optimized(node)
                # Try to extract method name from the text
                import re

                match = re.search(
                    r"(?:async\s+)?(?:static\s+)?(?:public\s+|private\s+|protected\s+)?(\w+)\s*\(",
                    node_text,
                )
                if match:
                    name = match.group(1)

            # Set constructor flag after name is determined
            if name:
                is_constructor = name == "constructor"

            # Check for getter/setter
            if "get " in node_text:
                is_getter = True
            elif "set " in node_text:
                is_setter = True

            return (
                name,
                parameters,
                is_async,
                is_static,
                is_getter,
                is_setter,
                is_constructor,
                return_type,
                visibility,
                generics,
            )
        except Exception:
            return None

    # Extract elements from AST: _extract_parameters_with_types
    def _extract_parameters_with_types(
        self, params_node: "tree_sitter.Node"
    ) -> list[str]:
        """Extract function parameters with TypeScript type annotations"""
        parameters = []

        for child in params_node.children:
            if child.type == "identifier":
                param_name = self._get_node_text_optimized(child)
                parameters.append(param_name)
            elif child.type == "required_parameter":
                # Handle typed parameters
                param_text = self._get_node_text_optimized(child)
                parameters.append(param_text)
            elif child.type == "optional_parameter":
                # Handle optional parameters
                param_text = self._get_node_text_optimized(child)
                parameters.append(param_text)
            elif child.type == "rest_parameter":
                # Handle rest parameters (...args)
                rest_text = self._get_node_text_optimized(child)
                parameters.append(rest_text)
            elif child.type in ["object_pattern", "array_pattern"]:
                # Handle destructuring parameters
                destructure_text = self._get_node_text_optimized(child)
                parameters.append(destructure_text)

        return parameters

    # Extract elements from AST: _extract_generics
    def _extract_generics(self, type_params_node: "tree_sitter.Node") -> list[str]:
        """Extract generic type parameters"""
        generics = []

        for child in type_params_node.children:
            if child.type == "type_parameter":
                generic_text = self._get_node_text_optimized(child)
                generics.append(generic_text)

        # Return result
        return generics

    # Extract elements from AST: _extract_import_info_simple
    def _extract_import_info_simple(self, node: "tree_sitter.Node") -> Import | None:
        # Return result
        return _import_info_standalone(
            node, self.source_code, self._get_node_text_optimized
        )

    # Extract elements from AST: _extract_import_names
    def _extract_import_names(
        self, import_clause_node: "tree_sitter.Node", import_text: str = ""
    ) -> list[str]:
        # Return result
        return _import_names_standalone(
            import_clause_node, self.source_code, self._get_node_text_optimized
        )

    # Extract elements from AST: _extract_dynamic_import
    def _extract_dynamic_import(self, node: "tree_sitter.Node") -> Import | None:
        # Return result
        return _dynamic_import_standalone(node, self._get_node_text_optimized)

    # Extract elements from AST: _extract_commonjs_requires
    def _extract_commonjs_requires(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        # Return result
        return _commonjs_requires_standalone(
            tree, source_code, self._get_node_text_optimized
        )

    # Process: _is_framework_component
    def _is_framework_component(
        self, node: "tree_sitter.Node", class_name: str
    ) -> bool:
        """Check if class is a framework component"""
        # Check: self.framework_type == "react"
        if self.framework_type == "react":
            # Check if extends React.Component or Component
            node_text = self._get_node_text_optimized(node)
            # Return result
            return "extends" in node_text and (
                "Component" in node_text or "PureComponent" in node_text
            )
        elif self.framework_type == "angular":
            # Check for Angular component decorator
            return "@Component" in self.source_code
        elif self.framework_type == "vue":
            # Check for Vue component patterns
            return "Vue" in self.source_code or "@Component" in self.source_code
        # Return result
        return False

    # Process: _is_exported_class
    def _is_exported_class(self, class_name: str) -> bool:
        """Check if class is exported"""
        # Simple check for export statements
        return (
            f"export class {class_name}" in self.source_code
            or f"export default {class_name}" in self.source_code
        )

    # Process: _infer_type_from_value
    def _infer_type_from_value(self, value: str | None) -> str:
        """Infer TypeScript type from value"""
        # Check: not value
        if not value:
            # Return result
            return "any"

        value = value.strip()

        # Check: value.startswith('"') or value.startswit
        if value.startswith('"') or value.startswith("'") or value.startswith("`"):
            # Return result
            return "string"
        elif value in ["true", "false"]:
            # Return result
            return "boolean"
        elif value == "null":
            # Return result
            return "null"
        elif value == "undefined":
            # Return result
            return "undefined"
        elif value.startswith("[") and value.endswith("]"):
            # Return result
            return "array"
        elif value.startswith("{") and value.endswith("}"):
            # Return result
            return "object"
        elif value.replace(".", "").replace("-", "").isdigit():
            # Return result
            return "number"
        elif "function" in value or "=>" in value:
            # Return result
            return "function"
        else:
            # Return result
            return "any"

    # Extract elements from AST: _extract_tsdoc_for_line
    def _extract_tsdoc_for_line(self, target_line: int) -> str | None:
        """Extract TSDoc comment immediately before the specified line"""
        # Check: target_line in self._tsdoc_cache
        if target_line in self._tsdoc_cache:
            # Return result
            return self._tsdoc_cache[target_line]

        try:
            # Check: not self.content_lines or target_line <=
            if not self.content_lines or target_line <= 1:
                # Return result
                return None

            # Search backwards from target_line
            tsdoc_lines = []
            current_line = target_line - 1

            # Skip empty lines
            while current_line > 0:
                line = self.content_lines[current_line - 1].strip()
                # Check: line
                if line:
                    break
                current_line -= 1

            # Check for TSDoc end or single-line TSDoc
            if current_line > 0:
                line = self.content_lines[current_line - 1].strip()

                # Check for single-line TSDoc comment
                if line.startswith("/**") and line.endswith("*/"):
                    # Single line TSDoc
                    cleaned = self._clean_tsdoc(line)
                    self._tsdoc_cache[target_line] = cleaned
                    # Return result
                    return cleaned
                elif line.endswith("*/"):
                    # Multi-line TSDoc
                    tsdoc_lines.append(self.content_lines[current_line - 1])
                    current_line -= 1

                    # Collect TSDoc content
                    while current_line > 0:
                        line_content = self.content_lines[current_line - 1]
                        line_stripped = line_content.strip()
                        tsdoc_lines.append(line_content)

                        # Check: line_stripped.startswith("/**")
                        if line_stripped.startswith("/**"):
                            tsdoc_lines.reverse()
                            tsdoc_text = "\n".join(tsdoc_lines)
                            cleaned = self._clean_tsdoc(tsdoc_text)
                            self._tsdoc_cache[target_line] = cleaned
                            # Return result
                            return cleaned
                        current_line -= 1

            self._tsdoc_cache[target_line] = ""
            # Return result
            return None

        except Exception as e:
            log_debug(f"Failed to extract TSDoc: {e}")
            # Return result
            return None

    # Process: _clean_tsdoc
    def _clean_tsdoc(self, tsdoc_text: str) -> str:
        """Clean TSDoc text by removing comment markers"""
        # Check: not tsdoc_text
        if not tsdoc_text:
            # Return result
            return ""

        lines = tsdoc_text.split("\n")
        cleaned_lines = []

        # Iterate over line
        for line in lines:
            line = line.strip()

            # Check: line.startswith("/**")
            if line.startswith("/**"):
                line = line[3:].strip()
            elif line.startswith("*/"):
                line = line[2:].strip()
            elif line.startswith("*"):
                line = line[1:].strip()

            # Check: line
            if line:
                cleaned_lines.append(line)

        # Return result
        return " ".join(cleaned_lines) if cleaned_lines else ""

    # Process: _calculate_complexity_optimized
    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        """Calculate cyclomatic complexity efficiently"""
        node_id = id(node)
        # Check: node_id in self._complexity_cache
        if node_id in self._complexity_cache:
            # Return result
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
            # Iterate over keyword
            for keyword in keywords:
                complexity += node_text.count(keyword)
        except Exception as e:
            log_debug(f"Failed to calculate complexity: {e}")

        self._complexity_cache[node_id] = complexity
        # Return result
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

        # Return result
        return all_elements




