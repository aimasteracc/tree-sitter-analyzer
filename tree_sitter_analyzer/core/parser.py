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
from ..language_loader import get_loader, grammar_install_hint, is_grammar_installed

# Configure logging
logger = logging.getLogger(__name__)


def _collect_error_nodes(node: Any, errors: list[dict[str, Any]]) -> None:
    """Recursively walk a tree-sitter node, appending ERROR nodes to ``errors``.

    r37ax: extracted from ``get_parse_errors`` to drop nesting depth from
    8 to 4. The previous version inlined dict construction, a ternary for
    ``text`` decode, and the recursive walk all inside ``get_parse_errors``.
    """
    if hasattr(node, "type") and node.type == "ERROR":
        errors.append(_error_node_payload(node))
    if hasattr(node, "children"):
        for child in node.children:
            _collect_error_nodes(child, errors)


def _error_node_payload(node: Any) -> dict[str, Any]:
    """Build the canonical ``{type, start_point, end_point, text}`` dict."""
    text = ""
    if node.text:
        text = node.text.decode("utf-8", errors="replace")
    return {
        "type": "ERROR",
        "start_point": node.start_point,
        "end_point": node.end_point,
        "text": text,
    }


def _failed_parse(language: str, file_path: str, error_message: str) -> "ParseResult":
    """Return a ParseResult representing a failed parse — keeps callers terse.

    r37ax (dogfood): five identical 7-line ParseResult literals appeared
    inside parse_file's exception handlers. Consolidating them dropped the
    method from 113 lines to ~30 and let the function body read as a
    linear pipeline. Forward reference to ``ParseResult`` is fine because
    the function is only called at runtime, after the class is defined.
    """
    return ParseResult(
        tree=None,
        source_code="",
        language=language,
        file_path=file_path,
        success=False,
        error_message=error_message,
    )


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
    # 记录文件属性与内容键；属性只用于命中统计，不能绕过源码读取。
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

    @classmethod
    def invalidate_stat_cache(cls) -> None:
        """清理属性命中记录，保留已按实际解析内容寻址的 AST 缓存。"""
        cls._stat_cache.clear()

    def parse_file(self, file_path: str | Path, language: str) -> ParseResult:
        """读取当前源码，以同一文本查缓存或解析，避免属性键误命中。"""
        file_path_str = str(file_path)
        path_obj = Path(file_path_str)
        if not path_obj.exists():
            return _failed_parse(
                language, file_path_str, f"File not found: {file_path_str}"
            )

        try:
            read_outcome = self._read_source_code(path_obj, language)
            if isinstance(read_outcome, ParseResult):
                return read_outcome
            source_code = read_outcome
            cache_key, cached = self._cache_lookup(file_path_str, language, source_code)
            if cached is not None:
                return cached

            result = self.parse_code(source_code, language, filename=file_path_str)
            if result.success and cache_key:
                Parser._cache[cache_key] = result
            return result

        except Exception as e:
            err_str = str(e)
            logger.error(f"Unexpected error parsing file {file_path_str}: {e}")
            return _failed_parse(
                language, file_path_str, f"Unexpected error: {err_str}"
            )

    def _cache_lookup(
        self, file_path_str: str, language: str, source_code: str
    ) -> tuple[str | None, ParseResult | None]:
        """用同一次读取的源码查找 AST；文件属性不可替代内容身份。"""
        try:
            stat = os.stat(file_path_str)
            mtime_ns = int(stat.st_mtime_ns)
            size = int(stat.st_size)
        except (OSError, TypeError) as e:
            logger.debug(f"Could not check parser cache for {file_path_str}: {e}")
            return (None, None)

        cache_key = self._lookup_or_record_stat_key(
            file_path_str, mtime_ns, size, language, source_code
        )
        cached = Parser._cache.get(cache_key)
        if cached is not None:
            Parser._hits += 1
            logger.debug(f"Parser cache hit for {file_path_str}")
            return (cache_key, cached)
        Parser._misses += 1
        return (cache_key, None)

    def _lookup_or_record_stat_key(
        self,
        file_path_str: str,
        mtime_ns: int,
        size: int,
        language: str,
        source_code: str,
    ) -> str:
        """内容键绑定实际解析文本，属性一致仅增加兼容诊断计数。"""
        identity = f"{file_path_str}\0{language}\0{source_code}"
        cache_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        stat_entry = Parser._stat_cache.get(file_path_str)
        if (
            stat_entry is not None
            and stat_entry[0] == mtime_ns
            and stat_entry[1] == size
            and stat_entry[2] == language
            and stat_entry[3] == cache_key
        ):
            Parser._stat_hits += 1

        Parser._stat_cache[file_path_str] = (mtime_ns, size, language, cache_key)
        return cache_key

    def _read_source_code(self, path_obj: Path, language: str) -> str | ParseResult:
        """Read the file via the encoding manager, returning either source or a failed ParseResult."""
        file_path_str = str(path_obj)
        try:
            source_code, detected_encoding = self._encoding_manager.read_file_safe(
                path_obj
            )
            logger.debug(f"Read file {file_path_str} with encoding {detected_encoding}")
            return source_code
        except PermissionError as e:
            err_str = str(e)
            return _failed_parse(
                language, file_path_str, f"Permission denied: {err_str}"
            )
        except Exception as e:
            err_str = str(e)
            return _failed_parse(
                language, file_path_str, f"Error reading file: {err_str}"
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
                hint = grammar_install_hint(language)
                if hint and not is_grammar_installed(language):
                    err_msg = hint
                else:
                    err_msg = f"Unsupported language: {language}"
                return ParseResult(
                    tree=None,
                    source_code=source_code,
                    language=language,
                    file_path=filename,
                    success=False,
                    error_message=err_msg,
                )

            # Create parser for the language
            parser = self._loader.create_parser_safely(language)
            if parser is None:
                err_msg = f"Failed to create parser for language: {language}"
                return ParseResult(
                    tree=None,
                    source_code=source_code,
                    language=language,
                    file_path=filename,
                    success=False,
                    error_message=err_msg,
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
            err_msg = str(e)
            return ParseResult(
                tree=None,
                source_code=source_code,
                language=language,
                file_path=filename,
                success=False,
                error_message=f"Parsing error: {err_msg}",
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
        errors: list[dict[str, Any]] = []
        try:
            if tree and tree.root_node:
                _collect_error_nodes(tree.root_node, errors)
        except Exception as e:
            logger.error(f"Error extracting parse errors: {e}")
        return errors


# Module-level loader for backward compatibility
loader = get_loader()

loader = get_loader()
