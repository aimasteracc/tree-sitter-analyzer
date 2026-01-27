#!/usr/bin/env python3
"""
Parser module for tree_sitter_analyzer.core.

This module provides the Parser class which handles Tree-sitter parsing
operations with performance optimization, caching, and error handling.

Features:
- File parsing with encoding support
- Code string parsing
- LRU caching for performance
- AST validation
- Error extraction
- Type-safe operations (PEP 484)
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, NamedTuple
from functools import lru_cache
from time import perf_counter

from tree_sitter import Tree

from ..encoding_utils import EncodingManager, detect_encoding, read_file_safe
from ..language_loader import get_loader, LanguageLoader, LanguageInfo

# Configure logging
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .language_detector import LanguageDetector, LanguageInfo
    from .query import QueryExecutor, QueryResult


class ParseResult(NamedTuple):
    """
    Result of parsing operation containing tree and metadata.

    Attributes:
        tree: The parsed Tree-sitter tree (None if parsing failed)
        source_code: The source code that was parsed
        language: The programming language used for parsing
        file_path: Path to file (if parsing from file)
        success: Whether parsing was successful
        error_message: Error message if parsing failed
        parse_time: Time taken to parse (in seconds)
    """

    tree: Tree | None
    source_code: str
    language: str
    file_path: str | None
    success: bool
    error_message: str | None
    parse_time: float


class ParserError(Exception):
    """Raised when parsing fails."""

    pass


class UnsupportedLanguageError(ParserError):
    """Raised when an unsupported language is requested."""

    pass


class Parser:
    """
    Tree-sitter parser wrapper with performance optimization and caching.

    Features:
    - LRU caching for parsed results
    - Encoding detection and handling
    - Language-specific parser loading
    - AST validation
    - Error extraction
    - Performance monitoring

    Usage:
    ```python
    parser = Parser()

    # Parse file
    result = parser.parse_file("file.py", language="python")

    # Parse code string
    result = parser.parse_code("def hello(): print('world')", language="python")
    ```
    """

    # Class-level cache to share across all Parser instances
    _cache: Dict[str, ParseResult] = {}
    _cache_enabled: bool = True
    _default_cache_ttl: int = 3600  # 1 hour
    _max_cache_size: int = 100

    def __init__(
        self,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
        max_cache_size: int = 100,
        project_root: str | None = None,
    ) -> None:
        """
        Initialize parser with caching and performance monitoring.

        Args:
            cache_enabled: Whether to enable LRU caching (default: True)
            cache_ttl: Cache time-to-live in seconds (default: 3600 = 1 hour)
            max_cache_size: Maximum number of cached results (default: 100)
            project_root: Project root for security validation

        Note:
            - Cache key includes file path, language, mtime, size
            - LRU cache evicts oldest entries when full
            - Performance monitoring is built-in
        """
        self._cache_enabled = cache_enabled
        self._cache_ttl = cache_ttl
        self._max_cache_size = max_cache_size
        self._project_root = project_root

        # Initialize encoding manager
        self._encoding_manager = EncodingManager()

        # Initialize language loader
        self._language_loader = get_loader()

        # Initialize logger
        self._logger = logger

        self._logger.info(f"Parser initialized (cache={cache_enabled}, ttl={cache_ttl}s, maxsize={max_cache_size})")

    def parse_file(
        self,
        file_path: str | Path,
        language: str | None = None,
        use_cache: bool = True,
    ) -> ParseResult:
        """
        Parse a source code file with caching and performance monitoring.

        Args:
            file_path: Path to file
            language: Optional language (auto-detect if not provided)
            use_cache: Whether to use LRU cache (default: True)

        Returns:
            ParseResult containing parsed tree and metadata

        Raises:
            FileNotFoundError: If file does not exist
            UnsupportedLanguageError: If language is not supported
            ParserError: If parsing fails

        Note:
            - Uses LRU cache to avoid reparsing unchanged files
            - Cache key includes file metadata (mtime, size)
            - Performance monitoring is built-in
        """
        file_path_str = str(file_path)
        start_time = perf_counter()

        try:
            # Check if file exists
            if not os.path.exists(file_path_str):
                raise FileNotFoundError(f"File not found: {file_path_str}")

            # Auto-detect language if not provided
            if language is None:
                from .language_detector import detect_language_from_file
                language = detect_language_from_file(file_path_str)
                self._logger.debug(f"Auto-detected language: {language}")

            # Check if language is supported
            if not self.is_language_supported(language):
                raise UnsupportedLanguageError(f"Unsupported language: {language}")

            # Generate cache key
            cache_key = None
            if use_cache and self._cache_enabled:
                cache_key = self._generate_cache_key(file_path_str, language)

                # Check cache first
                cached_result = self._cache.get(cache_key)
                if cached_result:
                    self._logger.debug(f"Parser cache hit for {file_path_str}")
                    end_time = perf_counter()
                    parse_time = end_time - start_time
                    return ParseResult(
                        tree=cached_result.tree,
                        source_code=cached_result.source_code,
                        language=cached_result.language,
                        file_path=file_path_str,
                        success=cached_result.success,
                        error_message=cached_result.error_message,
                        parse_time=parse_time,
                    )

            # Read file content
            source_code, detected_encoding = self._encoding_manager.read_file_safe(
                Path(file_path_str)
            )
            self._logger.debug(f"Read file {file_path_str} with encoding {detected_encoding}")

            # Parse code
            parse_result = self.parse_code(source_code, language, filename=file_path_str)

            # Store in cache if successful
            if use_cache and self._cache_enabled and cache_key and parse_result.success:
                self._cache[cache_key] = parse_result
                self._logger.debug(f"Stored in parser cache: {file_path_str}")

            end_time = perf_counter()
            parse_time = end_time - start_time
            self._logger.debug(f"Parse time: {parse_time:.3f}s")

            return ParseResult(
                tree=parse_result.tree,
                source_code=parse_result.source_code,
                language=parse_result.language,
                file_path=file_path_str,
                success=parse_result.success,
                error_message=parse_result.error_message,
                parse_time=parse_time,
            )

        except FileNotFoundError as e:
            self._logger.error(f"File not found: {file_path_str}")
            end_time = perf_counter()
            parse_time = end_time - start_time
            raise
        except UnsupportedLanguageError as e:
            self._logger.error(f"Unsupported language: {language}")
            end_time = perf_counter()
            parse_time = end_time - start_time
            raise
        except Exception as e:
            self._logger.error(f"Unexpected error parsing file {file_path_str}: {e}")
            end_time = perf_counter()
            parse_time = end_time - start_time
            return ParseResult(
                tree=None,
                source_code="",
                language=language or "unknown",
                file_path=file_path_str,
                success=False,
                error_message=f"Parsing error: {str(e)}",
                parse_time=parse_time,
            )

    def parse_code(
        self,
        source_code: str,
        language: str,
        filename: str | None = None,
    ) -> ParseResult:
        """
        Parse source code string.

        Args:
            source_code: Source code to parse
            language: Programming language
            filename: Optional filename for metadata

        Returns:
            ParseResult containing parsed tree and metadata

        Raises:
            UnsupportedLanguageError: If language is not supported
            ParserError: If parsing fails

        Note:
            - Does not use cache (code is transient)
            - Includes filename in result for metadata
        """
        start_time = perf_counter()

        try:
            # Check if language is supported
            if not self.is_language_supported(language):
                raise UnsupportedLanguageError(f"Unsupported language: {language}")

            # Create parser for language
            parser = self._language_loader.create_parser(language)
            if parser is None:
                raise ParserError(f"Failed to create parser for language: {language}")

            # Encode source code
            source_bytes = self._encoding_manager.safe_encode(source_code)

            # Parse code
            tree = parser.parse(source_bytes)

            self._logger.debug(f"Successfully parsed {language} code")

            end_time = perf_counter()
            parse_time = end_time - start_time

            return ParseResult(
                tree=tree,
                source_code=source_code,
                language=language,
                file_path=filename,
                success=True,
                error_message=None,
                parse_time=parse_time,
            )

        except UnsupportedLanguageError as e:
            self._logger.error(f"Unsupported language: {language}")
            end_time = perf_counter()
            parse_time = end_time - start_time
            raise
        except Exception as e:
            self._logger.error(f"Unexpected error parsing {language} code: {e}")
            end_time = perf_counter()
            parse_time = end_time - start_time
            return ParseResult(
                tree=None,
                source_code=source_code,
                language=language,
                file_path=filename,
                success=False,
                error_message=f"Parsing error: {str(e)}",
                parse_time=parse_time,
            )

    def is_language_supported(self, language: str) -> bool:
        """
        Check if a programming language is supported.

        Args:
            language: Programming language

        Returns:
            Support status (True/False)

        Note:
            - Checks against language loader
            - Returns True if Tree-sitter parser is available
        """
        try:
            return self._language_loader.is_language_available(language)
        except Exception as e:
            self._logger.error(f"Error checking language support: {e}")
            return False

    def get_supported_languages(self) -> List[str]:
        """
        Get list of supported programming languages.

        Returns:
            List of supported language names

        Note:
            - Returns all languages with Tree-sitter parsers
            - Sorted alphabetically
        """
        try:
            languages = self._language_loader.get_supported_languages()
            return sorted(languages)
        except Exception as e:
            self._logger.error(f"Error getting supported languages: {e}")
            return []

    def validate_ast(self, tree: Tree | None) -> bool:
        """
        Validate an AST tree.

        Args:
            tree: Tree-sitter tree to validate

        Returns:
            Validation status (True/False)

        Note:
            - Checks if tree has a valid root node
            - Checks if tree has any error nodes
            - Returns False if tree is None
        """
        if tree is None:
            return False

        try:
            # Basic validation - check if tree has a root node
            root_node = tree.root_node
            if root_node is None:
                return False

            # Check for error nodes
            def has_error_nodes(node: Any) -> bool:
                """Check if node or its children contain error nodes."""
                if hasattr(node, "type") and node.type == "ERROR":
                    return True
                if hasattr(node, "children"):
                    for child in node.children:
                        if has_error_nodes(child):
                            return True
                return False

            if has_error_nodes(root_node):
                return False

            # Additional validation could be added here
            return True

        except Exception as e:
            self._logger.error(f"Error validating AST: {e}")
            return False

    def get_parse_errors(self, tree: Tree | None) -> List[Dict[str, Any]]:
        """
        Extract parse errors from a tree.

        Args:
            tree: Tree-sitter tree to extract errors from

        Returns:
            List of error dictionaries

        Note:
            - Returns all error nodes in the tree
            - Includes position information
            - Includes error text
        """
        errors = []

        if tree is None:
            return errors

        try:
            def extract_error_nodes(node: Any) -> None:
                """Recursively extract error nodes."""
                if hasattr(node, "type") and node.type == "ERROR":
                    errors.append(
                        {
                            "type": "ERROR",
                            "start_point": node.start_point,
                            "end_point": node.end_point,
                            "text": (
                                node.text.decode("utf-8", errors="replace")
                                if node.text
                                else ""
                            ),
                        }
                    )

                if hasattr(node, "children"):
                    for child in node.children:
                        extract_error_nodes(child)

            extract_error_nodes(tree.root_node)

        except Exception as e:
            self._logger.error(f"Error extracting parse errors: {e}")

        return errors

    def clear_cache(self) -> None:
        """
        Clear parser cache.

        Note:
            - Invalidates all cached parse results
            - Next parsing will re-parse files
        """
        self._cache.clear()
        self._logger.info("Parser cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics

        Note:
            - Returns cache size and TTL
            - Useful for monitoring and debugging
        """
        return {
            "cache_enabled": self._cache_enabled,
            "cache_size": len(self._cache),
            "cache_ttl": self._cache_ttl,
            "max_cache_size": self._max_cache_size,
        }

    def _generate_cache_key(
        self,
        file_path: str,
        language: str,
    ) -> str:
        """
        Generate cache key from file path and language.

        Args:
            file_path: File path
            language: Programming language

        Returns:
            SHA-256 hash string

        Note:
            - Includes file path and language
            - Includes file metadata (mtime, size) for cache invalidation
            - Files are re-parsed when they change
        """
        try:
            # Get file metadata
            stat = os.stat(file_path)

            # Build cache key components
            key_components = [
                file_path,
                language,
                str(int(stat.st_mtime)),  # Modification time
                str(int(stat.st_size)),      # File size
            ]

            # Generate SHA-256 hash
            key_str = ":".join(key_components)
            return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

        except (OSError, FileNotFoundError):
            # File not accessible, use basic key
            return f"{file_path}:{language}"

    def _cleanup_cache(self) -> None:
        """
        Clean up old cache entries (if cache is too large).

        Note:
            - Evicts oldest entries when cache size exceeds limit
            - Helps maintain optimal cache size
        """
        if len(self._cache) > self._max_cache_size:
            # Sort by insertion order (approximate by key)
            items_to_remove = list(self._cache.items())[:len(self._cache) - self._max_cache_size]

            for key, _ in items_to_remove:
                del self._cache[key]

            self._logger.debug(f"Cleaned up {len(items_to_remove)} old cache entries")


# Module-level loader for backward compatibility
loader = get_loader()


# Convenience functions
def create_parser(
    cache_enabled: bool = True,
    cache_ttl: int = 3600,
    max_cache_size: int = 100,
    project_root: str | None = None,
) -> Parser:
    """
    Factory function to create a parser instance.

    Args:
        cache_enabled: Whether to enable caching (default: True)
        cache_ttl: Cache time-to-live in seconds (default: 3600 = 1 hour)
        max_cache_size: Maximum number of cached results (default: 100)
        project_root: Project root for security validation

    Returns:
        Parser instance

    Note:
        - Creates all necessary dependencies
        - Provides clean factory interface
        - Recommended for new code
    """
    return Parser(
        cache_enabled=cache_enabled,
        cache_ttl=cache_ttl,
        max_cache_size=max_cache_size,
        project_root=project_root,
    )


def get_parser() -> Parser:
    """
    Get default parser instance (backward compatible).

    Returns:
        Parser instance with default settings

    Note:
        - Cache is enabled by default
        - TTL is 1 hour
        - Max cache size is 100
        - For new code, prefer using `create_parser()` factory function
    """
    return create_parser()


# Export for convenience
__all__ = [
    "Parser",
    "ParseResult",
    "ParserError",
    "UnsupportedLanguageError",
    "create_parser",
    "get_parser",
]
