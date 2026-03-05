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
from ..exceptions import FileHandlingError
from ..language_loader import get_loader

# Configure logging
logger = logging.getLogger(__name__)


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

    # Class-level cache to share across all Parser instances
    _cache: LRUCache = LRUCache(maxsize=100)

    # Default maximum file size: 10MB
    DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024

    def __init__(self, max_file_size: int | None = None) -> None:
        """
        Initialize the Parser with language loader.

        Args:
            max_file_size: Maximum file size in bytes to parse.
                          Defaults to 10MB. Set to 0 or negative to disable.
        """
        self._loader = get_loader()
        self._encoding_manager = EncodingManager()
        self._max_file_size = (
            max_file_size if max_file_size is not None else self.DEFAULT_MAX_FILE_SIZE
        )
        logger.info("Parser initialized successfully")

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

            # Get file stats for size check and caching
            try:
                stat = os.stat(file_path_str)
            except OSError as e:
                return ParseResult(
                    tree=None,
                    source_code="",
                    language=language,
                    file_path=file_path_str,
                    success=False,
                    error_message=f"Could not access file stats: {str(e)}",
                )

            # Check file size limit before processing
            if self._max_file_size > 0 and stat.st_size > self._max_file_size:
                raise FileHandlingError(
                    f"File size ({stat.st_size} bytes) exceeds maximum allowed "
                    f"size ({self._max_file_size} bytes)",
                    file_path=file_path_str,
                    operation="parse_file",
                )

            # Check cache first using file metadata for versioning
            cache_key = None
            try:
                # Key: path + mtime + size + language
                key_string = (
                    f"{file_path_str}:{stat.st_mtime}:{stat.st_size}:{language}"
                )
                cache_key = hashlib.sha256(key_string.encode("utf-8")).hexdigest()

                cached = Parser._cache.get(cache_key)
                if cached:
                    logger.debug(f"Parser cache hit for {file_path_str}")
                    return cached  # type: ignore[no-any-return]
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

        except FileHandlingError:
            # Re-raise file handling errors (like file size limit)
            raise
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

        Uses iterative traversal to avoid stack overflow on deeply nested code.

        Args:
            tree: Tree-sitter tree to check for errors

        Returns:
            List of error information dictionaries
        """
        errors = []

        try:
            if not tree or not tree.root_node:
                return errors  # Defensive: tree may be None or empty

            # Iterative traversal using a stack to avoid recursion depth issues
            stack = [tree.root_node]

            while stack:
                node = stack.pop()
                if node is None:
                    continue  # Defensive: node may be None from malformed trees

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

                # Add children to stack (reversed to maintain left-to-right order)
                if hasattr(node, "children"):
                    for child in reversed(node.children):
                        stack.append(child)

        except Exception as e:
            logger.error(f"Error extracting parse errors: {e}")

        return errors


# Module-level loader for backward compatibility
loader = get_loader()

loader = get_loader()
