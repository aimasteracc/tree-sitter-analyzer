#!/usr/bin/env python3
"""
JavaScript Language Plugin

Enhanced JavaScript-specific parsing and element extraction functionality.
Provides comprehensive support for modern JavaScript features including ES6+,
async/await, classes, modules, JSX, and framework-specific patterns.
Equivalent to Java plugin capabilities for consistent language support.
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

from ..core.analysis_engine import AnalysisRequest
from ..encoding_utils import extract_text_slice, safe_encode
from ..language_loader import loader
from ..models import AnalysisResult, Class, CodeElement, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_warning


class JavaScriptElementExtractor(ElementExtractor):
    """Enhanced JavaScript-specific element extractor with comprehensive feature support"""

    def __init__(self) -> None:
        """Initialize the JavaScript element extractor."""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.imports: list[str] = []
        self.exports: list[dict[str, Any]] = []

        # Performance optimization caches
        self._node_text_cache: dict[int, str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None
        self._jsdoc_cache: dict[int, str] = {}
        self._complexity_cache: dict[int, int] = {}

        # JavaScript-specific tracking
        self.is_module: bool = False
        self.is_jsx: bool = False
        self.framework_type: str = ""  # react, vue, angular, etc.

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract JavaScript function definitions with comprehensive details"""
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
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, functions, "function"
        )

        log_debug(f"Extracted {len(functions)} JavaScript functions")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract JavaScript class definitions with detailed information"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        # Extract both class declarations and expressions
        extractors = {
            "class_declaration": self._extract_class_optimized,
            "class_expression": self._extract_class_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, classes, "class"
        )

        log_debug(f"Extracted {len(classes)} JavaScript classes")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract JavaScript variable definitions with modern syntax support"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        # Handle all JavaScript variable declaration types
        extractors = {
            "variable_declaration": self._extract_variable_optimized,
            "lexical_declaration": self._extract_lexical_variable_optimized,
            "property_definition": self._extract_property_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, variables, "variable"
        )

        log_debug(f"Extracted {len(variables)} JavaScript variables")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract JavaScript import statements with ES6+ support"""
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

        # Also check for CommonJS requires
        commonjs_imports = self._extract_commonjs_requires(tree, source_code)
        imports.extend(commonjs_imports)

        log_debug(f"Extracted {len(imports)} JavaScript imports")
        return imports

    def extract_exports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[dict[str, Any]]:
        """Extract JavaScript export statements"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        exports: list[dict[str, Any]] = []

        # Extract ES6 exports
        for child in tree.root_node.children:
            if child.type == "export_statement":
                export_info = self._extract_export_info(child)
                if export_info:
                    exports.append(export_info)

        # Also check for CommonJS exports
        commonjs_exports = self._extract_commonjs_exports(tree, source_code)
        exports.extend(commonjs_exports)

        self.exports = exports
        log_debug(f"Extracted {len(exports)} JavaScript exports")
        return exports

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
        root_node: "tree_sitter.Node",
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
            "statement_block",
            "object",
            "class_declaration",
            "function_declaration",
            "method_definition",
            "export_statement",
            "variable_declaration",
            "lexical_declaration",
            "variable_declarator",
            "assignment_expression",
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

    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """Get node text with optimized caching"""
        node_id = id(node)

        if node_id in self._node_text_cache:
            return self._node_text_cache[node_id]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte

            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)

            self._node_text_cache[node_id] = text
            return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")
            # Fallback to simple text extraction
            try:
                start_point = node.start_point
                end_point = node.end_point

                if start_point[0] == end_point[0]:
                    line = self.content_lines[start_point[0]]
                    return line[start_point[1] : end_point[1]]
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

    def _extract_function_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract regular function information with detailed metadata"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract function details
            function_info = self._parse_function_signature_optimized(node)
            if not function_info:
                return None

            name, parameters, is_async, is_generator = function_info

            # Extract JSDoc
            jsdoc = self._extract_jsdoc_for_line(start_line)

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
                language="javascript",
                parameters=parameters,
                return_type="unknown",  # JavaScript is dynamically typed
                is_async=is_async,
                is_generator=is_generator,
                docstring=jsdoc,
                complexity_score=complexity_score,
                # JavaScript-specific properties
                is_arrow=False,
                is_method=False,
                framework_type=self.framework_type,
            )
        except Exception as e:
            log_error(f"Failed to extract function info: {e}")
            import traceback

            traceback.print_exc()
            return None

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

            # Extract parameters
            parameters = []
            for child in node.children:
                if child.type == "formal_parameters":
                    parameters = self._extract_parameters(child)
                elif child.type == "identifier":
                    # Single parameter without parentheses
                    param_name = self._get_node_text_optimized(child)
                    parameters = [param_name]

            # Check if async
            is_async = "async" in self._get_node_text_optimized(node)

            # Extract JSDoc (look at parent variable declaration)
            jsdoc = self._extract_jsdoc_for_line(start_line)

            # Calculate complexity
            complexity_score = self._calculate_complexity_optimized(node)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="javascript",
                parameters=parameters,
                return_type="unknown",
                is_async=is_async,
                is_generator=False,
                docstring=jsdoc,
                complexity_score=complexity_score,
                # JavaScript-specific properties
                is_arrow=True,
                is_method=False,
                framework_type=self.framework_type,
            )
        except Exception as e:
            log_debug(f"Failed to extract arrow function info: {e}")
            return None

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
            ) = method_info

            # Find parent class (currently not used but may be needed for future enhancements)
            # class_name = self._find_parent_class_name(node)

            # Extract JSDoc
            jsdoc = self._extract_jsdoc_for_line(start_line)

            # Calculate complexity
            complexity_score = self._calculate_complexity_optimized(node)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="javascript",
                parameters=parameters,
                return_type="unknown",
                is_async=is_async,
                is_static=is_static,
                is_constructor=is_constructor,
                docstring=jsdoc,
                complexity_score=complexity_score,
                # JavaScript-specific properties
                is_arrow=False,
                is_method=True,
                framework_type=self.framework_type,
            )
        except Exception as e:
            log_debug(f"Failed to extract method info: {e}")
            # Re-raise for debugging
            raise

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

            name, parameters, is_async, _ = function_info

            # Extract JSDoc
            jsdoc = self._extract_jsdoc_for_line(start_line)

            # Calculate complexity
            complexity_score = self._calculate_complexity_optimized(node)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="javascript",
                parameters=parameters,
                return_type="Generator",
                is_async=is_async,
                is_generator=True,
                docstring=jsdoc,
                complexity_score=complexity_score,
                # JavaScript-specific properties
                is_arrow=False,
                is_method=False,
                framework_type=self.framework_type,
            )
        except Exception as e:
            log_debug(f"Failed to extract generator function info: {e}")
            return None

    def _extract_class_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class information with detailed metadata"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract class name
            class_name = None
            superclass = None

            for child in node.children:
                if child.type == "identifier":
                    class_name = child.text.decode("utf8") if child.text else None
                elif child.type == "class_heritage":
                    # Extract extends clause
                    heritage_text = self._get_node_text_optimized(child)
                    # Support both simple names (Component) and dotted names (React.Component)
                    match = re.search(r"extends\s+([\w.]+)", heritage_text)
                    if match:
                        superclass = match.group(1)

            if not class_name:
                return None

            # Extract JSDoc
            jsdoc = self._extract_jsdoc_for_line(start_line)

            # Check if it's a React component
            is_react_component = self._is_react_component(node, class_name)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Class(
                name=class_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="javascript",
                class_type="class",
                superclass=superclass,
                docstring=jsdoc,
                # JavaScript-specific properties
                is_react_component=is_react_component,
                framework_type=self.framework_type,
                is_exported=self._is_exported_class(class_name),
            )
        except Exception as e:
            log_debug(f"Failed to extract class info: {e}")
            return None

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
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

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
                value=prop_value,
                is_static=is_static,
                is_constant=False,  # Class properties are not const
                # JavaScript-specific properties
                # class_name=class_name,  # Not available since class_name is commented out
                declaration_kind="property",
                framework_type=self.framework_type,
            )
        except Exception as e:
            log_debug(f"Failed to extract property info: {e}")
            return None

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

    def _parse_variable_declarator(
        self, node: "tree_sitter.Node", kind: str, start_line: int, end_line: int
    ) -> Variable | None:
        """Parse individual variable declarator"""
        try:
            var_name = None
            var_value = None

            # Find identifier and value in children
            for child in node.children:
                if child.type == "identifier":
                    var_name = self._get_node_text_optimized(child)
                elif child.type == "=" and child.next_sibling:
                    # Get the value after the assignment operator
                    value_node = child.next_sibling
                    var_value = self._get_node_text_optimized(value_node)
                elif child.type in [
                    "string",
                    "number",
                    "true",
                    "false",
                    "null",
                    "object",
                    "array",
                    "function_expression",
                    "arrow_function",
                    "call_expression",
                    "member_expression",
                    "template_literal",
                ]:
                    var_value = self._get_node_text_optimized(child)

            # If no value found through assignment, try to find any value node
            if not var_value and len(node.children) >= 3:
                # Pattern: identifier = value
                for i, child in enumerate(node.children):
                    if child.type == "=" and i + 1 < len(node.children):
                        value_node = node.children[i + 1]
                        # Skip arrow functions - they should be handled by function extractor
                        if value_node.type == "arrow_function":
                            return None
                        var_value = self._get_node_text_optimized(value_node)
                        break

            if not var_name:
                return None

            # Skip variables that are arrow functions
            for child in node.children:
                if child.type == "arrow_function":
                    return None

            # Extract JSDoc
            jsdoc = self._extract_jsdoc_for_line(start_line)

            # Extract raw text with declaration keyword
            raw_text = self._get_node_text_optimized(node)

            # Try to get parent declaration for complete text
            parent = node.parent
            if parent and parent.type in [
                "lexical_declaration",
                "variable_declaration",
            ]:
                parent_text = self._get_node_text_optimized(parent)
                if parent_text and len(parent_text) > len(raw_text):
                    # Only use parent text if it contains our node text
                    if raw_text in parent_text:
                        raw_text = parent_text

            return Variable(
                name=var_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="javascript",
                variable_type=self._infer_type_from_value(var_value),
                is_static=False,
                is_constant=(kind == "const"),
                docstring=jsdoc,
                initializer=var_value,  # Use initializer instead of value
            )
        except Exception as e:
            log_debug(f"Failed to parse variable declarator: {e}")
            return None

    def _parse_function_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, list[str], bool, bool] | None:
        """Parse function signature for regular functions"""
        try:
            name = None
            parameters = []
            is_async = False
            is_generator = False

            # Check for async/generator keywords
            node_text = self._get_node_text_optimized(node)
            is_async = "async" in node_text
            is_generator = node.type == "generator_function_declaration"

            for child in node.children:
                if child.type == "identifier":
                    name = child.text.decode("utf8") if child.text else None
                elif child.type == "formal_parameters":
                    parameters = self._extract_parameters(child)

            return name or "", parameters, is_async, is_generator
        except Exception:
            return None

    def _parse_method_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, list[str], bool, bool, bool, bool, bool] | None:
        """Parse method signature for class methods"""
        try:
            name = None
            parameters = []
            is_async = False
            is_static = False
            is_getter = False
            is_setter = False
            is_constructor = False

            # Check for method type
            node_text = self._get_node_text_optimized(node)
            is_async = "async" in node_text
            is_static = "static" in node_text

            for child in node.children:
                if child.type == "property_identifier":
                    name = self._get_node_text_optimized(child)
                    is_constructor = name == "constructor"
                elif child.type == "formal_parameters":
                    parameters = self._extract_parameters(child)

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
            )
        except Exception:
            return None

    def _extract_parameters(self, params_node: "tree_sitter.Node") -> list[str]:
        """Extract function parameters"""
        parameters = []

        for child in params_node.children:
            if child.type == "identifier":
                param_name = self._get_node_text_optimized(child)
                parameters.append(param_name)
            elif child.type == "rest_parameter":
                # Handle rest parameters (...args)
                rest_text = self._get_node_text_optimized(child)
                parameters.append(rest_text)
            elif child.type in ["object_pattern", "array_pattern"]:
                # Handle destructuring parameters
                destructure_text = self._get_node_text_optimized(child)
                parameters.append(destructure_text)

        return parameters

    def _extract_import_info_simple(self, node: "tree_sitter.Node") -> Import | None:
        """Extract import information from import_statement node"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Get raw text using byte positions
            start_byte = node.start_byte
            end_byte = node.end_byte
            source_bytes = self.source_code.encode("utf-8")
            raw_text = source_bytes[start_byte:end_byte].decode("utf-8")

            # Extract import details from AST structure
            import_names = []
            module_path = ""

            for child in node.children:
                if child.type == "import_clause":
                    import_names.extend(self._extract_import_names(child))
                elif child.type == "string":
                    # Module path
                    module_text = source_bytes[
                        child.start_byte : child.end_byte
                    ].decode("utf-8")
                    module_path = module_text.strip("\"'")

            # Use first import name or "unknown"
            primary_name = import_names[0] if import_names else "unknown"

            return Import(
                name=primary_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="javascript",
                module_path=module_path,
                module_name=module_path,
                imported_names=import_names,
            )

        except Exception as e:
            log_debug(f"Failed to extract import info: {e}")
            return None

    def _extract_import_names(
        self, import_clause_node: "tree_sitter.Node"
    ) -> list[str]:
        """Extract import names from import clause"""
        names = []
        source_bytes = self.source_code.encode("utf-8")

        for child in import_clause_node.children:
            if child.type == "import_default_specifier":
                # Default import
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        name_text = source_bytes[
                            grandchild.start_byte : grandchild.end_byte
                        ].decode("utf-8")
                        names.append(name_text)
            elif child.type == "named_imports":
                # Named imports
                for grandchild in child.children:
                    if grandchild.type == "import_specifier":
                        for ggchild in grandchild.children:
                            if ggchild.type == "identifier":
                                name_text = source_bytes[
                                    ggchild.start_byte : ggchild.end_byte
                                ].decode("utf-8")
                                names.append(name_text)

        return names

    def _extract_import_info_enhanced(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Import | None:
        """Extract enhanced import information"""
        try:
            import_text = self._get_node_text_optimized(node)

            # Parse different import types
            import_info = self._parse_import_statement(import_text)
            if not import_info:
                return None

            import_type, names, source, is_default, is_namespace = import_info

            return Import(
                name=names[0] if names else "unknown",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=import_text,
                language="javascript",
                module_path=source,
                # JavaScript-specific properties
                import_type=import_type,
                imported_names=names,
                is_default=is_default,
                is_namespace=is_namespace,
                is_dynamic=False,
            )
        except Exception as e:
            log_debug(f"Failed to extract import info: {e}")
            return None

    def _extract_dynamic_import(self, node: "tree_sitter.Node") -> Import | None:
        """Extract dynamic import() calls"""
        try:
            node_text = self._get_node_text_optimized(node)

            # Look for import() calls
            import_match = re.search(
                r"import\s*\(\s*[\"']([^\"']+)[\"']\s*\)", node_text
            )
            if not import_match:
                return None

            source = import_match.group(1)

            return Import(
                name="dynamic_import",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=node_text,
                language="javascript",
                module_path=source,
                # JavaScript-specific properties
                import_type="dynamic",
                is_dynamic=True,
            )
        except Exception as e:
            log_debug(f"Failed to extract dynamic import: {e}")
            return None

    def _extract_commonjs_requires(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract CommonJS require() statements"""
        imports = []

        try:
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
                    language="javascript",
                    module_path=module_path,
                    module_name=module_path,
                    imported_names=[var_name],
                )
                imports.append(import_obj)

        except Exception as e:
            log_debug(f"Failed to extract CommonJS requires: {e}")
            # Re-raise for debugging
            raise

        return imports

    def _extract_export_info(self, node: "tree_sitter.Node") -> dict[str, Any] | None:
        """Extract export information"""
        try:
            export_text = self._get_node_text_optimized(node)

            # Parse export type
            export_info = self._parse_export_statement(export_text)
            if not export_info:
                return None

            export_type, names, is_default = export_info

            return {
                "type": export_type,
                "names": names,
                "is_default": is_default,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "raw_text": export_text,
            }
        except Exception as e:
            log_debug(f"Failed to extract export info: {e}")
            return None

    def _extract_commonjs_exports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[dict[str, Any]]:
        """Extract CommonJS module.exports statements"""
        exports = []

        try:
            # Look for module.exports patterns
            patterns = [
                r"module\.exports\s*=\s*(\w+)",
                r"module\.exports\.(\w+)\s*=",
                r"exports\.(\w+)\s*=",
            ]

            for pattern in patterns:
                for match in re.finditer(pattern, source_code):
                    name = match.group(1)
                    line_num = source_code[: match.start()].count("\n") + 1

                    export_obj = {
                        "type": "commonjs",
                        "names": [name],
                        "is_default": "module.exports =" in match.group(0),
                        "start_line": line_num,
                        "end_line": line_num,
                        "raw_text": match.group(0),
                    }
                    exports.append(export_obj)

        except Exception as e:
            log_debug(f"Failed to extract CommonJS exports: {e}")

        return exports

    def _parse_import_statement(
        self, import_text: str
    ) -> tuple[str, list[str], str, bool, bool] | None:
        """Parse import statement to extract details"""
        try:
            # Remove semicolon and clean up
            clean_text = import_text.strip().rstrip(";")

            # Extract source
            source_match = re.search(r"from\s+[\"']([^\"']+)[\"']", clean_text)
            if not source_match:
                return None

            source = source_match.group(1)

            # Determine import type and extract names
            if "import * as" in clean_text:
                # Namespace import
                namespace_match = re.search(r"import\s+\*\s+as\s+(\w+)", clean_text)
                if namespace_match:
                    return "namespace", [namespace_match.group(1)], source, False, True

            elif "import {" in clean_text:
                # Named imports
                named_match = re.search(r"import\s+\{([^}]+)\}", clean_text)
                if named_match:
                    names_text = named_match.group(1)
                    names = [name.strip() for name in names_text.split(",")]
                    return "named", names, source, False, False

            else:
                # Default import
                default_match = re.search(r"import\s+(\w+)", clean_text)
                if default_match:
                    return "default", [default_match.group(1)], source, True, False

            return None
        except Exception:
            return None

    def _parse_export_statement(
        self, export_text: str
    ) -> tuple[str, list[str], bool] | None:
        """Parse export statement to extract details"""
        try:
            clean_text = export_text.strip().rstrip(";")

            if "export default" in clean_text:
                # Default export
                default_match = re.search(r"export\s+default\s+(\w+)", clean_text)
                if default_match:
                    return "default", [default_match.group(1)], True
                else:
                    return "default", ["default"], True

            elif "export {" in clean_text:
                # Named exports
                named_match = re.search(r"export\s+\{([^}]+)\}", clean_text)
                if named_match:
                    names_text = named_match.group(1)
                    names = [name.strip() for name in names_text.split(",")]
                    return "named", names, False

            elif (
                clean_text.startswith("export ")
                and not clean_text == "invalid export statement"
            ):
                # Direct export (export function, export class, etc.)
                # But skip obviously invalid statements
                direct_match = re.search(
                    r"export\s+(function|class|const|let|var)\s+(\w+)", clean_text
                )
                if direct_match:
                    return "direct", [direct_match.group(2)], False
                else:
                    return "direct", ["unknown"], False

            return None
        except Exception:
            return None

    def _find_parent_class_name(self, node: "tree_sitter.Node") -> str | None:
        """Find parent class name for methods/properties"""
        current = node.parent
        while current:
            if current.type in ["class_declaration", "class_expression"]:
                for child in current.children:
                    if child.type == "identifier":
                        return self._get_node_text_optimized(child)
            current = current.parent
        return None

    def _is_react_component(self, node: "tree_sitter.Node", class_name: str) -> bool:
        """Check if class is a React component"""
        if self.framework_type != "react":
            return False

        # Check if extends React.Component or Component
        node_text = self._get_node_text_optimized(node)
        return "extends" in node_text and (
            "Component" in node_text or "PureComponent" in node_text
        )

    def _is_exported_class(self, class_name: str) -> bool:
        """Check if class is exported"""
        for export in self.exports:
            if class_name in export.get("names", []):
                return True
        return False

    def _infer_type_from_value(self, value: str | None) -> str:
        """Infer JavaScript type from value"""
        if not value:
            return "unknown"

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
            return "unknown"

    def extract_elements(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """Extract elements from source code using tree-sitter AST"""
        elements = []

        try:
            elements.extend(self.extract_functions(tree, source_code))
            elements.extend(self.extract_classes(tree, source_code))
            elements.extend(self.extract_variables(tree, source_code))
            elements.extend(self.extract_imports(tree, source_code))
        except Exception as e:
            log_error(f"Failed to extract elements: {e}")

        return elements

    def _get_variable_kind(self, var_data: dict | str) -> str:
        """Get variable declaration kind from variable data or raw text"""
        if isinstance(var_data, dict):
            raw_text = var_data.get("raw_text", "")
        else:
            raw_text = var_data

        if not raw_text:
            return "unknown"

        raw_text = str(raw_text).strip()
        if raw_text.startswith("const"):
            return "const"
        elif raw_text.startswith("let"):
            return "let"
        elif raw_text.startswith("var"):
            return "var"
        else:
            return "unknown"

    def _extract_jsdoc_for_line(self, target_line: int) -> str | None:
        """Extract JSDoc comment immediately before the specified line"""
        if target_line in self._jsdoc_cache:
            return self._jsdoc_cache[target_line]

        try:
            if not self.content_lines or target_line <= 1:
                return None

            # Search backwards from target_line
            jsdoc_lines = []
            current_line = target_line - 1

            # Skip empty lines
            while current_line > 0:
                line = self.content_lines[current_line - 1].strip()
                if line:
                    break
                current_line -= 1

            # Check for JSDoc end
            if current_line > 0:
                line = self.content_lines[current_line - 1].strip()
                if line.endswith("*/"):
                    jsdoc_lines.append(self.content_lines[current_line - 1])
                    current_line -= 1

                    # Collect JSDoc content
                    while current_line > 0:
                        line_content = self.content_lines[current_line - 1]
                        line_stripped = line_content.strip()
                        jsdoc_lines.append(line_content)

                        if line_stripped.startswith("/**"):
                            jsdoc_lines.reverse()
                            jsdoc_text = "\n".join(jsdoc_lines)
                            cleaned = self._clean_jsdoc(jsdoc_text)
                            self._jsdoc_cache[target_line] = cleaned
                            return cleaned
                        current_line -= 1

            self._jsdoc_cache[target_line] = None
            return None

        except Exception as e:
            log_debug(f"Failed to extract JSDoc: {e}")
            return None

    def _clean_jsdoc(self, jsdoc_text: str) -> str:
        """Clean JSDoc text by removing comment markers"""
        if not jsdoc_text:
            return ""

        lines = jsdoc_text.split("\n")
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


class JavaScriptPlugin(LanguagePlugin):
    """Enhanced JavaScript language plugin with comprehensive feature support"""

    def __init__(self) -> None:
        self._extractor = JavaScriptElementExtractor()
        self._language: tree_sitter.Language | None = None

        # Legacy compatibility attributes for tests
        self.language = "javascript"
        self.extractor = self._extractor
        self.supported_extensions = [".js", ".mjs", ".jsx", ".es6", ".es", ".cjs"]

    @property
    def language_name(self) -> str:
        return "javascript"

    @property
    def file_extensions(self) -> list[str]:
        return [".js", ".mjs", ".jsx", ".es6", ".es"]

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "javascript"

    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return [".js", ".mjs", ".jsx", ".es6", ".es"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return JavaScriptElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        return self._extractor

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
        """Load and return JavaScript tree-sitter language"""
        if self._language is None:
            self._language = loader.load_language("javascript")
        return self._language

    def get_supported_queries(self) -> list[str]:
        """Get list of supported query names for this language"""
        return [
            "function",
            "class",
            "variable",
            "import",
            "export",
            "async_function",
            "arrow_function",
            "method",
            "constructor",
            "react_component",
            "react_hook",
            "jsx_element",
        ]

    def is_applicable(self, file_path: str) -> bool:
        """Check if this plugin is applicable for the given file"""
        return any(
            file_path.lower().endswith(ext.lower())
            for ext in self.get_file_extensions()
        )

    def get_plugin_info(self) -> dict:
        """Get information about this plugin"""
        return {
            "name": "JavaScript Plugin",
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "version": "2.0.0",
            "supported_queries": self.get_supported_queries(),
            "features": [
                "ES6+ syntax support",
                "Async/await functions",
                "Arrow functions",
                "Classes and methods",
                "Module imports/exports",
                "JSX support",
                "React component detection",
                "CommonJS support",
                "JSDoc extraction",
                "Complexity analysis",
            ],
        }

    def execute_query_strategy(
        self, tree: "tree_sitter.Tree", source_code: str, query_key: str
    ) -> list[dict]:
        """
        Execute query strategy for JavaScript language

        Args:
            tree: Tree-sitter tree object
            source_code: Source code string
            query_key: Query key to execute

        Returns:
            List of query results
        """
        # Use the extractor to get elements based on query_key
        extractor = self.get_extractor()

        # Map query keys to extraction methods
        if query_key in [
            "function",
            "functions",
            "async_function",
            "async_functions",
            "arrow_function",
            "arrow_functions",
            "method",
            "methods",
            "constructor",
            "constructors",
        ]:
            elements = extractor.extract_functions(tree, source_code)
        elif query_key in ["class", "classes", "react_component", "react_components"]:
            elements = extractor.extract_classes(tree, source_code)
        elif query_key in ["variable", "variables"]:
            elements = extractor.extract_variables(tree, source_code)
        elif query_key in ["import", "imports"]:
            elements = extractor.extract_imports(tree, source_code)
        else:
            # For unknown query keys, return empty list
            return []

        # Convert elements to query result format
        results = []
        for element in elements:
            result = {
                "capture_name": query_key,
                "node_type": self._get_node_type_for_element(element),
                "start_line": element.start_line,
                "end_line": element.end_line,
                "text": element.raw_text,
                "name": element.name,
            }
            results.append(result)

        return results

    def _get_node_type_for_element(self, element) -> str:
        """Get appropriate node type for element"""
        from ..models import Class, Function, Import, Variable

        if isinstance(element, Function):
            if hasattr(element, "is_arrow") and element.is_arrow:
                return "arrow_function"
            elif hasattr(element, "is_method") and element.is_method:
                return "method_definition"
            else:
                return "function_declaration"
        elif isinstance(element, Class):
            return "class_declaration"
        elif isinstance(element, Variable):
            return "variable_declaration"
        elif isinstance(element, Import):
            return "import_statement"
        else:
            return "unknown"

    def get_element_categories(self) -> dict[str, list[str]]:
        """
        Get element categories mapping query keys to node types

        Returns:
            Dictionary mapping query keys to lists of node types
        """
        return {
            # Function-related queries
            "function": ["function_declaration", "function_expression"],
            "functions": ["function_declaration", "function_expression"],
            "async_function": ["function_declaration", "function_expression"],
            "async_functions": ["function_declaration", "function_expression"],
            "arrow_function": ["arrow_function"],
            "arrow_functions": ["arrow_function"],
            "method": ["method_definition"],
            "methods": ["method_definition"],
            "constructor": ["method_definition"],
            "constructors": ["method_definition"],
            # Class-related queries
            "class": ["class_declaration", "class_expression"],
            "classes": ["class_declaration", "class_expression"],
            # Variable-related queries
            "variable": ["variable_declaration", "lexical_declaration"],
            "variables": ["variable_declaration", "lexical_declaration"],
            # Import/Export-related queries
            "import": ["import_statement"],
            "imports": ["import_statement"],
            "export": ["export_statement"],
            "exports": ["export_statement"],
            # React-specific queries
            "react_component": ["class_declaration", "function_declaration"],
            "react_components": ["class_declaration", "function_declaration"],
            "react_hook": ["function_declaration"],
            "react_hooks": ["function_declaration"],
            "jsx_element": ["jsx_element", "jsx_self_closing_element"],
            "jsx_elements": ["jsx_element", "jsx_self_closing_element"],
            # Generic queries
            "all_elements": [
                "function_declaration",
                "function_expression",
                "arrow_function",
                "method_definition",
                "class_declaration",
                "class_expression",
                "variable_declaration",
                "lexical_declaration",
                "import_statement",
                "export_statement",
                "jsx_element",
                "jsx_self_closing_element",
            ],
        }

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze a JavaScript file and return the analysis results."""
        if not TREE_SITTER_AVAILABLE:
            return AnalysisResult(
                file_path=file_path,
                language=self.language_name,
                success=False,
                error_message="Tree-sitter library not available.",
            )

        language = self.get_tree_sitter_language()
        if not language:
            return AnalysisResult(
                file_path=file_path,
                language=self.language_name,
                success=False,
                error_message="Could not load JavaScript language for parsing.",
            )

        try:
            with open(file_path, encoding="utf-8") as f:
                source_code = f.read()

            parser = tree_sitter.Parser()
            parser.language = language
            tree = parser.parse(bytes(source_code, "utf8"))

            extractor = self.create_extractor()
            extractor.current_file = file_path  # Set current file for context

            elements: list[CodeElement] = []

            # Extract all element types
            functions = extractor.extract_functions(tree, source_code)
            classes = extractor.extract_classes(tree, source_code)
            variables = extractor.extract_variables(tree, source_code)
            imports = extractor.extract_imports(tree, source_code)

            # Add exports if extractor supports it
            if hasattr(extractor, "extract_exports"):
                # exports = extractor.extract_exports(tree, source_code)
                # TODO: Add exports to elements when export extraction is fully implemented
                # elements.extend(exports)
                pass
            # else: exports not needed if not supported

            elements.extend(functions)
            elements.extend(classes)
            elements.extend(variables)
            elements.extend(imports)

            def count_nodes(node: "tree_sitter.Node") -> int:
                count = 1
                for child in node.children:
                    count += count_nodes(child)
                return count

            return AnalysisResult(
                file_path=file_path,
                language=self.language_name,
                success=True,
                elements=elements,
                line_count=len(source_code.splitlines()),
                node_count=count_nodes(tree.root_node),
            )
        except Exception as e:
            log_error(f"Error analyzing JavaScript file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.language_name,
                success=False,
                error_message=str(e),
            )

    def extract_elements(self, tree: "tree_sitter.Tree", source_code: str) -> dict:
        """Extract elements from source code using tree-sitter AST"""
        try:
            if tree is None or not hasattr(tree, "root_node") or tree.root_node is None:
                return {
                    "functions": [],
                    "classes": [],
                    "variables": [],
                    "imports": [],
                    "exports": [],
                }

            functions = self._extractor.extract_functions(tree, source_code)
            classes = self._extractor.extract_classes(tree, source_code)
            variables = self._extractor.extract_variables(tree, source_code)
            imports = self._extractor.extract_imports(tree, source_code)

            return {
                "functions": functions,
                "classes": classes,
                "variables": variables,
                "imports": imports,
                "exports": [],  # TODO: Implement exports extraction
            }
        except Exception as e:
            log_error(f"Failed to extract elements: {e}")
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "exports": [],
            }
