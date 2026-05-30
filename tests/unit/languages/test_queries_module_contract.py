"""Parametrized contract tests for CSS, HTML, and SQL query modules.

Replaces the structural boilerplate that was duplicated across:
  - test_queries_css_comprehensive.py  (identical API tests)
  - test_queries_html_comprehensive.py (identical API tests)
  - test_queries_sql.py                (identical API tests)

Language-specific query-name assertions stay in their original files.
"""

from __future__ import annotations

import types

import pytest

from tree_sitter_analyzer.queries import css, html, sql

_MODULES = [
    pytest.param(css, id="css"),
    pytest.param(html, id="html"),
    pytest.param(sql, id="sql"),
]


def _queries_dict(mod: types.ModuleType) -> dict:
    """Return the language-specific LANG_QUERIES dict."""
    for attr in dir(mod):
        if attr.endswith("_QUERIES") and not attr.startswith("ALL"):
            return getattr(mod, attr)
    return {}


def _descriptions_dict(mod: types.ModuleType) -> dict:
    for attr in dir(mod):
        if attr.endswith("_QUERY_DESCRIPTIONS"):
            return getattr(mod, attr)
    return {}


@pytest.mark.parametrize("mod", _MODULES)
class TestQueryModuleContract:
    """Every query module must satisfy these 10 invariants."""

    def test_lang_queries_dict_nonempty(self, mod: types.ModuleType) -> None:
        d = _queries_dict(mod)
        assert isinstance(d, dict) and d, (
            f"{mod.__name__} LANG_QUERIES must not be empty"
        )

    def test_descriptions_dict_nonempty(self, mod: types.ModuleType) -> None:
        d = _descriptions_dict(mod)
        assert isinstance(d, dict) and d, (
            f"{mod.__name__} LANG_QUERY_DESCRIPTIONS must not be empty"
        )

    def test_all_queries_dict_exists(self, mod: types.ModuleType) -> None:
        assert isinstance(mod.ALL_QUERIES, dict) and mod.ALL_QUERIES

    def test_all_queries_have_descriptions(self, mod: types.ModuleType) -> None:
        descs = _descriptions_dict(mod)
        for name in _queries_dict(mod):
            assert name in descs, f"Query {name!r} has no description"
            assert isinstance(descs[name], str) and descs[name].strip()

    def test_all_queries_have_nonempty_strings(self, mod: types.ModuleType) -> None:
        for name, q in _queries_dict(mod).items():
            assert isinstance(q, str) and q.strip(), f"Query {name!r} is empty"

    def test_get_all_queries_returns_dict(self, mod: types.ModuleType) -> None:
        result = mod.get_all_queries()
        assert isinstance(result, dict) and result

    def test_list_queries_returns_nonempty_list(self, mod: types.ModuleType) -> None:
        result = mod.list_queries()
        assert isinstance(result, list) and result
        assert len(result) == len(set(result)), (
            "list_queries() must not have duplicates"
        )

    def test_get_query_valid_key(self, mod: types.ModuleType) -> None:
        first_key = next(iter(_queries_dict(mod)))
        result = mod.get_query(first_key)
        assert isinstance(result, str) and result

    def test_get_query_invalid_key_raises(self, mod: types.ModuleType) -> None:
        with pytest.raises((ValueError, KeyError)):
            mod.get_query("NONEXISTENT_QUERY_XYZ_123")

    def test_all_query_strings_have_capture_syntax(self, mod: types.ModuleType) -> None:
        for name, q in _queries_dict(mod).items():
            assert "@" in q, f"Query {name!r} missing tree-sitter capture '@'"
