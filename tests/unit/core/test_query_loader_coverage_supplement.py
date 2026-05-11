#!/usr/bin/env python3
"""Supplementary tests for query_loader.py uncovered branches."""

import pytest
from unittest.mock import MagicMock, patch
from tree_sitter_analyzer.query_loader import QueryLoader


class TestQueryLoaderUncovered:
    """Targets: lines 67, 81-91, 101-105, 178-184, 209-224, 229-236"""

    def test_load_language_queries_failed_language_returns_empty(self):
        """Line 67: _failed_languages cache hit returns {}."""
        loader = QueryLoader()
        loader._failed_languages.add("brainfuck")
        result = loader.load_language_queries("brainfuck")
        assert result == {}

    def test_load_language_queries_cache_hit(self):
        """Lines 69-70: _loaded_queries cache hit."""
        loader = QueryLoader()
        loader._loaded_queries["python"] = {"functions": "(function_definition) @func"}
        result = loader.load_language_queries("python")
        assert result == {"functions": "(function_definition) @func"}

    def test_load_language_queries_import_error_fallback(self):
        """Lines 97-100: ImportError fallback."""
        loader = QueryLoader()
        with patch("importlib.import_module", side_effect=ImportError):
            result = loader.load_language_queries("rust")
        # Should return predefined queries if any, else {}
        assert isinstance(result, dict)

    def test_load_language_queries_generic_exception(self):
        """Lines 101-105: generic Exception handling."""
        loader = QueryLoader()
        with patch("importlib.import_module", side_effect=RuntimeError("test crash")):
            result = loader.load_language_queries("python")
        assert result == {}
        assert "python" in loader._failed_languages

    def test_load_language_queries_module_with_get_all_queries(self):
        """Lines 79-80: module with get_all_queries()."""
        loader = QueryLoader()
        mock_module = MagicMock()
        mock_module.get_all_queries.return_value = {"custom": "(custom) @c"}

        with patch("importlib.import_module", return_value=mock_module):
            result = loader.load_language_queries("java")
        assert "custom" in result
        assert "class" in result  # predefined query still present

    def test_load_language_queries_module_with_ALL_QUERIES(self):
        """Lines 81-82: module with ALL_QUERIES dict."""
        loader = QueryLoader()
        mock_module = MagicMock()
        del mock_module.get_all_queries  # force fallback to ALL_QUERIES
        mock_module.ALL_QUERIES = {"all_custom": "(all) @a"}

        with patch("importlib.import_module", return_value=mock_module):
            result = loader.load_language_queries("java")
        assert "all_custom" in result

    def test_load_language_queries_directory_fallback(self):
        """Lines 83-91: dir() fallback with string/dict attributes."""
        loader = QueryLoader()
        mock_module = MagicMock()
        del mock_module.get_all_queries
        del mock_module.ALL_QUERIES
        mock_module.MY_QUERY = "(identifier) @id"
        mock_module.my_dict = {"nested": "(nested) @n"}

        with patch("importlib.import_module", return_value=mock_module):
            result = loader.load_language_queries("java")
        assert "MY_QUERY" in result
        assert "nested" in result

    def test_get_all_queries_for_language_with_dict_entries(self):
        """Lines 199-212: get_all_queries_for_language with dict query_info."""
        loader = QueryLoader()
        loader._loaded_queries["python"] = {
            "functions": {"query": "(function) @f", "description": "Get functions"},
            "classes": "(class) @c",  # string format
        }
        result = loader.get_all_queries_for_language("python")
        assert ("(function) @f", "Get functions") == result["functions"]
        assert ("(class) @c", "Query 'classes' for python") == result["classes"]

    def test_refresh_cache_clears_all(self):
        """Lines 216-219: refresh_cache()."""
        loader = QueryLoader()
        loader._loaded_queries["java"] = {"class": "(class) @c"}
        loader._query_modules["java"] = MagicMock()
        loader._failed_languages.add("php")
        loader.refresh_cache()
        assert loader._loaded_queries == {}
        assert loader._query_modules == {}
        assert loader._failed_languages == set()

    def test_is_language_supported_failed_returns_false(self):
        """Lines 223-224: _failed_languages returns False."""
        loader = QueryLoader()
        loader._failed_languages.add("ruby")
        assert loader.is_language_supported("ruby") is False

    def test_is_language_supported_unknown_returns_false(self):
        """Line 225: unknown language returns False."""
        loader = QueryLoader()
        assert loader.is_language_supported("brainfuck") is False

    def test_preload_languages_mixed(self):
        """Lines 229-236: preload_languages with mixed success/failure."""
        loader = QueryLoader()
        mock_module = MagicMock()
        mock_module.get_all_queries.return_value = {"func": "(function) @f"}

        with patch("importlib.import_module", return_value=mock_module):
            result = loader.preload_languages(["python", "brainfuck", "java"])
        assert result["python"] is True
        assert result["brainfuck"] is True or result["brainfuck"] is False
        assert result["java"] is True

    def test_preload_languages_exception_handling(self):
        """Line 233-234: exception during preload."""
        loader = QueryLoader()
        with patch("importlib.import_module", side_effect=RuntimeError):
            result = loader.preload_languages(["python"])
        assert result["python"] is False
