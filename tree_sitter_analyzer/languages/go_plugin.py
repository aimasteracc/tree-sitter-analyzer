#!/usr/bin/env python3
"""
Go Language Plugin

Provides Go-specific parsing and element extraction functionality.
Supports packages, functions, methods, structs, interfaces, type aliases,
const/var declarations, goroutines, and channels.
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
from ._go_common import (
    extract_docstring as _extract_docstring_standalone,
)
from ._go_common import (
    extract_parameters as _extract_params_standalone,
)
from ._go_common import (
    extract_return_type as _extract_return_type_standalone,
)
from ._go_function import (
    extract_go_function as _extract_func_standalone,
)
from ._go_function import (
    extract_go_interface_methods as _extract_iface_methods_standalone,
)
from ._go_function import (
    extract_go_method as _extract_method_standalone,
)
from ._go_import import (
    _extract_import_declaration,
)
from ._go_import import (
    extract_import_spec as _extract_import_spec_standalone,
)
from ._go_import import (
    extract_imports_from_tree as _extract_imports_standalone,
)
from ._go_type import (
    extract_embedded_types as _extract_embedded_standalone,
)
from ._go_type import (
    extract_go_type_spec as _extract_type_spec_standalone,
)
from ._go_type import (
    extract_type_declaration,
)
from ._go_variable import (
    extract_struct_fields as _extract_struct_fields_standalone,
)
from ._go_variable import (
    extract_var_or_const,
)
from ._go_variable import (
    extract_var_spec as _extract_var_spec_standalone,
)


class GoElementExtractor(ElementExtractor):
    """Go-specific element extractor"""

    def __init__(self) -> None:
        """Initialize the Go element extractor."""
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}
        # Go-specific metadata
        self.goroutines: list[dict[str, Any]] = []
        self.channels: list[dict[str, Any]] = []
        self.defers: list[dict[str, Any]] = []

    def extract_functions(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """Extract Go function and method declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        extractors = {
            "function_declaration": self._extract_function,
            "method_declaration": self._extract_method,
            # Interface method signatures (method_elem) — owned by their
            # interface via receiver_type (#588).
            "type_spec": self._extract_interface_methods,
            "type_alias": self._extract_interface_methods,
        }

        self._traverse_and_extract(tree.root_node, extractors, functions)

        log_debug(f"Extracted {len(functions)} Go functions/methods")
        return functions

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """Extract Go struct and interface definitions"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        # Extract type declarations (struct, interface, type alias)
        self._traverse_for_types(tree.root_node, classes)

        log_debug(f"Extracted {len(classes)} Go structs/interfaces")
        return classes

    # Extract elements from AST: extract_variables
    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """Extract Go const and var declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        extractors = {
            "const_declaration": self._extract_const_declaration,
            "var_declaration": self._extract_var_declaration,
            "type_declaration": self._extract_struct_fields,
        }

        self._traverse_and_extract(tree.root_node, extractors, variables)

        log_debug(f"Extracted {len(variables)} Go const/var/field declarations")
        return variables

    # Extract elements from AST: extract_imports
    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """Extract Go import declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()
        imports = _extract_imports_standalone(tree, source_code, self._get_node_text)
        log_debug(f"Extracted {len(imports)} Go imports")
        return imports

    # Extract elements from AST: extract_packages
    def extract_packages(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Package]:
        """Extract Go package declaration"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        packages: list[Package] = []

        for child in tree.root_node.children:
            if child.type == "package_clause":
                pkg = self._extract_package(child)
                if pkg:
                    packages.append(pkg)
                    self.current_package = pkg.name
                break

        log_debug(f"Extracted {len(packages)} Go packages")
        return packages

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self.goroutines.clear()
        self.channels.clear()
        self.defers.clear()

    # Extract elements from AST: _traverse_and_extract
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
                if isinstance(element, list):
                    results.extend(element)
                else:
                    results.append(element)

        # Also detect goroutines, channels, defers
        if node.type == "go_statement":
            self._extract_goroutine(node)
        elif node.type == "send_statement":
            self._extract_channel_operation(node, "send")
        elif node.type == "defer_statement":
            self._extract_defer(node)

        for child in node.children:
            self._traverse_and_extract(child, extractors, results)

    def _traverse_for_types(self, node: tree_sitter.Node, results: list[Class]) -> None:
        """Traverse to find type declarations"""
        if node.type == "type_declaration":
            classes = self._extract_type_declaration(node)
            if classes:
                results.extend(classes)

        for child in node.children:
            self._traverse_for_types(child, results)

    # Extract elements from AST: _extract_package
    def _extract_package(self, node: tree_sitter.Node) -> Package | None:
        """Extract package declaration"""
        from ._go_package import extract_go_package

        return extract_go_package(node, self._get_node_text)

    # Extract elements from AST: _extract_import_declaration
    def _extract_import_declaration(
        self, node: tree_sitter.Node
    ) -> list[Import] | None:
        """Extract import declaration (may contain multiple imports)"""
        imports = _extract_import_declaration(node, self._get_node_text)
        return imports if imports else None

    # Extract elements from AST: _extract_import_spec
    def _extract_import_spec(self, node: tree_sitter.Node) -> Import | None:
        """Extract single import spec"""
        return _extract_import_spec_standalone(node, self._get_node_text)

    # Extract elements from AST: _extract_function
    def _extract_function(self, node: tree_sitter.Node) -> Function | None:
        """Extract function declaration"""
        return _extract_func_standalone(node, self._get_node_text, self.content_lines)

    # Extract elements from AST: _extract_method
    def _extract_method(self, node: tree_sitter.Node) -> Function | None:
        """Extract method declaration (function with receiver)"""
        return _extract_method_standalone(node, self._get_node_text, self.content_lines)

    # Extract elements from AST: _extract_interface_methods
    def _extract_interface_methods(self, node: tree_sitter.Node) -> list[Function]:
        """Extract interface method signatures owned by the interface (#588)"""
        return _extract_iface_methods_standalone(
            node, self._get_node_text, self.content_lines
        )

    # Extract elements from AST: _extract_parameters
    def _extract_parameters(self, node: tree_sitter.Node) -> list[str]:
        """Extract function/method parameters"""
        return _extract_params_standalone(node, self._get_node_text)

    # Extract elements from AST: _extract_return_type
    def _extract_return_type(self, node: tree_sitter.Node) -> str:
        """Extract function/method return type"""
        return _extract_return_type_standalone(node, self._get_node_text)

    # Extract elements from AST: _extract_type_declaration
    def _extract_type_declaration(self, node: tree_sitter.Node) -> list[Class]:
        """Extract type declaration (struct, interface, type alias)"""
        return extract_type_declaration(node, self._get_node_text, self.content_lines)

    # Extract elements from AST: _extract_type_spec
    def _extract_type_spec(self, node: tree_sitter.Node) -> Class | None:
        """Extract single type spec"""
        return _extract_type_spec_standalone(
            node, self._get_node_text, self.content_lines
        )

    # Extract elements from AST: _extract_embedded_types
    def _extract_embedded_types(self, struct_node: tree_sitter.Node) -> list[str]:
        """Extract embedded types from struct"""
        return _extract_embedded_standalone(struct_node, self._get_node_text)

    # Extract elements from AST: _extract_const_declaration
    def _extract_const_declaration(
        self, node: tree_sitter.Node
    ) -> list[Variable] | None:
        """Extract const declaration"""
        return self._extract_var_or_const(node, is_const=True)

    # Extract elements from AST: _extract_var_declaration
    def _extract_var_declaration(self, node: tree_sitter.Node) -> list[Variable] | None:
        """Extract var declaration"""
        return self._extract_var_or_const(node, is_const=False)

    # Extract elements from AST: _extract_var_or_const
    def _extract_var_or_const(
        self, node: tree_sitter.Node, is_const: bool
    ) -> list[Variable] | None:
        """Extract var or const declaration"""
        result = extract_var_or_const(node, is_const, self._get_node_text)
        return result if result else None

    # Extract elements from AST: _extract_var_spec
    def _extract_var_spec(
        self, node: tree_sitter.Node, is_const: bool
    ) -> list[Variable]:
        """Extract single var/const spec"""
        return _extract_var_spec_standalone(node, is_const, self._get_node_text)

    # Extract elements from AST: _extract_struct_fields
    def _extract_struct_fields(self, node: tree_sitter.Node) -> list[Variable]:
        """Extract struct field declarations from a type_declaration node."""
        return _extract_struct_fields_standalone(node, self._get_node_text)

    # Extract elements from AST: _extract_goroutine
    def _extract_goroutine(self, node: tree_sitter.Node) -> None:
        """Extract goroutine invocation"""
        try:
            self.goroutines.append(
                {
                    "line": node.start_point[0] + 1,
                    "text": self._get_node_text(node),
                }
            )
        except Exception as e:
            log_error(f"Error extracting goroutine: {e}")

    # Extract elements from AST: _extract_channel_operation
    def _extract_channel_operation(self, node: tree_sitter.Node, op_type: str) -> None:
        """Extract channel operation"""
        try:
            self.channels.append(
                {
                    "type": op_type,
                    "line": node.start_point[0] + 1,
                    "text": self._get_node_text(node),
                }
            )
        except Exception as e:
            log_error(f"Error extracting channel operation: {e}")

    # Extract elements from AST: _extract_defer
    def _extract_defer(self, node: tree_sitter.Node) -> None:
        """Extract defer statement"""
        try:
            self.defers.append(
                {
                    "line": node.start_point[0] + 1,
                    "text": self._get_node_text(node),
                }
            )
        except Exception as e:
            log_error(f"Error extracting defer: {e}")

    # Extract elements from AST: _extract_docstring
    def _extract_docstring(self, node: tree_sitter.Node) -> str | None:
        """Extract doc comments preceding the node"""
        return _extract_docstring_standalone(node, self.content_lines)

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


class GoPlugin(LanguagePlugin):
    """Go language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Go language plugin."""
        super().__init__()
        self.extractor = GoElementExtractor()
        self.language = "go"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "go"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".go"]

    # Extract elements from AST: create_extractor
    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return GoElementExtractor()

    def get_supported_element_types(self) -> list[str]:
        """Get supported element types for Go."""
        return [
            "package",
            "import",
            "function",
            "method",
            "struct",
            "interface",
            "type_alias",
            "const",
            "var",
            "goroutine",
            "channel",
        ]

    def get_queries(self) -> dict[str, str]:
        """Get Go-specific tree-sitter queries."""
        from ..queries.go import GO_QUERIES

        return GO_QUERIES

    # Analyze source code structure: analyze_file
    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze Go code and return structured results."""
        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            # Get tree-sitter language and parse
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="go",
                    line_count=len(file_content.splitlines()),
                    elements=[],
                    source_code=file_content,
                )

            import tree_sitter

            parser = tree_sitter.Parser()

            # Set language (handle different tree-sitter versions)
            if hasattr(parser, "set_language"):
                parser.set_language(language)
            elif hasattr(parser, "language"):
                parser.language = language
            else:
                parser = tree_sitter.Parser(language)

            tree = parser.parse(file_content.encode("utf-8"))

            # Extract elements
            extractor = self.create_extractor()
            all_elements: list[Any] = []
            all_elements.extend(extractor.extract_packages(tree, file_content))
            all_elements.extend(extractor.extract_imports(tree, file_content))
            all_elements.extend(extractor.extract_functions(tree, file_content))
            all_elements.extend(extractor.extract_classes(tree, file_content))
            all_elements.extend(extractor.extract_variables(tree, file_content))

            node_count = (
                self._count_tree_nodes(tree.root_node) if tree and tree.root_node else 0
            )

            result = AnalysisResult(
                file_path=file_path,
                language="go",
                line_count=len(file_content.splitlines()),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
            )

            if isinstance(extractor, GoElementExtractor):
                result.goroutines = extractor.goroutines
                result.channels = extractor.channels
                result.defers = extractor.defers

            return result

        except Exception as e:
            log_error(f"Error analyzing Go file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="go",
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
        """Get the tree-sitter language for Go."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_go

            caps_or_lang = tree_sitter_go.language()

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
            log_error(f"tree-sitter-go not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Go: {e}")
            return None

    # Extract elements from AST: extract_elements
    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements from Go source code."""
        if tree is None:
            return {
                "packages": [],
                "imports": [],
                "functions": [],
                "classes": [],
                "variables": [],
            }

        try:
            extractor = self.create_extractor()

            result = {
                "packages": extractor.extract_packages(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
            }

            return result

        except Exception as e:
            log_error(f"Error extracting Go elements: {e}")
            return {
                "packages": [],
                "imports": [],
                "functions": [],
                "classes": [],
                "variables": [],
            }
