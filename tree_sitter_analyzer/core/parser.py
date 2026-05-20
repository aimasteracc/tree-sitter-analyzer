#!/usr/bin/env python3
"""
Parser module for tree_sitter_analyzer.core.

This module provides the Parser class which handles Tree-sitter parsing
operations in the new architecture.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, NamedTuple

from cachetools import LRUCache
from tree_sitter import Tree

from ..encoding_utils import EncodingManager
from ..language_loader import get_loader

# Configure logging
logger = logging.getLogger(__name__)

# PERF-2: parser cache sizing
#   - LRU(100) was the original default, which thrashes on any project with
#     >100 source files (the analyzer's own repo has ~1280).
#   - Tree objects are tree-sitter C objects and cannot be pickled, so we
#     cannot persist them across processes — the cache stays in-memory only.
#   - The new default (2000) covers the common medium-project case
#     (Django/Flask app: ~3000 files, but only the actively-scanned subset
#     ends up in cache). Each cached entry holds a Tree (~10-50 KB) so the
#     memory ceiling is ~100 MB on the worst case — acceptable for an AI
#     analysis daemon, configurable via TSA_PARSER_CACHE_SIZE.
_PARSER_CACHE_SIZE = int(os.environ.get("TSA_PARSER_CACHE_SIZE", "2000"))


class ParseResult(NamedTuple):
    """
    Result of parsing operation containing tree and metadata.

    Attributes:
        tree: The parsed Tree-sitter tree (None if parsing failed)
        source_code: The source code that was parsed
        language: The programming language used for parsing
        file_path: Path to the file (if parsing from file)
        success: Whether parsing was successful
        error_message: Error message if parsing failed
    """

    tree: Tree | None
    source_code: str
    language: str
    file_path: str | None
    success: bool
    error_message: str | None


class Parser:
    """
    Tree-sitter parser wrapper for the new architecture.

    This class provides a unified interface for parsing code files and strings
    using Tree-sitter parsers with proper error handling and encoding support.
    """

    # Class-level cache shared across all Parser instances. Sized for medium
    # projects.
    _cache: LRUCache = LRUCache(maxsize=_PARSER_CACHE_SIZE)
    # Stat-only fast path: maps file_path → (mtime_ns, size, language,
    # cache_key) so a hot warm pass can skip the SHA-256 entirely when
    # mtime+size are unchanged. Falls back to the SHA-256 path on any miss.
    _stat_cache: dict[str, tuple[int, int, str, str]] = {}
    # Hit/miss counters — used by tests and by `cache_info()`.
    _hits = 0
    _misses = 0
    _stat_hits = 0

    def __init__(self) -> None:
        """Initialize the Parser with language loader."""
        self._loader = get_loader()
        self._encoding_manager = EncodingManager()
        logger.info("Parser initialized successfully")

    @classmethod
    def cache_info(cls) -> dict[str, Any]:
        """Return cache occupancy and hit/miss counters for diagnostics."""
        return {
            "size": len(cls._cache),
            "maxsize": cls._cache.maxsize,
            "hits": cls._hits,
            "misses": cls._misses,
            "stat_hits": cls._stat_hits,
            "stat_cache_size": len(cls._stat_cache),
        }

    @classmethod
    def cache_clear(cls) -> None:
        """Clear the parser cache. Used by tests and by tooling that knows
        files on disk have changed in ways the mtime-based fast path
        cannot detect."""
        cls._cache.clear()
        cls._stat_cache.clear()
        cls._hits = 0
        cls._misses = 0
        cls._stat_hits = 0

    def parse_file(self, file_path: str | Path, language: str) -> ParseResult:
        """
        Parse a source code file.

        Args:
            file_path: Path to the file to parse
            language: Programming language for parsing

        Returns:
            ParseResult containing the parsed tree and metadata
        """
        file_path_str = str(file_path)

        try:
            # Check if file exists
            path_obj = Path(file_path_str)
            if not path_obj.exists():
                return ParseResult(
                    tree=None,
                    source_code="",
                    language=language,
                    file_path=file_path_str,
                    success=False,
                    error_message=f"File not found: {file_path_str}",
                )

            # Check cache first using file metadata for versioning
            cache_key = None
            try:
                stat = os.stat(file_path_str)
                mtime_ns = int(stat.st_mtime_ns)
                size = int(stat.st_size)

                # Fast path: if we've seen this (path, mtime_ns, size, lang)
                # before, reuse the cache_key without re-hashing.
                stat_entry = Parser._stat_cache.get(file_path_str)
                if (
                    stat_entry is not None
                    and stat_entry[0] == mtime_ns
                    and stat_entry[1] == size
                    and stat_entry[2] == language
                ):
                    cache_key = stat_entry[3]
                    cached = Parser._cache.get(cache_key)
                    if cached is not None:
                        Parser._hits += 1
                        Parser._stat_hits += 1
                        return cached  # type: ignore[no-any-return]
                else:
                    key_string = f"{file_path_str}:{mtime_ns}:{size}:{language}"
                    cache_key = hashlib.sha256(key_string.encode("utf-8")).hexdigest()
                    Parser._stat_cache[file_path_str] = (
                        mtime_ns,
                        size,
                        language,
                        cache_key,
                    )

                cached = Parser._cache.get(cache_key)
                if cached is not None:
                    Parser._hits += 1
                    logger.debug(f"Parser cache hit for {file_path_str}")
                    return cached  # type: ignore[no-any-return]
                Parser._misses += 1
            except (OSError, TypeError) as e:
                logger.debug(f"Could not check parser cache for {file_path_str}: {e}")

            # Read file content with encoding detection
            try:
                source_code, detected_encoding = self._encoding_manager.read_file_safe(
                    path_obj
                )
                logger.debug(
                    f"Read file {file_path_str} with encoding {detected_encoding}"
                )
            except PermissionError as e:
                return ParseResult(
                    tree=None,
                    source_code="",
                    language=language,
                    file_path=file_path_str,
                    success=False,
                    error_message=f"Permission denied: {str(e)}",
                )
            except Exception as e:
                return ParseResult(
                    tree=None,
                    source_code="",
                    language=language,
                    file_path=file_path_str,
                    success=False,
                    error_message=f"Error reading file: {str(e)}",
                )

            # Parse the code
            result = self.parse_code(source_code, language, filename=file_path_str)

            # Save to cache if successful
            if result.success and cache_key:
                Parser._cache[cache_key] = result

            return result

        except Exception as e:
            logger.error(f"Unexpected error parsing file {file_path_str}: {e}")
            return ParseResult(
                tree=None,
                source_code="",
                language=language,
                file_path=file_path_str,
                success=False,
                error_message=f"Unexpected error: {str(e)}",
            )

    def parse_code(
        self, source_code: str, language: str, filename: str | None = None
    ) -> ParseResult:
        """
        Parse source code string.

        Args:
            source_code: The source code to parse
            language: Programming language for parsing
            filename: Optional filename for metadata

        Returns:
            ParseResult containing the parsed tree and metadata
        """
        try:
            # Check if language is supported
            if not self.is_language_supported(language):
                return ParseResult(
                    tree=None,
                    source_code=source_code,
                    language=language,
                    file_path=filename,
                    success=False,
                    error_message=f"Unsupported language: {language}",
                )

            # Create parser for the language
            parser = self._loader.create_parser_safely(language)
            if parser is None:
                return ParseResult(
                    tree=None,
                    source_code=source_code,
                    language=language,
                    file_path=filename,
                    success=False,
                    error_message=f"Failed to create parser for language: {language}",
                )

            # Parse the code
            source_bytes = self._encoding_manager.safe_encode(source_code)
            tree = parser.parse(source_bytes)

            logger.debug(f"Successfully parsed {language} code")
            return ParseResult(
                tree=tree,
                source_code=source_code,
                language=language,
                file_path=filename,
                success=True,
                error_message=None,
            )

        except Exception as e:
            # logger.error(f"Error parsing {language} code: {e}")
            return ParseResult(
                tree=None,
                source_code=source_code,
                language=language,
                file_path=filename,
                success=False,
                error_message=f"Parsing error: {str(e)}",
            )

    def is_language_supported(self, language: str) -> bool:
        """
        Check if a programming language is supported.

        Args:
            language: Programming language to check

        Returns:
            True if language is supported, False otherwise
        """
        try:
            return self._loader.is_language_available(language)
        except Exception as e:
            logger.error(f"Error checking language support for {language}: {e}")
            return False

    def get_supported_languages(self) -> list[str]:
        """
        Get list of supported programming languages.

        Returns:
            List of supported language names
        """
        try:
            return self._loader.get_supported_languages()
        except Exception as e:
            logger.error(f"Error getting supported languages: {e}")
            return []

    def validate_ast(self, tree: Tree | None) -> bool:
        """
        Validate an AST tree.

        Args:
            tree: Tree-sitter tree to validate

        Returns:
            True if tree is valid, False otherwise
        """
        if tree is None:
            return False

        try:
            # Basic validation - check if tree has a root node
            root_node = tree.root_node
            return root_node is not None
        except Exception as e:
            logger.error(f"Error validating AST: {e}")
            return False

    def get_parse_errors(self, tree: Tree) -> list[dict[str, Any]]:
        """
        Extract parse errors from a tree.

        Args:
            tree: Tree-sitter tree to check for errors

        Returns:
            List of error information dictionaries
        """
        errors = []

        try:

            def find_error_nodes(node: Any) -> None:
                """Recursively find error nodes in the tree."""
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
                        find_error_nodes(child)

            if tree and tree.root_node:
                find_error_nodes(tree.root_node)

        except Exception as e:
            logger.error(f"Error extracting parse errors: {e}")

        return errors


# Module-level loader for backward compatibility
loader = get_loader()

loader = get_loader()
