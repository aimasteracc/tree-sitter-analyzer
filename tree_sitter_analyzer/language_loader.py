#!/usr/bin/env python3
"""
Dynamic Language Loader

Handles loading of Tree-sitter language parsers with efficient caching
and lazy loading for optimal performance.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling
- LRU caching for language parsers
- Lazy loading for language modules
- Thread-safe operations
- Performance monitoring

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import importlib.util
import sys
from typing import TYPE_CHECKING, Optional, Dict, List, Any, Union, Tuple, Callable, Type
import functools
import threading
import time
from pathlib import Path

# Type checking setup
if TYPE_CHECKING:
    from tree_sitter import Language, Parser

    # Plugins
    from .plugins import ElementExtractor, LanguagePlugin

    # Utilities
    from .utils import (
        log_debug,
        log_info,
        log_warning,
        log_error,
        log_performance,
    )
else:
    # Runtime imports (when type checking is disabled)
    Language = Any
    Parser = Any
    ElementExtractor = Any
    LanguagePlugin = Any

# ============================================================================
# Type Definitions
# ============================================================================

if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    Protocol = object

class LanguageLoaderProtocol(Protocol):
    """Protocol for language loader creation functions."""

    def __call__(self, project_root: str) -> "LanguageLoader":
        """
        Create language loader instance.

        Args:
            project_root: Root directory of the project

        Returns:
            LanguageLoader instance
        """
        ...


# ============================================================================
# Custom Exceptions
# ============================================================================

class LanguageLoaderError(Exception):
    """Base exception for language loader errors."""

    pass


class LanguageNotAvailableError(LanguageLoaderError):
    """Exception raised when a language is not available."""

    pass


class LanguageLoadError(LanguageLoaderError):
    """Exception raised when a language fails to load."""

    pass


class ParserCreationError(LanguageLoaderError):
    """Exception raised when parser creation fails."""

    pass


# ============================================================================
# Language Loader Configuration
# ============================================================================

class LanguageLoaderConfig:
    """Configuration for language loader."""

    def __init__(
        self,
        enable_caching: bool = True,
        cache_max_size: int = 128,
        enable_lazy_loading: bool = True,
        enable_thread_safety: bool = True,
    ):
        """
        Initialize language loader configuration.

        Args:
            enable_caching: Enable LRU caching for language parsers
            cache_max_size: Maximum size of LRU cache
            enable_lazy_loading: Enable lazy loading for language modules
            enable_thread_safety: Enable thread-safe operations
        """
        self.enable_caching = enable_caching
        self.cache_max_size = cache_max_size
        self.enable_lazy_loading = enable_lazy_loading
        self.enable_thread_safety = enable_thread_safety


# ============================================================================
# Language Loader
# ============================================================================

class LanguageLoader:
    """
    Optimized language loader with enhanced caching, lazy loading, and thread safety.

    Features:
    - LRU caching for language parsers
    - Lazy loading for language modules
    - Thread-safe operations
    - Performance monitoring
    - Comprehensive error handling

    Usage:
        >>> loader = LanguageLoader()
        >>> parser = loader.create_parser("python")
        >>> result = parser.parse(source_code, "example.py")
    """

    # Language modules mapping
    LANGUAGE_MODULES: Dict[str, str] = {
        "python": "tree_sitter_python",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
        "tsx": "tree_sitter_typescript",
        "java": "tree_sitter_java",
        "c": "tree_sitter_c",
        "cpp": "tree_sitter_cpp",
        "rust": "tree_sitter_rust",
        "go": "tree_sitter_go",
        "markdown": "tree_sitter_markdown",
        "html": "tree_sitter_html",
        "css": "tree_sitter_css",
        "yaml": "tree_sitter_yaml",
        "sql": "tree_sitter_sql",
        "csharp": "tree_sitter_c_sharp",
        "cs": "tree_sitter_c_sharp",
        "php": "tree_sitter_php",
        "ruby": "tree_sitter_ruby",
        "kotlin": "tree_sitter_kotlin",
    }

    # TypeScript dialects
    TYPESCRIPT_DIALECTS = {
        "typescript": "typescript",
        "tsx": "tsx",
    }

    # Thread-safe lock for operations
    _lock: threading.RLock

    def __init__(self, config: Optional[LanguageLoaderConfig] = None):
        """
        Initialize language loader.

        Args:
            config: Optional configuration (uses defaults if None)
        """
        self.config = config or LanguageLoaderConfig()

        # Loaded language modules
        self._loaded_modules: Dict[str, Any] = {}

        # Parser cache (LRU)
        self._parser_cache: Dict[str, Parser] = {}

        # Language availability cache
        self._availability_cache: Dict[str, bool] = {}

        # Unavailable languages set (to avoid repeated checks)
        self._unavailable_languages: set = set()

    def is_language_available(self, language: str) -> bool:
        """
        Check if a language's tree-sitter library is available.

        Args:
            language: Language name to check

        Returns:
            True if available, False otherwise

        Performance:
            Uses caching to avoid repeated imports.
        """
        # Check unavailable languages first
        if language in self._unavailable_languages:
            return False

        # Check availability cache
        if language in self._availability_cache:
            return self._availability_cache[language]

        module_name = self.LANGUAGE_MODULES.get(language)
        if not module_name:
            self._availability_cache[language] = False
            self._unavailable_languages.add(language)
            return False

        # Try to import the language module
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                self._availability_cache[language] = False
                self._unavailable_languages.add(language)
                return False

            importlib.import_module(module_name)
            self._availability_cache[language] = True
            return True

        except ImportError:
            self._availability_cache[language] = False
            self._unavailable_languages.add(language)
            return False
        except Exception as e:
            log_warning(f"Failed to import language module {module_name}: {e}")
            self._availability_cache[language] = False
            self._unavailable_languages.add(language)
            return False

    def load_language_module(self, language: str) -> Any:
        """
        Load a language module with lazy loading and error handling.

        Args:
            language: Language name to load

        Returns:
            Loaded language module

        Raises:
            LanguageNotAvailableError: If language is not available
            LanguageLoadError: If language fails to load

        Performance:
            Uses module caching to avoid repeated imports.
        """
        # Check if language is available
        if not self.is_language_available(language):
            raise LanguageNotAvailableError(f"Language '{language}' is not available")

        module_name = self.LANGUAGE_MODULES.get(language)
        if not module_name:
            raise LanguageNotAvailableError(f"Unknown language: {language}")

        # Check if already loaded
        if module_name in self._loaded_modules:
            return self._loaded_modules[module_name]

        # Load the language module
        try:
            start_time = time.perf_counter()
            module = importlib.import_module(module_name)
            end_time = time.perf_counter()

            log_debug(
                f"Loaded language module {module_name} in {(end_time - start_time) * 1000:.2f}ms"
            )

            # Cache the module
            if self.config.enable_lazy_loading:
                self._loaded_modules[module_name] = module

            return module

        except ImportError as e:
            raise LanguageLoadError(f"Failed to import language module {module_name}: {e}")
        except Exception as e:
            raise LanguageLoadError(f"Failed to load language module {module_name}: {e}")

    def create_parser(
        self, language: str, project_root: Optional[str] = None
    ) -> Parser:
        """
        Create a parser for a specified language with caching and error handling.

        Args:
            language: Language name (e.g., 'python', 'java')
            project_root: Optional root directory for language-specific queries

        Returns:
            Tree-sitter Parser object

        Raises:
            LanguageNotAvailableError: If language is not available
            ParserCreationError: If parser creation fails

        Performance:
            Uses LRU caching to avoid repeated parser creation.
        """
        # Check if language is available
        if not self.is_language_available(language):
            raise LanguageNotAvailableError(f"Language '{language}' is not available")

        # Check parser cache
        if self.config.enable_caching and language in self._parser_cache:
            return self._parser_cache[language]

        # Load language module
        module = self.load_language_module(language)

        # Create parser with error handling
        try:
            start_time = time.perf_counter()

            # Handle TypeScript dialects
            if language in self.TYPESCRIPT_DIALECTS:
                dialect = self.TYPESCRIPT_DIALECTS[language]
                if hasattr(module, f"language_{dialect}"):
                    language_func = getattr(module, f"language_{dialect}")
                elif hasattr(module, "language"):
                    language_func = module.language
                else:
                    raise ParserCreationError(
                        f"Module {module.__name__} does not have language_{dialect} or language"
                    )
            else:
                if hasattr(module, "language"):
                    language_func = module.language
                else:
                    raise ParserCreationError(f"Module {module.__name__} does not have language")
        except Exception as e:
            raise ParserCreationError(f"Failed to create parser for {language}: {e}")

        # Create Tree-sitter Language object
        try:
            # Modern tree-sitter API: language_func() returns Language object directly
            caps_or_lang = language_func()

            # Modern tree-sitter API: Language object returned
            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
                tree_sitter_language = caps_or_lang
            else:
                # Legacy tree-sitter API: PyCapsule returned
                # Try to create Language object from PyCapsule
                log_debug(f"Using legacy API for {language}")
                try:
                    tree_sitter_language = Language(caps_or_lang)
                except Exception as e:
                    raise ParserCreationError(
                        f"Failed to create Language object for {language}: {e}"
                    )

            # Create parser
            try:
                parser = Parser()
            except Exception as e:
                raise ParserCreationError(f"Failed to create Parser for {language}: {e}")

            # Set language properly for modern API
            if hasattr(parser, "set_language"):
                parser.set_language(tree_sitter_language)
            elif hasattr(parser, "language"):
                parser.language = tree_sitter_language
            else:
                raise ParserCreationError(f"Parser does not have set_language or language")

            end_time = time.perf_counter()
            log_debug(
                f"Created parser for {language} in {(end_time - start_time) * 1000:.2f}ms"
            )

            # Cache the parser
            if self.config.enable_caching:
                if len(self._parser_cache) >= self.config.cache_max_size:
                    # Clear oldest entry (simple implementation)
                    oldest_key = next(iter(self._parser_cache))
                    del self._parser_cache[oldest_key]
                self._parser_cache[language] = parser

            return parser

        except Exception as e:
            raise ParserCreationError(f"Failed to create parser for {language}: {e}")

    def get_parser(
        self, language: str, project_root: Optional[str] = None
    ) -> Parser:
        """
        Get a parser for a specified language (alias for create_parser).

        Args:
            language: Language name (e.g., 'python', 'java')
            project_root: Optional root directory for language-specific queries

        Returns:
            Tree-sitter Parser object

        Raises:
            LanguageNotAvailableError: If language is not available
            ParserCreationError: If parser creation fails

        Performance:
            Uses LRU caching to avoid repeated parser creation.
        """
        return self.create_parser(language, project_root)

    def get_supported_languages(self) -> List[str]:
        """
        Get list of supported languages with availability checking.

        Returns:
            List of supported language names

        Performance:
            Uses availability caching to avoid repeated checks.
        """
        supported = []
        for lang in self.LANGUAGE_MODULES.keys():
            if self.is_language_available(lang):
                supported.append(lang)
        return sorted(supported)

    def get_available_languages(self) -> List[str]:
        """
        Get list of available languages (cached).

        Returns:
            List of available language names

        Performance:
            Returns cached list for performance.
        """
        return sorted(self._availability_cache.keys())

    def clear_cache(self) -> None:
        """Clear all caches (parser cache, module cache, availability cache)."""
        with self._lock if self.config.enable_thread_safety else type(None):
            self._parser_cache.clear()
            self._loaded_modules.clear()
            self._availability_cache.clear()
            self._unavailable_languages.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "parser_cache_size": len(self._parser_cache),
            "module_cache_size": len(self._loaded_modules),
            "availability_cache_size": len(self._availability_cache),
            "unavailable_languages_count": len(self._unavailable_languages),
            "config": {
                "enable_caching": self.config.enable_caching,
                "cache_max_size": self.config.cache_max_size,
                "enable_lazy_loading": self.config.enable_lazy_loading,
                "enable_thread_safety": self.config.enable_thread_safety,
            },
        }


# ============================================================================
# Convenience Functions with Caching
# ============================================================================

# Global language loader instance (singleton pattern)
_loader_instance: Optional[LanguageLoader] = None
_loader_lock: threading.RLock = threading.RLock()


@functools.lru_cache(maxsize=128, typed=True)
def get_language_loader(project_root: Optional[str] = None) -> LanguageLoader:
    """
    Get language loader instance (singleton with caching).

    Args:
        project_root: Optional root directory of the project

    Returns:
        LanguageLoader instance

    Performance:
        Uses LRU caching with maxsize=128 to reduce overhead.
    """
    global _loader_instance

    with _loader_lock:
        if _loader_instance is None:
            config = LanguageLoaderConfig(
                enable_caching=True,
                cache_max_size=128,
                enable_lazy_loading=True,
                enable_thread_safety=True,
            )
            _loader_instance = LanguageLoader(config=config)

        return _loader_instance


def create_parser(language: str, project_root: Optional[str] = None) -> Parser:
    """
    Create a parser for a specified language (convenience function).

    Args:
        language: Language name (e.g., 'python', 'java')
        project_root: Optional root directory for language-specific queries

    Returns:
        Tree-sitter Parser object

    Raises:
        LanguageNotAvailableError: If language is not available
        ParserCreationError: If parser creation fails

    Performance:
        Uses LRU-cached language loader and parser creation.
    """
    loader = get_language_loader()
    return loader.get_parser(language, project_root)


def get_parser_cached(language: str, project_root: Optional[str] = None) -> Parser:
    """
    Create a parser with LRU caching (alternative function).

    Args:
        language: Language name (e.g., 'python', 'java')
        project_root: Optional root directory for language-specific queries

    Returns:
        Tree-sitter Parser object

    Performance:
        Uses LRU caching with maxsize=128 to reduce overhead.
    """
    return create_parser(language, project_root)


def get_supported_languages() -> List[str]:
    """
    Get list of supported languages (convenience function).

    Returns:
        List of supported language names

    Performance:
        Returns cached list for performance.
    """
    loader = get_language_loader()
    return loader.get_supported_languages()


def check_language_availability(language: str) -> bool:
    """
    Check if a language is available (convenience function).

    Args:
        language: Language name to check

    Returns:
        True if available, False otherwise

    Performance:
        Uses availability caching to avoid repeated checks.
    """
    loader = get_language_loader()
    return loader.is_language_available(language)


# Module-level exports for backward compatibility
def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of the component to import

    Returns:
        Imported component or function

    Raises:
        ImportError: If component not found
    """
    # Handle legacy imports
    if name == "create_parser":
        return create_parser
    elif name == "get_parser":
        return create_parser
    elif name == "get_language_loader":
        return get_language_loader
    elif name == "create_parser_safely":
        return create_parser
    elif name == "get_parser_safely":
        return create_parser

    # Default behavior
    try:
        # Try to import from current package
        module = __import__(f".{name}", fromlist=["__name__"])
        return module
    except ImportError:
        raise ImportError(f"module {name} not found")
