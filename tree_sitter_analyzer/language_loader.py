#!/usr/bin/env python3
"""
Dynamic Language Loader

Handles loading of Tree-sitter language parsers with efficient caching
and lazy loading for optimal performance.
"""

import importlib
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Language, Parser

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from .utils import log_warning


class LanguageLoader:
    """Optimized language loader with enhanced caching"""

    # 対応言語とモジュールのマッピング（最適化：frozendict使用を検討）
    LANGUAGE_MODULES = {
        "java": "tree_sitter_java",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
        "tsx": "tree_sitter_typescript",
        "python": "tree_sitter_python",
        "c": "tree_sitter_c",
        "cpp": "tree_sitter_cpp",
        "rust": "tree_sitter_rust",
        "go": "tree_sitter_go",
    }

    # TypeScript特別処理（TypeScriptとTSX）
    TYPESCRIPT_DIALECTS = {"typescript": "typescript", "tsx": "tsx"}

    @property
    def SUPPORTED_LANGUAGES(self) -> list:
        """サポートされている言語のリストを取得するプロパティ"""
        return list(self.LANGUAGE_MODULES.keys())

    def __init__(self) -> None:
        """ローダーを初期化（最適化：事前キャッシュ容量指定）"""
        self._loaded_languages: dict[str, Language] = {}
        self._loaded_modules: dict[str, Any] = {}
        self._availability_cache: dict[str, bool] = {}
        self._parser_cache: dict[str, Parser] = {}  # パーサーキャッシュ追加
        self._unavailable_languages: set[str] = set()  # 利用不可言語の記録

    def is_language_available(self, language: str) -> bool:
        """
        指定された言語のライブラリが利用可能かチェック

        Args:
            language: 言語名

        Returns:
            利用可能性
        """
        # 事前に利用不可とわかっている言語は即座に返す
        if language in self._unavailable_languages:
            return False

        if language in self._availability_cache:
            return self._availability_cache[language]

        if not TREE_SITTER_AVAILABLE:
            self._availability_cache[language] = False
            self._unavailable_languages.add(language)
            return False

        module_name = self.LANGUAGE_MODULES.get(language)
        if not module_name:
            self._availability_cache[language] = False
            self._unavailable_languages.add(language)
            return False

        try:
            importlib.import_module(module_name)
            self._availability_cache[language] = True
            return True
        except ImportError:
            self._availability_cache[language] = False
            self._unavailable_languages.add(language)
            return False

    def load_language(self, language: str) -> Optional["Language"]:
        """Load and return a tree-sitter Language object for the specified language"""
        if not TREE_SITTER_AVAILABLE:
            log_warning("Tree-sitter is not available")
            return None

        # キャッシュから取得（最適化）
        if language in self._loaded_languages:
            return self._loaded_languages[language]

        if not self.is_language_available(language):
            return None

        try:
            module_name = self.LANGUAGE_MODULES[language]

            # モジュールキャッシュから取得または新規読み込み
            if module_name not in self._loaded_modules:
                self._loaded_modules[module_name] = importlib.import_module(module_name)

            module = self._loaded_modules[module_name]

            # TypeScript特別処理
            if language in self.TYPESCRIPT_DIALECTS:
                dialect = self.TYPESCRIPT_DIALECTS[language]
                if hasattr(module, "language_typescript") and dialect == "typescript":
                    language_func = module.language_typescript
                elif hasattr(module, "language_tsx") and dialect == "tsx":
                    language_func = module.language_tsx
                elif hasattr(module, "language"):
                    language_func = module.language
                else:
                    return None
            else:
                if hasattr(module, "language"):
                    language_func = module.language
                else:
                    return None

            # Language オブジェクト作成（最適化：一度だけ作成）
            tree_sitter_language = tree_sitter.Language(language_func())
            self._loaded_languages[language] = tree_sitter_language
            return tree_sitter_language

        except (ImportError, AttributeError, Exception) as e:
            log_warning(f"Failed to load language '{language}': {e}")
            self._unavailable_languages.add(language)
            return None

    def create_parser_safely(self, language: str) -> Optional["Parser"]:
        """Create a parser for the specified language with error handling"""
        if not TREE_SITTER_AVAILABLE:
            log_warning("Tree-sitter is not available")
            return None

        # パーサーキャッシュから取得
        if language in self._parser_cache:
            return self._parser_cache[language]

        tree_sitter_language = self.load_language(language)
        if tree_sitter_language is None:
            return None

        try:
            parser = tree_sitter.Parser(tree_sitter_language)
            # パーサーをキャッシュ（最適化）
            self._parser_cache[language] = parser
            return parser
        except Exception as e:
            log_warning(f"Failed to create parser for '{language}': {e}")
            return None

    def create_parser(self, language: str) -> Optional["Parser"]:
        """Create a parser for the specified language (alias for create_parser_safely)"""
        return self.create_parser_safely(language)

    def get_supported_languages(self) -> list:
        """
        サポートされている言語のリストを取得（最適化：結果キャッシュ）

        Returns:
            サポート言語のリスト
        """
        # 利用可能な言語のみを返す（効率化）
        return [
            lang
            for lang in self.LANGUAGE_MODULES.keys()
            if lang not in self._unavailable_languages
            and self.is_language_available(lang)
        ]

    def clear_cache(self) -> None:
        """キャッシュをクリア（メモリ管理用）"""
        self._loaded_languages.clear()
        self._loaded_modules.clear()
        self._availability_cache.clear()
        self._parser_cache.clear()
        self._unavailable_languages.clear()
        # 可用性キャッシュもクリア
        self._availability_cache.clear()


# グローバルインスタンス（最適化：シングルトンパターン）
_loader_instance = None


def get_loader() -> "LanguageLoader":
    """Get singleton loader instance"""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = LanguageLoader()
    return _loader_instance


# 後方互換性のため
loader = get_loader()


def check_language_availability(language: str) -> bool:
    """言語の利用可能性をチェック"""
    return get_loader().is_language_available(language)


def create_parser_safely(language: str) -> Optional["Parser"]:
    """安全にパーサーを作成"""
    return get_loader().create_parser_safely(language)


def load_language(language: str) -> Optional["Language"]:
    """言語をロード"""
    return get_loader().load_language(language)
