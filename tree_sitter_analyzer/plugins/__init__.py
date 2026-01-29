#!/usr/bin/env python3
"""
Plugin System for Multi-Language Code Analysis

This package provides a plugin-based architecture for extending the
tree-sitter analyzer with language-specific parsers and extractors.

Features:
- Abstract base classes for extensibility
- Type-safe operations (PEP 484)
- Comprehensive error handling
- Performance optimization (caching, monitoring)
- Language-specific extractors
- Plugin management and discovery

Architecture:
- ElementExtractor: Base class for extracting code elements
- LanguagePlugin: Base class for language-specific plugins
- CachedElementExtractor: Cached version of extractors
- MarkupLanguageExtractor: Base for markup languages
- ProgrammingLanguageExtractor: Base for programming languages
- PluginManager: Manages plugin discovery and loading
"""

import logging
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, Type
from abc import ABC, abstractmethod
from functools import lru_cache, wraps
from time import perf_counter
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from tree_sitter import Tree, Node
    from ..models import (
        CodeElement,
        Function,
        Class as ModelClass,
        Import as ModelImport,
        Variable,
    )
    from ..utils import (
        log_debug,
        log_info,
        log_warning,
        log_error,
        log_performance,
    )

# Configure logging
logger = logging.getLogger(__name__)


class PluginType(Enum):
    """Plugin type enumeration."""

    PROGRAMMING = "programming"
    MARKUP = "markup"
    DATA = "data"


class PluginState(Enum):
    """Plugin state enumeration."""

    LOADED = "loaded"
    UNLOADED = "unloaded"
    ERROR = "error"


class PluginError(Exception):
    """Base exception for plugin-related errors."""

    pass


class PluginLoadError(PluginError):
    """Raised when a plugin fails to load."""

    pass


class PluginNotFoundError(PluginError):
    """Raised when a requested plugin is not found."""

    pass


class PluginExecutionError(PluginError):
    """Raised when a plugin fails to execute."""

    pass


@dataclass
class ExtractorResult:
    """
    Result of an extraction operation.

    Attributes:
        elements: List of extracted code elements
        extractor_name: Name of the extractor that performed the extraction
        execution_time: Time taken for extraction (seconds)
        success: Whether extraction was successful
        error_message: Error message if extraction failed
    """

    elements: List[CodeElement]
    extractor_name: str
    execution_time: float
    success: bool
    error_message: Optional[str] = None


@dataclass
class PluginInfo:
    """
    Information about a plugin.

    Attributes:
        name: Plugin name
        type: Plugin type (programming, markup, data)
        state: Plugin state (loaded, unloaded, error)
        version: Plugin version
        description: Plugin description
        language: Programming language this plugin supports
        file_extensions: List of file extensions this plugin supports
    """

    name: str
    type: PluginType
    state: PluginState
    version: Optional[str]
    description: str
    language: str
    file_extensions: List[str]


class ElementExtractor(ABC):
    """
    Abstract base class for language-specific element extractors.

    Subclasses must implement extraction methods for functions, classes,
    variables, and imports.

    Usage:
    ```python
    class MyExtractor(ElementExtractor):
        def extract_functions(self, tree, source_code):
            # Implementation
            return functions

        def extract_classes(self, tree, source_code):
            # Implementation
            return classes
    ```
    """

    @abstractmethod
    def extract_functions(
        self,
        tree: Tree,
        source_code: str,
    ) -> List[Function]:
        """
        Extract function definitions from the syntax tree.

        Args:
            tree: Tree-sitter syntax tree
            source_code: Source code (for context)

        Returns:
            List of Function objects

        Raises:
            PluginExecutionError: If extraction fails

        Note:
            - Implementation should be language-specific
            - Should extract function name, parameters, return type, etc.
        """
        pass

    @abstractmethod
    def extract_classes(
        self,
        tree: Tree,
        source_code: str,
    ) -> List[ModelClass]:
        """
        Extract class definitions from the syntax tree.

        Args:
            tree: Tree-sitter syntax tree
            source_code: Source code (for context)

        Returns:
            List of Class objects

        Raises:
            PluginExecutionError: If extraction fails

        Note:
            - Implementation should be language-specific
            - Should extract class name, methods, attributes, etc.
        """
        pass

    @abstractmethod
    def extract_variables(
        self,
        tree: Tree,
        source_code: str,
    ) -> List[Variable]:
        """
        Extract variable declarations from the syntax tree.

        Args:
            tree: Tree-sitter syntax tree
            source_code: Source code (for context)

        Returns:
            List of Variable objects

        Raises:
            PluginExecutionError: If extraction fails

        Note:
            - Implementation should be language-specific
            - Should extract variable name, type, initial value, etc.
        """
        pass

    @abstractmethod
    def extract_imports(
        self,
        tree: Tree,
        source_code: str,
    ) -> List[ModelImport]:
        """
        Extract import statements from the syntax tree.

        Args:
            tree: Tree-sitter syntax tree
            source_code: Source code (for context)

        Returns:
            List of Import objects

        Raises:
            PluginExecutionError: If extraction fails

        Note:
            - Implementation should be language-specific
            - Should extract module name, imported symbols, etc.
        """
        pass

    def extract_all(
        self,
        tree: Tree,
        source_code: str,
        language: str = "unknown",
    ) -> ExtractorResult:
        """
        Extract all elements (functions, classes, variables, imports).

        Args:
            tree: Tree-sitter syntax tree
            source_code: Source code (for context)
            language: Programming language (optional, for metadata)

        Returns:
            ExtractorResult with all elements and metadata

        Raises:
            PluginExecutionError: If extraction fails

        Note:
            - Extracts all elements in a single call
            - Provides performance monitoring
            - Includes error handling
        """
        start_time = perf_counter()
        self._language = language
        self._extractor_name = self.__class__.__name__

        try:
            # Extract all elements
            functions = self.extract_functions(tree, source_code)
            classes = self.extract_classes(tree, source_code)
            variables = self.extract_variables(tree, source_code)
            imports = self.extract_imports(tree, source_code)

            # Combine all elements
            all_elements = (
                functions + classes + variables + imports
            )

            end_time = perf_counter()
            execution_time = end_time - start_time

            log_performance(
                f"{self._extractor_name} extraction time: {execution_time:.3f}s, "
                f"{len(all_elements)} elements"
            )

            return ExtractorResult(
                elements=all_elements,
                extractor_name=self._extractor_name,
                execution_time=execution_time,
                success=True,
                error_message=None,
            )

        except Exception as e:
            end_time = perf_counter()
            execution_time = end_time - start_time

            log_error(f"Error in {self._extractor_name} extraction: {e}")

            return ExtractorResult(
                elements=[],
                extractor_name=self._extractor_name,
                execution_time=execution_time,
                success=False,
                error_message=f"Extraction failed: {str(e)}",
            )


class LanguagePlugin(ABC):
    """
    Abstract base class for language-specific plugins.

    Subclasses must implement language detection, parser creation,
    and file extension handling.

    Usage:
    ```python
    class MyLanguagePlugin(LanguagePlugin):
        def get_language_name(self):
            return "mylang"

        def get_file_extensions(self):
            return [".mylang", ".mylang2"]

        def create_parser(self):
            # Implementation
            return parser
    ```
    """

    @abstractmethod
    def get_language_name(self) -> str:
        """
        Get the name of the programming language.

        Returns:
            Language name (e.g., "python", "java", "javascript")

        Raises:
            PluginLoadError: If language name cannot be determined

        Note:
            - Should match Tree-sitter language names
            - Used for parser selection
        """
        pass

    @abstractmethod
    def get_file_extensions(self) -> List[str]:
        """
        Get list of file extensions supported by this plugin.

        Returns:
            List of file extensions (e.g., [".py", ".pyx", ".pyi"])

        Note:
            - Should include all extensions this language uses
            - Extensions should include the dot (e.g., ".py" not "py")
        """
        pass

    @abstractmethod
    def create_parser(self) -> Optional[Tree]:
        """
        Create a Tree-sitter parser for this language.

        Returns:
            Tree-sitter parser or None if creation fails

        Raises:
            PluginLoadError: If parser creation fails

        Note:
            - Returns None if parser cannot be created
            - Implementation should handle parser compilation
        """
        pass

    def create_extractor(self) -> Optional[ElementExtractor]:
        """
        Create an element extractor for this language.

        Returns:
            ElementExtractor or None if creation fails

        Note:
            - Returns None if extractor cannot be created
            - Implementation may return cached extractors
        """
        # Default implementation - to be overridden by subclasses
        try:
            # Try to import from current package
            from . import programming_language_extractor, markup_language_extractor

            # Check if this is a programming language
            if isinstance(self, programming_language_extractor.ProgrammingLanguageExtractor):
                return programming_language_extractor.ProgrammingLanguageExtractor()

            # Check if this is a markup language
            elif isinstance(self, markup_language_extractor.MarkupLanguageExtractor):
                return markup_language_extractor.MarkupLanguageExtractor()

            # Fallback to default
            else:
                return DefaultExtractor()

        except Exception as e:
            log_error(f"Error creating extractor for {self.get_language_name()}: {e}")
            return None

    def is_applicable(self, file_path: str) -> bool:
        """
        Check if this plugin is applicable for a given file.

        Args:
            file_path: Path to file

        Returns:
            True if this plugin can handle the file

        Note:
            - Checks file extension
            - Can also check file content
            - Used for automatic plugin selection
        """
        extensions = self.get_file_extensions()
        return any(file_path.lower().endswith(ext.lower()) for ext in extensions)


class DefaultExtractor(ElementExtractor):
    """
    Default implementation of ElementExtractor with basic functionality.

    Provides a fallback extractor for unsupported languages with
    basic functionality for testing and compatibility.
    """

    def __init__(self) -> None:
        """Initialize default extractor."""
        self._language = "unknown"
        self._extractor_name = "DefaultExtractor"

    def extract_functions(
        self,
        tree: Optional[Tree],
        source_code: str,
    ) -> List[Function]:
        """
        Extract functions using basic pattern matching.

        Args:
            tree: Tree-sitter syntax tree (may be None)
            source_code: Source code

        Returns:
            List of Function objects (empty for default implementation)
        """
        log_warning("DefaultExtractor does not support function extraction")
        return []

    def extract_classes(
        self,
        tree: Optional[Tree],
        source_code: str,
    ) -> List[ModelClass]:
        """
        Extract classes using basic pattern matching.

        Args:
            tree: Tree-sitter syntax tree (may be None)
            source_code: Source code

        Returns:
            List of Class objects (empty for default implementation)
        """
        log_warning("DefaultExtractor does not support class extraction")
        return []

    def extract_variables(
        self,
        tree: Optional[Tree],
        source_code: str,
    ) -> List[Variable]:
        """
        Extract variables using basic pattern matching.

        Args:
            tree: Tree-sitter syntax tree (may be None)
            source_code: Source code

        Returns:
            List of Variable objects (empty for default implementation)
        """
        log_warning("DefaultExtractor does not support variable extraction")
        return []

    def extract_imports(
        self,
        tree: Optional[Tree],
        source_code: str,
    ) -> List[ModelImport]:
        """
        Extract imports using basic pattern matching.

        Args:
            tree: Tree-sitter syntax tree (may be None)
            source_code: Source code

        Returns:
            List of Import objects (empty for default implementation)
        """
        log_warning("DefaultExtractor does not support import extraction")
        return []


class DefaultLanguagePlugin(LanguagePlugin):
    """
    Default implementation of LanguagePlugin with basic functionality.

    Provides a fallback language plugin for unsupported languages with
    basic functionality for testing and compatibility.
    """

    def __init__(self, language: str = "unknown") -> None:
        """Initialize default language plugin.

        Args:
            language: Language name (default: "unknown")
        """
        self._language = language

    def get_language_name(self) -> str:
        """
        Get the name of the programming language.

        Returns:
            Language name ("unknown" for default implementation)
        """
        return self._language

    def get_file_extensions(self) -> List[str]:
        """
        Get list of file extensions supported by this plugin.

        Returns:
            List of file extensions ([".txt"] for default implementation)
        """
        return [".txt", ".md"]

    def create_parser(self) -> Optional[Tree]:
        """
        Create a Tree-sitter parser for this language.

        Returns:
            Tree-sitter parser or None (for default implementation)
        """
        log_warning(f"DefaultLanguagePlugin does not support parser creation for {self._language}")
        return None

    def is_applicable(self, file_path: str) -> bool:
        """
        Check if this plugin is applicable for a given file.

        Args:
            file_path: Path to file

        Returns:
            True if this plugin can handle the file (always true for default)

        Note:
            - Default implementation accepts all files
            - Used as fallback when no specific plugin matches
        """
        return True


# Layered extractor support
# Import layered extractors for better performance
from .cached_element_extractor import CachedElementExtractor
from .programming_language_extractor import ProgrammingLanguageExtractor
from .markup_language_extractor import MarkupLanguageExtractor


# Export for backward compatibility
__all__ = [
    # Base classes
    "ElementExtractor",
    "LanguagePlugin",
    "DefaultExtractor",
    "DefaultLanguagePlugin",

    # Data classes
    "ExtractorResult",
    "PluginInfo",
    "PluginState",
    "PluginType",

    # Exceptions
    "PluginError",
    "PluginLoadError",
    "PluginNotFoundError",
    "PluginExecutionError",

    # Layered extractors
    "CachedElementExtractor",
    "ProgrammingLanguageExtractor",
    "MarkupLanguageExtractor",
]
