#!/usr/bin/env python3
"""Tests for uncovered branches in query_loader.py.

Targets lines: 62, 68, 82-92, 102-106, 120-121, 129, 136,
179, 184-185, 210, 225, 230-237.
"""

from __future__ import annotations

import importlib
import types
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.query_loader import QueryLoader, get_query_loader


@pytest.fixture
def loader() -> QueryLoader:
    """Provide a fresh QueryLoader instance for every test."""
    return QueryLoader()


# ---------------------------------------------------------------------------
# Line 62: language.strip() == "" branch in load_language_queries
# ---------------------------------------------------------------------------


class TestLoadLanguageQueriesEmptyLanguage:
    """Cover the whitespace-only language guard."""

    def test_whitespace_only_language_returns_empty(self, loader: QueryLoader) -> None:
        result = loader.load_language_queries("   ")
        assert result == {}

    def test_tab_only_language_returns_empty(self, loader: QueryLoader) -> None:
        result = loader.load_language_queries("\t")
        assert result == {}

    def test_string_none_language_returns_empty(self, loader: QueryLoader) -> None:
        result = loader.load_language_queries("None")
        assert result == {}


# ---------------------------------------------------------------------------
# Line 68: early return when language is in _failed_languages
# ---------------------------------------------------------------------------


class TestFailedLanguageCache:
    """Cover the _failed_languages short-circuit."""

    def test_failed_language_returns_empty_without_reimport(
        self, loader: QueryLoader
    ) -> None:
        loader._failed_languages.add("cobol")

        with patch("importlib.import_module") as mock_import:
            result = loader.load_language_queries("cobol")
            mock_import.assert_not_called()

        assert result == {}


# ---------------------------------------------------------------------------
# Lines 82-92: module attribute fallback paths
# ---------------------------------------------------------------------------


class TestModuleAttributeFallbacks:
    """Cover ALL_QUERIES path and the generic dir() fallback."""

    @staticmethod
    def _make_module(**attrs: object) -> types.ModuleType:
        """Create a fake module with the given public attributes."""
        mod = types.ModuleType("fake_query_module")
        for key, value in attrs.items():
            setattr(mod, key, value)
        return mod

    def test_module_with_all_queries_dict(self, loader: QueryLoader) -> None:
        """Module exposes ALL_QUERIES (a dict) -- line 82-83."""
        fake_module = self._make_module(
            ALL_QUERIES={"custom": "(custom_node) @c"},
        )
        with patch("importlib.import_module", return_value=fake_module):
            result = loader.load_language_queries("fakelang")
        assert "custom" in result

    def test_module_with_get_all_queries_function(
        self, loader: QueryLoader
    ) -> None:
        """Module exposes get_all_queries() -- line 80-81."""
        fake_module = self._make_module(
            get_all_queries=lambda: {"func_query": "(func) @f"},
        )
        with patch("importlib.import_module", return_value=fake_module):
            result = loader.load_language_queries("fakelang")
        assert "func_query" in result

    def test_module_with_neither_all_queries_nor_get_all(
        self, loader: QueryLoader
    ) -> None:
        """Module has neither get_all_queries nor ALL_QUERIES -- lines 84-92.

        The fallback scans dir() for string and dict public attributes.
        """
        fake_module = self._make_module(
            my_string_query="(my_node) @my",
            my_dict_group={"group_a": "(ga) @ga"},
        )
        # Remove the two recognised attributes so the else branch is taken
        if hasattr(fake_module, "get_all_queries"):
            del fake_module.get_all_queries
        if hasattr(fake_module, "ALL_QUERIES"):
            del fake_module.ALL_QUERIES

        with patch("importlib.import_module", return_value=fake_module):
            result = loader.load_language_queries("fakelang")
        assert "my_string_query" in result
        assert "group_a" in result

    def test_module_dir_ignores_private_attrs(self, loader: QueryLoader) -> None:
        """Private attributes (starting with _) should be skipped in fallback."""
        fake_module = self._make_module(
            _private_thing="should_not_appear",
            public_thing="(pub) @p",
        )
        if hasattr(fake_module, "get_all_queries"):
            del fake_module.get_all_queries
        if hasattr(fake_module, "ALL_QUERIES"):
            del fake_module.ALL_QUERIES

        with patch("importlib.import_module", return_value=fake_module):
            result = loader.load_language_queries("fakelang")
        assert "_private_thing" not in result
        assert "public_thing" in result


# ---------------------------------------------------------------------------
# Lines 102-106: generic Exception during module import
# ---------------------------------------------------------------------------


class TestGenericExceptionOnImport:
    """Cover the except-Exception handler that logs and records failure."""

    def test_non_import_exception_adds_to_failed_and_returns_empty(
        self, loader: QueryLoader
    ) -> None:
        original_import = importlib.import_module

        def selective_import(name: str) -> object:
            if "badlang" in name:
                raise RuntimeError("boom")
            return original_import(name)

        with (
            patch("tree_sitter_analyzer.query_loader.log_error") as mock_log,
            patch("tree_sitter_analyzer.query_loader.importlib.import_module", side_effect=selective_import),
        ):
            result = loader.load_language_queries("badlang")

        assert result == {}
        assert "badlang" in loader._failed_languages
        mock_log.assert_called_once()

    def test_subsequent_call_uses_failed_cache(
        self, loader: QueryLoader
    ) -> None:
        """After a failure, second call must hit the _failed_languages path."""
        original_import = importlib.import_module

        def selective_import(name: str) -> object:
            if "badlang2" in name:
                raise RuntimeError("boom")
            return original_import(name)

        with patch(
            "tree_sitter_analyzer.query_loader.importlib.import_module", side_effect=selective_import
        ):
            loader.load_language_queries("badlang2")

        # Second call -- import_module should NOT be invoked again
        with patch("tree_sitter_analyzer.query_loader.importlib.import_module") as mock_import:
            result = loader.load_language_queries("badlang2")
            mock_import.assert_not_called()

        assert result == {}


# ---------------------------------------------------------------------------
# Lines 120-121: get_query with string query value
# ---------------------------------------------------------------------------


class TestGetQueryStringValue:
    """Cover the `elif isinstance(query_info, str)` branch in get_query."""

    def test_returns_string_query_directly(self, loader: QueryLoader) -> None:
        # Java predefined queries are plain strings in _PREDEFINED_QUERIES
        loader._loaded_queries["java"] = {"my_q": "(something) @s"}
        assert loader.get_query("java", "my_q") == "(something) @s"

    def test_returns_query_from_dict_form(self, loader: QueryLoader) -> None:
        """Cover the `isinstance(query_info, dict) and 'query' in ...` branch."""
        loader._loaded_queries["java"] = {
            "dict_q": {"query": "(d) @d", "description": "desc"}
        }
        assert loader.get_query("java", "dict_q") == "(d) @d"

    def test_returns_none_for_unknown_query_name(
        self, loader: QueryLoader
    ) -> None:
        loader._loaded_queries["java"] = {"existing": "(e) @e"}
        assert loader.get_query("java", "nonexistent") is None


# ---------------------------------------------------------------------------
# Lines 129, 136: get_query_description branches
# ---------------------------------------------------------------------------


class TestGetQueryDescriptionBranches:
    """Cover predefined description path and fallback description string."""

    def test_predefined_description_returned(self, loader: QueryLoader) -> None:
        """Line 129 -- query_name is in _QUERY_DESCRIPTIONS."""
        desc = loader.get_query_description("java", "method")
        assert desc is not None
        assert "method" in desc.lower() or "Extract" in desc

    def test_fallback_description_for_unknown_query_name(
        self, loader: QueryLoader
    ) -> None:
        """Line 136 -- query is found in loaded queries but not in _QUERY_DESCRIPTIONS."""
        loader._loaded_queries["java"] = {"weird_q": "(w) @w"}
        desc = loader.get_query_description("java", "weird_q")
        # Should return the generic fallback string
        assert desc is not None
        assert "weird_q" in desc

    def test_description_from_dict_query_info(self, loader: QueryLoader) -> None:
        """Cover dict form with 'description' key in query_info."""
        loader._loaded_queries["java"] = {
            "special": {"query": "(s) @s", "description": "My special query"}
        }
        desc = loader.get_query_description("java", "special")
        assert desc == "My special query"

    def test_returns_none_for_completely_unknown(
        self, loader: QueryLoader
    ) -> None:
        desc = loader.get_query_description("java", "absolutely_missing")
        assert desc is None


# ---------------------------------------------------------------------------
# Lines 179, 184-185: list_supported_languages with failed languages
# ---------------------------------------------------------------------------


class TestListSupportedLanguagesFailed:
    """Cover the failed-languages guard in list_supported_languages."""

    def test_skips_failed_language(self, loader: QueryLoader) -> None:
        """Line 179 -- language in _failed_languages is skipped."""
        loader._failed_languages.add("java")
        languages = loader.list_supported_languages()
        assert "java" not in languages

    def test_import_error_adds_to_failed_languages(
        self, loader: QueryLoader
    ) -> None:
        """Lines 184-185 -- ImportError records language as failed."""
        real_import = importlib.import_module
        call_count = {"n": 0}

        def selective_import(name: str) -> object:
            # Allow the first few calls to succeed (for "java" which is
            # listed first in known_languages).  Then make the rest fail
            # with ImportError so they get recorded in _failed_languages.
            call_count["n"] += 1
            # Let the very first import succeed to verify the success path
            if call_count["n"] == 1:
                return real_import(name)
            raise ImportError("nope")

        with patch("tree_sitter_analyzer.query_loader.importlib.import_module", side_effect=selective_import):
            languages = loader.list_supported_languages()

        # The first language (java) should succeed; the rest fail
        assert "java" in languages
        # At least one language should be in _failed_languages
        assert len(loader._failed_languages) > 0


# ---------------------------------------------------------------------------
# Line 210: get_all_queries_for_language string branch
# ---------------------------------------------------------------------------


class TestGetAllQueriesForLanguageStringBranch:
    """Cover the `elif isinstance(query_info, str)` branch (line 210-211)."""

    def test_string_query_produces_tuple(self, loader: QueryLoader) -> None:
        loader._loaded_queries["java"] = {"my_str_q": "(x) @x"}
        result = loader.get_all_queries_for_language("java")
        assert "my_str_q" in result
        query_str, desc = result["my_str_q"]
        assert query_str == "(x) @x"
        assert "my_str_q" in desc

    def test_dict_query_produces_tuple(self, loader: QueryLoader) -> None:
        loader._loaded_queries["java"] = {
            "my_dict_q": {"query": "(d) @d", "description": "a dict query"}
        }
        result = loader.get_all_queries_for_language("java")
        assert result["my_dict_q"] == ("(d) @d", "a dict query")


# ---------------------------------------------------------------------------
# Line 225: is_language_supported checks _failed_languages
# ---------------------------------------------------------------------------


class TestIsLanguageSupportedFailed:
    """Cover the _failed_languages short-circuit in is_language_supported."""

    def test_returns_false_for_failed_language(
        self, loader: QueryLoader
    ) -> None:
        loader._failed_languages.add("java")
        assert loader.is_language_supported("java") is False


# ---------------------------------------------------------------------------
# Lines 230-237: preload_languages
# ---------------------------------------------------------------------------


class TestPreloadLanguages:
    """Cover the preload_languages method including its exception handler."""

    def test_preload_returns_dict_of_booleans(
        self, loader: QueryLoader
    ) -> None:
        result = loader.preload_languages(["java", "unknown_language_xyz"])
        assert isinstance(result, dict)
        assert "java" in result
        assert "unknown_language_xyz" in result
        assert result["java"] is True
        assert result["unknown_language_xyz"] is False

    def test_preload_handles_exception(self, loader: QueryLoader) -> None:
        """Exception inside load_language_queries should be caught."""
        with patch.object(
            loader,
            "load_language_queries",
            side_effect=RuntimeError("unexpected"),
        ):
            result = loader.preload_languages(["crashlang"])
        assert result["crashlang"] is False

    def test_preload_empty_list(self, loader: QueryLoader) -> None:
        result = loader.preload_languages([])
        assert result == {}


# ---------------------------------------------------------------------------
# Additional edge cases for list_queries_for_language and get_query
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Various boundary conditions not covered elsewhere."""

    def test_get_query_with_empty_language(self, loader: QueryLoader) -> None:
        assert loader.get_query("", "anything") is None

    def test_get_query_with_none_language(self, loader: QueryLoader) -> None:
        assert loader.get_query(None, "anything") is None

    def test_list_queries_for_language_whitespace(
        self, loader: QueryLoader
    ) -> None:
        assert loader.list_queries_for_language("   ") == []

    def test_list_queries_for_language_none(
        self, loader: QueryLoader
    ) -> None:
        assert loader.list_queries_for_language(None) == []

    def test_list_queries_delegates_to_list_queries_for_language(
        self, loader: QueryLoader
    ) -> None:
        assert loader.list_queries("java") == loader.list_queries_for_language("java")

    def test_load_language_queries_caches_result(
        self, loader: QueryLoader
    ) -> None:
        """Second call returns the same dict object (from cache)."""
        first = loader.load_language_queries("java")
        second = loader.load_language_queries("java")
        assert first is second

    def test_refresh_clears_all_caches(self, loader: QueryLoader) -> None:
        loader.load_language_queries("java")
        assert len(loader._loaded_queries) > 0

        loader.refresh_cache()
        assert len(loader._loaded_queries) == 0
        assert len(loader._query_modules) == 0
        assert len(loader._failed_languages) == 0

    def test_get_query_loader_singleton(self) -> None:
        """get_query_loader should return the same instance."""
        # Reset singleton for test isolation
        import tree_sitter_analyzer.query_loader as ql_mod

        ql_mod._query_loader_instance = None
        try:
            a = get_query_loader()
            b = get_query_loader()
            assert a is b
        finally:
            ql_mod._query_loader_instance = None
