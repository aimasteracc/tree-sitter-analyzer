"""Tests for ``nav action=test_map`` — RFC-0014 Phase B.

All tests written RED-first (before implementation).
Boundary: dispatched through the nav facade's bespoke route.

Key test design: the impact_inner is registered as a bespoke_inner in the
facade, accessible via facade._bespoke_inners. We patch get_call_graph on
that instance to inject mock call-graph data.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.mcp.tools.codegraph_impact_tool import CodeGraphImpactTool
from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_func(
    name: str,
    file: str = "src/mod.py",
    line: int = 1,
    language: str = "python",
) -> FunctionRef:
    return FunctionRef(
        file_path=file,
        name=name,
        start_line=line,
        language=language,
    )


def _get_impact_inner(facade) -> CodeGraphImpactTool:
    """Retrieve the impact_inner from the facade's registered bespoke inners."""
    for inner in facade._bespoke_inners:
        if isinstance(inner, CodeGraphImpactTool):
            return inner
    raise AssertionError("impact_inner not found in facade._bespoke_inners")


# ---------------------------------------------------------------------------
# 1. test_map action is present in the nav facade
# ---------------------------------------------------------------------------


def test_test_map_action_present_in_bespoke_map() -> None:
    """test_map must be registered as a bespoke route (NOT action_map)."""
    facade = build_nav_facade(project_root=None)
    assert "test_map" in facade.bespoke_map
    assert "test_map" not in facade.action_map


def test_nav_facade_all_actions_include_test_map() -> None:
    """Full action set must include test_map."""
    facade = build_nav_facade(project_root=None)
    all_actions = set(facade.action_map) | set(facade.bespoke_map)
    assert "test_map" in all_actions


def test_nav_facade_schema_action_enum_includes_test_map() -> None:
    """Schema action enum must include test_map."""
    facade = build_nav_facade(project_root=None)
    schema = facade.get_tool_schema()
    enum = set(schema["properties"]["action"]["enum"])
    assert "test_map" in enum


# ---------------------------------------------------------------------------
# 2. test_map route: returns test_files, test_functions, edge_count, truncated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_map_returns_test_files_and_functions() -> None:
    """3 test callers from 2 files → correct counts and file::fn format."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("my_fn", "src/mymodule.py")
    test_caller_1a = _make_func("test_case_1", "tests/test_a.py", 10)
    test_caller_1b = _make_func("test_case_2", "tests/test_a.py", 20)
    test_caller_2 = _make_func("test_case_3", "tests/test_b.py", 5)

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = [
        test_caller_1a,
        test_caller_1b,
        test_caller_2,
    ]
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute({"action": "test_map", "symbol": "my_fn"})

    assert result["success"] is True
    assert result["edge_count"] == 3
    assert result["unique_function_count"] == 3
    assert result["test_files"] == ["tests/test_a.py", "tests/test_b.py"]
    assert "tests/test_a.py::test_case_1" in result["test_functions"]
    assert "tests/test_a.py::test_case_2" in result["test_functions"]
    assert "tests/test_b.py::test_case_3" in result["test_functions"]
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_test_map_excludes_prod_callers() -> None:
    """2 prod callers + 1 test caller → edge_count=1, only test files."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("my_fn", "src/mymodule.py")
    prod_caller_1 = _make_func("call_site_a", "src/other.py", 10)
    prod_caller_2 = _make_func("call_site_b", "src/another.py", 20)
    test_caller = _make_func("test_it", "tests/test_foo.py", 5)

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = [
        prod_caller_1,
        prod_caller_2,
        test_caller,
    ]
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute({"action": "test_map", "symbol": "my_fn"})

    assert result["success"] is True
    assert result["edge_count"] == 1
    assert result["unique_function_count"] == 1
    assert result["test_files"] == ["tests/test_foo.py"]
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_test_map_symbol_not_found() -> None:
    """Unknown symbol → success=False with error message containing symbol name."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = []  # not found
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute({"action": "test_map", "symbol": "nonexistent_fn"})

    assert result["success"] is False
    assert "nonexistent_fn" in result["error"]


@pytest.mark.asyncio
async def test_test_map_no_test_callers() -> None:
    """Function exists but has no test callers → empty lists, edge_count=0."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("isolated_fn", "src/core.py")
    prod_caller = _make_func("prod_caller", "src/other.py", 10)

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = [prod_caller]
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute({"action": "test_map", "symbol": "isolated_fn"})

    assert result["success"] is True
    assert result["edge_count"] == 0
    assert result["unique_function_count"] == 0
    assert result["test_files"] == []
    assert result["test_functions"] == []
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_test_map_truncated_flag_set_when_cap_reached() -> None:
    """51 test callers → edge_count=51, truncated=True (cap=50)."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("hub_fn", "src/hub.py")
    test_callers = [
        _make_func(f"test_{i}", f"tests/test_file_{i % 5}.py", i) for i in range(51)
    ]

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = test_callers
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute({"action": "test_map", "symbol": "hub_fn"})

    assert result["success"] is True
    assert result["edge_count"] == 51
    assert result["unique_function_count"] == 51
    assert result["truncated"] is True
    # test_functions list is capped at 50
    assert len(result["test_functions"]) == 50


@pytest.mark.asyncio
async def test_test_map_test_functions_sorted() -> None:
    """test_functions list must be sorted."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("fn", "src/x.py")
    callers = [
        _make_func("test_z", "tests/test_b.py", 1),
        _make_func("test_a", "tests/test_a.py", 1),
        _make_func("test_m", "tests/test_a.py", 2),
    ]

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = callers
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute({"action": "test_map", "symbol": "fn"})

    assert result["test_functions"] == sorted(result["test_functions"])
    assert result["test_files"] == sorted(result["test_files"])


@pytest.mark.asyncio
async def test_test_map_result_has_agent_summary() -> None:
    """test_map result must include agent_summary for downstream routing."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("fn", "src/x.py")

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = []
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute({"action": "test_map", "symbol": "fn"})

    assert "agent_summary" in result


@pytest.mark.asyncio
async def test_test_map_file_path_param_forwarded() -> None:
    """file_path param must be forwarded to resolve_targets for disambiguation."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("fn", "src/specific.py")

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = []
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {
            "action": "test_map",
            "symbol": "fn",
            "file_path": "src/specific.py",
        }
    )

    assert result["success"] is True
    # Verify resolve_targets was called with file_path
    mock_graph.resolve_targets.assert_called_once_with("fn", "src/specific.py")


@pytest.mark.asyncio
async def test_test_map_symbol_alias_function_name_accepted() -> None:
    """function_name= is an alias for symbol= (R3 normalization already done
    by _clean_bespoke_args, but the route should accept either)."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("fn", "src/x.py")

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = []
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    # Pass function_name= instead of symbol= (R3 normalize maps symbol→function_name
    # for action_map routes; bespoke routes get cleaned_args after _clean_bespoke_args)
    result = await facade.execute({"action": "test_map", "function_name": "fn"})

    assert result["success"] is True


# ---------------------------------------------------------------------------
# 3. _NAV_DESCRIPTION mentions test_map
# ---------------------------------------------------------------------------


def test_nav_description_mentions_test_map() -> None:
    """_NAV_DESCRIPTION must include test_map so agents can discover the action."""
    from tree_sitter_analyzer.mcp.tools.nav_facade import _NAV_DESCRIPTION

    assert "test_map" in _NAV_DESCRIPTION


# ---------------------------------------------------------------------------
# 4. server instructions mention test_map
# ---------------------------------------------------------------------------


def test_server_instructions_mention_test_map() -> None:
    """MCP server instructions must document test_map."""
    from tree_sitter_analyzer.mcp._server_helpers import _SERVER_INSTRUCTIONS

    assert "test_map" in _SERVER_INSTRUCTIONS


# ---------------------------------------------------------------------------
# 5. CLI parity: --test-map flag must exist
# ---------------------------------------------------------------------------


def test_cli_test_map_flag_exists() -> None:
    """--test-map must be registered in the argument parser."""
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    flags = {s for a in parser._actions for s in a.option_strings if s.startswith("--")}
    assert "--test-map" in flags


# ---------------------------------------------------------------------------
# 6. P1 regression: nav_test_map is NOT a legacy name (no deprecation envelope)
# ---------------------------------------------------------------------------


def test_is_legacy_name_nav_test_map_returns_false() -> None:
    """nav_test_map was never a v1.x tool name — is_legacy_name must return False.

    Regression guard: if nav_test_map were ever re-added to LEGACY_TOOL_MAP,
    dispatch_legacy would inject FALSE deprecation envelopes for it.
    """
    from tree_sitter_analyzer.mcp.facade_map import is_legacy_name

    assert is_legacy_name("nav_test_map") is False


def test_nav_test_map_in_new_action_parity_not_legacy() -> None:
    """nav_test_map lives in NEW_ACTION_PARITY, NOT LEGACY_TOOL_MAP."""
    from tree_sitter_analyzer.mcp.facade_map import LEGACY_TOOL_MAP, NEW_ACTION_PARITY

    assert "nav_test_map" not in LEGACY_TOOL_MAP
    assert "nav_test_map" in NEW_ACTION_PARITY


# ---------------------------------------------------------------------------
# 7. P2 divergence: two targets sharing one test caller →
#    edge_count==2, unique_function_count==1, truncated=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_map_edge_count_vs_unique_function_count_divergence() -> None:
    """Two targets sharing the same test caller: edge_count==2, unique_function_count==1.

    edge_count tracks raw call edges (one per target→caller pair).
    unique_function_count deduplicates across all targets — the test function
    ``shared_test`` appears once in test_functions regardless of how many targets
    it covers. truncated is keyed to unique_function_count, not edge_count.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_a = _make_func("fn_a", "src/mod_a.py")
    target_b = _make_func("fn_b", "src/mod_b.py")
    shared_caller = _make_func("shared_test", "tests/test_shared.py", 10)

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_a, target_b]
    # Both targets are called by the same test function
    mock_graph.caller_refs_of.return_value = [shared_caller]
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "fn_a", "output_format": "json"}
    )

    # Raw edges: shared_caller is a caller of BOTH targets → 2 edges
    assert result["edge_count"] == 2
    # Post-dedup: shared_caller is one unique test function
    assert result["unique_function_count"] == 1
    # Cap not hit — unique_function_count (1) <= 50
    assert result["truncated"] is False
    assert result["test_functions"] == ["tests/test_shared.py::shared_test"]


# ---------------------------------------------------------------------------
# 8. P3 output_format threading — TOON / JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_map_output_format_toon_wraps_result() -> None:
    """output_format=toon → response has toon_content key (TOON wrapper applied)."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("fn", "src/x.py")

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = []
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "fn", "output_format": "toon"}
    )

    assert "toon_content" in result
    assert result.get("format") == "toon"
    # Metadata is still accessible alongside toon_content
    assert result["success"] is True


@pytest.mark.asyncio
async def test_test_map_default_output_format_is_toon() -> None:
    """MCP house rule: default output_format is toon (not json) — LOCKED design.

    When output_format is not specified, _test_map_route must default to toon.
    This matches the locked CLAUDE.md §1 house rule: MCP defaults to TOON.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("fn", "src/x.py")

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = []
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    # No output_format → should default to toon
    result = await facade.execute({"action": "test_map", "symbol": "fn"})

    assert "toon_content" in result
    assert result.get("format") == "toon"


@pytest.mark.asyncio
async def test_test_map_output_format_json_no_toon_content() -> None:
    """output_format=json → no toon_content (plain dict with scalar fields)."""
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("fn", "src/x.py")

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = []
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "fn", "output_format": "json"}
    )

    assert "toon_content" not in result
    assert result["success"] is True
    assert result["edge_count"] == 0
    assert result["unique_function_count"] == 0
