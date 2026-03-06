#!/usr/bin/env python3
"""
C++ Language Plugin

Provides C++ specific parsing and element extraction functionality.
Supports modern C++ features including classes, templates, namespaces,
and advanced constructs.
"""

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_warning


class CppElementExtractor(ElementExtractor):
    """C++ specific element extractor with advanced analysis support"""

    def __init__(self) -> None:
        """Initialize the C++ element extractor."""
        self.current_namespace: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.includes: list[str] = []

        # Performance optimization caches - use position-based keys for deterministic caching
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None
        self._comment_cache: dict[int, str] = {}
        self._complexity_cache: dict[int, int] = {}

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract C++ function definitions with comprehensive details"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        # Use optimized traversal for function types
        extractors = {
            "function_definition": self._extract_function_optimized,
            "function_declarator": self._extract_function_declaration,
            "template_declaration": self._extract_template_function,
            "field_declaration": self._extract_function_from_field_declaration,  # Pure virtual, etc
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, functions, "function"
        )

        log_debug(f"Extracted {len(functions)} C++ functions")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract C++ class/struct definitions with detailed information"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        # Extract class, struct, and union declarations
        extractors = {
            "class_specifier": self._extract_class_optimized,
            "struct_specifier": self._extract_struct_optimized,
            "union_specifier": self._extract_union_optimized,
            "template_declaration": self._extract_template_class,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, classes, "class"
        )

        log_debug(f"Extracted {len(classes)} C++ classes/structs")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract C++ variable/field declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        # Extract field and variable declarations
        extractors = {
            "field_declaration": self._extract_field_optimized,
            "declaration": self._extract_variable_declaration,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, variables, "variable"
        )

        log_debug(f"Extracted {len(variables)} C++ variables/fields")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract C++ include directives"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        imports: list[Import] = []

        # Extract preprocessor includes and using declarations
        for child in tree.root_node.children:
            if child.type == "preproc_include":
                import_info = self._extract_include_info(child, source_code)
                if import_info:
                    imports.append(import_info)
            elif child.type == "using_declaration":
                using_text = self._get_node_text_optimized(child)
                line_num = child.start_point[0] + 1
                imports.append(
                    Import(
                        name=using_text,
                        start_line=line_num,
                        end_line=line_num,
                        raw_text=using_text,
                        language="cpp",
                        module_name="",
                        import_statement=using_text,
                    )
                )
            elif child.type == "alias_declaration":
                # Handle 'using StringList = vector<string>;'
                # Treat as import/declaration? Or Variable?
                # Usually considered type definition.
                # Let's add to imports for now as it's a 'using' statement
                alias_text = self._get_node_text_optimized(child)
                line_num = child.start_point[0] + 1
                imports.append(
                    Import(
                        name=alias_text,
                        start_line=line_num,
                        end_line=line_num,
                        raw_text=alias_text,
                        language="cpp",
                        module_name="",
                        import_statement=alias_text,
                    )
                )

        # Fallback: use regex if tree-sitter doesn't catch all includes
        if not imports and "#include" in source_code:
            log_debug("No includes found via tree-sitter, trying regex fallback")
            fallback_imports = self._extract_includes_fallback(source_code)
            imports.extend(fallback_imports)

        log_debug(f"Extracted {len(imports)} C++ includes")
        return imports

    def extract_packages(self, tree: "tree_sitter.Tree", source_code: str) -> list[Any]:
        """Extract C++ namespace declarations"""
        from ..models import Package

        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        packages: list[Package] = []

        def find_namespaces(node: "tree_sitter.Node") -> None:
            if node.type == "namespace_definition":
                namespace_info = self._extract_namespace_info(node)
                if namespace_info:
                    packages.append(namespace_info)

            for child in node.children:
                find_namespaces(child)

        find_namespaces(tree.root_node)

        log_debug(f"Extracted {len(packages)} C++ namespaces")
        return packages

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        self._comment_cache.clear()
        self._complexity_cache.clear()
        self.current_namespace = ""

    def _traverse_and_extract_iterative(
        self,
        root_node: "tree_sitter.Node | None",
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """Iterative node traversal and extraction with caching"""
        if root_node is None:
            return

        target_node_types = set(extractors.keys())
        container_node_types = {
            "translation_unit",
            "namespace_definition",
            "class_specifier",
            "struct_specifier",
            "union_specifier",
            "declaration_list",
            "field_declaration_list",
            "compound_statement",
            "template_declaration",
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
                extractor = extractors[node_type]
                element = extractor(current_node)
                self._element_cache[cache_key] = element
                if element:
                    if isinstance(element, list):
                        results.extend(element)
                    else:
                        results.append(element)
                self._processed_nodes.add(node_id)

            # Add children to stack (reversed for correct DFS traversal)
            if current_node.children:
                for child in reversed(current_node.children):
                    node_stack.append((child, depth + 1))

        log_debug(f"Iterative traversal processed {processed_nodes} nodes")

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
                    result: str = line[start_point[1] : end_point[1]]
                    return result
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
        """Extract function information optimized"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract function details
            function_info = self._parse_function_signature(node)
            if not function_info:
                return None

            name, return_type, parameters, modifiers = function_info

            # Extract raw text
            start_line_idx = max(0, start_line - 1)
            end_line_idx = min(len(self.content_lines), end_line)
            raw_text = "\n".join(self.content_lines[start_line_idx:end_line_idx])

            # Calculate complexity
            complexity_score = self._calculate_complexity_optimized(node)

            # Determine visibility (check if function is global or class member)
            is_global = self._is_global_scope(node)
            visibility = self._determine_visibility(
                modifiers, is_global=is_global, node=node
            )

            # Extract comments/documentation
            docstring = self._extract_comment_for_line(start_line)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="cpp",
                parameters=parameters,
                return_type=return_type or "void",
                modifiers=modifiers,
                is_static="static" in modifiers,
                is_private="private" in modifiers,
                is_public="public" in modifiers,
                visibility=visibility,
                docstring=docstring,
                complexity_score=complexity_score,
            )
        except (AttributeError, ValueError, TypeError) as e:
            log_debug(f"Failed to extract function info: {e}")
            return None
        except Exception as e:
            log_error(f"Unexpected error in function extraction: {e}")
            return None

    def _extract_function_from_field_declaration(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """
        Extract function declaration from field_declaration (pure virtual functions, etc).

        Example: virtual double area() const = 0;
        """
        try:
            # Check if this field_declaration contains a function_declarator
            has_function_declarator = False
            for child in node.children:
                if child.type == "function_declarator":
                    has_function_declarator = True
                    break

            if not has_function_declarator:
                return None

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            name = None
            return_type = "void"
            parameters: list[str] = []
            modifiers: list[str] = []

            # Check for pure virtual (= 0) or deleted/defaulted

            for child in node.children:
                if child.type == "virtual":
                    modifiers.append("virtual")
                elif child.type in [
                    "primitive_type",
                    "type_identifier",
                    "qualified_identifier",
                    "template_type",
                ]:
                    return_type = self._get_node_text_optimized(child)
                elif child.type == "function_declarator":
                    for grandchild in child.children:
                        if grandchild.type in [
                            "field_identifier",
                            "identifier",
                            "destructor_name",
                            "operator_name",
                        ]:
                            name = self._get_node_text_optimized(grandchild)
                        elif grandchild.type == "parameter_list":
                            parameters = self._extract_parameters(grandchild)
                        elif grandchild.type == "type_qualifier":
                            mod = self._get_node_text_optimized(grandchild)
                            if mod:
                                modifiers.append(mod)
                elif (
                    child.type == "number_literal"
                    and self._get_node_text_optimized(child) == "0"
                ):
                    # Check if previous sibling is '=' to confirm pure virtual
                    if "pure_virtual" not in modifiers:
                        modifiers.append("pure_virtual")
                elif child.type == "delete_method_clause":
                    if "deleted" not in modifiers:
                        modifiers.append("deleted")
                elif child.type == "default_method_clause":
                    if "default" not in modifiers:
                        modifiers.append("default")

            if not name:
                return None

            raw_text = self._get_node_text_optimized(node)

            # Determine visibility
            is_global = self._is_global_scope(node)
            visibility = self._determine_visibility(
                modifiers, is_global=is_global, node=node
            )

            # Extract comments
            docstring = self._extract_comment_for_line(start_line)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="cpp",
                parameters=parameters,
                return_type=return_type,
                modifiers=modifiers,
                visibility=visibility,
                docstring=docstring,
                complexity_score=1,  # Declarations have minimal complexity
            )
        except Exception as e:
            log_debug(f"Failed to extract function from field declaration: {e}")
            return None

    def _extract_function_declaration(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract function declaration (prototype)"""
        # Only extract if parent is not a function_definition
        if node.parent and node.parent.type == "function_definition":
            return None  # Already handled by _extract_function_optimized

        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            name = None
            parameters: list[str] = []

            for child in node.children:
                if child.type == "identifier":
                    name = self._get_node_text_optimized(child)
                elif child.type == "qualified_identifier":
                    name = self._get_node_text_optimized(child)
                elif child.type == "parameter_list":
                    parameters = self._extract_parameters(child)

            if not name:
                return None

            raw_text = self._get_node_text_optimized(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="cpp",
                parameters=parameters,
                return_type="void",
                modifiers=[],
            )
        except Exception as e:
            log_debug(f"Failed to extract function declaration: {e}")
            return None

    def _extract_template_function(self, node: "tree_sitter.Node") -> Function | None:
        """Extract template function definition"""
        try:
            # Find the actual function definition inside the template
            for child in node.children:
                if child.type == "function_definition":
                    # Mark child as processed to prevent double extraction
                    child_id = id(child)
                    self._processed_nodes.add(child_id)

                    func = self._extract_function_optimized(child)
                    if func:
                        func.modifiers = func.modifiers or []
                        if "template" not in func.modifiers:
                            func.modifiers.append("template")
                        return func
            return None
        except Exception as e:
            log_debug(f"Failed to extract template function: {e}")
            return None

    def _parse_function_signature(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, str, list[str], list[str]] | None:
        """Parse C++ function signature"""
        try:
            name = None
            return_type = "void"
            parameters: list[str] = []
            modifiers: list[str] = []

            for child in node.children:
                if child.type == "function_declarator":
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            name = self._get_node_text_optimized(grandchild)
                        elif grandchild.type == "qualified_identifier":
                            name = self._get_node_text_optimized(grandchild)
                        elif grandchild.type == "field_identifier":
                            name = self._get_node_text_optimized(grandchild)
                        elif grandchild.type == "operator_name":
                            name = self._get_node_text_optimized(grandchild)
                        elif grandchild.type == "destructor_name":
                            name = self._get_node_text_optimized(grandchild)
                        elif grandchild.type == "parameter_list":
                            parameters = self._extract_parameters(grandchild)
                elif child.type == "reference_declarator":
                    # Handle reference return types (e.g., ostream& operator<<)
                    return_type = return_type + "&" if return_type else "&"
                    for grandchild in child.children:
                        if grandchild.type == "function_declarator":
                            for ggchild in grandchild.children:
                                if ggchild.type in [
                                    "identifier",
                                    "field_identifier",
                                    "operator_name",
                                    "destructor_name",
                                ]:
                                    name = self._get_node_text_optimized(ggchild)
                                elif ggchild.type == "parameter_list":
                                    parameters = self._extract_parameters(ggchild)
                elif child.type == "pointer_declarator":
                    # Handle pointer return types
                    return_type = return_type + "*" if return_type else "*"
                    for grandchild in child.children:
                        if grandchild.type == "function_declarator":
                            for ggchild in grandchild.children:
                                if ggchild.type in [
                                    "identifier",
                                    "field_identifier",
                                    "operator_name",
                                ]:
                                    name = self._get_node_text_optimized(ggchild)
                                elif ggchild.type == "parameter_list":
                                    parameters = self._extract_parameters(ggchild)
                elif child.type in [
                    "primitive_type",
                    "type_identifier",
                    "qualified_identifier",
                    "template_type",
                ]:
                    return_type = self._get_node_text_optimized(child)
                elif child.type == "storage_class_specifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)
                elif child.type == "type_qualifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)
                elif child.type == "virtual":
                    modifiers.append("virtual")

            if not name:
                return None

            return name, return_type, parameters, modifiers
        except Exception:
            return None

    def _extract_parameters(self, params_node: "tree_sitter.Node") -> list[str]:
        """Extract function parameters"""
        parameters: list[str] = []

        for child in params_node.children:
            if child.type == "parameter_declaration":
                param_text = self._get_node_text_optimized(child)
                parameters.append(param_text)
            elif child.type == "optional_parameter_declaration":
                param_text = self._get_node_text_optimized(child)
                parameters.append(param_text)
            elif child.type == "variadic_parameter_declaration":
                parameters.append("...")

        return parameters

    def _extract_class_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class information optimized"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            class_name = None
            superclasses: list[str] = []
            modifiers: list[str] = []

            for child in node.children:
                if child.type == "type_identifier":
                    class_name = self._get_node_text_optimized(child)
                elif child.type == "base_class_clause":
                    superclasses = self._extract_base_classes(child)

            if not class_name:
                return None

            # Extract raw text
            start_line_idx = max(0, start_line - 1)
            end_line_idx = min(len(self.content_lines), end_line)
            raw_text = "\n".join(self.content_lines[start_line_idx:end_line_idx])

            # Extract comments/documentation
            docstring = self._extract_comment_for_line(start_line)

            # Build fully qualified name with namespace
            full_qualified_name = (
                f"{self.current_namespace}::{class_name}"
                if self.current_namespace
                else class_name
            )

            return Class(
                name=class_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="cpp",
                class_type="class",
                full_qualified_name=full_qualified_name,
                package_name=self.current_namespace,
                superclass=superclasses[0] if superclasses else None,
                interfaces=superclasses[1:] if len(superclasses) > 1 else [],
                modifiers=modifiers,
                docstring=docstring,
            )
        except Exception as e:
            log_debug(f"Failed to extract class info: {e}")
            return None

    def _extract_struct_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract struct information optimized"""
        try:
            result = self._extract_class_optimized(node)
            if result:
                result.class_type = "struct"
            return result
        except Exception as e:
            log_debug(f"Failed to extract struct info: {e}")
            return None

    def _extract_union_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract union information optimized"""
        try:
            result = self._extract_class_optimized(node)
            if result:
                result.class_type = "union"
            return result
        except Exception as e:
            log_debug(f"Failed to extract union info: {e}")
            return None

    def _extract_template_class(self, node: "tree_sitter.Node") -> Class | None:
        """Extract template class definition"""
        try:
            for child in node.children:
                if child.type == "class_specifier":
                    # Mark child as processed to prevent double extraction
                    child_id = id(child)
                    self._processed_nodes.add(child_id)

                    cls = self._extract_class_optimized(child)
                    if cls:
                        cls.modifiers = cls.modifiers or []
                        if "template" not in cls.modifiers:
                            cls.modifiers.append("template")
                        return cls
                elif child.type == "struct_specifier":
                    # Mark child as processed to prevent double extraction
                    child_id = id(child)
                    self._processed_nodes.add(child_id)

                    cls = self._extract_struct_optimized(child)
                    if cls:
                        cls.modifiers = cls.modifiers or []
                        if "template" not in cls.modifiers:
                            cls.modifiers.append("template")
                        return cls
            return None
        except Exception as e:
            log_debug(f"Failed to extract template class: {e}")
            return None

    def _extract_base_classes(self, node: "tree_sitter.Node") -> list[str]:
        """Extract base class names from base_class_clause"""
        base_classes: list[str] = []

        for child in node.children:
            if child.type == "base_specifier":
                for grandchild in child.children:
                    if grandchild.type == "type_identifier":
                        base_classes.append(self._get_node_text_optimized(grandchild))
                    elif grandchild.type == "template_type":
                        base_classes.append(self._get_node_text_optimized(grandchild))

        return base_classes

    def _extract_field_optimized(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract field declaration"""
        fields: list[Variable] = []

        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            field_type = None
            field_names: list[str] = []
            modifiers: list[str] = []

            for child in node.children:
                if child.type in [
                    "primitive_type",
                    "type_identifier",
                    "qualified_identifier",
                    "template_type",
                ]:
                    field_type = self._get_node_text_optimized(child)
                elif child.type == "storage_class_specifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)
                elif child.type == "type_qualifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)
                elif child.type == "field_identifier":
                    field_names.append(self._get_node_text_optimized(child))
                elif child.type == "init_declarator":
                    for grandchild in child.children:
                        if grandchild.type == "field_identifier":
                            field_names.append(
                                self._get_node_text_optimized(grandchild)
                            )
                        elif grandchild.type == "identifier":
                            field_names.append(
                                self._get_node_text_optimized(grandchild)
                            )

            if not field_type or not field_names:
                return fields

            raw_text = self._get_node_text_optimized(node)

            # Determine visibility (check if field/variable is global or class member)
            is_global = self._is_global_scope(node)
            visibility = self._determine_visibility(
                modifiers, is_global=is_global, node=node
            )

            for field_name in field_names:
                field = Variable(
                    name=field_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="cpp",
                    variable_type=field_type,
                    modifiers=modifiers,
                    is_static="static" in modifiers,
                    is_constant="const" in modifiers,
                    visibility=visibility,
                )
                fields.append(field)

        except Exception as e:
            log_debug(f"Failed to extract field info: {e}")

        return fields

    def _extract_variable_declaration(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract variable declarations (not class members)"""
        # Skip if parent is a class/struct body
        if node.parent and node.parent.type == "field_declaration_list":
            return []

        variables: list[Variable] = []

        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            var_type = None
            var_names: list[str] = []
            modifiers: list[str] = []

            for child in node.children:
                if child.type in [
                    "primitive_type",
                    "type_identifier",
                    "qualified_identifier",
                    "template_type",
                ]:
                    var_type = self._get_node_text_optimized(child)
                elif child.type == "storage_class_specifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)
                elif child.type == "type_qualifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)
                elif child.type == "identifier":
                    var_names.append(self._get_node_text_optimized(child))
                elif child.type == "init_declarator":
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            var_names.append(self._get_node_text_optimized(grandchild))

            if not var_type or not var_names:
                return variables

            raw_text = self._get_node_text_optimized(node)

            # Determine visibility (check if variable is global or local)
            is_global = self._is_global_scope(node)
            visibility = self._determine_visibility(
                modifiers, is_global=is_global, node=node
            )

            for var_name in var_names:
                variable = Variable(
                    name=var_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="cpp",
                    variable_type=var_type,
                    modifiers=modifiers,
                    is_static="static" in modifiers,
                    is_constant="const" in modifiers,
                    visibility=visibility,
                )
                variables.append(variable)

        except Exception as e:
            log_debug(f"Failed to extract variable declaration: {e}")

        return variables

    def _extract_include_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Import | None:
        """Extract include directive information"""
        try:
            include_text = self._get_node_text_optimized(node)
            line_num = node.start_point[0] + 1

            # Determine if it's a system include (<...>) or local include ("...")
            is_system = "<" in include_text

            # Extract the included file path
            if is_system:
                match = re.search(r"<([^>]+)>", include_text)
            else:
                match = re.search(r'"([^"]+)"', include_text)

            if match:
                include_path = match.group(1)

                return Import(
                    name=include_path,
                    start_line=line_num,
                    end_line=line_num,
                    raw_text=include_text,
                    language="cpp",
                    module_name=include_path,
                    import_statement=include_text,
                )

        except Exception as e:
            log_debug(f"Failed to extract include info: {e}")

        return None

    def _extract_includes_fallback(self, source_code: str) -> list[Import]:
        """Fallback include extraction using regex"""
        imports: list[Import] = []
        lines = source_code.split("\n")

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if line.startswith("#include"):
                # System include
                system_match = re.search(r"#include\s*<([^>]+)>", line)
                if system_match:
                    include_path = system_match.group(1)
                    imports.append(
                        Import(
                            name=include_path,
                            start_line=line_num,
                            end_line=line_num,
                            raw_text=line,
                            language="cpp",
                            module_name=include_path,
                            import_statement=line,
                        )
                    )
                else:
                    # Local include
                    local_match = re.search(r'#include\s*"([^"]+)"', line)
                    if local_match:
                        include_path = local_match.group(1)
                        imports.append(
                            Import(
                                name=include_path,
                                start_line=line_num,
                                end_line=line_num,
                                raw_text=line,
                                language="cpp",
                                module_name=include_path,
                                import_statement=line,
                            )
                        )

        return imports

    def _extract_namespace_info(self, node: "tree_sitter.Node") -> Any:
        """Extract namespace information"""
        from ..models import Package

        try:
            namespace_name = None

            for child in node.children:
                if child.type == "identifier":
                    namespace_name = self._get_node_text_optimized(child)
                elif child.type == "namespace_identifier":
                    namespace_name = self._get_node_text_optimized(child)

            if namespace_name:
                self.current_namespace = namespace_name
                return Package(
                    name=namespace_name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_text=self._get_node_text_optimized(node),
                    language="cpp",
                )

        except Exception as e:
            log_debug(f"Failed to extract namespace info: {e}")

        return None

    def _is_global_scope(self, node: "tree_sitter.Node") -> bool:
        """
        Check if a node is in global scope (not inside a class/struct/union).

        Args:
            node: The tree-sitter node to check

        Returns:
            True if the node is in global scope, False if inside a class/struct/union
        """
        current = node.parent
        while current is not None:
            if current.type in (
                "class_specifier",
                "struct_specifier",
                "union_specifier",
            ):
                return False
            current = current.parent
        return True

    def _get_access_specifier(self, node: "tree_sitter.Node") -> str | None:
        """
        Get the current access specifier for a class member.

        Searches backwards through siblings to find the most recent access_specifier.
        Returns None if not in a class context or no specifier found.

        Args:
            node: The tree-sitter node (function/field definition)

        Returns:
            "public", "private", "protected", or None
        """
        # Check if we're in a field_declaration_list (class body)
        parent = node.parent
        if not parent or parent.type != "field_declaration_list":
            return None

        # Find which child we are
        siblings = list(parent.children)
        try:
            node_index = siblings.index(node)
        except ValueError:
            return None

        # Search backwards for access_specifier
        for i in range(node_index - 1, -1, -1):
            sibling = siblings[i]
            if sibling.type == "access_specifier":
                spec_text = self._get_node_text_optimized(sibling).strip().rstrip(":")
                if spec_text in ("public", "private", "protected"):
                    return spec_text

        # No explicit specifier found, determine default based on parent class type
        # Need to find if parent is class (default private) or struct (default public)
        class_node = parent.parent
        if class_node:
            if class_node.type == "class_specifier":
                return "private"  # C++ class default
            elif class_node.type in ("struct_specifier", "union_specifier"):
                return "public"  # C++ struct/union default

        return None  # Fallback

    def _determine_visibility(
        self,
        modifiers: list[str],
        is_global: bool = False,
        node: "tree_sitter.Node | None" = None,
    ) -> str:
        """
        Determine visibility from modifiers and context.

        Args:
            modifiers: List of modifier keywords
            is_global: True if this is a global function/variable (not a class member)
            node: The tree-sitter node (used to check access specifier in class context)

        Returns:
            Visibility string: "public", "private", or "protected"

        Note:
            - Global functions/variables are public by default (external linkage)
            - Global static functions/variables are private (internal linkage)
            - Class members follow access specifiers (public:/private:/protected:)
            - Struct/union members are public by default
        """
        # Explicit modifiers take precedence
        if "public" in modifiers:
            return "public"
        elif "private" in modifiers:
            return "private"
        elif "protected" in modifiers:
            return "protected"

        # Check for static global (internal linkage = private)
        if "static" in modifiers and is_global:
            return "private"

        # If node provided and in class context, check access specifier
        if node and not is_global:
            access_spec = self._get_access_specifier(node)
            if access_spec:
                return access_spec

        # Default visibility depends on context
        return "public" if is_global else "private"

    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        """Calculate cyclomatic complexity"""
        complexity = 1  # Base complexity

        decision_nodes = [
            "if_statement",
            "while_statement",
            "for_statement",
            "for_range_loop",
            "switch_statement",
            "case_statement",
            "conditional_expression",
            "catch_clause",
            "do_statement",
        ]

        def count_decisions(n: "tree_sitter.Node") -> int:
            count = 0
            if hasattr(n, "type") and n.type in decision_nodes:
                count += 1
            if hasattr(n, "children"):
                try:
                    for child in n.children:
                        count += count_decisions(child)
                except (TypeError, AttributeError):
                    pass
            return count

        complexity += count_decisions(node)
        return complexity

    def _extract_comment_for_line(self, line: int) -> str | None:
        """Extract comment (documentation) for a specific line"""
        try:
            # Look for comment immediately before the line
            for i in range(max(0, line - 5), line):
                if i < len(self.content_lines):
                    line_content = self.content_lines[i].strip()
                    # Check for Doxygen-style comments
                    if line_content.startswith("/**"):
                        comment_lines = []
                        for j in range(i, min(len(self.content_lines), line)):
                            doc_line = self.content_lines[j].strip()
                            comment_lines.append(doc_line)
                            if doc_line.endswith("*/"):
                                break
                        return "\n".join(comment_lines)
                    # Check for /// style comments
                    elif line_content.startswith("///"):
                        return line_content

        except Exception as e:
            log_debug(f"Failed to extract comment: {e}")

        return None


class CppPlugin(LanguagePlugin):
    """C++ language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the C++ language plugin."""
        super().__init__()
        self.extractor = CppElementExtractor()
        self.language = "cpp"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "cpp"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".h++", ".c++"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return CppElementExtractor()

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze C++ code and return structured results."""
        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="cpp",
                    line_count=len(file_content.split("\n")),
                    elements=[],
                    source_code=file_content,
                )

            import tree_sitter

            parser = tree_sitter.Parser()

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
                        language="cpp",
                        line_count=len(file_content.split("\n")),
                        elements=[],
                        source_code=file_content,
                        error_message=f"Parser creation failed: {e}",
                        success=False,
                    )

            tree = parser.parse(file_content.encode("utf-8"))

            elements_dict = self.extract_elements(tree, file_content)

            all_elements = []
            all_elements.extend(elements_dict.get("functions", []))
            all_elements.extend(elements_dict.get("classes", []))
            all_elements.extend(elements_dict.get("variables", []))
            all_elements.extend(elements_dict.get("imports", []))
            all_elements.extend(elements_dict.get("packages", []))

            node_count = (
                self._count_tree_nodes(tree.root_node) if tree and tree.root_node else 0
            )

            return AnalysisResult(
                file_path=file_path,
                language="cpp",
                line_count=len(file_content.split("\n")),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
            )

        except Exception as e:
            log_error(f"Error analyzing C++ file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="cpp",
                line_count=0,
                elements=[],
                source_code="",
                error_message=str(e),
                success=False,
            )

    def _count_tree_nodes(self, node: Any) -> int:
        """Recursively count nodes in the AST tree."""
        if node is None:
            return 0

        count = 1
        if hasattr(node, "children"):
            for child in node.children:
                count += self._count_tree_nodes(child)
        return count

    def get_tree_sitter_language(self) -> Any | None:
        """Get the tree-sitter language for C++."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_cpp

            caps_or_lang = tree_sitter_cpp.language()

            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
                self._cached_language = caps_or_lang
            else:
                try:
                    self._cached_language = tree_sitter.Language(caps_or_lang)
                except Exception as e:
                    log_error(f"Failed to create Language object from PyCapsule: {e}")
                    return None

            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-cpp not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for C++: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements from C++ code."""
        if tree is None:
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "packages": [],
            }

        try:
            extractor = self.create_extractor()
            return {
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
                "packages": extractor.extract_packages(tree, source_code),
            }
        except Exception as e:
            log_error(f"Error extracting elements: {e}")
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "packages": [],
            }
