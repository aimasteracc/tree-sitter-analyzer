#!/usr/bin/env python3
"""
Language Detection System

Automatically detects programming language from file extensions and content.
Supports multiple languages with extensible configuration and caching.

Features:
- Extension-based detection (fast)
- Content-based detection (accurate)
- Ambiguity resolution (smart)
- Caching for performance (LRU)
- Extensible configuration
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union
from functools import lru_cache
import re
import logging
import os

if TYPE_CHECKING:
    from .utils import log_debug, log_info, log_warning, log_error
    from .mcp.utils.shared_cache import get_shared_cache, CacheConfig

# Configure logging
logger = logging.getLogger(__name__)


class LanguageDetectionError(Exception):
    """Raised when language detection fails."""

    pass


class LanguageInfo:
    """
    Language information container.

    Attributes:
        name: Language name (e.g., "python")
        extensions: List of file extensions (e.g., [".py", ".pyx"])
        confidence: Detection confidence (0.0 to 1.0)
        supported: Whether Tree-sitter supports this language
    """

    def __init__(
        self,
        name: str,
        extensions: List[str],
        confidence: float = 1.0,
        supported: bool = True,
    ):
        """
        Initialize language information.

        Args:
            name: Language name
            extensions: List of file extensions
            confidence: Detection confidence (default: 1.0)
            supported: Whether Tree-sitter supports this language (default: True)
        """
        self.name = name
        self.extensions = extensions
        self.confidence = confidence
        self.supported = supported

    def __repr__(self) -> str:
        return f"LanguageInfo(name={self.name}, confidence={self.confidence}, supported={self.supported})"


class LanguageDetector:
    """
    Automatic programming language detector with caching and ambiguity resolution.

    Features:
    - Extension-based detection (fast, O(1))
    - Content-based detection (accurate, O(n))
    - Ambiguity resolution (smart, for .h, .m, etc.)
    - LRU caching for performance (avoid re-scanning)
    - Extensible configuration
    - Type-safe operations

    Usage:
    ```python
    detector = LanguageDetector()
    language, confidence = detector.detect_language("file.py")
    # language: "python", confidence: 0.95

    # Or use the global instance
    from language_detector import detector
    language, confidence = detector.detect_language("file.py")
    ```
    """

    # Basic extension mapping
    EXTENSION_MAPPING: Dict[str, Tuple[str, float]] = {
        # Java family
        ".java": ("java", 1.0),
        ".jsp": ("jsp", 0.9),
        ".jspx": ("jsp", 0.9),
        # JavaScript/TypeScript family
        ".js": ("javascript", 0.95),
        ".jsx": ("javascript", 0.8),
        ".ts": ("typescript", 0.95),
        ".tsx": ("typescript", 0.85),  # TSX is TS with JSX
        ".mjs": ("javascript", 0.9),
        ".cjs": ("javascript", 0.9),
        # Python family
        ".py": ("python", 1.0),
        ".pyx": ("python", 0.9),
        ".pyi": ("python", 0.9),
        ".pyw": ("python", 0.9),
        # C/C++ family
        ".c": ("c", 0.9),
        ".cpp": ("cpp", 0.95),
        ".cxx": ("cpp", 0.95),
        ".cc": ("cpp", 0.95),
        ".h": ("c", 0.5),  # Ambiguous
        ".hpp": ("cpp", 0.9),
        ".hxx": ("cpp", 0.9),
        # Other languages
        ".rs": ("rust", 1.0),
        ".go": ("go", 1.0),
        ".rb": ("ruby", 1.0),
        ".php": ("php", 1.0),
        ".kt": ("kotlin", 1.0),
        ".kts": ("kotlin", 0.9),
        ".swift": ("swift", 1.0),
        ".cs": ("csharp", 1.0),
        ".vb": ("vbnet", 1.0),
        ".fs": ("fsharp", 1.0),
        ".scala": ("scala", 1.0),
        ".clj": ("clojure", 1.0),
        ".hs": ("haskell", 1.0),
        ".ml": ("ocaml", 1.0),
        ".lua": ("lua", 1.0),
        ".pl": ("perl", 1.0),
        ".r": ("r", 1.0),
        ".m": ("objc", 0.7),  # Ambiguous (MATLAB as well)
        ".dart": ("dart", 1.0),
        ".elm": ("elm", 1.0),
        # Markup and data formats
        ".md": ("markdown", 0.95),
        ".markdown": ("markdown", 1.0),
        ".mdown": ("markdown", 0.9),
        ".mkd": ("markdown", 0.9),
        ".mkdn": ("markdown", 0.9),
        ".mdx": ("markdown", 0.9),  # MDX might be mixed with JSX
        ".html": ("html", 0.95),
        ".htm": ("html", 0.9),
        ".xhtml": ("html", 0.8),
        ".css": ("css", 0.95),
        ".scss": ("css", 0.9),
        ".sass": ("css", 0.9),
        ".less": ("css", 0.9),
        ".sql": ("sql", 0.9),
        ".json": ("json", 0.95),
        ".jsonc": ("json", 0.8),
        ".json5": ("json", 0.8),
        ".yaml": ("yaml", 0.95),
        ".yml": ("yaml", 0.9),
    }

    # Ambiguous extensions (map to multiple languages)
    AMBIGUOUS_EXTENSIONS: Dict[str, List[Tuple[str, float]]] = {
        ".h": [("c", 0.9), ("cpp", 0.8), ("objc", 0.7)],
        ".m": [("objc", 0.7), ("matlab", 0.8)],
        ".sql": [("sql", 0.9), ("plsql", 0.6), ("mysql", 0.5)],
        ".xml": [("xml", 0.9), ("html", 0.5), ("jsp", 0.4)],
        ".json": [("json", 0.95), ("jsonc", 0.8), ("json5", 0.8)],
    }

    # Content-based detection patterns (compiled regex for performance)
    CONTENT_PATTERNS: Dict[str, List[Tuple[str, float]]] = {
        "java_vs_cpp": {
            "cpp": [
                (r"#include\s*<iostream>", 0.8),
                (r"std::", 0.8),
                (r"namespace\s+\w+", 0.7),
                (r"class\s+\w+.*{", 0.7),
                (r"template\s*<", 0.6),
            ],
            "c": [
                (r"#include\s*<stdio.h>", 0.8),
                (r"printf\s*\(", 0.8),
                (r"malloc\s*\(", 0.8),
                (r"typedef\s+struct", 0.7),
            ],
        },
        "objc_vs_matlab": {
            "objc": [
                (r"#import", 0.9),
                (r"@interface", 0.9),
                (r"@implementation", 0.9),
                (r"NSString", 0.8),
                (r"alloc\]", 0.8),
            ],
            "matlab": [
                (r"function\s+", 0.9),
                (r"end\s*;", 0.9),
                (r"disp\s*\(", 0.8),
                (r"clc\s*;", 0.8),
                (r"clear\s+all", 0.8),
            ],
        },
    }

    # Tree-sitter supported languages (from official docs)
    SUPPORTED_LANGUAGES = frozenset({
        "java",
        "javascript",
        "typescript",
        "python",
        "c",
        "cpp",
        "csharp",
        "rust",
        "go",
        "kotlin",
        "php",
        "ruby",
        "markdown",
        "html",
        "css",
        "json",
        "yaml",
        "sql",
    })

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize language detector.

        Args:
            project_root: Project root path (for validation, optional)
        """
        self._project_root = project_root

        # Compile content patterns for performance
        self._compiled_patterns: Dict[str, List[Tuple[re.Pattern, float]]] = {}
        for category, patterns in self.CONTENT_PATTERNS.items():
            self._compiled_patterns[category] = [
                (re.compile(pattern), weight) for pattern, weight in patterns.items()
            ]

        # Cache for metadata (enabled by default)
        self._enable_cache = True

        # Initialize cache
        self._cache_enabled = True
        self._cache = {}

        # Initialize logger
        self._logger = logger

    @lru_cache(maxsize=4096)
    def _detect_language_cached(
        self,
        file_path: str,
        use_cache: bool = True,
        project_root: str | None = None,
    ) -> str:
        """
        Detect language with caching.

        Args:
            file_path: File path
            use_cache: Whether to use cache (default: True)
            project_root: Project root (for cache key)

        Returns:
            Detected language name (e.g., "python")
        """
        # Try cache first
        if use_cache and self._cache_enabled:
            cache_key = self._generate_cache_key(file_path, project_root)
            if cache_key in self._cache:
                self._logger.debug(f"Cache hit for {file_path}")
                return self._cache[cache_key]

        # Detect language
        result = self._detect_language(file_path)

        # Store in cache
        if use_cache and self._cache_enabled:
            cache_key = self._generate_cache_key(file_path, project_root)
            self._cache[cache_key] = result

        return result

    def detect_language(
        self,
        file_path: str,
        content: str | None = None,
        project_root: str | None = None,
    ) -> str:
        """
        Detect language from file path and optional content.

        Args:
            file_path: File path (required)
            content: File content (optional, for ambiguity resolution)
            project_root: Project root (for cache)

        Returns:
            Detected language name (e.g., "python")
        """
        # Handle invalid input
        if not file_path or not isinstance(file_path, str):
            self._logger.error(f"Invalid file path: {file_path}")
            return "unknown"

        path = Path(file_path)
        extension = path.suffix.lower()

        # Direct mapping by extension (fast)
        if extension in self.EXTENSION_MAPPING:
            language, confidence = self.EXTENSION_MAPPING[extension]
            self._logger.debug(f"Extension mapping: {extension} -> {language} (confidence: {confidence})")
            return language

        # Handle ambiguous extensions
        if extension in self.AMBIGUOUS_EXTENSIONS:
            self._logger.debug(f"Ambiguous extension: {extension}")
            if content:
                return self._resolve_ambiguity(extension, content)
            else:
                # Fallback to first candidate without content
                return self.AMBIGUOUS_EXTENSIONS[extension][0][0]

        # Unknown extension - return "unknown"
        return "unknown"

    def detect_from_extension(self, file_path: str) -> str:
        """
        Quick detection using extension only (no content analysis).

        Args:
            file_path: File path

        Returns:
            Detected language name (e.g., "python")

        Note:
            - Fast (O(1)) but less accurate
            - Doesn't resolve ambiguous extensions
            - Recommended for quick scans
        """
        # Handle invalid input
        if not file_path or not isinstance(file_path, str):
            return "unknown"

        path = Path(file_path)
        extension = path.suffix.lower()

        # Direct mapping by extension
        if extension in self.EXTENSION_MAPPING:
            language, _ = self.EXTENSION_MAPPING[extension]
            return language

        # Handle ambiguous extensions (fallback to first candidate)
        if extension in self.AMBIGUOUS_EXTENSIONS:
            return self.AMBIGUOUS_EXTENSIONS[extension][0][0]

        # Unknown extension
        return "unknown"

    def is_supported(self, language: str) -> bool:
        """
        Check if language is supported by Tree-sitter.

        Args:
            language: Language name

        Returns:
            Support status (True/False)
        """
        return language in self.SUPPORTED_LANGUAGES

    def get_supported_extensions(self) -> List[str]:
        """
        Get list of supported extensions.

        Returns:
            Sorted list of extensions
        """
        return sorted(self.EXTENSION_MAPPING.keys())

    def get_supported_languages(self) -> List[str]:
        """
        Get list of supported languages.

        Returns:
            Sorted list of languages
        """
        return sorted(self.SUPPORTED_LANGUAGES)

    def get_language_info(self, language: str) -> LanguageInfo:
        """
        Get language information.

        Args:
            language: Language name

        Returns:
            LanguageInfo object
        """
        extensions = [
            ext for ext, lang in self.EXTENSION_MAPPING.items()
            if lang == language
        ]

        return LanguageInfo(
            name=language,
            extensions=extensions,
            confidence=1.0,  # Extension-based detection is usually high confidence
            supported=self.is_supported(language),
        )

    def _detect_language(self, file_path: str) -> str:
        """
        Internal method for language detection.

        Args:
            file_path: File path

        Returns:
            Detected language name
        """
        # Handle invalid input
        if not file_path or not isinstance(file_path, str):
            return "unknown"

        path = Path(file_path)
        extension = path.suffix.lower()

        # Direct mapping by extension
        if extension in self.EXTENSION_MAPPING:
            language, _ = self.EXTENSION_MAPPING[extension]
            return language

        # Handle ambiguous extensions
        if extension in self.AMBIGUOUS_EXTENSIONS:
            # We need content to resolve ambiguity
            # This will be handled by the caller
            # Fallback to first candidate
            return self.AMBIGUOUS_EXTENSIONS[extension][0][0]

        # Unknown extension
        return "unknown"

    def _resolve_ambiguity(self, extension: str, content: str) -> str:
        """
        Resolve ambiguous extension using content.

        Args:
            extension: File extension (e.g., ".h")
            content: File content

        Returns:
            Resolved language name (e.g., "cpp")
        """
        # Get candidates for this extension
        candidates = self.AMBIGUOUS_EXTENSIONS.get(extension, [])
        if not candidates:
            return "unknown"

        # Score each candidate using content patterns
        scores: Dict[str, float] = {}
        for language, _ in candidates:
            score = 0.0
            category = None

            # Find the category for this language
            if language == "c":
                category = "java_vs_cpp"
            elif language == "cpp":
                category = "java_vs_cpp"
            elif language == "objc":
                category = "objc_vs_matlab"
            elif language == "matlab":
                category = "objc_vs_matlab"
            else:
                continue

            # Score using content patterns
            if category in self._compiled_patterns:
                for pattern, weight in self._compiled_patterns[category]:
                    if language == "c":
                        score += weight if pattern.search(content) else 0
                    elif language == "cpp":
                        score += weight if pattern.search(content) else 0
                    elif language == "objc":
                        score += weight * 3 if pattern.search(content) else 0  # Stronger weight for ObjC
                    elif language == "matlab":
                        score += weight if pattern.search(content) else 0

            # Normalize score (0.0 to 1.0)
            max_score = 4.0  # Maximum possible score
            scores[language] = score / max_score if max_score > 0 else 0.0

        # Select best-scoring language
        if scores:
            best_language = max(scores, key=scores.get)
            best_score = scores[best_language]

            # If best score is too low, fallback to first candidate
            if best_score < 0.2:
                self._logger.warning(f"Ambiguity resolution score too low: {best_language} (score: {best_score})")
                return candidates[0][0]

            return best_language

        # Fallback to first candidate
        return candidates[0][0]

    def _generate_cache_key(
        self,
        file_path: str,
        project_root: str | None = None,
    ) -> str:
        """
        Generate cache key from file path and project root.

        Args:
            file_path: File path
            project_root: Project root

        Returns:
            Cache key string
        """
        # Use relative path if project_root is provided
        if project_root and file_path:
            try:
                path = Path(file_path)
                root = Path(project_root)
                relative_path = path.relative_to(root)
                return str(relative_path)
            except ValueError:
                # file_path is not relative to project_root
                pass

        # Fallback to absolute path
        return file_path

    def clear_cache(self) -> None:
        """
        Clear language detection cache.

        Note:
            - Invalidates all cached language detection results
            - Next detection will re-scan files
        """
        self._cache.clear()
        self._logger.info("Language detection cache cleared")


# Global instance for backward compatibility
detector = LanguageDetector()


# Convenience functions with caching
def detect_language_from_file(
    file_path: str,
    content: str | None = None,
    project_root: str | None = None,
    use_cache: bool = True,
) -> str:
    """
    Detect language from file path (with caching).

    Args:
        file_path: File path
        content: File content (optional)
        project_root: Project root (optional)
        use_cache: Whether to use cache (default: True)

    Returns:
        Detected language name (e.g., "python")
    """
    return detector._detect_language_cached(file_path, use_cache, project_root)


def detect_language_from_extension(file_path: str) -> str:
    """
    Quick detection using extension only.

    Args:
        file_path: File path

    Returns:
        Detected language name (e.g., "python")
    """
    return detector.detect_from_extension(file_path)


def is_language_supported(language: str) -> bool:
    """
    Check if language is supported (convenience function).

    Args:
        language: Language name

    Returns:
        Support status (True/False)
    """
    return detector.is_supported(language)


def get_supported_extensions() -> List[str]:
    """
    Get list of supported extensions (convenience function).

    Returns:
        Sorted list of extensions
    """
    return detector.get_supported_extensions()


def get_supported_languages() -> List[str]:
    """
    Get list of supported languages (convenience function).

    Returns:
        Sorted list of languages
    """
    return detector.get_supported_languages()


def get_language_info(language: str) -> LanguageInfo:
    """
    Get language information (convenience function).

    Args:
        language: Language name

    Returns:
        LanguageInfo object
    """
    return detector.get_language_info(language)


def add_extension_mapping(extension: str, language: str) -> None:
    """
    Add custom extension mapping (convenience function).

    Args:
        extension: File extension (with dot, e.g., ".java")
        language: Language name
    """
    detector.EXTENSION_MAPPING[extension.lower()] = (language, 1.0)
    logger.info(f"Added extension mapping: {extension} -> {language}")


# Export for backward compatibility
__all__ = [
    "LanguageDetector",
    "LanguageInfo",
    "LanguageDetectionError",
    "detector",
    "detect_language_from_file",
    "detect_language_from_extension",
    "is_language_supported",
    "get_supported_extensions",
    "get_supported_languages",
    "get_language_info",
    "add_extension_mapping",
]
