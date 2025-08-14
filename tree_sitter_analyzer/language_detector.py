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
        ".tsx": "tsx",
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
            (言語名, 信頼度) のタプル
        """
        path = Path(file_path)
        extension = path.suffix.lower()

        # Direct mapping by extension
        if extension in self.EXTENSION_MAPPING:
            language = self.EXTENSION_MAPPING[extension]

            # No ambiguity -> high confidence
            if extension not in self.AMBIGUOUS_EXTENSIONS:
                return language, 1.0

            # Resolve ambiguity using content
            if content:
                refined_language = self._resolve_ambiguity(extension, content)
                return refined_language, 0.9 if refined_language != language else 0.7
            else:
                return language, 0.7  # Lower confidence without content

        # Unknown extension
        return "unknown", 0.0

    def detect_from_extension(self, file_path: str) -> str:
        """
        Quick detection using extension only

        Args:
            file_path: File path

        Returns:
            Detected language name
        """
        language, _ = self.detect_language(file_path)
        return language

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
        Detected language name
    """
    return detector.detect_from_extension(file_path)


def is_language_supported(language: str) -> bool:
    """
    Check if language is supported (simple API)

    Args:
        language: Language name

    Returns:
        Support status
    """
    return detector.is_supported(language)
