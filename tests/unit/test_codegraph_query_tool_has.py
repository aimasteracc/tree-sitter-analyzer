"""Tests for CodeGraphQueryTool has-step, relation cache, and apply_step guard."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.unit._codegraph_query_helpers import _make_def, _patch_resolver_with
from tree_sitter_analyzer.mcp.tools._codegraph_query_dsl import _ChainStep
from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    CodeGraphQueryTool,
    _QueryState,
)


class TestCodeGraphQueryToolHas:
    @pytest.mark.asyncio
    async def test_execute_has_filters_sources_by_related_symbols(self, tmp_path):
        mock_cache = MagicMock()

        def _query_callees(name, file_path, max_depth):
            assert max_depth == 1
            if name == "run":
                return [
                    {
                        "callee_name": "authorize",
                        "callee_file": "auth.py",
                        "callee_line": 4,
                        "depth": 1,
                    },
                    {
                        "callee_name": "helper",
                        "callee_file": "helper.py",
                        "callee_line": 8,
                        "depth": 1,
                    },
                ]
            return [
                {
                    "callee_name": "helper",
                    "callee_file": "helper.py",
                    "callee_line": 8,
                    "depth": 1,
                }
            ]

        mock_cache.query_callees.side_effect = _query_callees
        defs = {
            "run": [_make_def(file="main.py", name="run", line=1)],
            "skip": [_make_def(file="main.py", name="skip", line=10)],
        }

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search(['run', 'skip']).has(callees=True, name='authorize')",
                    "output_format": "json",
                }
            )

        assert [symbol["name"] for symbol in result["symbols"]] == ["run"]
        assert result["relationships"]["callees"]["main.py:1:run"] == [
            {
                "name": "authorize",
                "kind": "function",
                "file": "auth.py",
                "line": 4,
                "end_line": 4,
                "language": "",
                "depth": 1,
            }
        ]
        assert mock_cache.query_callees.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_has_reuses_relation_cache_for_later_include(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "helper",
                "callee_file": "helper.py",
                "callee_line": 4,
                "depth": 1,
            },
            {
                "callee_name": "other",
                "callee_file": "other.py",
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
                    "query": (
                        "search('run').has(callees=True, name='helper')"
                        ".include(callees=True)"
                    ),
                    "output_format": "json",
                }
            )

        assert [symbol["name"] for symbol in result["symbols"]] == [
            "run",
            "helper",
            "other",
        ]
        assert [
            symbol["name"]
            for symbol in result["relationships"]["callees"]["main.py:1:run"]
        ] == ["helper", "other"]
        assert mock_cache.query_callees.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_has_reports_missing_direction(self, tmp_path):
        defs = {"run": [_make_def(file="main.py", name="run", line=1)]}

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()),
            _patch_resolver_with(defs),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run').has(name='helper')",
                    "output_format": "json",
                }
            )

        assert [symbol["name"] for symbol in result["symbols"]] == ["run"]
        assert result["warnings"] == ["has() requires callers=True or callees=True"]

    @pytest.mark.asyncio
    async def test_execute_reuses_relation_cache_within_single_chain(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.query_callers.return_value = [
            {
                "caller_name": "entry",
                "caller_file": "entry.py",
                "caller_line": 10,
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
                        "search('run').include(callers=True).include(callers=True)"
                    ),
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert mock_cache.query_callers.call_count == 1
        assert result["relationships"]["callers"]["main.py:1:run"][0]["name"] == "entry"

    def test_apply_step_rejects_unknown_step(self):
        with pytest.raises(ValueError, match="unsupported chain step"):
            CodeGraphQueryTool("/tmp")._apply_step(
                cache=MagicMock(),
                state=_QueryState(),
                step=_ChainStep("unknown", [], {}),
                default_max_symbols=10,
                default_max_files=3,
                default_include_code=True,
            )
