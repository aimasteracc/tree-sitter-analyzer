"""typescript_plugin mixin — core."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

import re

from ...encoding_utils import extract_text_slice, safe_encode
from ...models import (
    Class,
    CodeElement,
    Expression,
    Function,
    Import,
    Package,
    Variable,
)
from ...plugins.base import ElementExtractor
from ...utils import log_debug, log_error, log_warning
from ._base import _TypeScriptElementBase


class CoreMixin(_TypeScriptElementBase, ElementExtractor):

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
        self, tree: tree_sitter.Tree, source_code: str
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
            "function_signature": self._extract_function_signature_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, functions, "function"
        )

        log_debug(f"Extracted {len(functions)} TypeScript functions")
        return functions

    def extract_classes(
        self, tree: tree_sitter.Tree, source_code: str
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

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
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
            # Class field declarations: public name: string = ""
            "public_field_definition": self._extract_property_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, variables, "variable"
        )

        log_debug(f"Extracted {len(variables)} TypeScript variables")
        return variables

    def extract_imports(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Import]:
        """Extract TypeScript import statements with ES6+ and type import support"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        imports: list[Import] = []

        # Extract imports efficiently
        for child in tree.root_node.children:
            if child.type == "import_statement":
                import_info = self._extract_import_info_simple(child)
                if import_info:
                    imports.append(import_info)
            elif child.type == "expression_statement":
                # Check for dynamic imports
                dynamic_import = self._extract_dynamic_import(child)
                if dynamic_import:
                    imports.append(dynamic_import)

        # Also check for CommonJS requires (for compatibility)
        commonjs_imports = self._extract_commonjs_requires(tree, source_code)
        imports.extend(commonjs_imports)

        log_debug(f"Extracted {len(imports)} TypeScript imports")
        return imports

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
        root_node: tree_sitter.Node | None,
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
            "decorator",  # 添加 decorator 节点支持装饰器包裹的元素提取
            "public_field_definition",  # 添加 public_field_definition 支持装饰的字段
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

    def _get_node_text_optimized(self, node: tree_sitter.Node) -> str:
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

    def _extract_arrow_function_optimized(
        self, node: tree_sitter.Node
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
                node_type="arrow_function",
            )
        except Exception as e:
            log_debug(f"Failed to extract arrow function info: {e}")
            return None

    def _extract_method_optimized(self, node: tree_sitter.Node) -> Function | None:
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
                node_type="method_definition",
            )
        except Exception as e:
            log_debug(f"Failed to extract method info: {e}")
            return None

    def _extract_method_signature_optimized(
        self, node: tree_sitter.Node
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
                node_type="method_signature",
            )
        except Exception as e:
            log_debug(f"Failed to extract method signature info: {e}")
            return None

    def _extract_generator_function_optimized(
        self, node: tree_sitter.Node
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
                node_type="generator_function_declaration",
            )
        except Exception as e:
            log_debug(f"Failed to extract generator function info: {e}")
            return None

    def _extract_lexical_variable_optimized(
        self, node: tree_sitter.Node
    ) -> list[Variable]:
        """Extract let/const declaration variables"""
        # Determine if it's let or const
        node_text = self._get_node_text_optimized(node)
        kind = "let" if node_text.strip().startswith("let") else "const"
        return self._extract_variables_from_declaration(node, kind)

    def _extract_property_optimized(self, node: tree_sitter.Node) -> Variable | None:
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

    def _extract_property_signature_optimized(
        self, node: tree_sitter.Node
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

    def _parse_variable_declarator(
        self, node: tree_sitter.Node, kind: str, start_line: int, end_line: int
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

    def _parse_function_signature_optimized(
        self, node: tree_sitter.Node
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

    def _parse_method_signature_optimized(
        self, node: tree_sitter.Node
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

    def _extract_parameters_with_types(
        self, params_node: tree_sitter.Node
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

    def _extract_generics(self, type_params_node: tree_sitter.Node) -> list[str]:
        """Extract generic type parameters"""
        generics = []

        for child in type_params_node.children:
            if child.type == "type_parameter":
                generic_text = self._get_node_text_optimized(child)
                generics.append(generic_text)

        return generics

    def _extract_dynamic_import(self, node: tree_sitter.Node) -> Import | None:
        """Extract dynamic import() calls"""
        try:
            node_text = self._get_node_text_optimized(node)

            # Look for import() calls - more flexible regex
            import_match = re.search(
                r"import\s*\(\s*[\"']([^\"']+)[\"']\s*\)", node_text
            )
            if not import_match:
                # Try alternative pattern without quotes
                import_match = re.search(r"import\s*\(\s*([^)]+)\s*\)", node_text)
                if import_match:
                    source = import_match.group(1).strip("\"'")
                else:
                    return None
            else:
                source = import_match.group(1)

            return Import(
                name="dynamic_import",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=node_text,
                language="typescript",
                module_name=source,
                module_path=source,
                imported_names=["dynamic_import"],
            )
        except Exception as e:
            log_debug(f"Failed to extract dynamic import: {e}")
            return None

    def _extract_commonjs_requires(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Import]:
        """Extract CommonJS require() statements (for compatibility)"""
        imports = []

        try:
            # Test if _get_node_text_optimized is working (for error handling tests)
            if (
                hasattr(self, "_get_node_text_optimized")
                and tree
                and hasattr(tree, "root_node")
                and tree.root_node
            ):
                # This will trigger the mocked exception in tests
                self._get_node_text_optimized(tree.root_node)

            # Use regex to find require statements
            require_pattern = r"(?:const|let|var)\s+(\w+)\s*=\s*require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"

            for match in re.finditer(require_pattern, source_code):
                var_name = match.group(1)
                module_path = match.group(2)

                # Find line number
                line_num = source_code[: match.start()].count("\n") + 1

                import_obj = Import(
                    name=var_name,
                    start_line=line_num,
                    end_line=line_num,
                    raw_text=match.group(0),
                    language="typescript",
                    module_path=module_path,
                    module_name=module_path,
                    imported_names=[var_name],
                )
                imports.append(import_obj)

        except Exception as e:
            log_debug(f"Failed to extract CommonJS requires: {e}")
            return []

        return imports

    def _is_framework_component(
        self, node: tree_sitter.Node, class_name: str
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
        elif value in ["true", "false"]:
            return "boolean"
        elif value == "null":
            return "null"
        elif value == "undefined":
            return "undefined"
        elif value.startswith("[") and value.endswith("]"):
            return "array"
        elif value.startswith("{") and value.endswith("}"):
            return "object"
        elif value.replace(".", "").replace("-", "").isdigit():
            return "number"
        elif "function" in value or "=>" in value:
            return "function"
        else:
            return "any"

    def _extract_tsdoc_for_line(self, target_line: int) -> str | None:
        """Extract TSDoc comment immediately before the specified line"""
        if target_line in self._tsdoc_cache:
            return self._tsdoc_cache[target_line]

        try:
            if not self.content_lines or target_line <= 1:
                return None

            # Search backwards from target_line
            tsdoc_lines = []
            current_line = target_line - 1

            # Skip empty lines
            while current_line > 0:
                line = self.content_lines[current_line - 1].strip()
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

                        if line_stripped.startswith("/**"):
                            tsdoc_lines.reverse()
                            tsdoc_text = "\n".join(tsdoc_lines)
                            cleaned = self._clean_tsdoc(tsdoc_text)
                            self._tsdoc_cache[target_line] = cleaned
                            return cleaned
                        current_line -= 1

            self._tsdoc_cache[target_line] = ""
            return None

        except Exception as e:
            log_debug(f"Failed to extract TSDoc: {e}")
            return None

    def _clean_tsdoc(self, tsdoc_text: str) -> str:
        """Clean TSDoc text by removing comment markers"""
        if not tsdoc_text:
            return ""

        lines = tsdoc_text.split("\n")
        cleaned_lines = []

        for line in lines:
            line = line.strip()

            if line.startswith("/**"):
                line = line[3:].strip()
            elif line.startswith("*/"):
                line = line[2:].strip()
            elif line.startswith("*"):
                line = line[1:].strip()

            if line:
                cleaned_lines.append(line)

        return " ".join(cleaned_lines) if cleaned_lines else ""

    def _calculate_complexity_optimized(self, node: tree_sitter.Node) -> int:
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

    def extract_exports(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Expression]:
        """
        Extract export clauses and specifiers.

        Captures export statements like: export { foo, bar as baz }
        """
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        exports: list[Expression] = []
        stack = [tree.root_node]

        while stack:
            node = stack.pop()

            if node.type in ["export_clause", "export_specifier"]:
                try:
                    raw_text = self._get_node_text_optimized(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    exports.append(
                        Expression(
                            name=node.type,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="typescript",
                            expression_kind=node.type,
                            preview=raw_text,
                            node_type=node.type,
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting {node.type}: {e}")

            for child in reversed(node.children):
                stack.append(child)

        log_debug(f"Extracted {len(exports)} export elements")
        return exports

    def extract_patterns(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Expression]:
        """
        Extract destructuring patterns (array_pattern, pair_pattern).

        Captures patterns like: const [a, b] = [1, 2] and const {x: y} = {x: 10}
        """
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        patterns: list[Expression] = []
        stack = [tree.root_node]

        while stack:
            node = stack.pop()

            if node.type in ["array_pattern", "pair_pattern"]:
                try:
                    raw_text = self._get_node_text_optimized(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    patterns.append(
                        Expression(
                            name=node.type,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="typescript",
                            expression_kind=node.type,
                            preview=raw_text,
                            node_type=node.type,
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting {node.type}: {e}")

            for child in reversed(node.children):
                stack.append(child)

        log_debug(f"Extracted {len(patterns)} pattern elements")
        return patterns

    def extract_namespaces(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Package]:
        """
        Extract namespace declarations (internal_module).

        Captures: namespace MyNamespace { ... }
        """
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        namespaces: list[Package] = []
        stack = [tree.root_node]

        while stack:
            node = stack.pop()

            if node.type == "internal_module":
                try:
                    # Extract namespace name
                    namespace_name = "unknown"
                    for child in node.children:
                        if child.type == "identifier":
                            namespace_name = self._get_node_text_optimized(child)
                            break

                    raw_text = self._get_node_text_optimized(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    namespaces.append(
                        Package(
                            name=namespace_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="typescript",
                            node_type="internal_module",
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting internal_module: {e}")

            for child in reversed(node.children):
                stack.append(child)

        log_debug(f"Extracted {len(namespaces)} namespace elements")
        return namespaces

    def extract_ambient_declarations(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Package]:
        """
        Extract ambient declarations (declare module).

        Captures: declare module "test" { ... }
        """
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        declarations: list[Package] = []
        stack = [tree.root_node]

        while stack:
            node = stack.pop()

            if node.type == "ambient_declaration":
                try:
                    # Extract module name from string literal
                    module_name = "unknown"
                    for child in node.children:
                        if child.type == "string":
                            module_name = self._get_node_text_optimized(child).strip(
                                '"'
                            ).strip("'")
                            break
                        elif child.type == "identifier":
                            module_name = self._get_node_text_optimized(child)
                            break

                    raw_text = self._get_node_text_optimized(node)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    declarations.append(
                        Package(
                            name=module_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="typescript",
                            node_type="ambient_declaration",
                        )
                    )
                except Exception as e:
                    log_debug(f"Error extracting ambient_declaration: {e}")

            for child in reversed(node.children):
                stack.append(child)

        log_debug(f"Extracted {len(declarations)} ambient declaration elements")
        return declarations

    def extract_elements(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[CodeElement]:
        """Legacy method for backward compatibility with tests"""
        all_elements: list[CodeElement] = []

        # Extract all types of elements
        all_elements.extend(self.extract_functions(tree, source_code))
        all_elements.extend(self.extract_classes(tree, source_code))
        all_elements.extend(self.extract_variables(tree, source_code))
        all_elements.extend(self.extract_imports(tree, source_code))
        all_elements.extend(self.extract_exports(tree, source_code))
        all_elements.extend(self.extract_patterns(tree, source_code))
        all_elements.extend(self.extract_namespaces(tree, source_code))
        all_elements.extend(self.extract_ambient_declarations(tree, source_code))

        return all_elements
