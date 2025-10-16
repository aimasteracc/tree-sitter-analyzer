#!/usr/bin/env python3
"""
Language Detection System

Automatically detects programming language from file extensions and content.
Supports multiple languages with extensible configuration.
"""

from pathlib import Path
from typing import Any


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
        # JSON系
        ".json": "json",
        ".jsonc": "json",
        ".json5": "json",
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
        "rust",
        "go",
        "markdown",
        "html",
        "css",
        "json",
    }

    def __init__(self) -> None:
        """Initialize detector"""
        self.extension_map = {
            ".java": ("java", 0.9),
            ".js": ("javascript", 0.9),
            ".jsx": ("javascript", 0.8),
            ".ts": ("typescript", 0.9),
            ".tsx": ("typescript", 0.8),
            ".py": ("python", 0.9),
            ".pyw": ("python", 0.8),
            ".c": ("c", 0.9),
            ".h": ("c", 0.7),
            ".cpp": ("cpp", 0.9),
            ".cxx": ("cpp", 0.9),
            ".cc": ("cpp", 0.9),
            ".hpp": ("cpp", 0.8),
            ".rs": ("rust", 0.9),
            ".go": ("go", 0.9),
            ".cs": ("csharp", 0.9),
            ".php": ("php", 0.9),
            ".rb": ("ruby", 0.9),
            ".swift": ("swift", 0.9),
            ".kt": ("kotlin", 0.9),
            ".scala": ("scala", 0.9),
            ".clj": ("clojure", 0.9),
            ".hs": ("haskell", 0.9),
            ".ml": ("ocaml", 0.9),
            ".fs": ("fsharp", 0.9),
            ".elm": ("elm", 0.9),
            ".dart": ("dart", 0.9),
            ".lua": ("lua", 0.9),
            ".r": ("r", 0.9),
            ".m": ("objectivec", 0.7),
            ".mm": ("objectivec", 0.8),
            # Markdown extensions
            ".md": ("markdown", 0.9),
            ".markdown": ("markdown", 0.9),
            ".mdown": ("markdown", 0.8),
            ".mkd": ("markdown", 0.8),
            ".mkdn": ("markdown", 0.8),
            ".mdx": ("markdown", 0.7),  # MDX might be mixed with JSX
            # HTML extensions
            ".html": ("html", 0.9),
            ".htm": ("html", 0.9),
            ".xhtml": ("html", 0.8),
            # CSS extensions
            ".css": ("css", 0.9),
            ".scss": ("css", 0.8),  # Sass/SCSS
            ".sass": ("css", 0.8),  # Sass
            ".less": ("css", 0.8),  # Less
            # JSON extensions
            ".json": ("json", 0.9),
            ".jsonc": ("json", 0.8),  # JSON with comments
            ".json5": ("json", 0.8),  # JSON5 format
        }

        # Content-based detection patterns
        self.content_patterns = {
            "java": [
                (r"package\s+[\w\.]+\s*;", 0.3),
                (r"public\s+class\s+\w+", 0.3),
                (r"import\s+[\w\.]+\s*;", 0.2),
                (r"@\w+\s*\(", 0.2),  # Annotations
            ],
            "python": [
                (r"def\s+\w+\s*\(", 0.3),
                (r"import\s+\w+", 0.2),
                (r"from\s+\w+\s+import", 0.2),
                (r'if\s+__name__\s*==\s*["\']__main__["\']', 0.3),
            ],
            "javascript": [
                (r"function\s+\w+\s*\(", 0.3),
                (r"var\s+\w+\s*=", 0.2),
                (r"let\s+\w+\s*=", 0.2),
                (r"const\s+\w+\s*=", 0.2),
                (r"console\.log\s*\(", 0.1),
            ],
            "typescript": [
                (r"interface\s+\w+", 0.3),
                (r"type\s+\w+\s*=", 0.2),
                (r":\s*\w+\s*=", 0.2),  # Type annotations
                (r"export\s+(interface|type|class)", 0.2),
            ],
            "c": [
                (r"#include\s*<[\w\.]+>", 0.3),
                (r"int\s+main\s*\(", 0.3),
                (r"printf\s*\(", 0.2),
                (r"#define\s+\w+", 0.2),
            ],
            "cpp": [
                (r"#include\s*<[\w\.]+>", 0.2),
                (r"using\s+namespace\s+\w+", 0.3),
                (r"std::\w+", 0.2),
                (r"class\s+\w+\s*{", 0.3),
            ],
            "markdown": [
                (r"^#{1,6}\s+", 0.4),  # ATX headers
                (r"^\s*[-*+]\s+", 0.3),  # List items
                (r"```[\w]*", 0.3),  # Fenced code blocks
                (r"\[.*\]\(.*\)", 0.2),  # Links
                (r"!\[.*\]\(.*\)", 0.2),  # Images
                (r"^\s*>\s+", 0.2),  # Blockquotes
                (r"^\s*\|.*\|", 0.2),  # Tables
                (r"^[-=]{3,}$", 0.2),  # Setext headers or horizontal rules
            ],
            "html": [
                (r"<!DOCTYPE\s+html", 0.4),  # HTML5 doctype
                (r"<html[^>]*>", 0.3),  # HTML tag
                (r"<head[^>]*>", 0.3),  # Head tag
                (r"<body[^>]*>", 0.3),  # Body tag
                (r"<div[^>]*>", 0.2),  # Div tag
                (r"<p[^>]*>", 0.2),  # Paragraph tag
                (r"<a\s+href=", 0.2),  # Link tag with href
                (r"<img\s+src=", 0.2),  # Image tag with src
            ],
            "css": [
                (r"[.#][\w-]+\s*{", 0.4),  # CSS selectors
                (r"@media\s+", 0.3),  # Media queries
                (r"@import\s+", 0.3),  # Import statements
                (r"@keyframes\s+", 0.3),  # Keyframes
                (r":\s*[\w-]+\s*;", 0.2),  # Property declarations
                (r"color\s*:", 0.2),  # Color property
                (r"font-", 0.2),  # Font properties
                (r"margin\s*:", 0.2),  # Margin property
            ],
        }

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

        # Direct mapping by extension
        if extension in self.EXTENSION_MAPPING:
            language = self.EXTENSION_MAPPING[extension]

            # Ensure language is valid
            if not language or language.strip() == "":
                return "unknown", 0.0

            # Use confidence from extension_map if available
            if extension in self.extension_map:
                _, confidence = self.extension_map[extension]
                return language, confidence

            # No ambiguity -> high confidence
            if extension not in self.AMBIGUOUS_EXTENSIONS:
                return language, 1.0

            # Resolve ambiguity using content
            if content:
                refined_language = self._resolve_ambiguity(extension, content)
                # Ensure refined language is valid
                if not refined_language or refined_language.strip() == "":
                    refined_language = "unknown"
                return refined_language, 0.9 if refined_language != language else 0.7
            else:
                return language, 0.7  # Lower confidence without content

        # Unknown extension - always return "unknown" instead of None
        return "unknown", 0.0

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
        else:
            # Fallback for unexpected result format
            return "unknown"

    def is_supported(self, language: str) -> bool:
        """
        Check if language is supported by Tree-sitter

        Args:
            language: Language name

        Returns:
            Support status
        """
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


def detect_language_from_file(file_path: str) -> str:
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

    # Create a fresh instance to ensure latest configuration
    fresh_detector = LanguageDetector()
    result = fresh_detector.detect_from_extension(file_path)

    # Ensure result is valid
    if not result or result.strip() == "":
        return "unknown"

    return result


def is_language_supported(language: str) -> bool:
    """
    Check if language is supported (simple API)

    Args:
        language: Language name

    Returns:
        Support status
    """
    return detector.is_supported(language)
