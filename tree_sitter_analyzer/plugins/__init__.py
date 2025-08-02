#!/usr/bin/env python3
"""
Plugin System for Multi-Language Code Analysis

This package provides a plugin-based architecture for extending
the tree-sitter analyzer with language-specific parsers and extractors.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

# from ..models import (
#     CodeElement,
# )  # Not used currently
from ..models import Class as ModelClass
from ..models import Function as ModelFunction
from ..models import Import as ModelImport
from ..models import Variable as ModelVariable
from ..utils import log_debug, log_error, log_warning

__all__ = [
    "LanguagePlugin",
    "ElementExtractor",
    "DefaultExtractor",
    "DefaultLanguagePlugin",
]


class ElementExtractor(ABC):
    """Abstract base class for language-specific element extractors"""

    @abstractmethod
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelFunction]:
        """Extract function definitions from the syntax tree"""
        log_warning("extract_functions not implemented in subclass")
        return []

    @abstractmethod
    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelClass]:
        """Extract class definitions from the syntax tree"""
        log_warning("extract_classes not implemented in subclass")
        return []

    @abstractmethod
    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelVariable]:
        """Extract variable declarations from the syntax tree"""
        log_warning("extract_variables not implemented in subclass")
        return []

    @abstractmethod
    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelImport]:
        """Extract import statements from the syntax tree"""
        log_warning("extract_imports not implemented in subclass")
        return []


class LanguagePlugin(ABC):
    """Abstract base class for language-specific plugins"""

    @abstractmethod
    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "unknown"

    @abstractmethod
    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return []

    @abstractmethod
    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return DefaultExtractor()

    def is_applicable(self, file_path: str) -> bool:
        """Check if this plugin is applicable for the given file"""
        extensions = self.get_file_extensions()
        return any(file_path.lower().endswith(ext.lower()) for ext in extensions)


class DefaultExtractor(ElementExtractor):
    """Default implementation of ElementExtractor with basic functionality"""

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelFunction]:
        """Basic function extraction implementation"""
        functions: list[ModelFunction] = []
        try:
            if hasattr(tree, "root_node"):
                # Generic function extraction logic
                self._traverse_for_functions(
                    tree.root_node, functions, source_code.splitlines()
                )
        except Exception as e:
            log_error(f"Error in function extraction: {e}")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelClass]:
        """Basic class extraction implementation"""
        classes: list[ModelClass] = []
        try:
            if hasattr(tree, "root_node"):
                # Generic class extraction logic
                self._traverse_for_classes(
                    tree.root_node, classes, source_code.splitlines()
                )
        except Exception as e:
            log_error(f"Error in class extraction: {e}")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelVariable]:
        """Basic variable extraction implementation"""
        variables: list[ModelVariable] = []
        try:
            if hasattr(tree, "root_node"):
                # Generic variable extraction logic
                self._traverse_for_variables(
                    tree.root_node, variables, source_code.splitlines()
                )
        except Exception as e:
            log_error(f"Error in variable extraction: {e}")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelImport]:
        """Basic import extraction implementation"""
        imports: list[ModelImport] = []
        try:
            if hasattr(tree, "root_node"):
                # Generic import extraction logic
                self._traverse_for_imports(
                    tree.root_node, imports, source_code.splitlines()
                )
        except Exception as e:
            log_error(f"Error in import extraction: {e}")
        return imports

    def _traverse_for_functions(
        self, node: "tree_sitter.Node", functions: list[ModelFunction], lines: list[str]
    ) -> None:
        """Traverse tree to find function-like nodes"""
        if hasattr(node, "type") and "function" in node.type.lower():
            try:
                func = ModelFunction(
                    name=self._extract_node_name(node) or "unknown",
                    start_line=(
                        node.start_point[0] + 1 if hasattr(node, "start_point") else 0
                    ),
                    end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                    raw_text="",
                    language="unknown",
                )
                functions.append(func)
            except Exception as e:
                log_debug(f"Failed to extract function: {e}")

        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_functions(child, functions, lines)

    def _traverse_for_classes(
        self, node: "tree_sitter.Node", classes: list[ModelClass], lines: list[str]
    ) -> None:
        """Traverse tree to find class-like nodes"""
        if hasattr(node, "type") and "class" in node.type.lower():
            try:
                cls = ModelClass(
                    name=self._extract_node_name(node) or "unknown",
                    start_line=(
                        node.start_point[0] + 1 if hasattr(node, "start_point") else 0
                    ),
                    end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                    raw_text="",
                    language="unknown",
                )
                classes.append(cls)
            except Exception as e:
                log_debug(f"Failed to extract class: {e}")

        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_classes(child, classes, lines)

    def _traverse_for_variables(
        self, node: "tree_sitter.Node", variables: list[ModelVariable], lines: list[str]
    ) -> None:
        """Traverse tree to find variable declarations"""
        if hasattr(node, "type") and (
            "variable" in node.type.lower() or "declaration" in node.type.lower()
        ):
            try:
                var = ModelVariable(
                    name=self._extract_node_name(node) or "unknown",
                    start_line=(
                        node.start_point[0] + 1 if hasattr(node, "start_point") else 0
                    ),
                    end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                    raw_text="",
                    language="unknown",
                )
                variables.append(var)
            except Exception as e:
                log_debug(f"Failed to extract variable: {e}")

        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_variables(child, variables, lines)

    def _traverse_for_imports(
        self, node: "tree_sitter.Node", imports: list[ModelImport], lines: list[str]
    ) -> None:
        """Traverse tree to find import statements"""
        if hasattr(node, "type") and "import" in node.type.lower():
            try:
                imp = ModelImport(
                    name=self._extract_node_name(node) or "unknown",
                    start_line=(
                        node.start_point[0] + 1 if hasattr(node, "start_point") else 0
                    ),
                    end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                    raw_text="",
                    language="unknown",
                )
                imports.append(imp)
            except Exception as e:
                log_debug(f"Failed to extract import: {e}")

        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_imports(child, imports, lines)

    def _extract_node_name(self, node: "tree_sitter.Node") -> str | None:
        """Extract name from a tree-sitter node"""
        try:
            # Look for identifier children
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type") and child.type == "identifier":
                        # This would need actual text extraction in real implementation
                        return f"element_{child.start_point[0]}_{child.start_point[1]}"
            return None
        except Exception:
            return None


# Legacy PluginRegistry removed - now using PluginManager from .manager


class DefaultLanguagePlugin(LanguagePlugin):
    """Default plugin that provides basic functionality for any language"""

    def get_language_name(self) -> str:
        return "generic"

    def get_file_extensions(self) -> list[str]:
        return [".txt", ".md"]  # Fallback extensions

    def create_extractor(self) -> ElementExtractor:
        return DefaultExtractor()


# Legacy plugin registry removed - now using PluginManager
# from .manager import PluginManager
