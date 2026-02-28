#!/usr/bin/env python3
"""
Unit tests for query accessor functions in all language query modules.

Covers: queries.c, queries.cpp, queries.javascript, queries.python
Functions: get_X_query, get_X_query_description, get_available_X_queries,
           get_query, get_all_queries, list_queries
"""

import pytest


# ---------------------------------------------------------------------------
# C query accessors
# ---------------------------------------------------------------------------


class TestCQueryAccessors:
    """Tests for tree_sitter_analyzer.queries.c accessor functions."""

    def setup_method(self):
        from tree_sitter_analyzer.queries.c import (
            ALL_QUERIES,
            C_QUERIES,
            C_QUERY_DESCRIPTIONS,
            get_all_queries,
            get_available_c_queries,
            get_c_query,
            get_c_query_description,
            get_query,
            list_queries,
        )

        self.C_QUERIES = C_QUERIES
        self.C_QUERY_DESCRIPTIONS = C_QUERY_DESCRIPTIONS
        self.ALL_QUERIES = ALL_QUERIES
        self.get_c_query = get_c_query
        self.get_c_query_description = get_c_query_description
        self.get_available_c_queries = get_available_c_queries
        self.get_query = get_query
        self.get_all_queries = get_all_queries
        self.list_queries = list_queries

    def test_get_c_query_returns_string(self):
        first = next(iter(self.C_QUERIES))
        result = self.get_c_query(first)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_get_c_query_known_names(self):
        for name in ("function", "struct", "include"):
            q = self.get_c_query(name)
            assert isinstance(q, str) and len(q.strip()) > 0

    def test_get_c_query_raises_for_unknown(self):
        with pytest.raises(ValueError, match="does not exist"):
            self.get_c_query("nonexistent_query_xyz")

    def test_get_c_query_description_returns_string(self):
        for name in self.C_QUERIES:
            desc = self.get_c_query_description(name)
            assert isinstance(desc, str)

    def test_get_c_query_description_unknown_returns_fallback(self):
        desc = self.get_c_query_description("nonexistent_xyz")
        assert isinstance(desc, str)

    def test_get_available_c_queries_returns_list(self):
        available = self.get_available_c_queries()
        assert isinstance(available, list)
        assert len(available) > 0

    def test_get_available_c_queries_contains_core_names(self):
        available = self.get_available_c_queries()
        for name in ("function", "struct", "include"):
            assert name in available

    def test_get_query_returns_string(self):
        first = next(iter(self.ALL_QUERIES))
        result = self.get_query(first)
        assert isinstance(result, str) and len(result.strip()) > 0

    def test_get_query_raises_for_unknown(self):
        with pytest.raises(ValueError):
            self.get_query("__totally_nonexistent__")

    def test_get_all_queries_returns_dict(self):
        result = self.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list_of_strings(self):
        names = self.list_queries()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)


# ---------------------------------------------------------------------------
# C++ query accessors
# ---------------------------------------------------------------------------


class TestCppQueryAccessors:
    """Tests for tree_sitter_analyzer.queries.cpp accessor functions."""

    def setup_method(self):
        from tree_sitter_analyzer.queries.cpp import (
            ALL_QUERIES,
            CPP_QUERIES,
            CPP_QUERY_DESCRIPTIONS,
            get_all_queries,
            get_available_cpp_queries,
            get_cpp_query,
            get_cpp_query_description,
            get_query,
            list_queries,
        )

        self.CPP_QUERIES = CPP_QUERIES
        self.CPP_QUERY_DESCRIPTIONS = CPP_QUERY_DESCRIPTIONS
        self.ALL_QUERIES = ALL_QUERIES
        self.get_cpp_query = get_cpp_query
        self.get_cpp_query_description = get_cpp_query_description
        self.get_available_cpp_queries = get_available_cpp_queries
        self.get_query = get_query
        self.get_all_queries = get_all_queries
        self.list_queries = list_queries

    def test_get_cpp_query_returns_string(self):
        first = next(iter(self.CPP_QUERIES))
        result = self.get_cpp_query(first)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_get_cpp_query_known_names(self):
        for name in ("function", "class", "include"):
            q = self.get_cpp_query(name)
            assert isinstance(q, str) and len(q.strip()) > 0

    def test_get_cpp_query_raises_for_unknown(self):
        with pytest.raises(ValueError, match="does not exist"):
            self.get_cpp_query("nonexistent_query_xyz")

    def test_get_cpp_query_description_returns_string(self):
        for name in self.CPP_QUERIES:
            desc = self.get_cpp_query_description(name)
            assert isinstance(desc, str)

    def test_get_cpp_query_description_unknown_returns_fallback(self):
        desc = self.get_cpp_query_description("nonexistent_xyz")
        assert isinstance(desc, str)

    def test_get_available_cpp_queries_returns_list(self):
        available = self.get_available_cpp_queries()
        assert isinstance(available, list)
        assert len(available) > 0

    def test_get_available_cpp_queries_contains_core_names(self):
        available = self.get_available_cpp_queries()
        for name in ("function", "class", "include"):
            assert name in available, f"'{name}' not in available C++ queries"

    def test_get_query_returns_string(self):
        first = next(iter(self.ALL_QUERIES))
        result = self.get_query(first)
        assert isinstance(result, str) and len(result.strip()) > 0

    def test_get_query_raises_for_unknown(self):
        with pytest.raises(ValueError):
            self.get_query("__totally_nonexistent__")

    def test_get_all_queries_returns_dict(self):
        result = self.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list_of_strings(self):
        names = self.list_queries()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)


# ---------------------------------------------------------------------------
# JavaScript query accessors
# ---------------------------------------------------------------------------


class TestJavaScriptQueryAccessors:
    """Tests for tree_sitter_analyzer.queries.javascript accessor functions."""

    def setup_method(self):
        from tree_sitter_analyzer.queries.javascript import (
            ALL_QUERIES,
            JAVASCRIPT_QUERIES,
            JAVASCRIPT_QUERY_DESCRIPTIONS,
            get_all_queries,
            get_available_javascript_queries,
            get_javascript_query,
            get_javascript_query_description,
            get_query,
            list_queries,
        )

        self.JAVASCRIPT_QUERIES = JAVASCRIPT_QUERIES
        self.JAVASCRIPT_QUERY_DESCRIPTIONS = JAVASCRIPT_QUERY_DESCRIPTIONS
        self.ALL_QUERIES = ALL_QUERIES
        self.get_javascript_query = get_javascript_query
        self.get_javascript_query_description = get_javascript_query_description
        self.get_available_javascript_queries = get_available_javascript_queries
        self.get_query = get_query
        self.get_all_queries = get_all_queries
        self.list_queries = list_queries

    def test_get_javascript_query_returns_string(self):
        first = next(iter(self.JAVASCRIPT_QUERIES))
        result = self.get_javascript_query(first)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_get_javascript_query_raises_for_unknown(self):
        with pytest.raises(ValueError, match="does not exist"):
            self.get_javascript_query("nonexistent_query_xyz")

    def test_get_javascript_query_description_returns_string(self):
        for name in self.JAVASCRIPT_QUERIES:
            desc = self.get_javascript_query_description(name)
            assert isinstance(desc, str)

    def test_get_javascript_query_description_unknown_returns_fallback(self):
        desc = self.get_javascript_query_description("nonexistent_xyz")
        assert isinstance(desc, str)

    def test_get_available_javascript_queries_returns_list(self):
        available = self.get_available_javascript_queries()
        assert isinstance(available, list)
        assert len(available) > 0

    def test_get_available_javascript_queries_matches_queries_dict(self):
        available = self.get_available_javascript_queries()
        assert set(available) == set(self.JAVASCRIPT_QUERIES.keys())

    def test_get_query_returns_string(self):
        first = next(iter(self.ALL_QUERIES))
        result = self.get_query(first)
        assert isinstance(result, str) and len(result.strip()) > 0

    def test_get_query_raises_for_unknown(self):
        with pytest.raises(ValueError):
            self.get_query("__totally_nonexistent__")

    def test_get_all_queries_returns_dict(self):
        result = self.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list_of_strings(self):
        names = self.list_queries()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)


# ---------------------------------------------------------------------------
# Python query accessors
# ---------------------------------------------------------------------------


class TestPythonQueryAccessors:
    """Tests for tree_sitter_analyzer.queries.python accessor functions."""

    def setup_method(self):
        from tree_sitter_analyzer.queries.python import (
            ALL_QUERIES,
            PYTHON_QUERIES,
            PYTHON_QUERY_DESCRIPTIONS,
            get_all_queries,
            get_available_python_queries,
            get_python_query,
            get_python_query_description,
            get_query,
            list_queries,
        )

        self.PYTHON_QUERIES = PYTHON_QUERIES
        self.PYTHON_QUERY_DESCRIPTIONS = PYTHON_QUERY_DESCRIPTIONS
        self.ALL_QUERIES = ALL_QUERIES
        self.get_python_query = get_python_query
        self.get_python_query_description = get_python_query_description
        self.get_available_python_queries = get_available_python_queries
        self.get_query = get_query
        self.get_all_queries = get_all_queries
        self.list_queries = list_queries

    def test_get_python_query_returns_string(self):
        first = next(iter(self.PYTHON_QUERIES))
        result = self.get_python_query(first)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_get_python_query_known_names(self):
        for name in ("function", "class", "import"):
            q = self.get_python_query(name)
            assert isinstance(q, str) and len(q.strip()) > 0

    def test_get_python_query_raises_for_unknown(self):
        with pytest.raises(ValueError, match="does not exist"):
            self.get_python_query("nonexistent_query_xyz")

    def test_get_python_query_description_returns_string(self):
        for name in self.PYTHON_QUERIES:
            desc = self.get_python_query_description(name)
            assert isinstance(desc, str)

    def test_get_python_query_description_unknown_returns_fallback(self):
        desc = self.get_python_query_description("nonexistent_xyz")
        assert isinstance(desc, str)

    def test_get_available_python_queries_returns_list(self):
        available = self.get_available_python_queries()
        assert isinstance(available, list)
        assert len(available) > 0

    def test_get_available_python_queries_contains_core_names(self):
        available = self.get_available_python_queries()
        for name in ("function", "class", "import"):
            assert name in available, f"'{name}' not in available Python queries"

    def test_get_query_returns_string(self):
        first = next(iter(self.ALL_QUERIES))
        result = self.get_query(first)
        assert isinstance(result, str) and len(result.strip()) > 0

    def test_get_query_raises_for_unknown(self):
        with pytest.raises(ValueError):
            self.get_query("__totally_nonexistent__")

    def test_get_all_queries_returns_dict(self):
        result = self.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list_of_strings(self):
        names = self.list_queries()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_all_queries_dict_has_query_and_description_keys(self):
        all_q = self.get_all_queries()
        for name, entry in all_q.items():
            assert "query" in entry, f"Entry '{name}' missing 'query' key"
            assert "description" in entry, f"Entry '{name}' missing 'description' key"
