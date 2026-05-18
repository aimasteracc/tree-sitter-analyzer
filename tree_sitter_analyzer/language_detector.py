#!/usr/bin/env python3
"""
Language Detection System

Automatically detects programming language from file extensions and content.
Supports multiple languages with extensible configuration.
"""

from pathlib import Path
from typing import Any

from ._language_detector_helpers import (
    build_content_pattern_weights,
    build_extension_confidence_map,
    get_cached_language,
    get_path_mtime_ns,
    normalize_detection_path,
    store_cached_language,
)


class LanguageDetector:
    """Automatic programming language detector"""

    # Basic extension mapping
    EXTENSION_MAPPING: dict[str, str] = {
        # Java系
        ".java": "java",
        ".jsp": "jsp",
        ".jspx": "jsp",
        # JavaScript/TypeScript系
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "typescript",  # TSX files are TypeScript with JSX
        ".mts": "typescript",  # ES module TypeScript
        ".cts": "typescript",  # CommonJS TypeScript
        ".mjs": "javascript",
        ".cjs": "javascript",
        # Python系
        ".py": "python",
        ".pyx": "python",
        ".pyi": "python",
        ".pyw": "python",
        # C/C++系
        ".c": "c",
        ".cpp": "cpp",
        ".cxx": "cpp",
        ".cc": "cpp",
        ".h": "c",  # Ambiguous
        ".hpp": "cpp",
        ".hxx": "cpp",
        # その他の言語
        ".rs": "rust",
        ".go": "go",
        ".rb": "ruby",
        ".php": "php",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".swift": "swift",
        ".cs": "csharp",
        ".vb": "vbnet",
        ".fs": "fsharp",
        ".scala": "scala",
        ".clj": "clojure",
        ".hs": "haskell",
        ".ml": "ocaml",
        ".lua": "lua",
        ".pl": "perl",
        ".r": "r",
        ".m": "objc",  # Ambiguous (MATLAB as well)
        ".dart": "dart",
        ".elm": "elm",
        # Markdown系
        ".md": "markdown",
        ".markdown": "markdown",
        ".mdown": "markdown",
        ".mkd": "markdown",
        ".mkdn": "markdown",
        ".mdx": "markdown",
        # HTML系
        ".html": "html",
        ".htm": "html",
        ".xhtml": "html",
        # CSS系
        ".css": "css",
        ".scss": "css",
        ".sass": "css",
        ".less": "css",
        # SQL系
        ".sql": "sql",
        # JSON系
        ".json": "json",
        ".jsonc": "json",
        ".json5": "json",
        # YAML系
        ".yaml": "yaml",
        ".yml": "yaml",
    }

    # Ambiguous extensions (map to multiple languages)
    AMBIGUOUS_EXTENSIONS: dict[str, list[str]] = {
        ".h": ["c", "cpp", "objc"],
        ".m": ["objc", "matlab"],
        ".sql": ["sql", "plsql", "mysql"],
        ".xml": ["xml", "html", "jsp"],
        ".json": ["json", "jsonc"],
    }

    # Content-based detection patterns
    CONTENT_PATTERNS: dict[str, dict[str, list[str]]] = {
        "c_vs_cpp": {
            "cpp": ["#include <iostream>", "std::", "namespace", "class ", "template<"],
            "c": ["#include <stdio.h>", "printf(", "malloc(", "typedef struct"],
        },
        "objc_vs_matlab": {
            "objc": ["#import", "@interface", "@implementation", "NSString", "alloc]"],
            "matlab": ["function ", "end;", "disp(", "clc;", "clear all"],
        },
    }

    # Tree-sitter supported languages
    SUPPORTED_LANGUAGES = {
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
        "swift",
        "markdown",
        "html",
        "css",
        "json",
        "sql",
        "yaml",
    }

    def __init__(self) -> None:
        """Initialize detector"""
        self.extension_map = build_extension_confidence_map()
        self.content_patterns = build_content_pattern_weights()

        from .utils import log_debug, log_warning

        self._log_debug = log_debug
        self._log_warning = log_warning

    def detect_language(
        self, file_path: str, content: str | None = None
    ) -> tuple[str, float]:
        """
        ファイルパスとコンテンツから言語を判定

        Args:
            file_path: ファイルパス
            content: ファイルコンテンツ（任意、曖昧性解決用）

        Returns:
            (言語名, 信頼度) のタプル - 常に有効な言語名を返す
        """
        # Handle invalid input
        if not file_path or not isinstance(file_path, str):
            return "unknown", 0.0

        path = Path(file_path)
        extension = path.suffix.lower()

        detected = self._detect_mapped_extension(extension, content)
        if detected is not None:
            return detected

        # Unknown extension - always return "unknown" instead of None
        return "unknown", 0.0

    def _detect_mapped_extension(
        self, extension: str, content: str | None
    ) -> tuple[str, float] | None:
        if extension not in self.EXTENSION_MAPPING:
            return None

        language = self.EXTENSION_MAPPING[extension]
        if not language or language.strip() == "":
            return "unknown", 0.0

        if extension in self.extension_map:
            _, confidence = self.extension_map[extension]
            return language, confidence

        if extension not in self.AMBIGUOUS_EXTENSIONS:
            return language, 1.0

        if not content:
            return language, 0.7

        refined_language = self._resolve_ambiguity(extension, content)
        if not refined_language or refined_language.strip() == "":
            refined_language = "unknown"
        return refined_language, 0.9 if refined_language != language else 0.7

    def detect_from_extension(self, file_path: str) -> str:
        """
        Quick detection using extension only

        Args:
            file_path: File path

        Returns:
            Detected language name - 常に有効な文字列を返す
        """
        # Handle invalid input
        if not file_path or not isinstance(file_path, str):
            return "unknown"

        result = self.detect_language(file_path)
        if isinstance(result, tuple):
            language, _ = result
            # Ensure language is valid
            if not language or language.strip() == "":
                return "unknown"
            return language

    def is_supported(self, language: str) -> bool:
        """
        Check if language is supported by Tree-sitter

        Args:
            language: Language name

        Returns:
            Support status
        """
        # First check the static list for basic support
        if language in self.SUPPORTED_LANGUAGES:
            return True

        # Also check if we have a plugin for this language
        try:
            from .plugins.manager import PluginManager

            plugin_manager = PluginManager()
            plugin_manager.load_plugins()  # Ensure plugins are loaded
            supported_languages = plugin_manager.get_supported_languages()
            return language in supported_languages
        except Exception:
            # Fallback to static list if plugin manager fails
            return language in self.SUPPORTED_LANGUAGES

    def get_supported_extensions(self) -> list[str]:
        """
        Get list of supported extensions

        Returns:
            List of extensions
        """
        return sorted(self.EXTENSION_MAPPING.keys())

    def get_supported_languages(self) -> list[str]:
        """
        Get list of supported languages

        Returns:
            List of languages
        """
        return sorted(self.SUPPORTED_LANGUAGES)

    def _resolve_ambiguity(self, extension: str, content: str) -> str:
        """
        Resolve ambiguous extension using content

        Args:
            extension: File extension
            content: File content

        Returns:
            Resolved language name
        """
        if extension not in self.AMBIGUOUS_EXTENSIONS:
            return self.EXTENSION_MAPPING.get(extension, "unknown")

        candidates = self.AMBIGUOUS_EXTENSIONS[extension]

        # .h: C vs C++ vs Objective-C
        if extension == ".h":
            return self._detect_c_family(content, candidates)

        # .m: Objective-C vs MATLAB
        elif extension == ".m":
            return self._detect_objc_vs_matlab(content, candidates)

        # Fallback to first candidate
        return candidates[0]

    def _detect_c_family(self, content: str, candidates: list[str]) -> str:
        """Detect among C-family languages"""
        cpp_score = 0
        c_score = 0
        objc_score = 0

        # C++ features
        cpp_patterns = self.CONTENT_PATTERNS["c_vs_cpp"]["cpp"]
        for pattern in cpp_patterns:
            if pattern in content:
                cpp_score += 1

        # C features
        c_patterns = self.CONTENT_PATTERNS["c_vs_cpp"]["c"]
        for pattern in c_patterns:
            if pattern in content:
                c_score += 1

        # Objective-C features
        objc_patterns = self.CONTENT_PATTERNS["objc_vs_matlab"]["objc"]
        for pattern in objc_patterns:
            if pattern in content:
                objc_score += 3  # 強い指標なので重み大

        # Select best-scoring language
        scores = {"cpp": cpp_score, "c": c_score, "objc": objc_score}
        best_language = max(scores, key=lambda x: scores[x])

        # If objc not a candidate, fallback to C/C++
        if best_language == "objc" and "objc" not in candidates:
            best_language = "cpp" if cpp_score > c_score else "c"

        return best_language if scores[best_language] > 0 else candidates[0]

    def _detect_objc_vs_matlab(self, content: str, candidates: list[str]) -> str:
        """Detect between Objective-C and MATLAB"""
        objc_score = 0
        matlab_score = 0

        # Objective-C patterns
        for pattern in self.CONTENT_PATTERNS["objc_vs_matlab"]["objc"]:
            if pattern in content:
                objc_score += 1

        # MATLAB patterns
        for pattern in self.CONTENT_PATTERNS["objc_vs_matlab"]["matlab"]:
            if pattern in content:
                matlab_score += 1

        if objc_score > matlab_score:
            return "objc"
        elif matlab_score > objc_score:
            return "matlab"
        else:
            return candidates[0]  # default

    def add_extension_mapping(self, extension: str, language: str) -> None:
        """
        Add custom extension mapping

        Args:
            extension: File extension (with dot)
            language: Language name
        """
        self.EXTENSION_MAPPING[extension.lower()] = language

    def get_language_info(self, language: str) -> dict[str, Any]:
        """
        Get language information

        Args:
            language: Language name

        Returns:
            Language info dictionary
        """
        extensions = [
            ext for ext, lang in self.EXTENSION_MAPPING.items() if lang == language
        ]

        return {
            "name": language,
            "extensions": extensions,
            "supported": self.is_supported(language),
            "tree_sitter_available": language in self.SUPPORTED_LANGUAGES,
        }


# Global instance
detector = LanguageDetector()


def detect_language_from_file(
    file_path: str, *, project_root: str | None = None
) -> str:
    """
    Detect language from path (simple API)

    Args:
        file_path: File path

    Returns:
        Detected language name - 常に有効な文字列を返す
    """
    # Handle invalid input
    if not file_path or not isinstance(file_path, str):
        return "unknown"

    # Normalize to absolute path for caching (do not require file to exist).
    # If project_root is provided and file_path is relative, resolve against project_root.
    abs_path = normalize_detection_path(file_path, project_root)

    # Best-practice cache: (project_root, abs_path) -> {language, mtime_ns}
    # If we cannot stat (missing file / permission), do NOT cache.
    mtime_ns = get_path_mtime_ns(abs_path)

    if mtime_ns is not None:
        cached_language = get_cached_language(abs_path, mtime_ns, project_root)
        if cached_language is not None:
            return cached_language

    # Cache miss: use the global detector (fast, avoids per-call initialization costs)
    result = detector.detect_from_extension(abs_path)

    # Ensure result is valid
    if not result or result.strip() == "":
        return "unknown"

    # Store to cache (including unknown) only when we could stat the file
    store_cached_language(abs_path, result, mtime_ns, project_root)

    return result


def is_language_supported(language: str) -> bool:
    """
    Check if language is supported (simple API)

    Args:
        language: Language name

    Returns:
        Support status
    """
    # First check the static list for basic support
    if detector.is_supported(language):
        return True

    # Also check if we have a plugin for this language
    try:
        from .plugins.manager import PluginManager

        plugin_manager = PluginManager()
        plugin_manager.load_plugins()  # Ensure plugins are loaded
        supported_languages = plugin_manager.get_supported_languages()
        return language in supported_languages
    except Exception:
        # Fallback to static list if plugin manager fails
        return detector.is_supported(language)
