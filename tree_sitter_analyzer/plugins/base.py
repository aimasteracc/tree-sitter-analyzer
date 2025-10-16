#!/usr/bin/env python3
"""
Plugin Base Classes

Defines the base interfaces for language plugins and element extractors.
All language plugins must inherit from these base classes.
"""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..models import Class as ModelClass
from ..models import CodeElement
from ..models import Function as ModelFunction
from ..models import Import as ModelImport
from ..models import Variable as ModelVariable
from ..utils import log_debug, log_error

logger = logging.getLogger(__name__)


class ElementExtractor(ABC):
    """
    Abstract base class for language-specific element extractors.

    Element extractors are responsible for parsing ASTs and extracting
    meaningful code elements like functions, classes, variables, etc.
    """

    @abstractmethod
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelFunction]:
        """
        Extract function definitions from the syntax tree.

        Args:
            tree: Tree-sitter AST
            source_code: Original source code

        Returns:
            List of extracted function objects
        """
        pass

    @abstractmethod
    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelClass]:
        """
        Extract class definitions from the syntax tree.

        Args:
            tree: Tree-sitter AST
            source_code: Original source code

        Returns:
            List of extracted class objects
        """
        pass

    @abstractmethod
    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelVariable]:
        """
        Extract variable declarations from the syntax tree.

        Args:
            tree: Tree-sitter AST
            source_code: Original source code

        Returns:
            List of extracted variable objects
        """
        pass

    @abstractmethod
    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelImport]:
        """
        Extract import statements from the syntax tree.

        Args:
            tree: Tree-sitter AST
            source_code: Original source code

        Returns:
            List of extracted import objects
        """
        pass

    def extract_all_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """
        Extract all code elements from the syntax tree.

        Args:
            tree: Tree-sitter AST
            source_code: Original source code

        Returns:
            List of all extracted code elements
        """
        elements: list[CodeElement] = []

        try:
            elements.extend(self.extract_functions(tree, source_code))
            elements.extend(self.extract_classes(tree, source_code))
            elements.extend(self.extract_variables(tree, source_code))
            elements.extend(self.extract_imports(tree, source_code))
        except Exception as e:
            log_error(f"Failed to extract all elements: {e}")

        return elements


class LanguagePlugin(ABC):
    """
    Abstract base class for language-specific plugins.

    Language plugins provide language-specific functionality including
    element extraction, file extension mapping, and language identification.
    """

    @abstractmethod
    def get_language_name(self) -> str:
        """
        Return the name of the programming language this plugin supports.

        Returns:
            Language name (e.g., "java", "python", "javascript")
        """
        pass

    @abstractmethod
    def get_file_extensions(self) -> list[str]:
        """
        Return list of file extensions this plugin supports.

        Returns:
            List of file extensions (e.g., [".java", ".class"])
        """
        pass

    @abstractmethod
    def create_extractor(self) -> ElementExtractor:
        """
        Create and return an element extractor for this language.

        Returns:
            ElementExtractor instance for this language
        """
        pass

    @abstractmethod
    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """
        Analyze a file and return analysis results.

        Args:
            file_path: Path to the file to analyze
            request: Analysis request with configuration

        Returns:
            AnalysisResult containing extracted information
        """
        pass

    def get_supported_element_types(self) -> list[str]:
        """
        Return list of supported CodeElement types.

        Returns:
            List of element types (e.g., ["function", "class", "variable"])
        """
        return ["function", "class", "variable", "import"]

    def get_queries(self) -> dict[str, str]:
        """
        Return language-specific tree-sitter queries.

        Returns:
            Dictionary mapping query names to query strings
        """
        return {}

    def execute_query_strategy(
        self, query_key: str | None, language: str
    ) -> str | None:
        """
        Execute query strategy for this language plugin.

        Args:
            query_key: Query key to execute
            language: Programming language

        Returns:
            Query string or None if not supported
        """
        queries = self.get_queries()
        return queries.get(query_key) if query_key else None

    def get_formatter_map(self) -> dict[str, str]:
        """
        Return mapping of format types to formatter class names.

        Returns:
            Dictionary mapping format names to formatter classes
        """
        return {}

    def get_element_categories(self) -> dict[str, list[str]]:
        """
        Return element categories for HTML/CSS languages.

        Returns:
            Dictionary mapping category names to element lists
        """
        return {}

    def is_applicable(self, file_path: str) -> bool:
        """
        Check if this plugin is applicable for the given file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if this plugin can handle the file
        """
        extensions = self.get_file_extensions()
        return any(file_path.lower().endswith(ext.lower()) for ext in extensions)

    def get_plugin_info(self) -> dict[str, Any]:
        """
        Get information about this plugin.

        Returns:
            Dictionary containing plugin information
        """
        return {
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "class_name": self.__class__.__name__,
            "module": self.__class__.__module__,
        }


class DefaultExtractor(ElementExtractor):
    """
    Default implementation of ElementExtractor with basic functionality.

    This extractor provides generic extraction logic that works across
    multiple languages by looking for common node types.
    """

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelFunction]:
        """Basic function extraction implementation."""
        functions: list[ModelFunction] = []

        try:
            if hasattr(tree, "root_node"):
                lines = source_code.splitlines()
                self._traverse_for_functions(
                    tree.root_node, functions, lines, source_code
                )
        except Exception as e:
            log_error(f"Error in function extraction: {e}")

        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelClass]:
        """Basic class extraction implementation."""
        classes: list[ModelClass] = []

        try:
            if hasattr(tree, "root_node"):
                lines = source_code.splitlines()
                self._traverse_for_classes(tree.root_node, classes, lines, source_code)
        except Exception as e:
            log_error(f"Error in class extraction: {e}")

        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelVariable]:
        """Basic variable extraction implementation."""
        variables: list[ModelVariable] = []

        try:
            if hasattr(tree, "root_node"):
                lines = source_code.splitlines()
                self._traverse_for_variables(
                    tree.root_node, variables, lines, source_code
                )
        except Exception as e:
            log_error(f"Error in variable extraction: {e}")

        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelImport]:
        """Basic import extraction implementation."""
        imports: list[ModelImport] = []

        try:
            if hasattr(tree, "root_node"):
                lines = source_code.splitlines()
                self._traverse_for_imports(tree.root_node, imports, lines, source_code)
        except Exception as e:
            log_error(f"Error in import extraction: {e}")

        return imports

    def _traverse_for_functions(
        self,
        node: "tree_sitter.Node",
        functions: list[ModelFunction],
        lines: list[str],
        source_code: str,
    ) -> None:
        """Traverse tree to find function-like nodes."""
        if hasattr(node, "type") and self._is_function_node(node.type):
            try:
                name = self._extract_node_name(node, source_code) or "unknown"
                raw_text = self._extract_node_text(node, source_code)

                func = ModelFunction(
                    name=name,
                    start_line=(
                        node.start_point[0] + 1 if hasattr(node, "start_point") else 0
                    ),
                    end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                    raw_text=raw_text,
                    language=self._get_language_hint(),
                )
                functions.append(func)
            except Exception as e:
                log_debug(f"Failed to extract function: {e}")

        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_functions(child, functions, lines, source_code)

    def _traverse_for_classes(
        self,
        node: "tree_sitter.Node",
        classes: list[ModelClass],
        lines: list[str],
        source_code: str,
    ) -> None:
        """Traverse tree to find class-like nodes."""
        if hasattr(node, "type") and self._is_class_node(node.type):
            try:
                name = self._extract_node_name(node, source_code) or "unknown"
                raw_text = self._extract_node_text(node, source_code)

                cls = ModelClass(
                    name=name,
                    start_line=(
                        node.start_point[0] + 1 if hasattr(node, "start_point") else 0
                    ),
                    end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                    raw_text=raw_text,
                    language=self._get_language_hint(),
                )
                classes.append(cls)
            except Exception as e:
                log_debug(f"Failed to extract class: {e}")

        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_classes(child, classes, lines, source_code)

    def _traverse_for_variables(
        self,
        node: "tree_sitter.Node",
        variables: list[ModelVariable],
        lines: list[str],
        source_code: str,
    ) -> None:
        """Traverse tree to find variable declarations."""
        if hasattr(node, "type") and self._is_variable_node(node.type):
            try:
                name = self._extract_node_name(node, source_code) or "unknown"
                raw_text = self._extract_node_text(node, source_code)

                var = ModelVariable(
                    name=name,
                    start_line=(
                        node.start_point[0] + 1 if hasattr(node, "start_point") else 0
                    ),
                    end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                    raw_text=raw_text,
                    language=self._get_language_hint(),
                )
                variables.append(var)
            except Exception as e:
                log_debug(f"Failed to extract variable: {e}")

        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_variables(child, variables, lines, source_code)

    def _traverse_for_imports(
        self,
        node: "tree_sitter.Node",
        imports: list[ModelImport],
        lines: list[str],
        source_code: str,
    ) -> None:
        """Traverse tree to find import statements."""
        if hasattr(node, "type") and self._is_import_node(node.type):
            try:
                name = self._extract_node_name(node, source_code) or "unknown"
                raw_text = self._extract_node_text(node, source_code)

                imp = ModelImport(
                    name=name,
                    start_line=(
                        node.start_point[0] + 1 if hasattr(node, "start_point") else 0
                    ),
                    end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                    raw_text=raw_text,
                    language=self._get_language_hint(),
                )
                imports.append(imp)
            except Exception as e:
                log_debug(f"Failed to extract import: {e}")

        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_imports(child, imports, lines, source_code)

    def _is_function_node(self, node_type: str) -> bool:
        """Check if a node type represents a function."""
        function_types = [
            "function_definition",
            "function_declaration",
            "method_definition",
            "function",
            "method",
            "procedure",
            "subroutine",
        ]
        return any(ftype in node_type.lower() for ftype in function_types)

    def _is_class_node(self, node_type: str) -> bool:
        """Check if a node type represents a class."""
        class_types = [
            "class_definition",
            "class_declaration",
            "interface_definition",
            "class",
            "interface",
            "struct",
            "enum",
        ]
        return any(ctype in node_type.lower() for ctype in class_types)

    def _is_variable_node(self, node_type: str) -> bool:
        """Check if a node type represents a variable."""
        variable_types = [
            "variable_declaration",
            "variable_definition",
            "field_declaration",
            "assignment",
            "declaration",
            "variable",
            "field",
        ]
        return any(vtype in node_type.lower() for vtype in variable_types)

    def _is_import_node(self, node_type: str) -> bool:
        """Check if a node type represents an import."""
        import_types = [
            "import_statement",
            "import_declaration",
            "include_statement",
            "import",
            "include",
            "require",
            "use",
        ]
        return any(itype in node_type.lower() for itype in import_types)

    def _extract_node_name(
        self, node: "tree_sitter.Node", source_code: str
    ) -> str | None:
        """Extract name from a tree-sitter node."""
        try:
            # Look for identifier children
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type") and child.type == "identifier":
                        return self._extract_node_text(child, source_code)

            # Fallback: use position-based name
            return f"element_{node.start_point[0]}_{node.start_point[1]}"
        except Exception:
            return None

    def _extract_node_text(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract text content from a tree-sitter node."""
        try:
            if hasattr(node, "start_byte") and hasattr(node, "end_byte"):
                source_bytes = source_code.encode("utf-8")
                node_bytes = source_bytes[node.start_byte : node.end_byte]
                return node_bytes.decode("utf-8", errors="replace")
            return ""
        except Exception as e:
            log_debug(f"Failed to extract node text: {e}")
            return ""

    def _get_language_hint(self) -> str:
        """Get a hint about the language being processed."""
        return "unknown"


class DefaultLanguagePlugin(LanguagePlugin):
    """Default plugin that provides basic functionality for any language."""

    def get_language_name(self) -> str:
        return "generic"

    def get_file_extensions(self) -> list[str]:
        return [".txt", ".md"]  # Fallback extensions

    def create_extractor(self) -> ElementExtractor:
        return DefaultExtractor()

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """
        Analyze a file using the default extractor.

        Args:
            file_path: Path to the file to analyze
            request: Analysis request with configuration

        Returns:
            AnalysisResult containing extracted information
        """
        from ..core.analysis_engine import UnifiedAnalysisEngine
        from ..models import AnalysisResult

        try:
            engine = UnifiedAnalysisEngine()
            return await engine.analyze_file(file_path)
        except Exception as e:
            log_error(f"Failed to analyze file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message=str(e),
            )
