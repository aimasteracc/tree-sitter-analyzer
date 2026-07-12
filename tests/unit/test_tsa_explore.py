"""Unit tests for tree_sitter_analyzer.mcp.tsa_explore (Phase 1b prototype).

Tests cover:
- _infer_task_type: keyword heuristic routing
- _extract_symbol: identifier extraction from natural-language queries
- tsa_explore: async routing with mocked facades
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from tree_sitter_analyzer.mcp.tsa_explore import (
    _DEFAULT_TASK_TYPE,
    _ROUTING,
    _extract_symbol,
    _infer_task_type,
    tsa_explore,
)

# ---------------------------------------------------------------------------
# _infer_task_type
# ---------------------------------------------------------------------------


class TestInferTaskType:
    def test_entrypoint_tracing_entry_point(self) -> None:
        assert _infer_task_type("where is the entrypoint") == "entrypoint-tracing"

    def test_entrypoint_tracing_main(self) -> None:
        assert _infer_task_type("what does main do") == "entrypoint-tracing"

    def test_entrypoint_tracing_startup(self) -> None:
        assert _infer_task_type("trace the startup sequence") == "entrypoint-tracing"

    def test_entrypoint_tracing_request_handler(self) -> None:
        assert _infer_task_type("find the request handler") == "entrypoint-tracing"

    def test_call_chain_trace(self) -> None:
        assert _infer_task_type("show me the call chain for build_cache") == "call-chain"

    def test_call_chain_execution_path(self) -> None:
        assert _infer_task_type("what is the execution path") == "call-chain"

    def test_call_chain_invoke(self) -> None:
        assert _infer_task_type("how does it invoke the parser") == "call-chain"

    def test_module_boundary_module(self) -> None:
        assert _infer_task_type("show the module structure") == "module-boundary"

    def test_module_boundary_import(self) -> None:
        assert _infer_task_type("what does it import") == "module-boundary"

    def test_module_boundary_package(self) -> None:
        assert _infer_task_type("describe the package layout") == "module-boundary"

    def test_change_impact_affect(self) -> None:
        assert _infer_task_type("what does changing X affect") == "change-impact"

    def test_change_impact_blast_radius(self) -> None:
        assert _infer_task_type("blast radius of this change") == "change-impact"

    def test_change_impact_downstream(self) -> None:
        assert _infer_task_type("downstream dependencies") == "change-impact"

    def test_subsystem_overview_overview(self) -> None:
        assert _infer_task_type("give me an overview of the architecture") == "subsystem-overview"

    def test_subsystem_overview_landscape(self) -> None:
        assert _infer_task_type("system landscape map") == "subsystem-overview"

    def test_default_no_match(self) -> None:
        assert _infer_task_type("random gibberish xyz") == _DEFAULT_TASK_TYPE

    def test_default_empty_string(self) -> None:
        assert _infer_task_type("") == _DEFAULT_TASK_TYPE

    def test_case_insensitive_MAIN(self) -> None:
        assert _infer_task_type("MAIN function") == "entrypoint-tracing"


# ---------------------------------------------------------------------------
# _extract_symbol
# ---------------------------------------------------------------------------


class TestExtractSymbol:
    def test_single_quoted(self) -> None:
        assert _extract_symbol("trace calls to 'build_cache'") == "build_cache"

    def test_double_quoted(self) -> None:
        assert _extract_symbol('find "IndexShard"') == "IndexShard"

    def test_backtick_quoted(self) -> None:
        assert _extract_symbol("where is `handle_request` defined") == "handle_request"

    def test_camel_case(self) -> None:
        assert _extract_symbol("trace IndexShard through the system") == "IndexShard"

    def test_snake_case(self) -> None:
        assert _extract_symbol("what calls build_cache") == "build_cache"

    def test_quoted_takes_priority_over_camel(self) -> None:
        assert _extract_symbol("'foo' and SomeClass") == "foo"

    def test_camel_takes_priority_over_snake(self) -> None:
        assert _extract_symbol("IndexShard calls build_cache") == "IndexShard"

    def test_no_identifier_returns_none(self) -> None:
        assert _extract_symbol("what does this do") is None

    def test_empty_string_returns_none(self) -> None:
        assert _extract_symbol("") is None

    def test_short_word_no_snake_no_camel_returns_none(self) -> None:
        # "foo" alone (no underscore) does not match snake_case or CamelCase
        assert _extract_symbol("foo bar baz") is None


# ---------------------------------------------------------------------------
# tsa_explore (async) — mocked facades
# ---------------------------------------------------------------------------


def _make_mock_facade(result: dict[str, Any] | Exception) -> MagicMock:
    """Build a mock facade whose .execute() is async and returns *result*."""
    facade = MagicMock()
    if isinstance(result, Exception):
        facade.execute = AsyncMock(side_effect=result)
    else:
        facade.execute = AsyncMock(return_value=result)
    return facade


class TestTsaExplore:
    def _run(self, coro):
        return asyncio.run(coro)

    def _fake_facades(self, nav=None, search=None, structure=None, health=None):
        return {
            "nav": nav or _make_mock_facade({"content": "nav_result"}),
            "search": search or _make_mock_facade({"content": "search_result"}),
            "structure": structure or _make_mock_facade({"content": "structure_result"}),
            "health": health or _make_mock_facade({"content": "health_result"}),
        }

    def test_explicit_task_type_used(self) -> None:
        with patch(
            "tree_sitter_analyzer.mcp.tsa_explore._get_facades",
            return_value=self._fake_facades(),
        ):
            result = self._run(
                tsa_explore("find module boundary", task_type="module-boundary")
            )
        assert result["task_type"] == "module-boundary"
        assert result["success"] is True

    def test_inferred_task_type_call_chain(self) -> None:
        with patch(
            "tree_sitter_analyzer.mcp.tsa_explore._get_facades",
            return_value=self._fake_facades(),
        ):
            result = self._run(tsa_explore("show the call chain for build_cache"))
        assert result["task_type"] == "call-chain"
        assert result["success"] is True

    def test_results_list_populated(self) -> None:
        with patch(
            "tree_sitter_analyzer.mcp.tsa_explore._get_facades",
            return_value=self._fake_facades(),
        ):
            result = self._run(tsa_explore("overview", task_type="subsystem-overview"))
        assert isinstance(result["results"], list)
        assert len(result["results"]) == 2  # structure + health

    def test_facade_exception_captured(self) -> None:
        failing = _make_mock_facade(RuntimeError("backend down"))
        with patch(
            "tree_sitter_analyzer.mcp.tsa_explore._get_facades",
            return_value={
                "nav": failing,
                "search": failing,
                "structure": failing,
                "health": failing,
            },
        ):
            result = self._run(tsa_explore("trace calls", task_type="call-chain"))
        assert result["success"] is False
        assert "error" in result
        assert result["results"][0]["success"] is False

    def test_missing_facade_reported(self) -> None:
        with patch(
            "tree_sitter_analyzer.mcp.tsa_explore._get_facades",
            return_value={},  # no facades at all
        ):
            result = self._run(tsa_explore("find module", task_type="module-boundary"))
        assert result["success"] is False
        assert result["results"][0]["success"] is False
        assert "not available" in result["results"][0]["error"]

    def test_unknown_task_type_falls_back_to_default(self) -> None:
        with patch(
            "tree_sitter_analyzer.mcp.tsa_explore._get_facades",
            return_value=self._fake_facades(),
        ):
            result = self._run(tsa_explore("query", task_type="nonexistent-type"))
        assert result["task_type"] == "nonexistent-type"
        assert result["success"] is True

    def test_bare_result_not_dict(self) -> None:
        """Facade returning a bare int (exit code) is handled gracefully."""
        facade = MagicMock()
        facade.execute = AsyncMock(return_value=0)
        with patch(
            "tree_sitter_analyzer.mcp.tsa_explore._get_facades",
            return_value={"nav": facade, "search": facade, "structure": facade, "health": facade},
        ):
            result = self._run(tsa_explore("context", task_type="call-chain"))
        assert result["success"] is True
        assert result["results"][0]["result"] == 0

    def test_query_and_task_type_in_response(self) -> None:
        with patch(
            "tree_sitter_analyzer.mcp.tsa_explore._get_facades",
            return_value=self._fake_facades(),
        ):
            result = self._run(tsa_explore("my query", task_type="change-impact"))
        assert result["query"] == "my query"
        assert result["task_type"] == "change-impact"

    def test_project_root_forwarded_to_get_facades(self) -> None:
        with patch(
            "tree_sitter_analyzer.mcp.tsa_explore._get_facades",
        ) as mock_get:
            mock_get.return_value = self._fake_facades()
            self._run(tsa_explore("query", project_root="/some/path"))
        mock_get.assert_called_once_with("/some/path")

    def test_facade_cache_reused(self) -> None:
        """_get_facades is called once per invocation; cache is at module level."""
        with patch(
            "tree_sitter_analyzer.mcp.tsa_explore._get_facades",
            return_value=self._fake_facades(),
        ) as mock_get:
            self._run(tsa_explore("query"))
            self._run(tsa_explore("another query"))
        assert mock_get.call_count == 2  # called each time tsa_explore is called


# ---------------------------------------------------------------------------
# Routing table completeness
# ---------------------------------------------------------------------------


def test_routing_table_covers_all_task_types() -> None:
    """Every task_type in the routing table has at least one route entry."""
    for task_type, routes in _ROUTING.items():
        assert routes != [], f"{task_type} has empty route"


def test_default_task_type_in_routing_table() -> None:
    assert _DEFAULT_TASK_TYPE in _ROUTING


# ---------------------------------------------------------------------------
# _get_facades — cache hit and cache miss paths
# ---------------------------------------------------------------------------


def test_get_facades_cache_hit() -> None:
    """_get_facades returns the same dict on a second call with the same root."""
    import tree_sitter_analyzer.mcp.tsa_explore as _mod

    mock_nav = MagicMock()
    mock_search = MagicMock()
    mock_structure = MagicMock()
    mock_health = MagicMock()

    injected = {
        "nav": mock_nav,
        "search": mock_search,
        "structure": mock_structure,
        "health": mock_health,
    }
    sentinel = "__test_root_cache_hit__"
    original_cache = dict(_mod._facade_cache)
    _mod._facade_cache[sentinel] = injected

    try:
        result = _mod._get_facades(sentinel)
        assert result is injected
    finally:
        _mod._facade_cache.clear()
        _mod._facade_cache.update(original_cache)


def test_get_facades_cache_miss_builds_facades() -> None:
    """_get_facades builds and caches facades on first call."""
    import tree_sitter_analyzer.mcp.tsa_explore as _mod

    mock_nav = MagicMock()
    mock_search = MagicMock()
    mock_structure = MagicMock()
    mock_health = MagicMock()

    sentinel = "__test_root_cache_miss__"
    original_cache = dict(_mod._facade_cache)
    _mod._facade_cache.pop(sentinel, None)

    with (
        patch("tree_sitter_analyzer.mcp.tools.nav_facade.build_nav_facade", return_value=mock_nav),
        patch("tree_sitter_analyzer.mcp.tools.search_facade.build_search_facade", return_value=mock_search),
        patch("tree_sitter_analyzer.mcp.tools.structure_facade.build_structure_facade", return_value=mock_structure),
        patch("tree_sitter_analyzer.mcp.tools.health_facade.build_health_facade", return_value=mock_health),
    ):
        result = _mod._get_facades(sentinel)

    try:
        assert result["nav"] is mock_nav
        assert result["search"] is mock_search
        assert result["structure"] is mock_structure
        assert result["health"] is mock_health
        assert _mod._facade_cache[sentinel] is result
    finally:
        _mod._facade_cache.clear()
        _mod._facade_cache.update(original_cache)
