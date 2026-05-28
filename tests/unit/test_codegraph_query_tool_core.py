"""Tests for CodeGraphQueryTool core flows: schema, validation, execute basics."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from tests.unit._codegraph_query_helpers import _make_def, _patch_resolver_with
from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    CodeGraphQueryTool,
)


class TestCodeGraphQueryTool:
    def test_definition(self):
        definition = CodeGraphQueryTool().get_tool_definition()

        assert definition["name"] == "codegraph_query"
        assert definition["annotations"]["readOnlyHint"] is True

    def test_schema_requires_query(self):
        schema = CodeGraphQueryTool().get_tool_schema()

        assert schema["required"] == ["query"]
        assert schema["additionalProperties"] is False

    def test_validate_requires_query(self):
        with pytest.raises(ValueError, match="query is required"):
            CodeGraphQueryTool().validate_arguments({})

    def test_get_cache_requires_project_root_and_reuses_instance(self, tmp_path):
        with pytest.raises(ValueError, match="Project root not set"):
            CodeGraphQueryTool().get_cache()

        mock_cache = MagicMock()
        tool = CodeGraphQueryTool(str(tmp_path))
        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache
        ) as ast_cache:
            assert tool.get_cache() is mock_cache
            assert tool.get_cache() is mock_cache

        ast_cache.assert_called_once_with(str(tmp_path))
        tool.set_project_path(str(tmp_path / "next"))
        assert not tool.cache_initialized

    @pytest.mark.asyncio
    async def test_execute_runs_chain_in_one_tool(self, tmp_path):
        source = tmp_path / "main.py"
        source.write_text(
            "def run():\n    return helper()\n\ndef helper():\n    return 1\n",
            encoding="utf-8",
        )
        mock_cache = MagicMock()
        mock_cache.query_callees.return_value = [
            {
                "caller_name": "run",
                "caller_file": "main.py",
                "caller_line": 1,
                "callee_name": "helper",
                "callee_file": "main.py",
                "callee_line": 4,
                "depth": 1,
            }
        ]
        mock_cache.query_callers.return_value = []

        with (
            patch(
                "tree_sitter_analyzer.ast_cache.ASTCache",
                return_value=mock_cache,
            ),
            _patch_resolver_with({"run": [_make_def(name="run")]}),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run').explore(max_files=2).callees(depth=1)",
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["stats"]["steps"] == 3
        assert result["stats"]["symbols_returned"] == 2
        assert result["files"][0]["file_path"] == "main.py"
        assert "code" in result["files"][0]["symbols"][0]
        assert (
            result["relationships"]["callees"]["main.py:1:run"][0]["name"] == "helper"
        )

    @pytest.mark.asyncio
    async def test_execute_returns_error_envelope_for_bad_chain(self):
        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()):
            result = await CodeGraphQueryTool("/tmp").execute(
                {
                    "query": "search('run').delete()",
                    "output_format": "json",
                }
            )

        assert result["success"] is False
        assert result["verdict"] == "ERROR"
        assert "unsupported chain step" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_collects_step_warnings_for_invalid_search_arg(
        self, tmp_path
    ):
        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search()",
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "NOT_FOUND"
        assert result["warnings"] == ["search() requires a string query"]

    @pytest.mark.asyncio
    async def test_execute_explore_callers_related_and_take(self, tmp_path):
        (tmp_path / "main.py").write_text(
            "def run():\n    return 1\n",
            encoding="utf-8",
        )
        mock_cache = MagicMock()

        def _query_callers(name, file_path, max_depth):
            if name == "run":
                return [
                    {
                        "caller_name": "entry",
                        "caller_file": "entry.py",
                        "caller_line": 10,
                        "depth": max_depth,
                    },
                    {"caller_name": "", "caller_file": "ignored.py", "caller_line": 1},
                ]
            return []

        def _query_callees(name, file_path, max_depth):
            if name == "entry":
                return [
                    {
                        "callee_name": "helper",
                        "callee_file": file_path or "helper.py",
                        "callee_line": 4,
                        "depth": max_depth,
                    }
                ]
            return []

        mock_cache.query_callers.side_effect = _query_callers
        mock_cache.query_callees.side_effect = _query_callees
        defs = {
            "run": [
                _make_def(file="main.py", name="run", line=1),
                _make_def(file="main.py", name="run", line=1),
                _make_def(file="other.py", name="run", line=1),
            ]
        }

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "explore('main.py run', max_symbols=3, include_code=False)"
                        ".callers(depth=1).related(limit=2).take(2)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert [symbol["name"] for symbol in result["symbols"]] == ["run", "entry"]
        assert result["symbols"][0]["file"] == "main.py"
        assert result["symbols"][1]["file"] == "entry.py"
        assert "code" not in result["files"][0]["symbols"][0]
        assert result["relationships"]["callers"]["main.py:1:run"][0]["name"] == "entry"
        assert (
            result["relationships"]["callees"]["entry.py:10:entry"][0]["name"]
            == "helper"
        )

    @pytest.mark.asyncio
    async def test_execute_search_limit_caps_symbols(self, tmp_path):
        defs = {
            "run": [
                _make_def(file="main.py", name="run", line=1),
                _make_def(file="main.py", name="helper", line=5),
            ]
        }

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run', limit=1)",
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert [symbol["name"] for symbol in result["symbols"]] == ["run"]

    @pytest.mark.asyncio
    async def test_execute_semantic_search_uses_vector_backend(self, tmp_path):
        defs = {
            "user formatting": [
                _make_def(file="utils.py", name="format_user", line=1),
            ]
        }

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "semantic('user formatting', limit=5)",
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert [symbol["name"] for symbol in result["symbols"]] == ["format_user"]

    @pytest.mark.asyncio
    async def test_execute_uml_step_renders_current_relationships_as_mermaid(
        self, tmp_path
    ):
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
                    "query": "search('run').callees().uml(direction='TD').answer()",
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["facets"]["uml"]["mermaid"].startswith("flowchart TD")
        assert 'run["run"]' in result["facets"]["uml"]["mermaid"]
        assert "run -->|calls| helper" in result["facets"]["uml"]["mermaid"]
        assert result["facets"]["uml"]["edge_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_explore_falls_back_to_concept_search_for_plain_language(
        self, tmp_path
    ):
        source = tmp_path / "router.py"
        source.write_text(
            "def handle_route():\n    # route matching lives here\n    return True\n",
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
                                "name": "handle_route",
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
        mock_cache.query_callers.return_value = []
        mock_cache.query_callees.return_value = []

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with({}),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search('route matching').explore(max_files=3)"
                        ".include(source=True).answer(compact=True)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["stats"]["concept_files_returned"] == 1
        assert result["symbols"][0]["name"] == "handle_route"
        source_facet = result["facets"]["source"]["files"][0]
        assert source_facet["file"] == "router.py"
        assert any(match["line"] == 2 for match in source_facet["matches"])
        assert source_facet["symbols"][0]["name"] == "handle_route"

    @pytest.mark.asyncio
    async def test_execute_include_source_can_trigger_concept_fallback(self, tmp_path):
        source = tmp_path / "router.py"
        source.write_text(
            "def handle_route():\n    # route matching lives here\n    return True\n",
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
                                "name": "handle_route",
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

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with({}),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search('route matching')"
                        ".include(source=True).answer(compact=True)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["verdict"] == "INFO"
        assert result["stats"]["concept_files_returned"] == 1
        assert result["facets"]["source"]["files"][0]["file"] == "router.py"
