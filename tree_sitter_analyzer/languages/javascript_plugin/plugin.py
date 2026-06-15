#!/usr/bin/env python3
"""JavaScript Language Plugin — wrapper class and query definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    import tree_sitter

    from ...core.analysis_engine import AnalysisRequest
    from ...models import AnalysisResult

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ...language_loader import loader
from ...models import AnalysisResult, CodeElement
from ...plugins.base import ElementExtractor, LanguagePlugin
from ...utils import log_error
from .extractor import JavaScriptElementExtractor

_JS_EXTENSIONS = [".js", ".mjs", ".jsx", ".es6", ".es", ".cjs"]


class JavaScriptPlugin(LanguagePlugin):
    """Enhanced JavaScript language plugin with comprehensive feature support"""

    def __init__(self) -> None:
        self._extractor = JavaScriptElementExtractor()
        self._language: tree_sitter.Language | None = None

        # Legacy compatibility attributes for tests
        self.language = "javascript"
        self.extractor = self._extractor
        self.supported_extensions = _JS_EXTENSIONS

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "javascript"

    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return _JS_EXTENSIONS

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return JavaScriptElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        return self._extractor

    def get_tree_sitter_language(self) -> tree_sitter.Language | None:
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
            "class_name": self.__class__.__name__,
            "module": self.__class__.__module__,
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
        self, query_key: str | None, language: str
    ) -> str | None:
        """Execute query strategy for JavaScript language"""
        queries = self.get_queries()
        return queries.get(query_key) if query_key else None

    def _get_node_type_for_element(self, element: Any) -> str:
        """Get appropriate node type for element"""
        from ...models import Class, Function, Import, Variable

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
            # Issue #891: field_definition covers class field declarations
            # (e.g. `name = 'x'`) which are distinct from var/let/const.
            "variable": [
                "variable_declaration",
                "lexical_declaration",
                "field_definition",
            ],
            "variables": [
                "variable_declaration",
                "lexical_declaration",
                "field_definition",
            ],
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
                language=self.get_language_name(),
                success=False,
                error_message="Tree-sitter library not available.",
            )

        language = self.get_tree_sitter_language()
        if not language:
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message="Could not load JavaScript language for parsing.",
            )

        try:
            from ...encoding_utils import read_file_safe_async

            # 1. Non-blocking I/O
            source_code, _ = await read_file_safe_async(file_path)

            # 2. Offload CPU-bound parsing and extraction to worker threads
            def _analyze_sync() -> tuple[list[CodeElement], int]:
                parser = tree_sitter.Parser()
                parser.language = language
                tree = parser.parse(bytes(source_code, "utf8"))

                extractor = self.create_extractor()
                extractor.current_file = file_path  # Set current file for context

                elements: list[CodeElement] = []

                # Extract all element types
                elements.extend(extractor.extract_functions(tree, source_code))
                elements.extend(extractor.extract_classes(tree, source_code))
                elements.extend(extractor.extract_variables(tree, source_code))
                elements.extend(extractor.extract_imports(tree, source_code))

                from ...utils.tree_sitter_compat import count_nodes_iterative

                node_count = 0
                if tree and tree.root_node:
                    node_count = count_nodes_iterative(tree.root_node)

                return elements, node_count

            elements, node_count = await anyio.to_thread.run_sync(_analyze_sync)

            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=True,
                elements=elements,
                line_count=len(source_code.splitlines()),
                node_count=node_count,
            )
        except Exception as e:
            log_error(f"Error analyzing JavaScript file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message=str(e),
            )

    def extract_elements(self, tree: tree_sitter.Tree, source_code: str) -> dict:
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

            extractor = self.extractor
            functions = extractor.extract_functions(tree, source_code)
            classes = extractor.extract_classes(tree, source_code)
            variables = extractor.extract_variables(tree, source_code)
            imports = extractor.extract_imports(tree, source_code)
            exports = extractor.extract_exports(tree, source_code)

            return {
                "functions": functions,
                "classes": classes,
                "variables": variables,
                "imports": imports,
                "exports": exports,
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
