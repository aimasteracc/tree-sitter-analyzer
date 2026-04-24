"""typescript_plugin — composable mixin architecture."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.request import AnalysisRequest
    from ...models import AnalysisResult

import importlib.util

import tree_sitter

from ...language_loader import loader
from ...models import (
    AnalysisResult,
    CodeElement,
)
from ...plugins.base import ElementExtractor, LanguagePlugin
from ...utils import log_debug, log_error
from ._classes import ClassesMixin
from ._core import CoreMixin
from ._functions import FunctionsMixin
from ._imports import ImportsMixin
from ._types import TypesMixin
from ._variables import VariablesMixin

TREE_SITTER_AVAILABLE = importlib.util.find_spec("tree_sitter") is not None

__all__ = ['TypeScriptElementExtractor', 'TypeScriptPlugin']

class TypeScriptElementExtractor(
    ClassesMixin,
    FunctionsMixin,
    ImportsMixin,
    TypesMixin,
    VariablesMixin,
    CoreMixin,
):
    """Composed from mixins."""


class TypeScriptPlugin(LanguagePlugin):
    """Enhanced TypeScript language plugin with comprehensive feature support"""

    def __init__(self) -> None:
        self._extractor = TypeScriptElementExtractor()
        self._language: tree_sitter.Language | None = None

    @property
    def language_name(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> list[str]:
        return [".ts", ".tsx", ".d.ts"]

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "typescript"

    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return [".ts", ".tsx", ".d.ts"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return TypeScriptElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        return self._extractor

    def get_tree_sitter_language(self) -> tree_sitter.Language | None:
        """Load and return TypeScript tree-sitter language"""
        if not TREE_SITTER_AVAILABLE:
            return None
        if self._language is None:
            try:
                self._language = loader.load_language("typescript")
            except Exception as e:
                log_debug(f"Failed to load TypeScript language: {e}")
                return None
        return self._language

    def get_supported_queries(self) -> list[str]:
        """Get list of supported query names for this language"""
        return [
            "function",
            "class",
            "interface",
            "type_alias",
            "enum",
            "variable",
            "import",
            "export",
            "async_function",
            "arrow_function",
            "method",
            "constructor",
            "generic",
            "decorator",
            "signature",
            "react_component",
            "angular_component",
            "vue_component",
        ]

    def is_applicable(self, file_path: str) -> bool:
        """Check if this plugin is applicable for the given file"""
        return any(
            file_path.lower().endswith(ext.lower())
            for ext in self.get_file_extensions()
        )

    def get_plugin_info(self) -> dict[str, Any]:
        """Get information about this plugin"""
        return {
            "name": "TypeScript Plugin",
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "version": "2.0.0",
            "supported_queries": self.get_supported_queries(),
            "features": [
                "TypeScript syntax support",
                "Interface declarations",
                "Type aliases",
                "Enums",
                "Generics",
                "Decorators",
                "Async/await support",
                "Arrow functions",
                "Classes and methods",
                "Import/export statements",
                "TSX/JSX support",
                "React component detection",
                "Angular component detection",
                "Vue component detection",
                "Type annotations",
                "Method signatures",
                "TSDoc extraction",
                "Complexity analysis",
            ],
        }

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze a TypeScript file and return the analysis results."""
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
                error_message="Could not load TypeScript language for parsing.",
            )

        try:
            from ...encoding_utils import read_file_safe

            source_code, _ = read_file_safe(file_path)

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
            exports = extractor.extract_exports(tree, source_code)
            patterns = extractor.extract_patterns(tree, source_code)  # type: ignore[attr-defined]
            namespaces = extractor.extract_namespaces(tree, source_code)  # type: ignore[attr-defined]
            ambient_decls = extractor.extract_ambient_declarations(tree, source_code)  # type: ignore[attr-defined]

            elements.extend(functions)
            elements.extend(classes)
            elements.extend(variables)
            elements.extend(imports)
            elements.extend(exports)
            elements.extend(patterns)
            elements.extend(namespaces)
            elements.extend(ambient_decls)

            def count_nodes(node: tree_sitter.Node) -> int:
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
            log_error(f"Error analyzing TypeScript file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.language_name,
                success=False,
                error_message=str(e),
            )

    def extract_elements(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[CodeElement]:
        """Legacy method for backward compatibility with tests"""
        extractor = self.create_extractor()
        all_elements: list[CodeElement] = []

        # Extract all types of elements
        all_elements.extend(extractor.extract_functions(tree, source_code))
        all_elements.extend(extractor.extract_classes(tree, source_code))
        all_elements.extend(extractor.extract_variables(tree, source_code))
        all_elements.extend(extractor.extract_imports(tree, source_code))
        all_elements.extend(extractor.extract_exports(tree, source_code))
        all_elements.extend(extractor.extract_patterns(tree, source_code))  # type: ignore[attr-defined]
        all_elements.extend(extractor.extract_namespaces(tree, source_code))  # type: ignore[attr-defined]
        all_elements.extend(extractor.extract_ambient_declarations(tree, source_code))  # type: ignore[attr-defined]

        return all_elements

    def execute_query_strategy(
        self, query_key: str | None, language: str
    ) -> str | None:
        """Execute query strategy for TypeScript language"""
        queries = self.get_queries()
        return queries.get(query_key) if query_key else None

    def get_element_categories(self) -> dict[str, list[str]]:
        """Get TypeScript element categories mapping query_key to node_types"""
        return {
            # Function-related categories
            "function": [
                "function_declaration",
                "function_expression",
                "arrow_function",
                "generator_function_declaration",
            ],
            "async_function": [
                "function_declaration",
                "function_expression",
                "arrow_function",
                "method_definition",
            ],
            "arrow_function": ["arrow_function"],
            "method": ["method_definition", "method_signature"],
            "constructor": ["method_definition"],
            "signature": ["method_signature"],
            # Class-related categories
            "class": ["class_declaration", "abstract_class_declaration"],
            "interface": ["interface_declaration"],
            "type_alias": ["type_alias_declaration"],
            "enum": ["enum_declaration"],
            # Variable-related categories
            "variable": [
                "variable_declaration",
                "lexical_declaration",
                "property_definition",
                "property_signature",
            ],
            # Import/Export categories
            "import": ["import_statement"],
            "export": ["export_statement", "export_declaration"],
            # TypeScript-specific categories
            "generic": ["type_parameters", "type_parameter"],
            "decorator": ["decorator", "decorator_call_expression"],
            # Framework-specific categories
            "react_component": [
                "class_declaration",
                "function_declaration",
                "arrow_function",
            ],
            "angular_component": ["class_declaration", "decorator"],
            "vue_component": ["class_declaration", "function_declaration"],
        }


