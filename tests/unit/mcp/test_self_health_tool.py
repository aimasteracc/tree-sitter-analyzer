#!/usr/bin/env python3
"""Tests for the ``health action=self`` MCP tool / ``--self-health`` CLI twin.

RFC-0025 Layer 5. Determinism policy: the report's latency numbers come from
**synthetic samples injected into the recorder**, never from timing real work,
so every count / tier / percentile assertion pins an exact value. The one
nondeterministic property asserted is the relationship ``p50 <= p95``.
"""

from __future__ import annotations

from typing import Any

import pytest

from tree_sitter_analyzer.latency import (
    TIER_COLD,
    TIER_WARM,
    get_latency_recorder,
)
from tree_sitter_analyzer.mcp.tools.self_health_tool import SelfHealthTool

MS = 1_000_000


@pytest.fixture
def tool(tmp_path: Any) -> SelfHealthTool:
    return SelfHealthTool(project_root=str(tmp_path))


async def _report(tool: SelfHealthTool) -> dict[str, Any]:
    """Fetch the JSON report body.

    ``output_format="json"`` is passed explicitly so these assertions target
    the report *payload*. The MCP-toon / CLI-json default split is a locked
    design decision (CLAUDE.md §1) and is asserted separately below.
    """
    return await tool.execute({"output_format": "json"})


# --------------------------------------------------------------------------
# Honest empty state
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_recorder_reports_no_observations_status(
    tool: SelfHealthTool,
) -> None:
    result = await _report(tool)
    assert result["observations_status"] == "NO_OBSERVATIONS"


@pytest.mark.asyncio
async def test_empty_recorder_reports_an_empty_route_list(
    tool: SelfHealthTool,
) -> None:
    result = await _report(tool)
    assert result["routes"] == []


@pytest.mark.asyncio
async def test_empty_recorder_reports_zero_total_invocations(
    tool: SelfHealthTool,
) -> None:
    """A *count* of zero is a real measurement; a percentile of zero is not."""
    result = await _report(tool)
    assert result["total_invocations"] == 0


@pytest.mark.asyncio
async def test_empty_state_verdict_is_warn(tool: SelfHealthTool) -> None:
    """No data must not read as a clean bill of health."""
    result = await _report(tool)
    assert result["agent_summary"]["verdict"] == "WARN"


@pytest.mark.asyncio
async def test_unmeasured_ast_cache_hit_rate_is_null_not_zero(
    tool: SelfHealthTool,
) -> None:
    """``CacheService.get_stats()`` returns ``hit_rate == 0.0`` for zero
    requests. A 0.0 that means "unmeasured" is the belief-shaped output this
    whole surface exists to eliminate — it must surface as ``null``."""
    result = await _report(tool)
    assert result["ast_cache"]["hit_rate"] is None


@pytest.mark.asyncio
async def test_unmeasured_ast_cache_status_is_no_observations(
    tool: SelfHealthTool,
) -> None:
    result = await _report(tool)
    assert result["ast_cache"]["status"] == "NO_OBSERVATIONS"


# --------------------------------------------------------------------------
# Populated report — exact values from injected samples
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_status_is_ok_once_a_route_is_observed(
    tool: SelfHealthTool,
) -> None:
    get_latency_recorder().record("nav", "callers", 24_800 * MS)
    result = await _report(tool)
    assert result["observations_status"] == "OK"


@pytest.mark.asyncio
async def test_report_verdict_is_info_once_a_route_is_observed(
    tool: SelfHealthTool,
) -> None:
    get_latency_recorder().record("nav", "callers", 24_800 * MS)
    result = await _report(tool)
    assert result["agent_summary"]["verdict"] == "INFO"


@pytest.mark.asyncio
async def test_report_row_records_the_exact_tier_label(
    tool: SelfHealthTool,
) -> None:
    get_latency_recorder().record("nav", "callers", 24_800 * MS)
    result = await _report(tool)
    assert result["routes"][0]["tier"] == TIER_COLD


@pytest.mark.asyncio
async def test_report_row_records_the_exact_invocation_count(
    tool: SelfHealthTool,
) -> None:
    recorder = get_latency_recorder()
    for _ in range(4):
        recorder.record("nav", "callers", 17 * MS, tier=TIER_WARM)
    result = await _report(tool)
    assert result["routes"][0]["count"] == 4


@pytest.mark.asyncio
async def test_report_row_p50_ms_matches_the_hand_checked_value(
    tool: SelfHealthTool,
) -> None:
    # samples 10..100 ms; nearest-rank p50 = ceil(0.5*10)=5 -> index 4 -> 50 ms
    recorder = get_latency_recorder()
    for n in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100):
        recorder.record("nav", "callers", n * MS, tier=TIER_WARM)
    result = await _report(tool)
    assert result["routes"][0]["p50_ms"] == 50.0


@pytest.mark.asyncio
async def test_report_row_p95_ms_matches_the_hand_checked_value(
    tool: SelfHealthTool,
) -> None:
    # nearest-rank p95 = ceil(0.95*10) = 10 -> index 9 -> 100 ms
    recorder = get_latency_recorder()
    for n in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100):
        recorder.record("nav", "callers", n * MS, tier=TIER_WARM)
    result = await _report(tool)
    assert result["routes"][0]["p95_ms"] == 100.0


@pytest.mark.asyncio
async def test_report_p50_never_exceeds_p95(tool: SelfHealthTool) -> None:
    recorder = get_latency_recorder()
    for n in range(100, 0, -1):
        recorder.record("nav", "callers", n * MS, tier=TIER_WARM)
    row = (await _report(tool))["routes"][0]
    assert row["p50_ms"] <= row["p95_ms"]


@pytest.mark.asyncio
async def test_warm_p95_is_below_cold_p95_for_a_route_with_a_warm_path(
    tool: SelfHealthTool,
) -> None:
    """A *relationship*, not a millisecond ceiling. Magnitudes are the ones
    measured on this repo: ``nav callers`` cold 24.8 s, warm 16-17 ms."""
    recorder = get_latency_recorder()
    recorder.record("nav", "callers", 24_800 * MS, tier=TIER_COLD)
    for n in (16, 17, 16, 17, 18):
        recorder.record("nav", "callers", n * MS, tier=TIER_WARM)
    rows = {row["tier"]: row for row in (await _report(tool))["routes"]}
    assert rows[TIER_WARM]["p95_ms"] < rows[TIER_COLD]["p95_ms"]


@pytest.mark.asyncio
async def test_total_invocations_sums_every_route_and_tier(
    tool: SelfHealthTool,
) -> None:
    recorder = get_latency_recorder()
    recorder.record("nav", "callers", 1 * MS)
    recorder.record("nav", "callers", 1 * MS)
    recorder.record("edit", "safe", 1 * MS)
    result = await _report(tool)
    assert result["total_invocations"] == 3


# --------------------------------------------------------------------------
# Self-describing metadata — the report must not be mis-readable
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_declares_the_percentile_method(
    tool: SelfHealthTool,
) -> None:
    result = await _report(tool)
    assert result["percentile_method"] == (
        "nearest-rank (exact sample value, no interpolation)"
    )


@pytest.mark.asyncio
async def test_report_declares_the_tier_definition(tool: SelfHealthTool) -> None:
    result = await _report(tool)
    assert "NOT a measured cache probe" in result["tier_definition"]


@pytest.mark.asyncio
async def test_report_declares_the_reservoir_window(
    tool: SelfHealthTool,
) -> None:
    result = await _report(tool)
    assert result["window"] == 256


@pytest.mark.asyncio
async def test_report_declares_instrumentation_enabled(
    tool: SelfHealthTool,
) -> None:
    """On by default — see ``latency.py``."""
    result = await _report(tool)
    assert result["instrumentation_enabled"] is True


@pytest.mark.asyncio
async def test_report_scope_is_declared_as_this_process(
    tool: SelfHealthTool,
) -> None:
    """The recorder is in-process with no persistence; the report says so."""
    result = await _report(tool)
    assert result["scope"] == "current_process"


# --------------------------------------------------------------------------
# Facade wiring + CLI parity (hard rule)
# --------------------------------------------------------------------------


def test_health_facade_exposes_the_self_action(tmp_path: Any) -> None:
    from tree_sitter_analyzer.mcp.tools.health_facade import build_health_facade

    facade = build_health_facade(str(tmp_path))
    assert "self" in facade.action_map


def test_health_facade_self_action_routes_to_self_health_tool(
    tmp_path: Any,
) -> None:
    from tree_sitter_analyzer.mcp.tools.health_facade import build_health_facade

    facade = build_health_facade(str(tmp_path))
    assert type(facade.action_map["self"]).__name__ == "SelfHealthTool"


def test_self_health_cli_flag_exists() -> None:
    from tree_sitter_analyzer.cli_main import create_argument_parser

    flags = {
        option
        for action in create_argument_parser()._actions
        for option in action.option_strings
    }
    assert "--self-health" in flags


@pytest.mark.asyncio
async def test_cli_and_mcp_report_identical_payloads(tmp_path: Any) -> None:
    """CLI↔MCP parity: both surfaces must render the same report body.

    The CLI reaches this tool directly (``--self-health`` →
    ``_run_mcp_tool_sync(SelfHealthTool, ...)``) and MCP reaches it through
    the ``health`` facade. Same payload, both ways.
    """
    from tree_sitter_analyzer.mcp.tools.health_facade import build_health_facade

    get_latency_recorder().record("nav", "callers", 42 * MS, tier=TIER_WARM)

    cli_side = await SelfHealthTool(project_root=str(tmp_path)).execute(
        {"output_format": "json"}
    )
    facade = build_health_facade(str(tmp_path))
    mcp_side = await facade.execute({"action": "self", "output_format": "json"})

    # The facade call itself is instrumented, so it records one extra
    # ``health/self`` observation. Compare everything except the live counters.
    volatile = {"routes", "total_invocations", "summary_line", "agent_summary"}
    assert {k: v for k, v in mcp_side.items() if k not in volatile} == {
        k: v for k, v in cli_side.items() if k not in volatile
    }


@pytest.mark.asyncio
async def test_mcp_default_output_format_is_toon(tmp_path: Any) -> None:
    """CLAUDE.md §1 (locked): MCP defaults to TOON."""
    result = await SelfHealthTool(project_root=str(tmp_path)).execute({})
    assert result["format"] == "toon"
