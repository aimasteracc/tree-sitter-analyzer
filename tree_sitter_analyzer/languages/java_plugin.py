#!/usr/bin/env python3
"""
Java Language Plugin

Provides Java-specific parsing and element extraction functionality.
Migrated from AdvancedAnalyzer implementation for future independence.
"""

import re
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, CodeElement, Function, Import, Package, Variable
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

        # Performance optimization caches (from AdvancedAnalyzer)
        self._node_text_cache: dict[int, str] = {}
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
        """Extract Java import statements"""
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

        log_debug(f"Extracted {len(imports)} imports")
        return imports

    def extract_packages(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Package]:
        """Extract Java package declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        packages: list[Package] = []

        # Extract package declaration
        for child in tree.root_node.children:
            if child.type == "package_declaration":
                package_info = self._extract_package_element(child)
                if package_info:
                    packages.append(package_info)
                break  # Only one package declaration per file

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

    def _traverse_and_extract_iterative(
        self,
        root_node: "tree_sitter.Node",
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """
        Iterative node traversal and extraction (from AdvancedAnalyzer)
        Uses batch processing for optimal performance
        """
        if not root_node:
            return  # type: ignore[unreachable]

        # Target node types for extraction
        target_node_types = set(extractors.keys())

        # Container node types that may contain target nodes (from AdvancedAnalyzer)
        container_node_types = {
            "program",
            "class_body",
            "interface_body",
            "enum_body",
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
        """Process field nodes with caching (from AdvancedAnalyzer)"""
        for node in batch:
            node_id = id(node)

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
                self._processed_nodes.add(node_id)
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
        """Get node text with optimized caching (from AdvancedAnalyzer)"""
        node_id = id(node)

        # Check cache first
        if node_id in self._node_text_cache:
            return self._node_text_cache[node_id]

        try:
            # Use encoding utilities for text extraction
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
                    # Single line
                    line = self.content_lines[start_point[0]]
                    return line[start_point[1] : end_point[1]]
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
                if child.type in [
                    "type_identifier",
                    "void_type",
                    "primitive_type",
                    "integral_type",
                    "boolean_type",
                    "floating_point_type",
                    "array_type",
                ]:
                    return_type = self._get_node_text_optimized(child)
                    break
                elif child.type == "generic_type":
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
        """
        Extract package information from the tree and set current_package.

        This method ensures that package information is available for class extraction
        regardless of the order in which extraction methods are called.
        """
        try:
            # Look for package declaration in the root node's children
            for child in tree.root_node.children:
                if child.type == "package_declaration":
                    self._extract_package_info(child)
                    break  # Only one package declaration per file
        except Exception as e:
            log_debug(f"Failed to extract package from tree: {e}")

    def _determine_visibility(self, modifiers: list[str]) -> str:
        """Determine visibility from modifiers"""
        if "public" in modifiers:
            return "public"
        elif "private" in modifiers:
            return "private"
        elif "protected" in modifiers:
            return "protected"
        else:
            return "package"  # Default package visibility

    def _find_annotations_for_line_cached(
        self, target_line: int
    ) -> list[dict[str, Any]]:
        """Find annotations for specified line with caching (from AdvancedAnalyzer)"""
        if target_line in self._annotation_cache:
            return self._annotation_cache[target_line]

        result_annotations = []
        for annotation in self.annotations:
            line_distance = target_line - annotation.get("end_line", 0)
            if 1 <= line_distance <= 5:
                result_annotations.append(annotation)

        self._annotation_cache[target_line] = result_annotations
        return result_annotations

    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        """Calculate cyclomatic complexity efficiently (from AdvancedAnalyzer)"""
        complexity = 1
        try:
            node_text = self._get_node_text_optimized(node).lower()
            keywords = ["if", "while", "for", "catch", "case", "switch"]
            for keyword in keywords:
                complexity += node_text.count(keyword)
        except (AttributeError, TypeError) as e:
            log_debug(f"Failed to calculate complexity: {e}")
        except Exception as e:
            log_error(f"Unexpected error in complexity calculation: {e}")
        return complexity

    def _extract_javadoc_for_line(self, target_line: int) -> str | None:
        """Extract JavaDoc comment immediately before the specified line"""
        try:
            if not self.content_lines or target_line <= 1:
                return None

            # Search backwards from target_line
            javadoc_lines = []
            current_line = target_line - 1

            # Skip empty lines
            while current_line > 0:
                line = self.content_lines[current_line - 1].strip()
                if line:
                    break
                current_line -= 1

            # Check for JavaDoc end
            if current_line > 0:
                line = self.content_lines[current_line - 1].strip()
                if line.endswith("*/"):
                    # This might be a JavaDoc comment
                    javadoc_lines.append(self.content_lines[current_line - 1])
                    current_line -= 1

                    # Collect JavaDoc content
                    while current_line > 0:
                        line_content = self.content_lines[current_line - 1]
                        line_stripped = line_content.strip()
                        javadoc_lines.append(line_content)

                        if line_stripped.startswith("/**"):
                            # Found the start of JavaDoc
                            javadoc_lines.reverse()
                            javadoc_text = "\n".join(javadoc_lines)

                            # Clean up the JavaDoc
                            return self._clean_javadoc(javadoc_text)
                        current_line -= 1

            return None

        except Exception as e:
            log_debug(f"Failed to extract JavaDoc: {e}")
            return None

    def _clean_javadoc(self, javadoc_text: str) -> str:
        """Clean JavaDoc text by removing comment markers"""
        if not javadoc_text:
            return ""

        lines = javadoc_text.split("\n")
        cleaned_lines = []

        for line in lines:
            # Remove leading/trailing whitespace
            line = line.strip()

            # Remove comment markers
            if line.startswith("/**"):
                line = line[3:].strip()
            elif line.startswith("*/"):
                line = line[2:].strip()
            elif line.startswith("*"):
                line = line[1:].strip()

            if line:  # Only add non-empty lines
                cleaned_lines.append(line)

        return " ".join(cleaned_lines) if cleaned_lines else ""

    def _is_nested_class(self, node: "tree_sitter.Node") -> bool:
        """Check if this is a nested class (from AdvancedAnalyzer)"""
        current = node.parent
        while current:
            if current.type in [
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
            ]:
                return True
            current = current.parent
        return False

    def _find_parent_class(self, node: "tree_sitter.Node") -> str | None:
        """Find parent class name (from AdvancedAnalyzer)"""
        current = node.parent
        while current:
            if current.type in [
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
            ]:
                return self._extract_class_name(current)
            current = current.parent
        return None

    def _extract_class_name(self, node: "tree_sitter.Node") -> str | None:
        """Extract class name from node (from AdvancedAnalyzer)"""
        for child in node.children:
            if child.type == "identifier":
                return self._get_node_text_optimized(child)
        return None

    def _extract_annotation_optimized(
        self, node: "tree_sitter.Node"
    ) -> dict[str, Any] | None:
        """Extract annotation information optimized (from AdvancedAnalyzer)"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            raw_text = self._get_node_text_optimized(node)

            # Extract annotation name efficiently
            name_match = re.search(r"@(\w+)", raw_text)
            if not name_match:
                return None

            annotation_name = name_match.group(1)

            # Extract parameters efficiently
            parameters = []
            param_match = re.search(r"\((.*?)\)", raw_text, re.DOTALL)
            if param_match:
                param_text = param_match.group(1).strip()
                if param_text:
                    # Simple parameter parsing
                    if "=" in param_text:
                        parameters = [
                            p.strip() for p in re.split(r",(?![^()]*\))", param_text)
                        ]
                    else:
                        parameters = [param_text]

            return {
                "name": annotation_name,
                "parameters": parameters,
                "start_line": start_line,
                "end_line": end_line,
                "raw_text": raw_text,
            }
        except (AttributeError, IndexError, ValueError) as e:
            log_debug(f"Failed to extract annotation from node: {e}")
            return None
        except Exception as e:
            log_error(f"Unexpected exception in annotation extraction: {e}")
            return None

    def _extract_import_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Import | None:
        """Extract import information (from AdvancedAnalyzer)"""
        try:
            import_text = self._get_node_text_optimized(node)
            # Simple approach: get everything until semicolon then process
            import_content = import_text.strip()
            if import_content.endswith(";"):
                import_content = import_content[:-1]

            if "static" in import_content:
                # Static import
                static_match = re.search(r"import\s+static\s+([\w.]+)", import_content)
                if static_match:
                    import_name = static_match.group(1)
                    # Handle wildcard case
                    if import_content.endswith(".*"):
                        import_name = import_name.replace(".*", "")
                        # For static wildcard, remove last element
                        parts = import_name.split(".")
                        if len(parts) > 1:
                            import_name = ".".join(parts[:-1])

                    return Import(
                        name=import_name,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        raw_text=import_text,
                        language="java",
                        module_name=import_name,
                        is_static=True,
                        is_wildcard=import_content.endswith(".*"),
                        import_statement=import_content,
                    )
            else:
                # Normal import
                normal_match = re.search(r"import\s+([\w.]+)", import_content)
                if normal_match:
                    import_name = normal_match.group(1)
                    # Handle wildcard case
                    if import_content.endswith(".*"):
                        if import_name.endswith(".*"):
                            import_name = import_name[:-2]  # Remove trailing .*
                        elif import_name.endswith("."):
                            import_name = import_name[:-1]  # Remove trailing .

                    return Import(
                        name=import_name,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        raw_text=import_text,
                        language="java",
                        module_name=import_name,
                        is_static=False,
                        is_wildcard=import_content.endswith(".*"),
                        import_statement=import_content,
                    )
        except (AttributeError, ValueError, IndexError) as e:
            log_debug(f"Failed to extract import info: {e}")
        except Exception as e:
            log_error(f"Unexpected error in import extraction: {e}")
        return None


class JavaPlugin(LanguagePlugin):
    """Java language plugin for the new architecture"""

    def __init__(self) -> None:
        """Initialize the Java plugin"""
        super().__init__()
        self._language_cache: tree_sitter.Language | None = None

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "java"

    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return [".java", ".jsp", ".jspx"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return JavaElementExtractor()

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
        """Get the Tree-sitter language object for Java"""
        if self._language_cache is None:
            try:
                import tree_sitter_java as tsjava

                self._language_cache = tsjava.language()  # type: ignore
            except ImportError:
                log_error("tree-sitter-java not available")
                return None
            except Exception as e:
                log_error(f"Failed to load Java language: {e}")
                return None
        return self._language_cache

    def get_supported_queries(self) -> list[str]:
        """Get list of supported query names for this language"""
        return ["class", "method", "field", "import"]

    def is_applicable(self, file_path: str) -> bool:
        """Check if this plugin is applicable for the given file"""
        return any(
            file_path.lower().endswith(ext.lower())
            for ext in self.get_file_extensions()
        )

    def get_plugin_info(self) -> dict:
        """Get information about this plugin"""
        return {
            "name": "Java Plugin",
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "version": "2.0.0",
            "supported_queries": self.get_supported_queries(),
        }

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """
        Analyze a Java file and return analysis results.

        Args:
            file_path: Path to the Java file to analyze
            request: Analysis request object

        Returns:
            AnalysisResult object containing the analysis results
        """
        try:
            from ..core.parser import Parser
            from ..models import AnalysisResult

            log_debug(f"Java Plugin: Starting analysis of {file_path}")

            # Read file content
            with open(file_path, encoding="utf-8") as f:
                source_code = f.read()

            log_debug(f"Java Plugin: Read {len(source_code)} characters from file")

            # Parse the file
            parser = Parser()
            parse_result = parser.parse_code(source_code, "java")

            log_debug(f"Java Plugin: Parse result success: {parse_result.success}")

            if not parse_result.success:
                log_error(f"Java Plugin: Parse failed: {parse_result.error_message}")
                return AnalysisResult(
                    file_path=file_path,
                    language="java",
                    line_count=len(source_code.splitlines()),
                    elements=[],
                    node_count=0,
                    query_results={},
                    source_code=source_code,
                    success=False,
                    error_message=parse_result.error_message,
                )

            # Extract elements
            extractor = self.create_extractor()

            if parse_result.tree:
                log_debug("Java Plugin: Extracting packages...")
                packages = extractor.extract_packages(parse_result.tree, source_code)
                log_debug(f"Java Plugin: Found {len(packages)} packages")

                log_debug("Java Plugin: Extracting functions...")
                functions = extractor.extract_functions(parse_result.tree, source_code)
                log_debug(f"Java Plugin: Found {len(functions)} functions")

                log_debug("Java Plugin: Extracting classes...")
                classes = extractor.extract_classes(parse_result.tree, source_code)
                log_debug(f"Java Plugin: Found {len(classes)} classes")

                log_debug("Java Plugin: Extracting variables...")
                variables = extractor.extract_variables(parse_result.tree, source_code)
                log_debug(f"Java Plugin: Found {len(variables)} variables")

                log_debug("Java Plugin: Extracting imports...")
                imports = extractor.extract_imports(parse_result.tree, source_code)
                log_debug(f"Java Plugin: Found {len(imports)} imports")
            else:
                packages = []
                functions = []
                classes = []
                variables = []
                imports = []

            # Combine all elements
            all_elements: list[CodeElement] = []
            all_elements.extend(packages)
            all_elements.extend(functions)
            all_elements.extend(classes)
            all_elements.extend(variables)
            all_elements.extend(imports)
            log_debug(f"Java Plugin: Total elements: {len(all_elements)}")

            return AnalysisResult(
                file_path=file_path,
                language="java",
                line_count=len(source_code.splitlines()),
                elements=all_elements,
                node_count=(
                    parse_result.tree.root_node.child_count if parse_result.tree else 0
                ),
                query_results={},
                source_code=source_code,
                success=True,
                error_message=None,
            )

        except Exception as e:
            log_error(f"Failed to analyze Java file {file_path}: {e}")
            import traceback

            log_error(f"Java Plugin traceback: {traceback.format_exc()}")
            return AnalysisResult(
                file_path=file_path,
                language="java",
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message=str(e),
            )
