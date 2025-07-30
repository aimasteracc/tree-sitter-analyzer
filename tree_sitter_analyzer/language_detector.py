#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Language Detection System

Automatically detects programming language from file extensions and content.
Supports multiple languages with extensible configuration.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class LanguageDetector:
    """プログラミング言語の自動判定システム"""

    # 基本的な拡張子マッピング
    EXTENSION_MAPPING: Dict[str, str] = {
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
        ".h": "c",  # 曖昧性あり
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
        ".m": "objc",  # 曖昧性あり（MATLABとも）
        ".dart": "dart",
        ".elm": "elm",
    }

    # 曖昧な拡張子（複数言語に対応）
    AMBIGUOUS_EXTENSIONS: Dict[str, List[str]] = {
        ".h": ["c", "cpp", "objc"],
        ".m": ["objc", "matlab"],
        ".sql": ["sql", "plsql", "mysql"],
        ".xml": ["xml", "html", "jsp"],
        ".json": ["json", "jsonc"],
    }

    # コンテンツベース判定のキーワード
    CONTENT_PATTERNS: Dict[str, Dict[str, List[str]]] = {
        "c_vs_cpp": {
            "cpp": ["#include <iostream>", "std::", "namespace", "class ", "template<"],
            "c": ["#include <stdio.h>", "printf(", "malloc(", "typedef struct"],
        },
        "objc_vs_matlab": {
            "objc": ["#import", "@interface", "@implementation", "NSString", "alloc]"],
            "matlab": ["function ", "end;", "disp(", "clc;", "clear all"],
        },
    }

    # Tree-sitter対応言語（現在サポート済み）
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
        """言語検出器を初期化"""
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
        self, file_path: str, content: Optional[str] = None
    ) -> Tuple[str, float]:
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

        # 直接マッピングで判定できる場合
        if extension in self.EXTENSION_MAPPING:
            language = self.EXTENSION_MAPPING[extension]

            # 曖昧性がない場合は高信頼度
            if extension not in self.AMBIGUOUS_EXTENSIONS:
                return language, 1.0

            # 曖昧性がある場合はコンテンツベース判定
            if content:
                refined_language = self._resolve_ambiguity(extension, content)
                return refined_language, 0.9 if refined_language != language else 0.7
            else:
                return language, 0.7  # コンテンツなしなので信頼度低下

        # 拡張子が不明な場合
        return "unknown", 0.0

    def detect_from_extension(self, file_path: str) -> str:
        """
        ファイル拡張子のみから言語を簡易判定

        Args:
            file_path: ファイルパス

        Returns:
            判定された言語名
        """
        language, _ = self.detect_language(file_path)
        return language

    def is_supported(self, language: str) -> bool:
        """
        指定された言語がTree-sitterでサポートされているか確認

        Args:
            language: 言語名

        Returns:
            サポート状況
        """
        return language in self.SUPPORTED_LANGUAGES

    def get_supported_extensions(self) -> List[str]:
        """
        サポートされている拡張子一覧を取得

        Returns:
            拡張子のリスト
        """
        return sorted(self.EXTENSION_MAPPING.keys())

    def get_supported_languages(self) -> List[str]:
        """
        サポートされている言語一覧を取得

        Returns:
            言語のリスト
        """
        return sorted(self.SUPPORTED_LANGUAGES)

    def _resolve_ambiguity(self, extension: str, content: str) -> str:
        """
        曖昧な拡張子をコンテンツベースで解決

        Args:
            extension: ファイル拡張子
            content: ファイルコンテンツ

        Returns:
            解決された言語名
        """
        if extension not in self.AMBIGUOUS_EXTENSIONS:
            return self.EXTENSION_MAPPING.get(extension, "unknown")

        candidates = self.AMBIGUOUS_EXTENSIONS[extension]

        # .h ファイルの場合（C vs C++ vs Objective-C）
        if extension == ".h":
            return self._detect_c_family(content, candidates)

        # .m ファイルの場合（Objective-C vs MATLAB）
        elif extension == ".m":
            return self._detect_objc_vs_matlab(content, candidates)

        # デフォルトは最初の候補
        return candidates[0]

    def _detect_c_family(self, content: str, candidates: List[str]) -> str:
        """C系言語の判定"""
        cpp_score = 0
        c_score = 0
        objc_score = 0

        # C++の特徴
        cpp_patterns = self.CONTENT_PATTERNS["c_vs_cpp"]["cpp"]
        for pattern in cpp_patterns:
            if pattern in content:
                cpp_score += 1

        # Cの特徴
        c_patterns = self.CONTENT_PATTERNS["c_vs_cpp"]["c"]
        for pattern in c_patterns:
            if pattern in content:
                c_score += 1

        # Objective-Cの特徴
        objc_patterns = self.CONTENT_PATTERNS["objc_vs_matlab"]["objc"]
        for pattern in objc_patterns:
            if pattern in content:
                objc_score += 3  # 強い指標なので重み大

        # 最高スコアの言語を選択
        scores = {"cpp": cpp_score, "c": c_score, "objc": objc_score}
        best_language = max(scores, key=lambda x: scores[x])

        # objcが候補にない場合は除外
        if best_language == "objc" and "objc" not in candidates:
            best_language = "cpp" if cpp_score > c_score else "c"

        return best_language if scores[best_language] > 0 else candidates[0]

    def _detect_objc_vs_matlab(self, content: str, candidates: List[str]) -> str:
        """Objective-C vs MATLAB の判定"""
        objc_score = 0
        matlab_score = 0

        # Objective-Cパターン
        for pattern in self.CONTENT_PATTERNS["objc_vs_matlab"]["objc"]:
            if pattern in content:
                objc_score += 1

        # MATLABパターン
        for pattern in self.CONTENT_PATTERNS["objc_vs_matlab"]["matlab"]:
            if pattern in content:
                matlab_score += 1

        if objc_score > matlab_score:
            return "objc"
        elif matlab_score > objc_score:
            return "matlab"
        else:
            return candidates[0]  # デフォルト

    def add_extension_mapping(self, extension: str, language: str) -> None:
        """
        カスタム拡張子マッピングを追加

        Args:
            extension: ファイル拡張子（.付き）
            language: 言語名
        """
        self.EXTENSION_MAPPING[extension.lower()] = language

    def get_language_info(self, language: str) -> Dict[str, Any]:
        """
        言語の詳細情報を取得

        Args:
            language: 言語名

        Returns:
            言語情報の辞書
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


# グローバルインスタンス
detector = LanguageDetector()


def detect_language_from_file(file_path: str) -> str:
    """
    ファイルパスから言語を自動判定（シンプルAPI）

    Args:
        file_path: ファイルパス

    Returns:
        判定された言語名
    """
    return detector.detect_from_extension(file_path)


def is_language_supported(language: str) -> bool:
    """
    言語がサポートされているか確認（シンプルAPI）

    Args:
        language: 言語名

    Returns:
        サポート状況
    """
    return detector.is_supported(language)
