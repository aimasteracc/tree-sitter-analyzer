"""Tests for FTS5 fast path integration in search_content."""

from __future__ import annotations

import asyncio
import os

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools._fts_fast_path import (
    _is_fts_eligible,
    try_fts5_fast_path,
)


def _write_py_file(directory: str, name: str, content: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestIsFtsEligible:
    def test_simple_identifier(self):
        assert _is_fts_eligible({"query": "my_function"}) is True

    def test_identifier_with_underscore(self):
        assert _is_fts_eligible({"query": "_private_method"}) is True

    def test_camel_case(self):
        assert _is_fts_eligible({"query": "MyClass"}) is True

    def test_regex_pattern_rejected(self):
        assert _is_fts_eligible({"query": "foo.*bar"}) is False

    def test_empty_query_rejected(self):
        assert _is_fts_eligible({"query": ""}) is False

    def test_query_with_spaces_rejected(self):
        assert _is_fts_eligible({"query": "foo bar"}) is False

    def test_fixed_strings_rejected(self):
        assert _is_fts_eligible({"query": "foo", "fixed_strings": True}) is False

    def test_word_flag_rejected(self):
        assert _is_fts_eligible({"query": "foo", "word": True}) is False

    def test_multiline_rejected(self):
        assert _is_fts_eligible({"query": "foo", "multiline": True}) is False

    def test_context_before_rejected(self):
        assert _is_fts_eligible({"query": "foo", "context_before": 3}) is False

    def test_context_after_rejected(self):
        assert _is_fts_eligible({"query": "foo", "context_after": 3}) is False

    def test_include_globs_rejected(self):
        assert _is_fts_eligible({"query": "foo", "include_globs": ["*.py"]}) is False

    def test_exclude_globs_rejected(self):
        assert _is_fts_eligible({"query": "foo", "exclude_globs": ["test_*"]}) is False

    def test_plain_extensions_allowed(self):
        assert _is_fts_eligible({"query": "foo", "extensions": ["py"]}) is True

    def test_no_query_key(self):
        assert _is_fts_eligible({}) is False


class TestTryFts5FastPath:
    def test_returns_none_when_no_index(self, tmp_path):
        result = try_fts5_fast_path(
            {"query": "MyClass"},
            str(tmp_path),
            "normal",
        )
        assert result is None

    def test_returns_none_for_regex_query(self, tmp_path):
        result = try_fts5_fast_path(
            {"query": "foo.*bar"},
            str(tmp_path),
            "normal",
        )
        assert result is None

    def test_returns_none_when_no_project_root(self, tmp_path):
        result = try_fts5_fast_path(
            {"query": "MyClass"},
            None,
            "normal",
        )
        assert result is None

    def test_finds_symbol_from_index(self, tmp_path):
        _write_py_file(
            str(tmp_path),
            "example.py",
            "class MyClass:\n    def my_method(self):\n        pass\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=100)
        stats = cache.get_stats()
        assert stats["total_files"] == 1
        cache.close()

        result = try_fts5_fast_path(
            {"query": "MyClass"},
            str(tmp_path),
            "normal",
        )
        assert result is not None
        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["data_source"] == "fts5"
        assert result["total_matches"] == 1
        found_names = [r["name"] for r in result["results"]]
        assert "MyClass" in found_names

    def test_total_only_mode_returns_dict(self, tmp_path):
        _write_py_file(
            str(tmp_path),
            "app.py",
            "def handler():\n    pass\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=100)
        cache.close()

        result = try_fts5_fast_path(
            {"query": "handler"},
            str(tmp_path),
            "total_only",
        )
        # total_only returns a success envelope dict with total_matches count
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert result.get("total_matches") == 1

    def test_count_only_mode(self, tmp_path):
        _write_py_file(
            str(tmp_path),
            "app.py",
            "def handler():\n    pass\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=100)
        cache.close()

        result = try_fts5_fast_path(
            {"query": "handler"},
            str(tmp_path),
            "count_only",
        )
        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["data_source"] == "fts5"
        assert "files" in result

    def test_summary_mode(self, tmp_path):
        _write_py_file(
            str(tmp_path),
            "app.py",
            "def my_func():\n    pass\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=100)
        cache.close()

        result = try_fts5_fast_path(
            {"query": "my_func"},
            str(tmp_path),
            "summary",
        )
        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["data_source"] == "fts5"
        assert "files" in result

    def test_no_match_returns_none(self, tmp_path):
        _write_py_file(
            str(tmp_path),
            "app.py",
            "def existing_func():\n    pass\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=100)
        cache.close()

        result = try_fts5_fast_path(
            {"query": "nonexistent_symbol_xyz"},
            str(tmp_path),
            "normal",
        )
        assert result is None

    def test_language_filter_via_extensions(self, tmp_path):
        _write_py_file(
            str(tmp_path),
            "app.py",
            "def my_func():\n    pass\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=100)
        cache.close()

        result = try_fts5_fast_path(
            {"query": "my_func", "extensions": ["py"]},
            str(tmp_path),
            "normal",
        )
        assert result is not None
        assert result["success"] is True
        assert result.get("language_filter") == "python"

    def test_multifile_search(self, tmp_path):
        _write_py_file(str(tmp_path), "a.py", "def alpha():\n    pass\n")
        _write_py_file(str(tmp_path), "b.py", "def beta():\n    pass\n")
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=100)
        cache.close()

        result = try_fts5_fast_path(
            {"query": "alpha"},
            str(tmp_path),
            "normal",
        )
        assert result is not None
        assert result["total_matches"] == 1


class TestSearchContentFtsIntegration:
    def _setup_indexed_project(self, tmp_path):
        _write_py_file(
            str(tmp_path),
            "example.py",
            "class MyWidget:\n    def render(self):\n        pass\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=100)
        cache.close()

    def test_search_content_uses_fts_for_simple_query(self, tmp_path):
        self._setup_indexed_project(tmp_path)
        from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

        tool = SearchContentTool(project_root=str(tmp_path))

        result = asyncio.run(
            tool.execute(
                {
                    "query": "MyWidget",
                    "roots": [str(tmp_path)],
                }
            )
        )
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert result.get("data_source") == "fts5"

    def test_search_content_falls_through_for_regex(self, tmp_path):
        _write_py_file(str(tmp_path), "example.py", "def foo():\n    pass\n")
        from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

        tool = SearchContentTool(project_root=str(tmp_path))
        result = asyncio.run(
            tool.execute(
                {
                    "query": "foo.*bar",
                    "roots": [str(tmp_path)],
                }
            )
        )
        assert isinstance(result, dict)
        assert result.get("data_source") != "fts5"
