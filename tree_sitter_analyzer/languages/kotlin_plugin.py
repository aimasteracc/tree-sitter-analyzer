#!/usr/bin/env python3
"""
Kotlin Language Plugin

Provides Kotlin-specific parsing and element extraction functionality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error
from .kotlin_helpers import (
    extract_import as _extract_import_standalone,
)
from .kotlin_helpers import (
    extract_kotlin_class_or_object as _extract_class_standalone,
)
from .kotlin_helpers import (
    extract_kotlin_function as _extract_func_standalone,
)
from .kotlin_helpers import (
    extract_kotlin_property as _extract_prop_standalone,
)


class KotlinElementExtractor(ElementExtractor):
    """Kotlin-specific element extractor"""

    def __init__(self) -> None:
        """Initialize the Kotlin element extractor."""
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}

    def extract_functions(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """Extract Kotlin function declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        self._traverse_and_extract(
            tree.root_node,
            {"function_declaration": self._extract_function},
            functions,
        )

        log_debug(f"Extracted {len(functions)} Kotlin functions")
        return functions

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """Extract Kotlin class declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        # Extract package
        self._extract_package(tree.root_node)

        classes: list[Class] = []

        extractors = {
            "class_declaration": self._extract_class,
            "object_declaration": self._extract_object,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            classes,
        )

        log_debug(f"Extracted {len(classes)} Kotlin classes")
        return classes

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """Extract Kotlin properties"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        extractors = {
            "property_declaration": self._extract_property,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            variables,
        )

        log_debug(f"Extracted {len(variables)} Kotlin properties")
        return variables

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """Extract Kotlin imports"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        imports: list[Import] = []

        extractors = {
            "import_header": self._extract_import,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            imports,
        )

        log_debug(f"Extracted {len(imports)} Kotlin imports")
        return imports

    def extract_packages(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Package]:
        """Extract Kotlin package"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        # r37ds (dogfood): flattened nesting 6 → 3 by extracting the
        # package_header lookup into ``_find_package_header_node``.
        packages: list[Package] = []
        self._extract_package(tree.root_node)
        if not self.current_package:
            return packages
        package_node = self._find_package_header_node(tree.root_node)
        if package_node is None:
            return packages
        packages.append(
            Package(
                name=self.current_package,
                start_line=package_node.start_point[0] + 1,
                end_line=package_node.end_point[0] + 1,
                raw_text=self._get_node_text(package_node),
                language="kotlin",
            )
        )
        return packages

    @staticmethod
    def _find_package_header_node(
        root_node: tree_sitter.Node,
    ) -> tree_sitter.Node | None:
        """Return the first ``package_header`` child or ``None``.

        Kotlin's tree-sitter grammar puts the package declaration as a
        ``package_header`` node directly under the root. We stop at the
        first match — there's only ever one per file.
        """
        for child in root_node.children:
            if child.type == "package_header":
                return child
        return None

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        # Keep current_package if already extracted?
        # Usually safe to re-extract or clear.
        if not self.source_code:
            self.current_package = ""

    def _traverse_and_extract(
        self,
        node: tree_sitter.Node,
        extractors: dict[str, Any],
        results: list[Any],
    ) -> None:
        """Recursive traversal to find and extract elements"""
        if node.type in extractors:
            element = extractors[node.type](node)
            if element:
                results.append(element)

        for child in node.children:
            self._traverse_and_extract(child, extractors, results)

    def _extract_package(self, node: tree_sitter.Node) -> None:
        """Extract package declaration.

        r37ds (dogfood): flattened nesting 6 → 3 by extracting the
        identifier scan into ``_kotlin_package_name_from_header``.
        """
        for child in node.children:
            if child.type != "package_header":
                continue
            pkg_name = self._kotlin_package_name_from_header(child)
            if pkg_name is not None:
                self.current_package = pkg_name
                return

    def _kotlin_package_name_from_header(
        self, package_header: tree_sitter.Node
    ) -> str | None:
        """Return the package name string from a ``package_header`` node.

        Kotlin grammars emit either ``identifier`` / ``simple_identifier``
        for bare names or a qualified-name node whose ``type`` contains
        ``identifier``. We pick the first matching child.
        """
        for grandchild in package_header.children:
            if grandchild.type in ("identifier", "simple_identifier"):
                return self._get_node_text(grandchild)
            if "identifier" in grandchild.type:
                return self._get_node_text(grandchild)
        return None

    def _extract_function(self, node: tree_sitter.Node) -> Function | None:
        """Extract function information"""
        return _extract_func_standalone(node, self._get_node_text, self.current_package)

    def _extract_class(self, node: tree_sitter.Node) -> Class | None:
        """Extract class declaration"""
        return self._extract_class_or_object(node, "class")

    def _extract_object(self, node: tree_sitter.Node) -> Class | None:
        """Extract object declaration"""
        return self._extract_class_or_object(node, "object")

    def _extract_class_or_object(
        self, node: tree_sitter.Node, kind: str
    ) -> Class | None:
        """Generic extraction for class/object/interface"""
        return _extract_class_standalone(
            node, kind, self._get_node_text, self.current_package
        )

    def _extract_property(self, node: tree_sitter.Node) -> Variable | None:
        """Extract property declaration"""
        return _extract_prop_standalone(node, self._get_node_text)

    def _extract_import(self, node: tree_sitter.Node) -> Import | None:
        """Extract import header"""
        return _extract_import_standalone(node, self._get_node_text)

    def _get_node_text(self, node: tree_sitter.Node) -> str:
        """Get node text with caching using position-based keys"""
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte
            encoding = "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)
            self._node_text_cache[cache_key] = text
            return text
        except Exception:
            return ""

    def _extract_docstring(self, node: tree_sitter.Node) -> str | None:
        """Extract KDoc"""
        # Similar to Rust/Java logic
        return None


class KotlinPlugin(LanguagePlugin):
    """Kotlin language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Kotlin language plugin."""
        super().__init__()
        self.extractor = KotlinElementExtractor()
        self.language = "kotlin"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "kotlin"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".kt", ".kts"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return KotlinElementExtractor()

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="kotlin",
                    line_count=len(file_content.splitlines()),
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
                parser = tree_sitter.Parser(language)

            tree = parser.parse(file_content.encode("utf-8"))

            extractor = self.create_extractor()
            all_elements: list[Any] = []
            all_elements.extend(extractor.extract_functions(tree, file_content))
            all_elements.extend(extractor.extract_classes(tree, file_content))
            all_elements.extend(extractor.extract_variables(tree, file_content))
            all_elements.extend(extractor.extract_imports(tree, file_content))
            packages = extractor.extract_packages(tree, file_content)
            all_elements.extend(packages)

            node_count = (
                self._count_tree_nodes(tree.root_node) if tree and tree.root_node else 0
            )

            package = packages[0] if packages else None

            return AnalysisResult(
                file_path=file_path,
                language="kotlin",
                line_count=len(file_content.splitlines()),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
                package=package,
            )

        except Exception as e:
            log_error(f"Error analyzing Kotlin file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="kotlin",
                line_count=0,
                elements=[],
                source_code="",
                error_message=str(e),
                success=False,
            )

    def _count_tree_nodes(self, node: Any) -> int:
        """Recursively count nodes."""
        if node is None:
            return 0
        count = 1
        if hasattr(node, "children"):
            for child in node.children:
                count += self._count_tree_nodes(child)
        return count

    def get_tree_sitter_language(self) -> Any | None:
        """Get the tree-sitter language for Kotlin."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_kotlin

            caps_or_lang = tree_sitter_kotlin.language()

            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
                self._cached_language = caps_or_lang
            else:
                try:
                    self._cached_language = tree_sitter.Language(caps_or_lang)
                except Exception as e:
                    log_error(f"Failed to create Language object: {e}")
                    return None

            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-kotlin not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Kotlin: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements."""
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
