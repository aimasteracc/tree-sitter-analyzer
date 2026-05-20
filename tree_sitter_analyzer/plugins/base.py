#!/usr/bin/env python3
"""
Plugin Base Classes

Defines the base interfaces for language plugins and element extractors.
All language plugins must inherit from these base classes.
"""

import logging
from abc import ABC, abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
)

from ..platform_compat.detector import PlatformInfo

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..models import Class as ModelClass
from ..models import CodeElement
from ..models import Function as ModelFunction
from ..models import Import as ModelImport
from ..models import Variable as ModelVariable
from ..utils import log_error
from ._base_traverse_mixin import DefaultTraverseMixin

logger = logging.getLogger(__name__)


class ElementExtractor(ABC):
    """
    Abstract base class for language-specific element extractors.

    Element extractors are responsible for parsing ASTs and extracting
    meaningful code elements like functions, classes, variables, etc.
    """

    def __init__(self) -> None:
        """Initialize the element extractor."""
        self.current_file: str = ""  # Current file being processed
        self.platform_info: PlatformInfo | None = None

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

    def extract_packages(self, tree: "tree_sitter.Tree", source_code: str) -> list[Any]:
        """
        Extract package declarations from the syntax tree.

        Args:
            tree: Tree-sitter AST
            source_code: Original source code

        Returns:
            List of extracted package objects
        """
        # Default implementation returns empty list
        return []

    def extract_annotations(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Any]:
        """
        Extract annotations from the syntax tree.

        Args:
            tree: Tree-sitter AST
            source_code: Original source code

        Returns:
            List of extracted annotation objects
        """
        # Default implementation returns empty list
        return []

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
            elements.extend(self.extract_packages(tree, source_code))
        except Exception as e:
            log_error(f"Failed to extract all elements: {e}")

        return elements

    def extract_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> dict[str, list[Any]]:
        """
        Extract elements grouped by type.

        Returns:
            Dict with keys 'functions', 'classes', 'variables', 'imports'.
            Subclasses may add extra keys (e.g. 'packages', 'elements').
        """
        return {
            "functions": self.extract_functions(tree, source_code),
            "classes": self.extract_classes(tree, source_code),
            "variables": self.extract_variables(tree, source_code),
            "imports": self.extract_imports(tree, source_code),
        }

    def extract_html_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Any]:
        """
        Extract HTML elements from the syntax tree.

        Args:
            tree: Tree-sitter AST
            source_code: Original source code

        Returns:
            List of extracted HTML elements
        """
        # Default implementation returns empty list
        return []

    def extract_css_rules(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Any]:
        """
        Extract CSS rules from the syntax tree.

        Args:
            tree: Tree-sitter AST
            source_code: Original source code

        Returns:
            List of extracted CSS rules
        """
        # Default implementation returns empty list
        return []


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


class DefaultExtractor(DefaultTraverseMixin, ElementExtractor):
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
        root_node = self._tree_root_node(tree)
        if root_node is None:
            return functions

        try:
            self._traverse_for_functions(
                root_node, functions, source_code.splitlines(), source_code
            )
        except Exception as e:
            log_error(f"Error in function extraction: {e}")

        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelClass]:
        """Basic class extraction implementation."""
        classes: list[ModelClass] = []
        root_node = self._tree_root_node(tree)
        if root_node is None:
            return classes

        try:
            self._traverse_for_classes(
                root_node, classes, source_code.splitlines(), source_code
            )
        except Exception as e:
            log_error(f"Error in class extraction: {e}")

        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelVariable]:
        """Basic variable extraction implementation."""
        variables: list[ModelVariable] = []
        root_node = self._tree_root_node(tree)
        if root_node is None:
            return variables

        try:
            self._traverse_for_variables(
                root_node, variables, source_code.splitlines(), source_code
            )
        except Exception as e:
            log_error(f"Error in variable extraction: {e}")

        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelImport]:
        """Basic import extraction implementation."""
        imports: list[ModelImport] = []
        root_node = self._tree_root_node(tree)
        if root_node is None:
            return imports

        try:
            self._traverse_for_imports(
                root_node, imports, source_code.splitlines(), source_code
            )
        except Exception as e:
            log_error(f"Error in import extraction: {e}")

        return imports


class DefaultLanguagePlugin(LanguagePlugin):
    """Default plugin that provides basic functionality for any language."""

    def get_language_name(self) -> str:
        return "generic"

    def get_file_extensions(self) -> list[str]:
        return [".txt", ".md"]  # Fallback extensions

    # Extract elements from AST: create_extractor
    def create_extractor(self) -> ElementExtractor:
        return DefaultExtractor()

    # Analyze source code structure: analyze_file
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
            return await engine.analyze_file(file_path)  # type: ignore[no-any-return]
        except Exception as e:
            log_error(f"Failed to analyze file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                line_count=0,
                elements=[],
                error_message=str(e),
                success=False,
            )
