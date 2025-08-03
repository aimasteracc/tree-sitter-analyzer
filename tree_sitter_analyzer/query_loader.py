#!/usr/bin/env python3
"""
Dynamic query loader for language-specific Tree-sitter queries.
Optimized with enhanced caching and lazy loading for better performance.
"""

import importlib

from .utils import log_error, log_warning


class QueryLoader:
    """Load and manage language-specific Tree-sitter queries with optimizations."""

    # --- Predefined Queries (from query_library.py) ---
    _PREDEFINED_QUERIES: dict[str, dict[str, str]] = {
        "java": {
            "class": "(class_declaration) @class",
            "interface": "(interface_declaration) @interface",
            "method": "(method_declaration) @method",
            "constructor": "(constructor_declaration) @constructor",
            "field": "(field_declaration) @field",
            "import": "(import_declaration) @import",
            "package": "(package_declaration) @package",
            "annotation": "(annotation) @annotation",
            "method_name": "(method_declaration name: (identifier) @method.name)",
            "class_name": "(class_declaration name: (identifier) @class.name)",
            "method_invocations": "(method_invocation name: (identifier) @invocation.name)",
            "class_with_body": "(class_declaration name: (identifier) @class.name body: (class_body) @class.body)",
            "method_with_body": "(method_declaration name: (identifier) @method.name body: (block) @method.body)",
        }
        # Add other languages here if needed
    }

    _QUERY_DESCRIPTIONS: dict[str, str] = {
        "class": "Extract class declarations",
        "interface": "Extract interface declarations",
        "method": "Extract method declarations",
        "constructor": "Extract constructor declarations",
        "field": "Extract field declarations",
        "import": "Extract import statements",
        "package": "Extract package declarations",
        "annotation": "Extract annotations",
        "method_name": "Extract method names only",
        "class_name": "Extract class names only",
        "method_invocations": "Extract method invocations",
        "class_with_body": "Extract class declarations with body",
        "method_with_body": "Extract method declarations with body",
    }

    def __init__(self) -> None:
        self._loaded_queries: dict[str, dict] = {}
        self._query_modules: dict[str, object] = {}
        self._failed_languages: set[str] = set()  # 読み込み失敗した言語をキャッシュ

    def load_language_queries(self, language: str) -> dict:
        """Load queries for a specific language with optimized caching."""
        if language in self._failed_languages:
            return {}

        if language in self._loaded_queries:
            return self._loaded_queries[language]

        # Start with predefined queries
        queries = self._PREDEFINED_QUERIES.get(language, {}).copy()

        try:
            module_name = f"tree_sitter_analyzer.queries.{language}"
            module = importlib.import_module(module_name)

            if hasattr(module, "get_all_queries"):
                queries.update(module.get_all_queries())
            elif hasattr(module, "ALL_QUERIES"):
                queries.update(module.ALL_QUERIES)
            else:
                for attr_name in dir(module):
                    if not attr_name.startswith("_"):
                        attr_value = getattr(module, attr_name)
                        if isinstance(attr_value, str):
                            queries[attr_name] = attr_value
                        elif isinstance(attr_value, dict):
                            # Convert dict to string representation for queries
                            queries[attr_name] = str(attr_value)

            self._loaded_queries[language] = queries
            self._query_modules[language] = module
            return queries

        except ImportError:
            log_warning(
                f"No dynamic query module for '{language}', using predefined queries."
            )
            self._loaded_queries[language] = queries
            return queries
        except Exception as e:
            log_error(f"Error loading dynamic queries for '{language}': {e}")
            self._failed_languages.add(language)
            self._loaded_queries[language] = {}  # Reset on error
            return {}

    def get_query(self, language: str, query_name: str) -> str | None:
        """Get a specific query for a language with optimized lookup."""
        queries = self.load_language_queries(language)

        if query_name in queries:
            query_info = queries[query_name]
            if isinstance(query_info, dict) and "query" in query_info:
                return str(query_info["query"])
            elif isinstance(query_info, str):
                return query_info

        return None

    def get_query_description(self, language: str, query_name: str) -> str | None:
        """Get description for a specific query."""
        # Check predefined descriptions first
        if query_name in self._QUERY_DESCRIPTIONS:
            return self._QUERY_DESCRIPTIONS[query_name]

        queries = self.load_language_queries(language)
        if query_name in queries:
            query_info = queries[query_name]
            if isinstance(query_info, dict) and "description" in query_info:
                return str(query_info["description"])
            return f"Query '{query_name}' for {language}"

        return None

    def list_queries_for_language(self, language: str) -> list[str]:
        """List all available queries for a language."""
        queries = self.load_language_queries(language)
        return list(queries.keys())

    def list_queries(self, language: str) -> list[str]:
        """List all available queries for a language.

        Args:
            language: The programming language to list queries for

        Returns:
            List of query names available for the specified language
        """
        return self.list_queries_for_language(language)

    def list_supported_languages(self) -> list[str]:
        """List all languages that have query modules available."""
        languages = []

        # 既知の言語をチェック
        known_languages = [
            "java",
            "javascript",
            "typescript",
            "python",
            "c",
            "cpp",
            "rust",
            "go",
        ]

        for language in known_languages:
            if language not in self._failed_languages:
                try:
                    module_name = f"tree_sitter_analyzer.queries.{language}"
                    importlib.import_module(module_name)
                    languages.append(language)
                except ImportError:
                    self._failed_languages.add(language)

        return languages

    def get_common_queries(self) -> list[str]:
        """Get commonly used queries across languages."""
        # Return a flat list of common query names
        return ["functions", "classes", "variables", "imports"]

    def get_all_queries_for_language(self, language: str) -> dict[str, tuple[str, str]]:
        """Get all query information for a language including metadata.

        Returns:
            Dictionary mapping query names to (query_string, description) tuples
        """
        queries = self.load_language_queries(language)
        result = {}

        for name, query_info in queries.items():
            if isinstance(query_info, dict):
                query_string = query_info.get("query", "")
                description = query_info.get(
                    "description", f"Query '{name}' for {language}"
                )
                result[name] = (query_string, description)
            elif isinstance(query_info, str):
                result[name] = (query_info, f"Query '{name}' for {language}")

        return result

    def refresh_cache(self) -> None:
        """Refresh the query cache."""
        self._loaded_queries.clear()
        self._query_modules.clear()
        self._failed_languages.clear()
        # Cache was removed for memory efficiency

    def is_language_supported(self, language: str) -> bool:
        """Check if a language has query support."""
        if language in self._failed_languages:
            return False
        return language in self.list_supported_languages()

    def preload_languages(self, languages: list[str]) -> dict[str, bool]:
        """Preload queries for multiple languages efficiently."""
        results = {}
        for language in languages:
            try:
                queries = self.load_language_queries(language)
                results[language] = len(queries) > 0
            except Exception:
                results[language] = False
        return results


# グローバルインスタンス（シングルトンパターン）
_query_loader_instance = None


def get_query_loader() -> QueryLoader:
    """Get singleton query loader instance."""
    global _query_loader_instance
    if _query_loader_instance is None:
        _query_loader_instance = QueryLoader()
    return _query_loader_instance


# 後方互換性のため
query_loader = get_query_loader()


# 便利関数（最適化済み）
def get_query(language: str, query_name: str) -> str | None:
    """Get a specific query."""
    return get_query_loader().get_query(language, query_name)


def list_queries(language: str) -> list[str]:
    """List queries for a language."""
    return get_query_loader().list_queries_for_language(language)


def list_supported_languages() -> list[str]:
    """List all supported languages."""
    return get_query_loader().list_supported_languages()


def is_language_supported(language: str) -> bool:
    """Check if language is supported."""
    return get_query_loader().is_language_supported(language)
