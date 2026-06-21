"""Tests for ``nav action=test_map`` — RFC-0014 Phase B.

All tests written RED-first (before implementation).
Boundary: dispatched through the nav facade's bespoke route.

Key test design: the impact_inner is registered as a bespoke_inner in the
facade, accessible via facade._bespoke_inners. We patch get_call_graph on
that instance to inject mock call-graph data.
"""

# ---------------------------------------------------------------------------
# INVARIANT DELEGATION NOTICE
# The following 4 common facade invariants are tested canonically in:
#   tests/unit/mcp/test_facade_envelope_contract.py
#
# Delegated invariants (do NOT add new duplicates here):
#   - envelope preserved       (verdict / agent_summary verbatim pass-through)
#   - arg projection           (action key stripped before reaching inner tool)
#   - missing action error     (success=False, verdict in {ERROR, NOT_FOUND})
#   - unknown action error     (success=False, available_actions listed)
#
# Facade-specific tests that remain in this file:
#   - nav action=test_map bespoke route (RFC-0014 Phase B)
#   - test_map call-graph data injection and output schema
#   - collectible caller / language-specific test detection helpers
# ---------------------------------------------------------------------------

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.mcp.tools.codegraph_impact_tool import CodeGraphImpactTool
from tree_sitter_analyzer.mcp.tools.nav_facade import (
    _MAX_TEST_MAP,
    _is_collectible_caller,
    _is_go_test_func,
    _is_java_test_method,
    _is_js_test_func,
    build_nav_facade,
)

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

    # Use json to access bulk list fields directly (value-kind rule strips lists in TOON)
    result = await facade.execute(
        {"action": "test_map", "symbol": "my_fn", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["edge_count"] == 3
    assert result["unique_function_count"] == 3
    assert result["test_files"] == ["tests/test_a.py", "tests/test_b.py"]
    assert "tests/test_a.py::test_case_1" in result["test_functions"]
    assert "tests/test_a.py::test_case_2" in result["test_functions"]
    assert "tests/test_b.py::test_case_3" in result["test_functions"]
    assert result["truncated"] is False
    assert result["agent_summary"]["next_step"].startswith(
        "Run per-file tests: pytest tests/test_a.py tests/test_b.py."
    )


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

    # Use json to access bulk list fields directly (value-kind rule strips lists in TOON)
    result = await facade.execute(
        {"action": "test_map", "symbol": "my_fn", "output_format": "json"}
    )

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

    # Use json to access bulk list fields directly (value-kind rule strips lists in TOON)
    result = await facade.execute(
        {"action": "test_map", "symbol": "hub_fn", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["edge_count"] == 51
    assert result["unique_function_count"] == 51
    assert result["truncated"] is True
    # test_functions list is capped at 50
    assert len(result["test_functions"]) == _MAX_TEST_MAP
    assert (
        f"Listed {_MAX_TEST_MAP} of 51 test function(s)"
        in result["agent_summary"]["next_step"]
    )
    assert (
        "test_files contains the complete file-level surface"
        in result["agent_summary"]["next_step"]
    )


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

    # Use json to access bulk list fields directly (value-kind rule strips lists in TOON)
    result = await facade.execute(
        {"action": "test_map", "symbol": "fn", "output_format": "json"}
    )

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
    # Must use test_ prefix — the collectible filter now applies (#790 fix).
    shared_caller = _make_func("test_shared_behaviour", "tests/test_shared.py", 10)

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
    assert result["test_functions"] == ["tests/test_shared.py::test_shared_behaviour"]


@pytest.mark.asyncio
async def test_test_map_shared_helper_edge_count_counts_both_targets() -> None:
    """Two targets share ONE helper called by ONE test → edge_count==2 (#967).

    ``fn_a`` and ``fn_b`` are each reached only via the non-collectible helper
    ``_setup``; ``_setup`` is called by a single ``test_shared``. Each
    (target, helper→test) pair is a genuine coverage edge, so edge_count must be
    2 even though ``test_shared`` appears once in test_functions. Previously the
    global dedupe branch fired before the second target's edge was counted,
    undercounting edge_count to 1.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_a = _make_func("fn_a", "src/mod_a.py")
    target_b = _make_func("fn_b", "src/mod_b.py")
    helper = _make_func("_setup", "tests/test_shared.py", 5)
    real_test = _make_func("test_shared", "tests/test_shared.py", 20)

    def _callers(func: FunctionRef):
        # Both fn_a and fn_b are called ONLY by the shared _setup helper;
        # _setup is called by the single test_shared function.
        if func.name in ("fn_a", "fn_b"):
            return [helper]
        if func.name == "_setup":
            return [real_test]
        return []

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_a, target_b]
    mock_graph.caller_refs_of.side_effect = _callers
    mock_graph.build = MagicMock()
    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "fn_a", "output_format": "json"}
    )

    assert result["success"] is True
    # Two genuine coverage edges: (fn_a → test_shared), (fn_b → test_shared).
    assert result["edge_count"] == 2
    # The test function is deduped in the SET — appears exactly once.
    assert result["unique_function_count"] == 1
    assert result["test_functions"] == ["tests/test_shared.py::test_shared"]


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


# ---------------------------------------------------------------------------
# 9. #790 regression: private helpers (``_run``) must be excluded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_map_excludes_private_helper_functions() -> None:
    """Private helpers like ``_run`` must be excluded from test_map results.

    Bug #790: ``_run`` in ``test_b1_reader_edge_parity.py`` was returned as a
    test function because it lives in a test file, but pytest does NOT collect
    functions whose name does not start with ``test_``.  The filter must
    exclude any caller whose name does not start with ``test_``.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("get_call_edges", "src/ast_cache.py")
    # _run is a private helper — present in test file but NOT pytest-collectible
    private_helper = _make_func("_run", "tests/unit/test_b1_reader_edge_parity.py", 10)
    # test_parity IS pytest-collectible
    real_test = _make_func(
        "test_parity_ok", "tests/unit/test_b1_reader_edge_parity.py", 50
    )

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = [private_helper, real_test]
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "get_call_edges", "output_format": "json"}
    )

    assert result["success"] is True
    # Only the real test function counts
    assert result["edge_count"] == 1
    assert result["unique_function_count"] == 1
    # _run must NOT appear in test_functions
    assert all("_run" not in fn for fn in result["test_functions"])
    # The real test IS present
    assert (
        "tests/unit/test_b1_reader_edge_parity.py::test_parity_ok"
        in result["test_functions"]
    )


@pytest.mark.asyncio
async def test_test_map_excludes_all_underscore_prefixed_helpers() -> None:
    """All ``_``-prefixed helpers in test files are excluded, not just ``_run``.

    Helpers like ``_helper``, ``_setup``, ``_common_check`` are test-file
    utilities, not pytest-collectible test functions.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("my_fn", "src/core.py")
    helpers = [
        _make_func("_run", "tests/test_a.py", 1),
        _make_func("_helper", "tests/test_a.py", 5),
        _make_func("_setup_graph", "tests/test_b.py", 3),
    ]
    real_test = _make_func("test_ok", "tests/test_a.py", 10)

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = helpers + [real_test]
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "my_fn", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["edge_count"] == 1
    assert result["unique_function_count"] == 1
    assert result["test_functions"] == ["tests/test_a.py::test_ok"]


@pytest.mark.asyncio
async def test_test_map_excludes_non_test_prefixed_public_helpers() -> None:
    """Public helpers without ``test_`` prefix are also excluded.

    ``run_scenario``, ``check_result``, etc. live in test files but are NOT
    collected by pytest.  Only ``test_*`` names pass the filter.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("fn", "src/mod.py")
    public_helper = _make_func("run_scenario", "tests/test_c.py", 2)
    real_test = _make_func("test_scenario", "tests/test_c.py", 20)

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = [public_helper, real_test]
    mock_graph.build = MagicMock()

    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "fn", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["edge_count"] == 1
    assert result["unique_function_count"] == 1
    assert result["test_functions"] == ["tests/test_c.py::test_scenario"]


# ---------------------------------------------------------------------------
# 10. #807 cross-language: non-Python test callers must NOT be dropped by the
#     pytest ``test_`` name filter (Go TestFoo, Java shouldHandleFoo, JS .test.ts)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_map_preserves_go_test_callers() -> None:
    """Go ``TestFoo`` in a ``*_test.go`` file is a valid test caller (#807).

    pytest's ``test_`` rule is Python-specific. Go's convention is ``TestXxx``
    in ``*_test.go`` — applying the pytest filter wrongly dropped it.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("Handle", "pkg/server.go", language="go")
    go_test = _make_func("TestHandle", "pkg/server_test.go", 10, language="go")

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = [go_test]
    mock_graph.build = MagicMock()
    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "Handle", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["edge_count"] == 1
    assert result["unique_function_count"] == 1
    assert result["test_functions"] == ["pkg/server_test.go::TestHandle"]


@pytest.mark.asyncio
async def test_test_map_go_helper_walks_up_to_test_func() -> None:
    """Go helper ``setupServer`` is NOT a test func → walk up to ``TestServer`` (#967).

    A direct caller in ``*_test.go`` whose name does not match Go's
    ``Test``/``Benchmark``/``Example``/``Fuzz`` convention (e.g. ``setupServer``)
    is a helper that ``go test`` never runs directly. It must be treated like a
    Python ``_run`` helper: the route walks up ONE hop to the convention-matching
    ``TestServer`` that calls it. The helper itself must NOT be recorded.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("Handle", "pkg/server.go", language="go")
    helper = _make_func("setupServer", "pkg/server_test.go", 5, language="go")
    real_test = _make_func("TestServer", "pkg/server_test.go", 20, language="go")

    def _callers(func: FunctionRef):
        # Handle is called ONLY by setupServer; setupServer by TestServer.
        if func.name == "Handle":
            return [helper]
        if func.name == "setupServer":
            return [real_test]
        return []

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.side_effect = _callers
    mock_graph.build = MagicMock()
    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "Handle", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["edge_count"] == 1
    assert result["unique_function_count"] == 1
    # The helper is excluded; only the TestXxx entry point is reported.
    assert result["test_functions"] == ["pkg/server_test.go::TestServer"]
    assert all("setupServer" not in fn for fn in result["test_functions"])


@pytest.mark.asyncio
async def test_test_map_preserves_js_and_java_test_callers() -> None:
    """JS ``*.test.ts`` and Java test-tree callers are preserved (#807).

    Java ``shouldHandleFoo`` lives under ``src/test/`` and JS specs are
    ``*.test.ts`` — neither matches the pytest ``test_`` rule, but both are
    valid test entry points for their language.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("render", "src/render.ts", language="typescript")
    js_test = _make_func(
        "renders correctly", "src/render.test.ts", 4, language="typescript"
    )
    java_test = _make_func(
        "shouldHandleFoo", "src/test/java/FooTest.java", 12, language="java"
    )

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.return_value = [js_test, java_test]
    mock_graph.build = MagicMock()
    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "render", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["edge_count"] == 2
    assert result["unique_function_count"] == 2
    assert result["test_functions"] == [
        "src/render.test.ts::renders correctly",
        "src/test/java/FooTest.java::shouldHandleFoo",
    ]


# ---------------------------------------------------------------------------
# 11. #807 helper resolution: walk up ONE hop from a non-collectible Python
#     helper (``_run``) to the ``test_*`` function that drives it.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_map_walks_up_one_hop_from_helper_to_test() -> None:
    """``test_foo`` → ``_run`` → prod fn: the test_* caller is recovered (#807).

    The production function is only reached via the ``_run`` helper, so the
    direct caller is the non-collectible ``_run``. The route walks up one hop
    to ``test_foo`` so the function is not reported as uncovered.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("prod_fn", "src/prod.py")
    helper = _make_func("_run", "tests/test_helpers.py", 5)
    real_test = _make_func("test_foo", "tests/test_helpers.py", 20)

    def _callers(func: FunctionRef):
        # prod_fn is called ONLY by _run; _run is called by test_foo.
        if func.name == "prod_fn":
            return [helper]
        if func.name == "_run":
            return [real_test]
        return []

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.side_effect = _callers
    mock_graph.build = MagicMock()
    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "prod_fn", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["edge_count"] == 1
    assert result["unique_function_count"] == 1
    assert result["test_functions"] == ["tests/test_helpers.py::test_foo"]


@pytest.mark.asyncio
async def test_test_map_walk_up_capped_at_one_hop() -> None:
    """The helper walk-up is capped at ONE hop — a 2-hop chain is NOT followed.

    ``prod_fn`` → ``_inner`` → ``_outer`` → ``test_foo``: only one hop up from
    ``_inner`` is taken, reaching ``_outer`` (non-collectible) and stopping.
    ``test_foo`` two hops away is NOT recovered.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("prod_fn", "src/prod.py")
    inner = _make_func("_inner", "tests/test_chain.py", 3)
    outer = _make_func("_outer", "tests/test_chain.py", 8)
    real_test = _make_func("test_foo", "tests/test_chain.py", 30)

    def _callers(func: FunctionRef):
        if func.name == "prod_fn":
            return [inner]
        if func.name == "_inner":
            return [outer]
        if func.name == "_outer":
            return [real_test]
        return []

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.side_effect = _callers
    mock_graph.build = MagicMock()
    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "prod_fn", "output_format": "json"}
    )

    assert result["success"] is True
    # No collectible test reachable within one hop → nothing recorded.
    assert result["edge_count"] == 0
    assert result["unique_function_count"] == 0
    assert result["test_functions"] == []


# ---------------------------------------------------------------------------
# 12. Per-language test-name helpers — direct unit coverage of every branch
#     (#967). Each helper is a pure predicate; assert the exact boolean.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_map_walk_up_skips_helper_parent_in_non_test_file() -> None:
    """Walk-up ignores a helper's parent that lives in a NON-test file (#967).

    ``prod_fn`` is reached only via the test-file helper ``_run``; ``_run`` is
    itself called from a PRODUCTION file (``src/driver.py``), not a test. The
    one-hop walk-up must skip that non-test parent, so no coverage edge is
    recorded.
    """
    facade = build_nav_facade(project_root=None)
    impact_inner = _get_impact_inner(facade)

    target_fn = _make_func("prod_fn", "src/prod.py")
    helper = _make_func("_run", "tests/test_helpers.py", 5)
    prod_caller = _make_func("driver", "src/driver.py", 20)

    def _callers(func: FunctionRef):
        # prod_fn called only by the test-file helper _run; _run called only
        # from a production (non-test) file.
        if func.name == "prod_fn":
            return [helper]
        if func.name == "_run":
            return [prod_caller]
        return []

    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [target_fn]
    mock_graph.caller_refs_of.side_effect = _callers
    mock_graph.build = MagicMock()
    impact_inner._call_graph = mock_graph

    result = await facade.execute(
        {"action": "test_map", "symbol": "prod_fn", "output_format": "json"}
    )

    assert result["success"] is True
    # The only helper parent is in a non-test file → skipped, nothing recorded.
    assert result["edge_count"] == 0
    assert result["unique_function_count"] == 0
    assert result["test_functions"] == []


def test_is_go_test_func_accepts_test_and_benchmark_example_fuzz() -> None:
    """Go test entry-point prefixes followed by uppercase / empty → True."""
    assert _is_go_test_func("TestHandle") is True
    assert _is_go_test_func("BenchmarkParse") is True
    assert _is_go_test_func("ExampleServer") is True
    assert _is_go_test_func("FuzzDecode") is True
    # Bare prefix with no suffix is a valid Go example/test name.
    assert _is_go_test_func("Example") is True


def test_is_go_test_func_rejects_lowercase_suffix_and_non_prefix() -> None:
    """``Testing``-style lowercase suffix and plain helpers → False."""
    # Starts with ``Test`` but suffix is lowercase alpha → not a test func.
    assert _is_go_test_func("Testing") is False
    # Lowercase helper with no recognised prefix → False.
    assert _is_go_test_func("setupServer") is False


def test_is_js_test_func_whitespace_description_is_test() -> None:
    """A spec description containing whitespace → True (no prefix check)."""
    assert _is_js_test_func("renders correctly") is True


def test_is_js_test_func_known_prefixes_are_tests() -> None:
    """``test``/``it``/``should``/``when``/``describe`` prefixes → True."""
    assert _is_js_test_func("testRender") is True
    assert _is_js_test_func("itWorks") is True
    assert _is_js_test_func("shouldRender") is True
    assert _is_js_test_func("whenClicked") is True
    assert _is_js_test_func("describeFlow") is True


def test_is_js_test_func_bare_camelcase_helper_is_not_test() -> None:
    """A bare camelCase / underscore helper identifier → False (walk up)."""
    assert _is_js_test_func("mountComponent") is False
    assert _is_js_test_func("_helper") is False


def test_is_java_test_method_public_vs_private() -> None:
    """Any public (non-underscore) Java method → True; ``_``-leading → False."""
    assert _is_java_test_method("shouldHandleFoo") is True
    assert _is_java_test_method("_privateHelper") is False


def test_is_collectible_caller_unknown_language_accepts() -> None:
    """A non-Python file with no recognised convention → accept the caller."""
    assert _is_collectible_caller("src/mod.rb", "anything", "ruby") is True
    # No language hint and an unrecognised extension also accepts.
    assert _is_collectible_caller("src/mod.xyz", "whatever", "") is True
