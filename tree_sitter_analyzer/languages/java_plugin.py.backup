#!/usr/bin/env python3
"""
Java Language Plugin

Provides Java-specific parsing and element extraction functionality.
Migrated from AdvancedAnalyzer implementation for future independence.
"""

import re
from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_warning


class JavaElementExtractor(ElementExtractor):
    """Java-specific element extractor with AdvancedAnalyzer implementation"""

    def __init__(self) -> None:
        """Initialize the Java element extractor."""
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.imports: list[str] = []

        # Performance optimization caches - use position-based keys for deterministic caching
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None
        self._annotation_cache: dict[int, list[dict[str, Any]]] = {}
        self._signature_cache: dict[int, str] = {}

        # Extracted annotations for cross-referencing
        self.annotations: list[dict[str, Any]] = []

    def extract_annotations(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[dict[str, Any]]:
        """Extract Java annotations using AdvancedAnalyzer implementation"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        annotations: list[dict[str, Any]] = []

        # Use AdvancedAnalyzer's optimized traversal for annotations
        extractors = {
            "annotation": self._extract_annotation_optimized,
            "marker_annotation": self._extract_annotation_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, annotations, "annotation"
        )

        # Store annotations for cross-referencing
        self.annotations = annotations

        log_debug(f"Extracted {len(annotations)} annotations")
        return annotations

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Java method definitions using AdvancedAnalyzer implementation"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        # Use AdvancedAnalyzer's optimized traversal
        extractors = {
            "method_declaration": self._extract_method_optimized,
            "constructor_declaration": self._extract_method_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, functions, "method"
        )

        log_debug(f"Extracted {len(functions)} methods")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract Java class definitions using AdvancedAnalyzer implementation"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        # Ensure package information is extracted before processing classes
        # This fixes the issue where current_package is empty when extract_classes
        # is called independently or before extract_imports
        if not self.current_package:
            self._extract_package_from_tree(tree)

        classes: list[Class] = []

        # Use AdvancedAnalyzer's optimized traversal
        extractors = {
            "class_declaration": self._extract_class_optimized,
            "interface_declaration": self._extract_class_optimized,
            "enum_declaration": self._extract_class_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, classes, "class"
        )

        log_debug(f"Extracted {len(classes)} classes")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract Java field definitions using AdvancedAnalyzer implementation"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        # Use AdvancedAnalyzer's optimized traversal
        extractors = {
            "field_declaration": self._extract_field_optimized,
        }

        log_debug("Starting field extraction with iterative traversal")
        self._traverse_and_extract_iterative(
            tree.root_node, extractors, variables, "field"
        )

        log_debug(f"Extracted {len(variables)} fields")
        for i, var in enumerate(variables[:3]):
            log_debug(f"Field {i}: {var.name} ({var.variable_type})")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract Java import statements with enhanced robustness"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        imports: list[Import] = []

        # Extract package and imports efficiently (from AdvancedAnalyzer)
        for child in tree.root_node.children:
            if child.type == "package_declaration":
                self._extract_package_info(child)
            elif child.type == "import_declaration":
                import_info = self._extract_import_info(child, source_code)
                if import_info:
                    imports.append(import_info)
            elif child.type in [
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
            ]:
                # After package and imports come class declarations, so stop
                break

        # Fallback: if no imports found via tree-sitter, try regex-based extraction
        if not imports and "import" in source_code:
            log_debug("No imports found via tree-sitter, trying regex fallback")
            fallback_imports = self._extract_imports_fallback(source_code)
            imports.extend(fallback_imports)

        log_debug(f"Extracted {len(imports)} imports")
        return imports

    def _extract_imports_fallback(self, source_code: str) -> list[Import]:
        """Fallback import extraction using regex when tree-sitter fails"""
        imports = []
        lines = source_code.split("\n")

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if line.startswith("import ") and line.endswith(";"):
                # Extract import statement
                import_content = line[:-1]  # Remove semicolon

                if "static" in import_content:
                    # Static import
                    static_match = re.search(
                        r"import\s+static\s+([\w.]+)", import_content
                    )
                    if static_match:
                        import_name = static_match.group(1)
                        if import_content.endswith(".*"):
                            import_name = import_name.replace(".*", "")

                        # For static imports, extract the class name (remove method/field name)
                        parts = import_name.split(".")
                        if len(parts) > 1:
                            # Remove the last part (method/field name) to get class name
                            import_name = ".".join(parts[:-1])

                        imports.append(
                            Import(
                                name=import_name,
                                start_line=line_num,
                                end_line=line_num,
                                raw_text=line,
                                language="java",
                                module_name=import_name,
                                is_static=True,
                                is_wildcard=import_content.endswith(".*"),
                                import_statement=import_content,
                            )
                        )
                else:
                    # Normal import
                    normal_match = re.search(r"import\s+([\w.]+)", import_content)
                    if normal_match:
                        import_name = normal_match.group(1)
                        if import_content.endswith(".*"):
                            if import_name.endswith(".*"):
                                import_name = import_name[:-2]
                            elif import_name.endswith("."):
                                import_name = import_name[:-1]

                        imports.append(
                            Import(
                                name=import_name,
                                start_line=line_num,
                                end_line=line_num,
                                raw_text=line,
                                language="java",
                                module_name=import_name,
                                is_static=False,
                                is_wildcard=import_content.endswith(".*"),
                                import_statement=import_content,
                            )
                        )

        return imports

    def extract_packages(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Package]:
        """Extract Java package declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        packages: list[Package] = []

        # Extract package declaration from AST
        if tree and tree.root_node:
            for child in tree.root_node.children:
                if child.type == "package_declaration":
                    package_info = self._extract_package_element(child)
                    if package_info:
                        packages.append(package_info)
                        # Also set current_package for use by other extractors
                        self.current_package = package_info.name
                    break  # Only one package declaration per file

        # Fallback: Parse package from source code if AST parsing failed
        if not packages:
            import re

            # Find package declaration with line number
            lines = source_code.split("\n")
            for line_num, line in enumerate(lines, start=1):
                match = re.search(r"^\s*package\s+([\w.]+)\s*;", line)
                if match:
                    package_name = match.group(1).strip()
                    packages.append(
                        Package(
                            name=package_name,
                            start_line=line_num,
                            end_line=line_num,
                            raw_text=line.strip(),
                            language="java",
                        )
                    )
                    self.current_package = package_name
                    log_debug(f"Package extracted via fallback: {package_name}")
                    break

        log_debug(f"Extracted {len(packages)} packages")
        return packages

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        self._annotation_cache.clear()
        self._signature_cache.clear()
        self.annotations.clear()
        self.current_package = (
            ""  # Reset package state to avoid cross-test contamination
        )

    def _traverse_and_extract_iterative(
        self,
        root_node: "tree_sitter.Node | None",
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """
        Iterative node traversal and extraction (from AdvancedAnalyzer)
        Uses batch processing for optimal performance
        """
        if not root_node:
            return

        # Target node types for extraction
        target_node_types = set(extractors.keys())

        # Container node types that may contain target nodes (from AdvancedAnalyzer)
        container_node_types = {
            "program",
            "class_body",
            "interface_body",
            "enum_body",
            "enum_body_declarations",  # Required for enum methods/fields/constructors
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "method_declaration",
            "constructor_declaration",
            "block",
            "modifiers",  # Annotation nodes can appear inside modifiers
        }

        # Iterative DFS stack: (node, depth)
        node_stack = [(root_node, 0)]
        processed_nodes = 0
        max_depth = 50  # Prevent infinite loops

        # Batch processing containers (from AdvancedAnalyzer)
        field_batch = []

        while node_stack:
            current_node, depth = node_stack.pop()

            # Safety check for maximum depth
            if depth > max_depth:
                log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
                continue

            processed_nodes += 1
            node_type = current_node.type

            # Early termination: skip nodes that don't contain target elements
            if (
                depth > 0
                and node_type not in target_node_types
                and node_type not in container_node_types
            ):
                continue

            # Collect target nodes for batch processing (from AdvancedAnalyzer)
            if node_type in target_node_types:
                if element_type == "field" and node_type == "field_declaration":
                    field_batch.append(current_node)
                else:
                    # Process non-field elements immediately
                    node_id = id(current_node)

                    # Skip if already processed
                    if node_id in self._processed_nodes:
                        continue

                    # Check element cache first
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

            # Add children to stack (reversed for correct DFS traversal)
            if current_node.children:
                for child in reversed(current_node.children):
                    node_stack.append((child, depth + 1))

            # Process field batch when it reaches optimal size (from AdvancedAnalyzer)
            if len(field_batch) >= 10:
                self._process_field_batch(field_batch, extractors, results)
                field_batch.clear()

        # Process remaining field batch (from AdvancedAnalyzer)
        if field_batch:
            self._process_field_batch(field_batch, extractors, results)

        log_debug(f"Iterative traversal processed {processed_nodes} nodes")

    def _process_field_batch(
        self, batch: list["tree_sitter.Node"], extractors: dict, results: list[Any]
    ) -> None:
        """Process field nodes with caching using position-based keys"""
        for node in batch:
            # Use stable node identifier
            node_id = id(node)
            node_key = node_id  # Maintain variable name for minimal changes

            # Skip if already processed
            if node_id in self._processed_nodes:
                continue

            # Check element cache first
            cache_key = (node_id, "field")
            if cache_key in self._element_cache:
                elements = self._element_cache[cache_key]
                if elements:
                    if isinstance(elements, list):
                        results.extend(elements)
                    else:
                        results.append(elements)
                self._processed_nodes.add(node_key)
                continue

            # Extract and cache
            extractor = extractors.get(node.type)
            if extractor:
                elements = extractor(node)
                self._element_cache[cache_key] = elements
                if elements:
                    if isinstance(elements, list):
                        results.extend(elements)
                    else:
                        results.append(elements)
                self._processed_nodes.add(node_id)

    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """Get node text with optimized caching using position-based keys"""
        # Use position-based cache key for deterministic behavior
        cache_key = (node.start_byte, node.end_byte)

        # Check cache first
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            # Use encoding utilities for text extraction
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
                    # Single line
                    line = self.content_lines[start_point[0]]
                    result: str = line[start_point[1] : end_point[1]]
                    return result
                else:
                    # Multiple lines
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

    def _extract_class_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class information optimized (from AdvancedAnalyzer)"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract class name efficiently
            class_name = None
            for child in node.children:
                if child.type == "identifier":
                    class_name = self._get_node_text_optimized(child)
                    break

            if not class_name:
                return None

            # Determine package name
            package_name = self.current_package
            full_qualified_name = (
                f"{package_name}.{class_name}" if package_name else class_name
            )

            # Determine class type (optimized: dictionary lookup)
            class_type_map = {
                "class_declaration": "class",
                "interface_declaration": "interface",
                "enum_declaration": "enum",
            }
            class_type = class_type_map.get(node.type, "class")

            # Extract modifiers efficiently
            modifiers = self._extract_modifiers_optimized(node)
            visibility = self._determine_visibility(modifiers)

            # Extract superclass and interfaces (optimized: single pass)
            extends_class = None
            implements_interfaces = []

            for child in node.children:
                if child.type == "superclass":
                    extends_text = self._get_node_text_optimized(child)
                    match = re.search(r"\b[A-Z]\w*", extends_text)
                    if match:
                        extends_class = match.group(0)
                elif child.type == "super_interfaces":
                    implements_text = self._get_node_text_optimized(child)
                    implements_interfaces = re.findall(r"\b[A-Z]\w*", implements_text)

            # Extract annotations for this class
            class_annotations = self._find_annotations_for_line_cached(start_line)

            # Check if this is a nested class
            is_nested = self._is_nested_class(node)
            parent_class = self._find_parent_class(node) if is_nested else None

            # Extract raw text
            start_line_idx = max(0, start_line - 1)
            end_line_idx = min(len(self.content_lines), end_line)
            raw_text = "\n".join(self.content_lines[start_line_idx:end_line_idx])

            return Class(
                name=class_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="java",
                class_type=class_type,
                full_qualified_name=full_qualified_name,
                package_name=package_name,
                superclass=extends_class,
                interfaces=implements_interfaces,
                modifiers=modifiers,
                visibility=visibility,
                # Java-specific detailed information
                annotations=class_annotations,
                is_nested=is_nested,
                parent_class=parent_class,
                extends_class=extends_class,  # Alias for superclass
                implements_interfaces=implements_interfaces,  # Alias for interfaces
            )
        except (AttributeError, ValueError, TypeError) as e:
            log_debug(f"Failed to extract class info: {e}")
            return None
        except Exception as e:
            log_error(f"Unexpected error in class extraction: {e}")
            return None

    def _extract_method_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract method information optimized (from AdvancedAnalyzer)"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract method information efficiently
            method_info = self._parse_method_signature_optimized(node)
            if not method_info:
                return None

            method_name, return_type, parameters, modifiers, throws = method_info
            is_constructor = node.type == "constructor_declaration"
            visibility = self._determine_visibility(modifiers)

            # Extract annotations for this method
            method_annotations = self._find_annotations_for_line_cached(start_line)

            # Calculate complexity score
            complexity_score = self._calculate_complexity_optimized(node)

            # Extract JavaDoc
            javadoc = self._extract_javadoc_for_line(start_line)

            # Extract raw text
            start_line_idx = max(0, start_line - 1)
            end_line_idx = min(len(self.content_lines), end_line)
            raw_text = "\n".join(self.content_lines[start_line_idx:end_line_idx])

            return Function(
                name=method_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="java",
                parameters=parameters,
                return_type=return_type if not is_constructor else "void",
                modifiers=modifiers,
                is_static="static" in modifiers,
                is_private="private" in modifiers,
                is_public="public" in modifiers,
                is_constructor=is_constructor,
                visibility=visibility,
                docstring=javadoc,
                # Java-specific detailed information
                annotations=method_annotations,
                throws=throws,
                complexity_score=complexity_score,
                is_abstract="abstract" in modifiers,
                is_final="final" in modifiers,
            )
        except (AttributeError, ValueError, TypeError) as e:
            log_debug(f"Failed to extract method info: {e}")
            return None
        except Exception as e:
            log_error(f"Unexpected error in method extraction: {e}")
            return None

    def _extract_field_optimized(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract field information optimized (from AdvancedAnalyzer)"""
        fields: list[Variable] = []
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Parse field declaration using AdvancedAnalyzer method
            field_info = self._parse_field_declaration_optimized(node)
            if not field_info:
                return fields

            field_type, variable_names, modifiers = field_info
            visibility = self._determine_visibility(modifiers)

            # Extract annotations for this field
            field_annotations = self._find_annotations_for_line_cached(start_line)

            # Extract JavaDoc for this field
            field_javadoc = self._extract_javadoc_for_line(start_line)

            # Create Variable object for each variable (matching AdvancedAnalyzer structure)
            for var_name in variable_names:
                # Extract raw text
                start_line_idx = max(0, start_line - 1)
                end_line_idx = min(len(self.content_lines), end_line)
                raw_text = "\n".join(self.content_lines[start_line_idx:end_line_idx])

                field = Variable(
                    name=var_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="java",
                    variable_type=field_type,
                    modifiers=modifiers,
                    is_static="static" in modifiers,
                    is_constant="final" in modifiers,
                    visibility=visibility,
                    docstring=field_javadoc,
                    # Java-specific detailed information
                    annotations=field_annotations,
                    is_final="final" in modifiers,
                    field_type=field_type,  # Alias for variable_type
                )
                fields.append(field)
        except (AttributeError, ValueError, TypeError) as e:
            log_debug(f"Failed to extract field info: {e}")
        except Exception as e:
            log_error(f"Unexpected error in field extraction: {e}")

        return fields

    def _parse_method_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, str, list[str], list[str], list[str]] | None:
        """Parse method signature optimized (from AdvancedAnalyzer)"""
        try:
            # Extract method name
            method_name = None
            for child in node.children:
                if child.type == "identifier":
                    method_name = self._get_node_text_optimized(child)
                    break

            if not method_name:
                return None

            # Extract return type
            return_type = "void"
            for child in node.children:
                if (
                    child.type
                    in [
                        "type_identifier",
                        "void_type",
                        "primitive_type",
                        "integral_type",
                        "boolean_type",
                        "floating_point_type",
                        "array_type",
                    ]
                    or child.type == "generic_type"
                ):
                    return_type = self._get_node_text_optimized(child)
                    break

            # Extract parameters
            parameters = []
            for child in node.children:
                if child.type == "formal_parameters":
                    for param in child.children:
                        if param.type == "formal_parameter":
                            param_text = self._get_node_text_optimized(param)
                            parameters.append(param_text)

            # Extract modifiers
            modifiers = self._extract_modifiers_optimized(node)

            # Extract throws clause
            throws = []
            for child in node.children:
                if child.type == "throws":
                    throws_text = self._get_node_text_optimized(child)
                    exceptions = re.findall(r"\b[A-Z]\w*Exception\b", throws_text)
                    throws.extend(exceptions)

            return method_name, return_type, parameters, modifiers, throws
        except Exception:
            return None

    def _parse_field_declaration_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, list[str], list[str]] | None:
        """Parse field declaration optimized (from AdvancedAnalyzer)"""
        try:
            # Extract type (exactly as in AdvancedAnalyzer)
            field_type = None
            for child in node.children:
                if child.type in [
                    "type_identifier",
                    "primitive_type",
                    "integral_type",
                    "generic_type",
                    "boolean_type",
                    "floating_point_type",
                    "array_type",
                ]:
                    field_type = self._get_node_text_optimized(child)
                    break

            if not field_type:
                return None

            # Extract variable names (exactly as in AdvancedAnalyzer)
            variable_names = []
            for child in node.children:
                if child.type == "variable_declarator":
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            var_name = self._get_node_text_optimized(grandchild)
                            variable_names.append(var_name)

            if not variable_names:
                return None

            # Extract modifiers (exactly as in AdvancedAnalyzer)
            modifiers = self._extract_modifiers_optimized(node)

            return field_type, variable_names, modifiers
        except Exception:
            return None

    def _extract_modifiers_optimized(self, node: "tree_sitter.Node") -> list[str]:
        """Extract modifiers efficiently (from AdvancedAnalyzer)"""
        modifiers = []
        for child in node.children:
            if child.type == "modifiers":
                for mod_child in child.children:
                    if mod_child.type in [
                        "public",
                        "private",
                        "protected",
                        "static",
                        "final",
                        "abstract",
                        "synchronized",
                        "volatile",
                        "transient",
                    ]:
                        modifiers.append(mod_child.type)
                    elif mod_child.type not in ["marker_annotation"]:
                        mod_text = self._get_node_text_optimized(mod_child)
                        if mod_text in [
                            "public",
                            "private",
                            "protected",
                            "static",
                            "final",
                            "abstract",
                            "synchronized",
                            "volatile",
                            "transient",
                        ]:
                            modifiers.append(mod_text)
        return modifiers

    def _extract_package_info(self, node: "tree_sitter.Node") -> None:
        """Extract package information (from AdvancedAnalyzer)"""
        try:
            package_text = self._get_node_text_optimized(node)
            match = re.search(r"package\s+([\w.]+)", package_text)
            if match:
                self.current_package = match.group(1)
        except (AttributeError, ValueError, IndexError) as e:
            log_debug(f"Failed to extract package info: {e}")
        except Exception as e:
            log_error(f"Unexpected error in package extraction: {e}")

    def _extract_package_element(self, node: "tree_sitter.Node") -> Package | None:
        """Extract package element for inclusion in results"""
        try:
            package_text = self._get_node_text_optimized(node)
            match = re.search(r"package\s+([\w.]+)", package_text)
            if match:
                package_name = match.group(1)
                return Package(
                    name=package_name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_text=package_text,
                    language="java",
                )
        except (AttributeError, ValueError, IndexError) as e:
            log_debug(f"Failed to extract package element: {e}")
        except Exception as e:
            log_error(f"Unexpected error in package element extraction: {e}")

        return None

    def _extract_package_from_tree(self, tree: "tree_sitter.Tree") -> None:
        """Extract package information from tree when needed"""
        if tree and tree.root_node:
            for child in tree.root_node.children:
                if child.type == "package_declaration":
                    self._extract_package_info(child)
                    break

    def _extract_import_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Import | None:
        """Extract import information from import declaration node"""
        try:
            import_text = self._get_node_text_optimized(node)
            line_num = node.start_point[0] + 1

            # Parse import statement
            if "static" in import_text:
                # Static import
                static_match = re.search(r"import\s+static\s+([\w.]+)", import_text)
                if static_match:
                    import_name = static_match.group(1)
                    if import_text.endswith(".*"):
                        import_name = import_name.replace(".*", "")

                    # For static imports, extract the class name
                    parts = import_name.split(".")
                    if len(parts) > 1:
                        import_name = ".".join(parts[:-1])

                    return Import(
                        name=import_name,
                        start_line=line_num,
                        end_line=line_num,
                        raw_text=import_text,
                        language="java",
                        module_name=import_name,
                        is_static=True,
                        is_wildcard=import_text.endswith(".*"),
                        import_statement=import_text,
                    )
            else:
                # Normal import
                normal_match = re.search(r"import\s+([\w.]+)", import_text)
                if normal_match:
                    import_name = normal_match.group(1)
                    if import_text.endswith(".*"):
                        if import_name.endswith(".*"):
                            import_name = import_name[:-2]
                        elif import_name.endswith("."):
                            import_name = import_name[:-1]

                    return Import(
                        name=import_name,
                        start_line=line_num,
                        end_line=line_num,
                        raw_text=import_text,
                        language="java",
                        module_name=import_name,
                        is_static=False,
                        is_wildcard=import_text.endswith(".*"),
                        import_statement=import_text,
                    )
        except Exception as e:
            log_debug(f"Failed to extract import info: {e}")

        return None

    def _extract_annotation_optimized(
        self, node: "tree_sitter.Node"
    ) -> dict[str, Any] | None:
        """Extract annotation information optimized"""
        try:
            annotation_text = self._get_node_text_optimized(node)
            start_line = node.start_point[0] + 1

            # Extract annotation name
            annotation_name = None
            for child in node.children:
                if child.type == "identifier":
                    annotation_name = self._get_node_text_optimized(child)
                    break

            if not annotation_name:
                # Try to extract from text
                match = re.search(r"@(\w+)", annotation_text)
                if match:
                    annotation_name = match.group(1)

            if annotation_name:
                return {
                    "name": annotation_name,
                    "line": start_line,
                    "text": annotation_text,
                    "type": "annotation",
                }
        except Exception as e:
            log_debug(f"Failed to extract annotation: {e}")

        return None

    def _determine_visibility(self, modifiers: list[str]) -> str:
        """Determine visibility from modifiers"""
        if "public" in modifiers:
            return "public"
        elif "private" in modifiers:
            return "private"
        elif "protected" in modifiers:
            return "protected"
        else:
            return "package"

    def _find_annotations_for_line_cached(self, line: int) -> list[dict[str, Any]]:
        """Find annotations for a specific line with caching"""
        if line in self._annotation_cache:
            return self._annotation_cache[line]

        # Find annotations near this line
        annotations = []
        for annotation in self.annotations:
            if abs(annotation.get("line", 0) - line) <= 2:
                annotations.append(annotation)

        self._annotation_cache[line] = annotations
        return annotations

    def _is_nested_class(self, node: "tree_sitter.Node") -> bool:
        """Check if this is a nested class"""
        parent = node.parent
        while parent:
            if parent.type in [
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
            ]:
                return True
            parent = parent.parent
        return False

    def _find_parent_class(self, node: "tree_sitter.Node") -> str | None:
        """Find parent class name for nested classes"""
        parent = node.parent
        while parent:
            if parent.type in [
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
            ]:
                for child in parent.children:
                    if child.type == "identifier":
                        return self._get_node_text_optimized(child)
            parent = parent.parent
        return None

    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        """Calculate cyclomatic complexity optimized"""
        complexity = 1  # Base complexity

        # Count decision points
        decision_nodes = [
            "if_statement",
            "while_statement",
            "for_statement",
            "switch_statement",
            "catch_clause",
            "conditional_expression",
            "enhanced_for_statement",
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
                    # Handle Mock objects or other non-iterable children
                    pass
            return count

        complexity += count_decisions(node)
        return complexity

    def _extract_javadoc_for_line(self, line: int) -> str | None:
        """Extract JavaDoc comment for a specific line"""
        try:
            # Look for JavaDoc comment before the line
            for i in range(max(0, line - 10), line):
                if i < len(self.content_lines):
                    line_content = self.content_lines[i].strip()
                    if line_content.startswith("/**"):
                        # Found start of JavaDoc, collect until */
                        javadoc_lines = []
                        for j in range(i, min(len(self.content_lines), line)):
                            doc_line = self.content_lines[j].strip()
                            javadoc_lines.append(doc_line)
                            if doc_line.endswith("*/"):
                                break
                        return "\n".join(javadoc_lines)
        except Exception as e:
            log_debug(f"Failed to extract JavaDoc: {e}")

        return None

    def _extract_class_name(self, node: "tree_sitter.Node") -> str | None:
        """Extract class name from a class declaration node."""
        try:
            for child in node.children:
                if child.type == "identifier":
                    return self._get_node_text_optimized(child)
            return None
        except Exception as e:
            log_debug(f"Failed to extract class name: {e}")
            return None


class JavaPlugin(LanguagePlugin):
    """Java language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Java language plugin."""
        super().__init__()
        self.extractor = JavaElementExtractor()
        self.language = "java"  # Add language property for test compatibility
        self.supported_extensions = (
            self.get_file_extensions()
        )  # Add for test compatibility
        self._cached_language: Any | None = None  # Cache for tree-sitter language

    def get_language_name(self) -> str:
        """Get the language name."""
        return "java"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".java", ".jsp", ".jspx"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return JavaElementExtractor()

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze Java code and return structured results."""

        from ..models import AnalysisResult

        try:
            # Read the file content using safe encoding detection
            from ..encoding_utils import read_file_safe_async

            file_content, detected_encoding = await read_file_safe_async(file_path)

            # Get tree-sitter language and parse
            language = self.get_tree_sitter_language()
            if language is None:
                # Return empty result if language loading fails
                return AnalysisResult(
                    file_path=file_path,
                    language="java",
                    line_count=len(file_content.split("\n")),
                    elements=[],
                    source_code=file_content,
                    success=False,
                    error_message="Failed to load tree-sitter language for Java",
                )

            # Offload CPU-bound parsing and extraction to worker threads
            def _analyze_sync() -> tuple[list[Any], int, Any]:
                import tree_sitter

                parser = tree_sitter.Parser()

                # Set language using the appropriate method
                if hasattr(parser, "set_language"):
                    parser.set_language(language)
                elif hasattr(parser, "language"):
                    parser.language = language
                else:
                    # Try constructor approach as last resort
                    parser = tree_sitter.Parser(language)

                tree = parser.parse(file_content.encode("utf-8"))

                # Extract elements using our extractor
                elements_dict = self.extract_elements(tree, file_content)

                # Combine all elements into a single list
                all_elements = []
                all_elements.extend(elements_dict.get("functions", []))
                all_elements.extend(elements_dict.get("classes", []))
                all_elements.extend(elements_dict.get("variables", []))
                all_elements.extend(elements_dict.get("imports", []))
                all_elements.extend(elements_dict.get("packages", []))

                # Extract packages and annotations if available
                packages = elements_dict.get("packages", [])
                package = packages[0] if packages else None

                # Count nodes in the AST tree
                from ..utils.tree_sitter_compat import count_nodes_iterative

                node_count = 0
                if tree and tree.root_node:
                    node_count = count_nodes_iterative(tree.root_node)

                return all_elements, node_count, package

            all_elements, node_count, package = await anyio.to_thread.run_sync(
                _analyze_sync
            )

            return AnalysisResult(
                file_path=file_path,
                language="java",
                line_count=len(file_content.split("\n")),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
                package=package,
            )

        except Exception as e:
            log_error(f"Error analyzing Java file {file_path}: {e}")
            # Return empty result on error
            return AnalysisResult(
                file_path=file_path,
                language="java",
                line_count=0,
                elements=[],
                source_code="",
                error_message=str(e),
                success=False,
            )

    def _count_tree_nodes(self, node: Any) -> int:
        """
        Recursively count nodes in the AST tree (Deprecated: use iterative version).
        """
        from ..utils.tree_sitter_compat import count_nodes_iterative

        return count_nodes_iterative(node)

    def get_tree_sitter_language(self) -> Any | None:
        """Get the tree-sitter language for Java."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_java

            # Get the language function result
            caps_or_lang = tree_sitter_java.language()

            # Convert to proper Language object if needed
            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
                # Already a Language object
                self._cached_language = caps_or_lang
            else:
                # PyCapsule - convert to Language object
                try:
                    # Use modern tree-sitter API - PyCapsule should be passed to Language constructor
                    self._cached_language = tree_sitter.Language(caps_or_lang)
                except Exception as e:
                    log_error(f"Failed to create Language object from PyCapsule: {e}")
                    return None

            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-java not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Java: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements from Java code for test compatibility."""
        if tree is None:
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "packages": [],
                "annotations": [],
            }

        try:
            extractor = self.create_extractor()
            return {
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
                "packages": extractor.extract_packages(tree, source_code),
                "annotations": extractor.extract_annotations(tree, source_code),
            }
        except Exception as e:
            log_error(f"Error extracting elements: {e}")
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "packages": [],
                "annotations": [],
            }

    def supports_file(self, file_path: str) -> bool:
        """Check if this plugin supports the given file."""
        return any(
            file_path.lower().endswith(ext) for ext in self.get_file_extensions()
        )
