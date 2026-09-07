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
from ..models import AnalysisResult, Class, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error
from ..utils.tree_sitter_compat import count_nodes_iterative
from ._java_extractor_support import _JavaExtractorSupport
from .java_helpers import (
    _extract_import_info,
    _extract_imports_fallback,
    _extract_package_element,
    _extract_package_name,
)
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
    parse_field_declaration as _parse_field_standalone,
)
from .java_helpers import (
    parse_method_signature as _parse_method_sig_standalone,
)


class JavaElementExtractor(_JavaExtractorSupport):
    """Java-specific element extractor with AdvancedAnalyzer implementation"""

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
            # Modern Java (2026-09-01): new function-like node types.
            "lambda_expression": self._extract_lambda_optimized,
            "static_initializer": self._extract_static_initializer_optimized,
            "compact_constructor_declaration": self._extract_method_optimized,
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

        if (
            not self.current_package
        ):  # extract package first to avoid empty current_package (#535)
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
            # 已安装 grammar 的匿名类使用 object_creation_expression 下的 class_body。
            "class_body": self._extract_anonymous_class_optimized,
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
        """提取包或模块；切换源码时清空按字节范围缓存的旧文本。"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()
        modules = [
            child
            for child in tree.root_node.children
            if child.type == "module_declaration"
        ]
        if modules:
            packages = []
            for node in modules:
                package = self._extract_module_declaration_optimized(node)
                if package is not None:
                    packages.append(package)
        else:
            packages = _extract_packages_standalone(tree, self._get_node_text_optimized)
        if packages and packages[0].name:
            self.current_package = packages[0].name
        return packages

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

    def _extract_import_info(
        self, node: tree_sitter.Node, source_code: str
    ) -> Import | None:
        return _extract_import_info(node, self._get_node_text_optimized)

    def _extract_annotation_optimized(
        self, node: tree_sitter.Node
    ) -> dict[str, Any] | None:
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
            (
                file_content,
                detected_encoding,
            ) = await _encoding_utils.read_file_safe_async(file_path)
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="java",
                    line_count=len(file_content.splitlines()),
                    elements=[],
                    source_code=file_content,
                    success=False,
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
                node_count = (
                    count_nodes_iterative(tree.root_node)
                    if tree and tree.root_node
                    else 0
                )
                return all_elements, node_count, packages[0] if packages else None

            all_elements, node_count, package = await anyio.to_thread.run_sync(
                _analyze_sync
            )
            return AnalysisResult(
                file_path=file_path,
                language="java",
                line_count=len(file_content.splitlines()),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
                package=package,
            )
        except Exception as e:
            log_error(f"Error analyzing Java file {file_path}: {e}")
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
            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
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
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
            "packages": [],
            "annotations": [],
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
