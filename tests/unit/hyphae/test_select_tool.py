"""Tests for the HyphaeSelectTool MCP wrapper."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.hyphae_select_tool import HyphaeSelectTool


class _FakeCache:
    def get_functions(self):
        return [
            {
                "name": "save",
                "file": "svc/UserService.java",
                "line": 10,
                "language": "java",
                "class": "UserService",
            },
            {
                "name": "find",
                "file": "svc/UserRepo.java",
                "line": 8,
                "language": "java",
                "class": "UserRepo",
            },
        ]

    def search_symbols_cascade(self, query, limit=100):
        return [f for f in self.get_functions() if f["name"] == query]

    def get_symbols_by_kind(self, kind, limit=50000):
        return []

    def query_edges(self, kind, caller_name=None, callee_name=None, limit=10000):
        if kind == "calls" and callee_name == "UserRepo":
            return [
                {
                    "caller_name": "save",
                    "callee_name": "UserRepo",
                    "file_path": "svc/UserService.java",
                }
            ]
        return []


def _tool():
    t = HyphaeSelectTool("/tmp")
    t._cache = _FakeCache()
    return t


def test_tool_definition_names_hyphae():
    defn = HyphaeSelectTool("/tmp").get_tool_definition()
    assert defn["name"] == "hyphae_select"
    assert "selector" in defn["inputSchema"]["properties"]
    assert defn["inputSchema"]["required"] == ["selector"]


def test_selector_required():
    with pytest.raises(ValueError):
        _tool().validate_arguments({"selector": "  "})


@pytest.mark.asyncio
async def test_execute_calls_selector_json():
    res = await _tool().execute(
        {"selector": ".method:calls(#UserRepo)", "output_format": "json"}
    )
    assert res["success"] is True
    assert res["count"] == 1
    assert res["symbols"][0]["name"] == "save"


@pytest.mark.asyncio
async def test_execute_syntax_error_is_graceful():
    res = await _tool().execute({"selector": "> broken", "output_format": "json"})
    assert res["success"] is False
    assert "syntax error" in res["error"].lower()
    assert res["symbols"] == []
