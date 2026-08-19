#!/usr/bin/env python3
"""Tests for the ``health action=self`` MCP tool / ``--self-health`` CLI twin.

RFC-0025 Layer 5. Determinism policy: the report's latency numbers come from
**synthetic samples injected into the recorder**, never from timing real work,
so every count / tier / percentile assertion pins an exact value. The one
nondeterministic property asserted is the relationship ``p50 <= p95``.
"""

from __future__ import annotations

import os
from typing import Any
from unittest import mock

import pytest

from tree_sitter_analyzer.latency import (
    TIER_COLD,
    TIER_WARM,
    LatencyRecorder,
    get_latency_recorder,
)
from tree_sitter_analyzer.mcp.tools.self_health_tool import (
    SelfHealthTool,
    _analysis_cache_report,
    _ast_index_report,
    _engine_root_conflict,
    _per_root_cache_stats,
)

MS = 1_000_000


class _UnreadableRegistry:
    """Stands in for ``UnifiedAnalysisEngine._instances`` when it cannot be read.

    Both call sites reach it differently — ``list(...)`` uses ``__iter__``,
    ``dict(...)`` uses ``keys()`` — so both raise.
    """

    def __iter__(self) -> Any:
        raise RuntimeError("registry gone")

    def keys(self) -> Any:
        raise RuntimeError("registry gone")


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
async def test_unmeasured_analysis_cache_hit_rate_is_null_not_zero(
    tool: SelfHealthTool,
) -> None:
    """``CacheService.get_stats()`` returns ``hit_rate == 0.0`` for zero
    requests. A 0.0 that means "unmeasured" is the belief-shaped output this
    whole surface exists to eliminate — it must surface as ``null``."""
    result = await _report(tool)
    assert result["analysis_cache"]["hit_rate"] is None


@pytest.mark.asyncio
async def test_unmeasured_analysis_cache_total_requests_is_null_not_zero(
    tool: SelfHealthTool,
) -> None:
    # Reviewer P2-5: total_requests was the one field the "never a fabricated
    # zero" rule was not applied to, so an unreadable cache DB was
    # byte-identical to a genuinely idle one.
    result = await _report(tool)
    assert result["analysis_cache"]["total_requests"] is None


@pytest.mark.asyncio
async def test_idle_analysis_cache_reason_is_no_requests_yet(
    tool: SelfHealthTool,
) -> None:
    # Reviewer P2-5: idle must be distinguishable from unreadable.
    result = await _report(tool)
    assert result["analysis_cache"]["reason"] == "NO_REQUESTS_YET"


@pytest.mark.asyncio
async def test_unreadable_analysis_cache_reason_names_the_failure(
    tool: SelfHealthTool,
) -> None:
    # Reviewer P2-5: a locked/unreadable cache DB must not read as idle.
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    with mock.patch.object(
        engine_module, "get_analysis_engine", side_effect=RuntimeError("db locked")
    ):
        result = await _report(tool)
    assert result["analysis_cache"]["reason"] == "CACHE_STATS_UNREADABLE:RuntimeError"


@pytest.mark.asyncio
async def test_unreadable_analysis_cache_status_is_unavailable(
    tool: SelfHealthTool,
) -> None:
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    with mock.patch.object(
        engine_module, "get_analysis_engine", side_effect=RuntimeError("db locked")
    ):
        result = await _report(tool)
    assert result["analysis_cache"]["status"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_unmeasured_analysis_cache_status_is_no_observations(
    tool: SelfHealthTool,
) -> None:
    result = await _report(tool)
    assert result["analysis_cache"]["status"] == "NO_OBSERVATIONS"


@pytest.mark.asyncio
async def test_report_has_no_field_named_ast_cache(tool: SelfHealthTool) -> None:
    # Reviewer P2-1: the field named ``ast_cache`` actually published the
    # in-process analysis cache and was provably insensitive to whether
    # .ast-cache/index.db existed. The misleading name must not come back.
    result = await _report(tool)
    assert "ast_cache" not in result


# --------------------------------------------------------------------------
# ast_index — the REAL on-disk index, and it must react to it
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_index_absent_when_no_index_on_disk(
    tool: SelfHealthTool,
) -> None:
    # Reviewer P2-1: tmp_path has no .ast-cache, so the honest answer is ABSENT.
    result = await _report(tool)
    assert result["ast_index"]["status"] == "ABSENT"


@pytest.mark.asyncio
async def test_ast_index_absent_reports_present_false(
    tool: SelfHealthTool,
) -> None:
    result = await _report(tool)
    assert result["ast_index"]["present"] is False


@pytest.mark.asyncio
async def test_ast_index_hit_rate_is_null_and_declared_uninstrumented(
    tool: SelfHealthTool,
) -> None:
    """The on-disk index keeps no hit/miss counters. Rather than substituting
    the in-process cache's rate — the P2-1 defect — say so explicitly."""
    result = await _report(tool)
    index = result["ast_index"]
    assert (index["hit_rate"], index["hit_rate_status"]) == (
        None,
        "UNAVAILABLE_NOT_INSTRUMENTED",
    )


def test_ast_index_reacts_to_a_real_index_on_disk(tmp_path: Any) -> None:
    """Reviewer P2-1 proof: the old field returned byte-identical values with
    .ast-cache deleted and with a real index present. This one must change."""
    import sqlite3

    absent = _ast_index_report(str(tmp_path))
    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir()
    connection = sqlite3.connect(str(cache_dir / "index.db"))
    connection.execute("CREATE TABLE ast_index (file_path TEXT, mtime_ns INTEGER)")
    connection.execute("INSERT INTO ast_index VALUES ('a.py', 1)")
    connection.commit()
    connection.close()
    present = _ast_index_report(str(tmp_path))
    assert (absent["status"], present["status"]) == ("ABSENT", "OK")


def test_ast_index_counts_indexed_files(tmp_path: Any) -> None:
    import sqlite3

    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir()
    connection = sqlite3.connect(str(cache_dir / "index.db"))
    connection.execute("CREATE TABLE ast_index (file_path TEXT, mtime_ns INTEGER)")
    connection.executemany(
        "INSERT INTO ast_index VALUES (?, 1)", [("a.py",), ("b.py",), ("c.py",)]
    )
    connection.commit()
    connection.close()
    assert _ast_index_report(str(tmp_path))["indexed_files"] == 3


def test_present_but_empty_index_is_reported_empty_not_ok(tmp_path: Any) -> None:
    """A schema-only index.db (this repo ships one at 200 KB with zero rows)
    must not read as OK — an agent would take that for a warm index."""
    import sqlite3

    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir()
    connection = sqlite3.connect(str(cache_dir / "index.db"))
    connection.execute("CREATE TABLE ast_index (file_path TEXT, mtime_ns INTEGER)")
    connection.commit()
    connection.close()
    assert _ast_index_report(str(tmp_path))["status"] == "EMPTY"


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

    # Reviewer P3: excluding ``routes`` entirely meant this test would pass
    # even if the facade returned ``routes: []`` unconditionally. Compare route
    # *structure* with the nondeterministic timings normalised away, so parity
    # is actually enforced.
    def shape(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
        return sorted(
            (row["tool"], row["action"], row["tier"], set(row))
            for row in payload["routes"]
        )

    # The facade call is itself instrumented, so it records one extra
    # ``health/self`` row; drop that one route from the comparison, not the key.
    def without_self(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            **payload,
            "routes": [r for r in payload["routes"] if r["tool"] != "health"],
        }

    assert shape(without_self(mcp_side)) == shape(without_self(cli_side))

    scalars = {"routes", "total_invocations", "summary_line", "agent_summary"}
    assert {k: v for k, v in mcp_side.items() if k not in scalars} == {
        k: v for k, v in cli_side.items() if k not in scalars
    }


@pytest.mark.asyncio
async def test_parity_test_would_fail_if_routes_were_dropped(tmp_path: Any) -> None:
    """Guard on the guard: the route-shape comparison must actually be able to
    detect an empty ``routes`` list (reviewer P3 — the previous version could
    not, because it excluded the key)."""
    get_latency_recorder().record("nav", "callers", 42 * MS, tier=TIER_WARM)
    real = await SelfHealthTool(project_root=str(tmp_path)).execute(
        {"output_format": "json"}
    )
    dropped = {**real, "routes": []}

    def shape(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
        return sorted(
            (row["tool"], row["action"], row["tier"], set(row))
            for row in payload["routes"]
        )

    assert shape(real) != shape(dropped)


# --------------------------------------------------------------------------
# Mixed project-root spellings must not produce a contradictory payload
# --------------------------------------------------------------------------


def test_mixed_engine_roots_are_detected_as_ambiguous(tmp_path: Any) -> None:
    # Reviewer P2-6: UnifiedAnalysisEngine keys its singleton on
    # ``project_root or "default"`` with no normalisation, so '.' and the
    # absolute path are different engines with different CacheServices. The
    # report used to publish one engine's zeros while the other was busy.
    from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

    root = str(tmp_path)
    get_analysis_engine(root)
    get_analysis_engine(root + os.sep)
    assert _engine_root_conflict(root) == "MULTIPLE_ENGINE_ROOTS"


def test_single_engine_root_reports_no_conflict(tmp_path: Any) -> None:
    """The detection must not fire on the normal single-root case."""
    from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

    get_analysis_engine(str(tmp_path))
    assert _engine_root_conflict(str(tmp_path)) is None


def test_two_unrelated_engine_roots_are_not_flagged_as_a_conflict(
    tmp_path: Any,
) -> None:
    """Two engines for genuinely different projects is normal, not ambiguous.
    Flagging it would make the whole analysis_cache block useless in any
    process that ever touched a second repository."""
    from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

    mine = tmp_path / "project-a"
    other = tmp_path / "project-b"
    mine.mkdir()
    other.mkdir()
    get_analysis_engine(str(mine))
    get_analysis_engine(str(other))
    assert _engine_root_conflict(str(mine)) is None


def test_unreadable_engine_registry_reports_no_conflict(tmp_path: Any) -> None:
    """A diagnostic must never raise: if the engine registry cannot be read,
    conflict detection reports "no conflict" rather than propagating."""
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    with mock.patch.object(
        engine_module.UnifiedAnalysisEngine, "_instances", _UnreadableRegistry()
    ):
        assert _engine_root_conflict(str(tmp_path)) is None


# --------------------------------------------------------------------------
# analysis_cache — the OK path and the per-root breakdown
# --------------------------------------------------------------------------


def _stub_engine(stats: Any) -> Any:
    """An engine whose ``get_cache_stats()`` returns *stats* (or raises it)."""
    engine = mock.Mock()
    if isinstance(stats, Exception):
        engine.get_cache_stats.side_effect = stats
    else:
        engine.get_cache_stats.return_value = stats
    return engine


def test_busy_analysis_cache_hit_rate_is_computed_exactly(tmp_path: Any) -> None:
    """The happy path: 3 hits of 4 requests is exactly 0.75, not 0.7 or 0.8."""
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    stats = {"hits": 3, "misses": 1, "total_requests": 4}
    with mock.patch.object(
        engine_module, "get_analysis_engine", return_value=_stub_engine(stats)
    ):
        report = _analysis_cache_report(str(tmp_path))
    assert report["hit_rate"] == 0.75


def test_busy_analysis_cache_reports_status_ok_with_no_reason(
    tmp_path: Any,
) -> None:
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    stats = {"hits": 3, "misses": 1, "total_requests": 4}
    with mock.patch.object(
        engine_module, "get_analysis_engine", return_value=_stub_engine(stats)
    ):
        report = _analysis_cache_report(str(tmp_path))
    assert (report["status"], report["reason"]) == ("OK", None)


def test_uninitialized_analysis_cache_reason_is_not_initialized(
    tmp_path: Any,
) -> None:
    """Empty stats means the engine exists but its cache was never built."""
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    with mock.patch.object(
        engine_module, "get_analysis_engine", return_value=_stub_engine({})
    ):
        report = _analysis_cache_report(str(tmp_path))
    assert (report["status"], report["reason"]) == (
        "UNAVAILABLE",
        "CACHE_NOT_INITIALIZED",
    )


def test_ambiguous_analysis_cache_carries_the_per_root_breakdown(
    tmp_path: Any,
) -> None:
    """AMBIGUOUS alone would be a dead end; the roots list must carry numbers."""
    from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

    root = str(tmp_path)
    get_analysis_engine(root)
    get_analysis_engine(root + os.sep)
    report = _analysis_cache_report(root)
    assert report["status"] == "AMBIGUOUS" and isinstance(report["roots"], list)


def test_per_root_stats_report_exact_hit_rate_for_a_busy_engine() -> None:
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    engines = {"a-root": _stub_engine({"hits": 3, "misses": 1, "total_requests": 4})}
    with mock.patch.object(engine_module.UnifiedAnalysisEngine, "_instances", engines):
        rows = _per_root_cache_stats()
    assert rows == [
        {
            "root_key": "a-root",
            "hits": 3,
            "misses": 1,
            "total_requests": 4,
            "hit_rate": 0.75,
        }
    ]


def test_per_root_stats_report_null_hit_rate_for_an_idle_engine() -> None:
    """An idle engine must report ``None``, never ``0.0`` — same honesty rule."""
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    engines = {"idle": _stub_engine({"hits": 0, "misses": 0, "total_requests": 0})}
    with mock.patch.object(engine_module.UnifiedAnalysisEngine, "_instances", engines):
        rows = _per_root_cache_stats()
    assert rows[0]["hit_rate"] is None


def test_per_root_stats_flag_an_unreadable_engine_with_a_reason() -> None:
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    engines = {"broken": _stub_engine(RuntimeError("db locked"))}
    with mock.patch.object(engine_module.UnifiedAnalysisEngine, "_instances", engines):
        rows = _per_root_cache_stats()
    assert rows[0]["reason"] == "CACHE_STATS_UNREADABLE:RuntimeError"


def test_per_root_stats_flag_an_uninitialized_engine_with_a_reason() -> None:
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    engines = {"fresh": _stub_engine({})}
    with mock.patch.object(engine_module.UnifiedAnalysisEngine, "_instances", engines):
        rows = _per_root_cache_stats()
    assert rows[0]["reason"] == "CACHE_NOT_INITIALIZED"


def test_per_root_stats_are_sorted_by_root_key() -> None:
    """Stable ordering so a diff of two reports is readable."""
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    engines = {
        "z-root": _stub_engine({"hits": 1, "misses": 0, "total_requests": 1}),
        "a-root": _stub_engine({"hits": 1, "misses": 0, "total_requests": 1}),
    }
    with mock.patch.object(engine_module.UnifiedAnalysisEngine, "_instances", engines):
        rows = _per_root_cache_stats()
    assert [row["root_key"] for row in rows] == ["a-root", "z-root"]


def test_per_root_stats_are_empty_when_the_registry_is_unreadable() -> None:
    import tree_sitter_analyzer.core.analysis_engine as engine_module

    with mock.patch.object(
        engine_module.UnifiedAnalysisEngine, "_instances", _UnreadableRegistry()
    ):
        assert _per_root_cache_stats() == []


# --------------------------------------------------------------------------
# ast_index — corrupt index, and the remaining tool surface
# --------------------------------------------------------------------------


def test_corrupt_ast_index_is_reported_unreadable(tmp_path: Any) -> None:
    """A file that is not a SQLite database must not read as ABSENT or OK."""
    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir()
    (cache_dir / "index.db").write_text("this is not a database", encoding="utf-8")
    assert _ast_index_report(str(tmp_path))["status"] == "UNREADABLE"


def test_corrupt_ast_index_names_the_failure(tmp_path: Any) -> None:
    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir()
    (cache_dir / "index.db").write_text("this is not a database", encoding="utf-8")
    reason = _ast_index_report(str(tmp_path))["reason"]
    assert reason.startswith("INDEX_UNREADABLE:")


def test_validate_arguments_accepts_the_parameterless_call(tmp_path: Any) -> None:
    """The report takes no required params, so validation always admits."""
    assert SelfHealthTool(project_root=str(tmp_path)).validate_arguments({}) is True


@pytest.mark.asyncio
async def test_next_step_names_the_env_var_when_instrumentation_is_disabled(
    tmp_path: Any,
) -> None:
    """An operator who opted out must be told why the report is empty."""
    import tree_sitter_analyzer.latency as latency_module

    with mock.patch.object(latency_module, "_recorder", LatencyRecorder(enabled=False)):
        result = await SelfHealthTool(project_root=str(tmp_path)).execute(
            {"output_format": "json"}
        )
    assert "TSA_LATENCY_INSTRUMENTATION" in result["agent_summary"]["next_step"]


@pytest.mark.asyncio
async def test_mcp_default_output_format_is_toon(tmp_path: Any) -> None:
    """CLAUDE.md §1 (locked): MCP defaults to TOON."""
    result = await SelfHealthTool(project_root=str(tmp_path)).execute({})
    assert result["format"] == "toon"
