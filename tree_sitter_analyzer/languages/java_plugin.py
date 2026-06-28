#!/usr/bin/env python3
"""
Java Language Plugin

Provides Java-specific parsing and element extraction functionality.
Migrated from AdvancedAnalyzer implementation for future independence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest

from .. import encoding_utils as _encoding_utils
from ..encoding_utils import extract_text_slice, safe_encode
from ..models import AnalysisResult, Class, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error
from ..utils.tree_sitter_compat import count_nodes_iterative
from .java_helpers import (
    _extract_import_info,
    _extract_imports_fallback,
    _extract_package_element,
    _extract_package_name,
    _process_field_batch,
    calculate_complexity as _calc_complexity_standalone,
    determine_visibility as _determine_vis_standalone,
    extract_annotation as _extract_annotation_standalone,
    extract_class_name as _extract_class_name_standalone,
    extract_java_class as _extract_class_standalone,
    extract_java_field as _extract_field_standalone,
    extract_java_imports as _extract_imports_standalone,
    extract_java_method as _extract_method_standalone,
    extract_java_packages as _extract_packages_standalone,
    extract_javadoc_for_line as _extract_javadoc_standalone,
    extract_modifiers as _extract_mods_standalone,
    find_parent_class as _find_parent_class_standalone,
    is_nested_class as _is_nested_standalone,
    java_traverse_and_extract as _traverse_standalone,
    parse_field_declaration as _parse_field_standalone,
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

        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None
        self._annotation_cache: dict[int, list[dict[str, Any]]] = {}
        self._signature_cache: dict[int, str] = {}
        self.annotations: list[dict[str, Any]] = []  # populated before class/method extraction

    def extract_annotations(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[dict[str, Any]]:
        """Extract Java annotations using AdvancedAnalyzer implementation"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        annotations: list[dict[str, Any]] = []

        extractors = {
            "annotation": self._extract_annotation_optimized,
            "marker_annotation": self._extract_annotation_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, annotations, "annotation"
        )

        self.annotations = annotations

        log_debug(f"Extracted {len(annotations)} annotations")
        return annotations

    def extract_functions(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """Extract Java method definitions using AdvancedAnalyzer implementation"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        extractors = {
            "method_declaration": self._extract_method_optimized,
            "constructor_declaration": self._extract_method_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, functions, "method"
        )

        log_debug(f"Extracted {len(functions)} methods")
        return functions

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """Extract Java class definitions using AdvancedAnalyzer implementation"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        if not self.current_package:  # extract package first to avoid empty current_package (#535)
            self._extract_package_from_tree(tree)

        classes: list[Class] = []

        extractors = {
            "class_declaration": self._extract_class_optimized,
            "interface_declaration": self._extract_class_optimized,
            "enum_declaration": self._extract_class_optimized,
            # Theme-I (2026-06-10): records and annotation types were silently
            # dropped from outlines — modern Java DTOs/annotations invisible.
            "record_declaration": self._extract_class_optimized,
            "annotation_type_declaration": self._extract_class_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, classes, "class"
        )

        log_debug(f"Extracted {len(classes)} classes")
        return classes

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """Extract Java field definitions using AdvancedAnalyzer implementation"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

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

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """Extract Java import statements with enhanced robustness"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        return _extract_imports_standalone(
            tree,
            source_code,
            self._get_node_text_optimized,
            lambda pkg: setattr(self, "current_package", pkg),
        )

    def _extract_imports_fallback(self, source_code: str) -> list[Import]:
        """Fallback import extraction using regex when tree-sitter fails"""
        return _extract_imports_fallback(source_code)

    def extract_packages(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Package]:
        """Extract Java package declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        packages = _extract_packages_standalone(tree, self._get_node_text_optimized)
        if packages and packages[0].name:
            self.current_package = packages[0].name
        return packages

    def _reset_caches(self) -> None:
        """Reset performance caches and package state to avoid cross-test contamination."""
        for cache in (self._node_text_cache, self._element_cache, self._annotation_cache, self._signature_cache):
            cache.clear()
        self._processed_nodes.clear()
        self.current_package = ""

    def _traverse_and_extract_iterative(
        self,
        root_node: tree_sitter.Node | None,
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

    def _process_field_batch(
        self, batch: list[tree_sitter.Node], extractors: dict, results: list[Any]
    ) -> None:
        """Process field nodes with caching — delegated to helper."""
        _process_field_batch(
            batch, extractors, results, self._processed_nodes, self._element_cache
        )

    def _get_node_text_optimized(self, node: tree_sitter.Node) -> str:
        """Get node text with position-based cache key for deterministic behavior."""
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]
        try:
            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, node.start_byte, node.end_byte, encoding)
            self._node_text_cache[cache_key] = text
            return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")
            return self._get_node_text_fallback(node)

    def _get_node_text_fallback(self, node: tree_sitter.Node) -> str:
        """Fallback: slice source lines by start/end points (handles encoding errors)."""
        try:
            sp, ep = node.start_point, node.end_point
            if sp[0] == ep[0]:
                return self.content_lines[sp[0]][sp[1]:ep[1]]
            return "\n".join(self._collect_multiline_slices(sp, ep))
        except Exception as fe:
            log_error(f"Fallback text extraction also failed: {fe}")
            return ""

    def _collect_multiline_slices(
        self, sp: tuple[int, int], ep: tuple[int, int]
    ) -> list[str]:
        """Collect sliced lines from sp[0] to ep[0] for multiline node text."""
        lines = []
        for i in range(sp[0], ep[0] + 1):
            if i >= len(self.content_lines):
                continue
            line = self.content_lines[i]
            if i == sp[0]:
                lines.append(line[sp[1]:])
            elif i == ep[0]:
                lines.append(line[:ep[1]])
            else:
                lines.append(line)
        return lines

    def _extract_class_optimized(self, node: tree_sitter.Node) -> Class | None:
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

    def _extract_method_optimized(self, node: tree_sitter.Node) -> Function | None:
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

    def _extract_field_optimized(self, node: tree_sitter.Node) -> list[Variable]:
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

    def _parse_method_signature_optimized(
        self, node: tree_sitter.Node
    ) -> tuple[str, str, list[str], list[str], list[str]] | None:
        """Parse method signature optimized (from AdvancedAnalyzer)"""
        return _parse_method_sig_standalone(node, self._get_node_text_optimized)

    def _parse_field_declaration_optimized(
        self, node: tree_sitter.Node
    ) -> tuple[str, list[str], list[str]] | None:
        """Parse field declaration optimized (from AdvancedAnalyzer)"""
        return _parse_field_standalone(node, self._get_node_text_optimized)

    def _extract_modifiers_optimized(self, node: tree_sitter.Node) -> list[str]:
        """Extract modifiers efficiently (from AdvancedAnalyzer)"""
        return _extract_mods_standalone(node, self._get_node_text_optimized)

    def _extract_package_info(self, node: tree_sitter.Node) -> None:
        """Extract package information"""
        pkg = _extract_package_name(node, self._get_node_text_optimized)
        if pkg:
            self.current_package = pkg

    def _extract_package_element(self, node: tree_sitter.Node) -> Package | None:
        return _extract_package_element(node, self._get_node_text_optimized)

    def _extract_package_from_tree(self, tree: tree_sitter.Tree) -> None:
        if tree and tree.root_node:
            for child in tree.root_node.children:
                if child.type == "package_declaration":
                    self._extract_package_info(child)
                    break

    def _extract_import_info(self, node: tree_sitter.Node, source_code: str) -> Import | None:
        return _extract_import_info(node, self._get_node_text_optimized)

    def _extract_annotation_optimized(self, node: tree_sitter.Node) -> dict[str, Any] | None:
        return _extract_annotation_standalone(node, self._get_node_text_optimized)

    def _determine_visibility(self, modifiers: list[str]) -> str:
        return _determine_vis_standalone(modifiers)

    def _find_annotations_for_line_cached(self, line: int) -> list[dict[str, Any]]:
        """Find annotations near a given line (within ±2), with caching."""
        if line in self._annotation_cache:
            return self._annotation_cache[line]
        result = [a for a in self.annotations if abs(a.get("line", 0) - line) <= 2]
        self._annotation_cache[line] = result
        return result

    def _is_nested_class(self, node: tree_sitter.Node) -> bool:
        return _is_nested_standalone(node)

    def _find_parent_class(self, node: tree_sitter.Node) -> str | None:
        return _find_parent_class_standalone(node, self._get_node_text_optimized)

    def _calculate_complexity_optimized(self, node: tree_sitter.Node) -> int:
        return _calc_complexity_standalone(node)

    def _extract_javadoc_for_line(self, line: int) -> str | None:
        return _extract_javadoc_standalone(line, self.content_lines)

    def _extract_class_name(self, node: tree_sitter.Node) -> str | None:
        return _extract_class_name_standalone(node, self._get_node_text_optimized)


class JavaPlugin(LanguagePlugin):
    """Java language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Java language plugin."""
        super().__init__()
        self.extractor = JavaElementExtractor()
        self.language = "java"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

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
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze Java code and return structured results."""
        try:
            file_content, detected_encoding = await _encoding_utils.read_file_safe_async(file_path)
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path, language="java",
                    line_count=len(file_content.splitlines()), elements=[],
                    source_code=file_content, success=False,
                    error_message="Failed to load tree-sitter language for Java",
                )

            def _analyze_sync() -> tuple[list[Any], int, Any]:
                import tree_sitter
                parser = tree_sitter.Parser()
                if hasattr(parser, "set_language"):
                    parser.set_language(language)
                elif hasattr(parser, "language"):
                    parser.language = language
                else:
                    parser = tree_sitter.Parser(language)
                tree = parser.parse(file_content.encode("utf-8"))
                extractor = self.create_extractor()
                extractor.set_file_encoding(detected_encoding)  # ARCH-A3
                # extract_annotations first so _find_annotations_for_line_cached has data
                extractor.extract_annotations(tree, file_content)
                all_elements: list[Any] = []
                all_elements.extend(extractor.extract_functions(tree, file_content))
                all_elements.extend(extractor.extract_classes(tree, file_content))
                all_elements.extend(extractor.extract_variables(tree, file_content))
                all_elements.extend(extractor.extract_imports(tree, file_content))
                packages = extractor.extract_packages(tree, file_content)
                all_elements.extend(packages)
                node_count = count_nodes_iterative(tree.root_node) if tree and tree.root_node else 0
                return all_elements, node_count, packages[0] if packages else None

            all_elements, node_count, package = await anyio.to_thread.run_sync(_analyze_sync)
            return AnalysisResult(
                file_path=file_path, language="java",
                line_count=len(file_content.splitlines()), elements=all_elements,
                node_count=node_count, source_code=file_content, package=package,
            )
        except Exception as e:
            log_error(f"Error analyzing Java file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path, language="java", line_count=0,
                elements=[], source_code="", error_message=str(e), success=False,
            )

    def _count_tree_nodes(self, node: Any) -> int:
        """Count nodes in the AST tree (Deprecated: use iterative version)."""
        return count_nodes_iterative(node)

    def get_tree_sitter_language(self) -> Any | None:
        """Get the tree-sitter language for Java."""
        if self._cached_language is not None:
            return self._cached_language
        try:
            import tree_sitter
            import tree_sitter_java

            caps_or_lang = tree_sitter_java.language()
            if hasattr(caps_or_lang, "__class__") and "Language" in str(type(caps_or_lang)):
                self._cached_language = caps_or_lang
            else:
                try:
                    self._cached_language = tree_sitter.Language(caps_or_lang)
                except Exception as e:
                    log_error(f"Failed to create Language from PyCapsule: {e}")
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
        _empty: dict[str, Any] = {
            "functions": [], "classes": [], "variables": [],
            "imports": [], "packages": [], "annotations": [],
        }
        if tree is None:
            return _empty
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
            return _empty
