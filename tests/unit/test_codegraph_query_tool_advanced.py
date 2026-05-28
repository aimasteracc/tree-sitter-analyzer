"""Tests for CodeGraphQueryTool advanced flows: filters, concept fallback, batch, sort, answer."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from tests.unit._codegraph_query_helpers import _make_def, _patch_resolver_with
from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    CodeGraphQueryTool,
)


class TestCodeGraphQueryToolAdvanced:
    @pytest.mark.asyncio
    async def test_execute_filter_applies_to_later_concept_fallback(self, tmp_path):
        router = tmp_path / "router.py"
        router.write_text(
            "def handle_route():\n    # route matching lives here\n    return True\n",
            encoding="utf-8",
        )
        service = tmp_path / "service.py"
        service.write_text(
            "def handle_service():\n    # route matching should be filtered\n    return True\n",
            encoding="utf-8",
        )
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT,
                language TEXT,
                file_size INTEGER,
                symbols_json TEXT
            )"""
        )
        for path, symbol_name in (
            (router, "handle_route"),
            (service, "handle_service"),
        ):
            conn.execute(
                "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
                (
                    path.name,
                    "python",
                    path.stat().st_size,
                    json.dumps(
                        {
                            "symbols": [
                                {
                                    "name": symbol_name,
                                    "kind": "function",
                                    "line": 1,
                                    "end_line": 3,
                                }
                            ]
                        }
                    ),
                ),
            )
        mock_cache = MagicMock()
        mock_cache.get_conn.return_value = conn
        mock_cache._get_conn.return_value = conn  # backward-compat alias

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with({}),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search('route matching').filter(file='router.py')"
                        ".include(source=True).answer(compact=True)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["verdict"] == "INFO"
        assert result["stats"]["concept_files_returned"] == 1
        assert [symbol["file"] for symbol in result["symbols"]] == ["router.py"]
        assert [file["file"] for file in result["facets"]["source"]["files"]] == [
            "router.py"
        ]

    @pytest.mark.asyncio
    async def test_execute_symbol_filter_applies_to_later_concept_fallback(
        self, tmp_path
    ):
        source = tmp_path / "router.py"
        source.write_text(
            "class Router:\n    pass\n\ndef handle_route():\n    return Router()\n",
            encoding="utf-8",
        )
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT,
                language TEXT,
                file_size INTEGER,
                symbols_json TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
            (
                "router.py",
                "python",
                source.stat().st_size,
                json.dumps(
                    {
                        "symbols": [
                            {
                                "name": "Router",
                                "kind": "class",
                                "line": 1,
                                "end_line": 2,
                            },
                            {
                                "name": "handle_route",
                                "kind": "function",
                                "line": 4,
                                "end_line": 5,
                            },
                        ]
                    }
                ),
            ),
        )
        mock_cache = MagicMock()
        mock_cache.get_conn.return_value = conn
        mock_cache._get_conn.return_value = conn  # backward-compat alias

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with({}),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search('route').filter(kind='function')"
                        ".include(source=True).answer(compact=True)"
                    ),
                    "output_format": "json",
                }
            )

        source_symbols = result["facets"]["source"]["files"][0]["symbols"]
        assert [symbol["name"] for symbol in source_symbols] == ["handle_route"]

    @pytest.mark.asyncio
    async def test_execute_batch_seed_include_sort_and_answer(self, tmp_path):
        source = tmp_path / "main.py"
        source.write_text(
            "def run():\n    return helper()\n\ndef helper():\n    return 1\n",
            encoding="utf-8",
        )
        mock_cache = MagicMock()
        mock_cache.query_callers.return_value = [
            {
                "caller_name": "entry",
                "caller_file": "tests/test_main.py",
                "caller_line": 8,
                "depth": 1,
            }
        ]
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "helper",
                "callee_file": "main.py",
                "callee_line": 4,
                "depth": 1,
            }
        ]

        defs = {
            "run": [_make_def(file="main.py", name="run", line=1)],
            "helper": [_make_def(file="main.py", name="helper", line=4)],
        }

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search(['run', 'helper']).explore(max_files=2)"
                        ".include(source=True, callers=True, callees=True, "
                        "affected_tests=True, risk=True)"
                        ".sort(by='fan_in', desc=True).answer()"
                    ),
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["stats"]["facets_returned"] == 5
        assert result["facets"]["source"]["file_count"] == 1
        assert result["facets"]["callers"]["edges"]
        assert result["facets"]["callees"]["edges"]
        assert result["facets"]["affected_tests"]["files"] == ["tests/test_main.py"]
        assert result["facets"]["risk"]["level"] == "info"
        assert result["normalized_chain"][-1]["name"] == "answer"

    @pytest.mark.asyncio
    async def test_execute_compact_answer_removes_duplicate_source_payload(
        self, tmp_path
    ):
        source = tmp_path / "main.py"
        source.write_text(
            "def run():\n    return helper()\n\ndef helper():\n    return 1\n",
            encoding="utf-8",
        )
        mock_cache = MagicMock()
        mock_cache.query_callers.return_value = []
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "helper",
                "callee_file": "main.py",
                "callee_line": 4,
                "depth": 1,
            }
        ]
        defs = {"run": [_make_def(file="main.py", name="run", line=1)]}

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search('run').explore(max_files=1)"
                        ".include(source=True, callees=True).answer(compact=True)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["stats"]["compact"] is True
        assert result["files"] == []
        assert result["facets"]["source"]["files"][0]["file"] == "main.py"
        assert result["facets"]["source"]["files"][0]["symbols"][0]["lines"] == "1-2"
        assert "language" not in result["relationships"]["callees"]["main.py:1:run"][0]

    @pytest.mark.asyncio
    async def test_execute_filter_narrows_current_selection_and_rebuilds_source(
        self, tmp_path
    ):
        source = tmp_path / "src" / "main.py"
        source.parent.mkdir()
        source.write_text("def run():\n    return 1\n", encoding="utf-8")
        test_source = tmp_path / "tests" / "test_main.py"
        test_source.parent.mkdir()
        test_source.write_text("def run():\n    return 1\n", encoding="utf-8")
        defs = {
            "run": [
                _make_def(file="src/main.py", name="run", line=1),
                _make_def(file="tests/test_main.py", name="run", line=1),
            ]
        }

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search('run').explore(max_files=5)"
                        ".filter(path='src/', test=False)"
                        ".include(source=True).answer(compact=True)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert [symbol["file"] for symbol in result["symbols"]] == ["src/main.py"]
        assert result["files"] == []
        assert result["facets"]["source"]["files"][0]["file"] == "src/main.py"

    @pytest.mark.asyncio
    async def test_execute_exclude_removes_matching_selection(self, tmp_path):
        defs = {
            "run": [_make_def(file="src/main.py", name="run", line=1)],
            "test_run": [_make_def(file="tests/test_main.py", name="test_run", line=1)],
        }

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search(['run', 'test_run']).exclude(test=True)",
                    "output_format": "json",
                }
            )

        assert [symbol["name"] for symbol in result["symbols"]] == ["run"]

    @pytest.mark.asyncio
    async def test_execute_filter_prunes_relationships_to_kept_entries(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "helper",
                "callee_file": "helper.py",
                "callee_line": 4,
                "depth": 1,
            },
            {
                "callee_name": "ignored",
                "callee_file": "ignored.py",
                "callee_line": 8,
                "depth": 1,
            },
        ]
        defs = {"run": [_make_def(file="main.py", name="run", line=1)]}

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run').callees().filter(name='helper')",
                    "output_format": "json",
                }
            )

        assert [symbol["name"] for symbol in result["symbols"]] == ["helper"]
        assert result["relationships"]["callees"]["main.py:1:run"] == [
            {
                "name": "helper",
                "kind": "function",
                "file": "helper.py",
                "line": 4,
                "end_line": 4,
                "language": "",
                "depth": 1,
            }
        ]

    @pytest.mark.asyncio
    async def test_execute_filter_keeps_relationships_for_kept_source(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "helper",
                "callee_file": "helper.py",
                "callee_line": 4,
                "depth": 1,
            }
        ]
        defs = {"run": [_make_def(file="main.py", name="run", line=1)]}

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run').include(callees=True).filter(name='run')",
                    "output_format": "json",
                }
            )

        assert [symbol["name"] for symbol in result["symbols"]] == ["run"]
        assert result["relationships"]["callees"]["main.py:1:run"] == [
            {
                "name": "helper",
                "kind": "function",
                "file": "helper.py",
                "line": 4,
                "end_line": 4,
                "language": "",
                "depth": 1,
            }
        ]

    @pytest.mark.asyncio
    async def test_execute_filter_removes_relationships_without_kept_edges(
        self, tmp_path
    ):
        mock_cache = MagicMock()
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "helper",
                "callee_file": "helper.py",
                "callee_line": 4,
                "depth": 1,
            }
        ]
        defs = {"run": [_make_def(file="main.py", name="run", line=1)]}

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run').callees().filter(name='missing')",
                    "output_format": "json",
                }
            )

        assert result["symbols"] == []
        assert result["relationships"]["callees"] == {}
