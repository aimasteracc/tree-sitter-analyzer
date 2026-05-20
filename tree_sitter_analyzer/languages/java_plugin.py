#!/usr/bin/env python3
"""
Java Language Plugin

Provides Java-specific parsing and element extraction functionality.
Migrated from AdvancedAnalyzer implementation for future independence.
"""

from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error
from .java_helpers import (
    calculate_complexity as _calc_complexity_standalone,
)
from .java_helpers import (
    determine_visibility as _determine_vis_standalone,
)
from .java_helpers import (
    extract_annotation as _extract_annotation_standalone,
)
from .java_helpers import (
    extract_class_name as _extract_class_name_standalone,
)
from .java_helpers import (
    extract_java_class as _extract_class_standalone,
)
from .java_helpers import (
    extract_java_field as _extract_field_standalone,
)
from .java_helpers import (
    extract_java_imports as _extract_imports_standalone,
)
from .java_helpers import (
    extract_java_method as _extract_method_standalone,
)
from .java_helpers import (
    extract_java_packages as _extract_packages_standalone,
)
from .java_helpers import (
    extract_javadoc_for_line as _extract_javadoc_standalone,
)
from .java_helpers import (
    extract_modifiers as _extract_mods_standalone,
)
from .java_helpers import (
    find_parent_class as _find_parent_class_standalone,
)
from .java_helpers import (
    is_nested_class as _is_nested_standalone,
)
from .java_helpers import (
    java_traverse_and_extract as _traverse_standalone,
)
from .java_helpers import (
    parse_field_declaration as _parse_field_standalone,
)
from .java_helpers import (
    parse_method_signature as _parse_method_sig_standalone,
)


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

    # Extract elements from AST: extract_annotations
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

    # Extract elements from AST: extract_functions
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

    # Extract elements from AST: extract_classes
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

    # Extract elements from AST: extract_variables
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

    # Extract elements from AST: extract_imports
    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract Java import statements with enhanced robustness"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        return _extract_imports_standalone(
            tree,
            source_code,
            self._get_node_text_optimized,
            lambda pkg: setattr(self, "current_package", pkg),
        )

    # Extract elements from AST: _extract_imports_fallback
    def _extract_imports_fallback(self, source_code: str) -> list[Import]:
        """Fallback import extraction using regex when tree-sitter fails"""
        from .java_helpers import _extract_imports_fallback as _impl

        return _impl(source_code)

    # Extract elements from AST: extract_packages
    def extract_packages(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Package]:
        """Extract Java package declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        packages = _extract_packages_standalone(tree, self._get_node_text_optimized)
        if packages and packages[0].name:
            self.current_package = packages[0].name
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

    # Extract elements from AST: _traverse_and_extract_iterative
    def _traverse_and_extract_iterative(
        self,
        root_node: "tree_sitter.Node | None",
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """Iterative node traversal and extraction with batch processing"""
        _traverse_standalone(
            root_node,
            extractors,
            results,
            element_type,
            self._processed_nodes,
            self._element_cache,
        )

    # Process data through pipeline: _process_field_batch
    def _process_field_batch(
        self, batch: list["tree_sitter.Node"], extractors: dict, results: list[Any]
    ) -> None:
        """Process field nodes with caching — delegated to helper."""
        from .java_helpers import _process_field_batch

        _process_field_batch(
            batch, extractors, results, self._processed_nodes, self._element_cache
        )

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

    # Extract elements from AST: _extract_class_optimized
    def _extract_class_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class information optimized"""
        return _extract_class_standalone(
            node,
            self._get_node_text_optimized,
            self.content_lines,
            self.current_package,
            self._extract_modifiers_optimized,
            self._determine_visibility,
            self._find_annotations_for_line_cached,
            self._is_nested_class,
            self._find_parent_class,
        )

    # Extract elements from AST: _extract_method_optimized
    def _extract_method_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract method information optimized"""
        return _extract_method_standalone(
            node,
            self._get_node_text_optimized,
            self.content_lines,
            self._parse_method_signature_optimized,
            self._determine_visibility,
            self._find_annotations_for_line_cached,
            self._calculate_complexity_optimized,
            self._extract_javadoc_for_line,
        )

    # Extract elements from AST: _extract_field_optimized
    def _extract_field_optimized(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract field information optimized"""
        return _extract_field_standalone(
            node,
            self._get_node_text_optimized,
            self.content_lines,
            self._parse_field_declaration_optimized,
            self._determine_visibility,
            self._find_annotations_for_line_cached,
            self._extract_javadoc_for_line,
        )

    # Parse input into structured data: _parse_method_signature_optimized
    def _parse_method_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, str, list[str], list[str], list[str]] | None:
        """Parse method signature optimized (from AdvancedAnalyzer)"""
        return _parse_method_sig_standalone(node, self._get_node_text_optimized)

    # Parse input into structured data: _parse_field_declaration_optimized
    def _parse_field_declaration_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, list[str], list[str]] | None:
        """Parse field declaration optimized (from AdvancedAnalyzer)"""
        return _parse_field_standalone(node, self._get_node_text_optimized)

    # Extract elements from AST: _extract_modifiers_optimized
    def _extract_modifiers_optimized(self, node: "tree_sitter.Node") -> list[str]:
        """Extract modifiers efficiently (from AdvancedAnalyzer)"""
        return _extract_mods_standalone(node, self._get_node_text_optimized)

    # Extract elements from AST: _extract_package_info
    def _extract_package_info(self, node: "tree_sitter.Node") -> None:
        """Extract package information"""
        from .java_helpers import _extract_package_name

        pkg = _extract_package_name(node, self._get_node_text_optimized)
        if pkg:
            self.current_package = pkg

    # Extract elements from AST: _extract_package_element
    def _extract_package_element(self, node: "tree_sitter.Node") -> Package | None:
        """Extract package element for inclusion in results"""
        from .java_helpers import _extract_package_element as _standalone

        return _standalone(node, self._get_node_text_optimized)

    # Extract elements from AST: _extract_package_from_tree
    def _extract_package_from_tree(self, tree: "tree_sitter.Tree") -> None:
        """Extract package information from tree when needed"""
        if tree and tree.root_node:
            for child in tree.root_node.children:
                if child.type == "package_declaration":
                    self._extract_package_info(child)
                    break

    # Extract elements from AST: _extract_import_info
    def _extract_import_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Import | None:
        """Extract import information from import declaration node"""
        from .java_helpers import _extract_import_info as _standalone

        return _standalone(node, self._get_node_text_optimized)

    # Extract elements from AST: _extract_annotation_optimized
    def _extract_annotation_optimized(
        self, node: "tree_sitter.Node"
    ) -> dict[str, Any] | None:
        """Extract annotation information optimized"""
        return _extract_annotation_standalone(node, self._get_node_text_optimized)

    def _determine_visibility(self, modifiers: list[str]) -> str:
        """Determine visibility from modifiers"""
        return _determine_vis_standalone(modifiers)

    # Search for patterns or elements: _find_annotations_for_line_cached
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
        return _is_nested_standalone(node)

    # Search for patterns or elements: _find_parent_class
    def _find_parent_class(self, node: "tree_sitter.Node") -> str | None:
        """Find parent class name for nested classes"""
        return _find_parent_class_standalone(node, self._get_node_text_optimized)

    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        """Calculate cyclomatic complexity optimized"""
        return _calc_complexity_standalone(node)

    # Extract elements from AST: _extract_javadoc_for_line
    def _extract_javadoc_for_line(self, line: int) -> str | None:
        """Extract JavaDoc comment for a specific line"""
        return _extract_javadoc_standalone(line, self.content_lines)

    # Extract elements from AST: _extract_class_name
    def _extract_class_name(self, node: "tree_sitter.Node") -> str | None:
        """Extract class name from a class declaration node."""
        return _extract_class_name_standalone(node, self._get_node_text_optimized)


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

    # Extract elements from AST: create_extractor
    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return JavaElementExtractor()

    # Analyze source code structure: analyze_file
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

                extractor = self.create_extractor()
                # ARCH-A3: use the standardised ElementExtractor hook.
                extractor.set_file_encoding(detected_encoding)
                all_elements: list[Any] = []
                all_elements.extend(extractor.extract_functions(tree, file_content))
                all_elements.extend(extractor.extract_classes(tree, file_content))
                all_elements.extend(extractor.extract_variables(tree, file_content))
                all_elements.extend(extractor.extract_imports(tree, file_content))
                packages = extractor.extract_packages(tree, file_content)
                all_elements.extend(packages)

                package = packages[0] if packages else None

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

    # Extract elements from AST: extract_elements
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
