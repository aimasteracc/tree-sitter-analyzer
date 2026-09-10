#!/usr/bin/env python3
"""Tests for :mod:`tree_sitter_analyzer.latency` (RFC-0025 Layer 5).

Determinism policy (CLAUDE.md exact-assertion rule):

Wall-clock latency is genuinely nondeterministic, so NOTHING here times real
work. Every percentile/count/tier assertion feeds the recorder **synthetic
nanosecond samples** via :meth:`LatencyRecorder.record` and pins the exact
expected output. The only nondeterministic quantity we assert on is a
*relationship* (``p50 <= p95``), never a millisecond ceiling.
"""

from __future__ import annotations

import os
import threading
import time
from unittest import mock

import pytest

from tree_sitter_analyzer.latency import (
    DEFAULT_WINDOW,
    ENV_ENABLED,
    NO_OBSERVATIONS,
    TIER_CACHED,
    TIER_COLD,
    TIER_WARM,
    LatencyRecorder,
    RouteLatency,
    get_latency_recorder,
    percentile_ns,
)

MS = 1_000_000  # nanoseconds per millisecond


# --------------------------------------------------------------------------
# percentile_ns — nearest-rank, hand-checked exact values
# --------------------------------------------------------------------------


def test_percentile_p50_of_ten_ascending_samples_is_fifth_value() -> None:
    # nearest-rank: rank = ceil(0.50 * 10) = 5 -> index 4 -> 50 ms
    samples = [n * MS for n in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)]
    assert percentile_ns(samples, 50) == 50 * MS


def test_percentile_p95_of_ten_ascending_samples_is_tenth_value() -> None:
    # nearest-rank: rank = ceil(0.95 * 10) = 10 -> index 9 -> 100 ms
    samples = [n * MS for n in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)]
    assert percentile_ns(samples, 95) == 100 * MS


def test_percentile_p50_of_twenty_ascending_samples_is_tenth_value() -> None:
    # nearest-rank: rank = ceil(0.50 * 20) = 10 -> index 9 -> 10 ms
    samples = [n * MS for n in range(1, 21)]
    assert percentile_ns(samples, 50) == 10 * MS


def test_percentile_p95_of_twenty_ascending_samples_is_nineteenth_value() -> None:
    # nearest-rank: rank = ceil(0.95 * 20) = 19 -> index 18 -> 19 ms
    samples = [n * MS for n in range(1, 21)]
    assert percentile_ns(samples, 95) == 19 * MS


def test_percentile_is_order_independent() -> None:
    """Unsorted input must give the same answer as sorted input."""
    shuffled = [n * MS for n in (70, 10, 100, 40, 20, 90, 30, 80, 50, 60)]
    assert percentile_ns(shuffled, 50) == 50 * MS


def test_percentile_of_single_sample_returns_that_sample() -> None:
    assert percentile_ns([42 * MS], 95) == 42 * MS


def test_percentile_of_empty_sample_returns_none() -> None:
    assert percentile_ns([], 50) is None


# --------------------------------------------------------------------------
# Empty state — honest NO_OBSERVATIONS, never 0.0
# --------------------------------------------------------------------------


def test_fresh_recorder_snapshot_has_no_routes() -> None:
    snapshot = LatencyRecorder().snapshot()
    assert snapshot.routes == ()


def test_fresh_recorder_status_is_no_observations() -> None:
    assert LatencyRecorder().snapshot().status == NO_OBSERVATIONS


def test_fresh_recorder_total_invocations_is_zero() -> None:
    """A count of zero is legitimate; a *percentile* of zero would not be."""
    assert LatencyRecorder().snapshot().total_invocations == 0


def test_recorder_with_one_observation_status_is_ok() -> None:
    recorder = LatencyRecorder()
    recorder.record("health", "file", 5 * MS)
    assert recorder.snapshot().status == "OK"


# --------------------------------------------------------------------------
# Tier labelling — exact label recorded
# --------------------------------------------------------------------------


def test_first_observation_of_a_route_is_labelled_cold() -> None:
    recorder = LatencyRecorder()
    recorder.record("nav", "callers", 24_800 * MS)
    assert recorder.snapshot().routes[0].tier == TIER_COLD


def test_second_observation_of_a_route_is_labelled_warm() -> None:
    recorder = LatencyRecorder()
    recorder.record("nav", "callers", 24_800 * MS)
    recorder.record("nav", "callers", 17 * MS)
    tiers = [route.tier for route in recorder.snapshot().routes]
    assert sorted(tiers) == [TIER_COLD, TIER_WARM]


def test_explicit_tier_overrides_the_cold_warm_derivation() -> None:
    recorder = LatencyRecorder()
    recorder.record("nav", "callers", 1 * MS, tier=TIER_CACHED)
    assert recorder.snapshot().routes[0].tier == TIER_CACHED


def test_cold_and_warm_of_the_same_route_are_separate_reservoirs() -> None:
    """A p95 that mixes cold and warm calls is meaningless — keep them split."""
    recorder = LatencyRecorder()
    recorder.record("nav", "callers", 24_800 * MS)  # cold
    recorder.record("nav", "callers", 17 * MS)  # warm
    by_tier = {route.tier: route for route in recorder.snapshot().routes}
    assert by_tier[TIER_COLD].p95_ns == 24_800 * MS


def test_a_second_route_gets_its_own_cold_observation() -> None:
    recorder = LatencyRecorder()
    recorder.record("nav", "callers", 1 * MS)
    recorder.record("edit", "safe", 2 * MS)
    tiers = {(r.tool, r.action): r.tier for r in recorder.snapshot().routes}
    assert tiers == {("nav", "callers"): TIER_COLD, ("edit", "safe"): TIER_COLD}


# --------------------------------------------------------------------------
# Invocation counts — exact
# --------------------------------------------------------------------------


def test_route_count_is_exact_for_repeated_observations() -> None:
    recorder = LatencyRecorder()
    for n in range(1, 8):
        recorder.record("health", "file", n * MS)
    warm = next(r for r in recorder.snapshot().routes if r.tier == TIER_WARM)
    assert warm.count == 6  # 1 cold + 6 warm == 7 records


def test_total_invocations_sums_every_route_and_tier() -> None:
    recorder = LatencyRecorder()
    for n in range(1, 8):
        recorder.record("health", "file", n * MS)
    recorder.record("edit", "safe", 1 * MS)
    assert recorder.snapshot().total_invocations == 8


# --------------------------------------------------------------------------
# Bounded memory — the window truncates samples but never the count
# --------------------------------------------------------------------------


def test_samples_in_window_is_capped_at_the_window_size() -> None:
    recorder = LatencyRecorder(window=4)
    for n in range(1, 11):
        recorder.record("health", "file", n * MS, tier=TIER_WARM)
    assert recorder.snapshot().routes[0].samples_in_window == 4


def test_count_is_exact_even_after_the_window_overflows() -> None:
    recorder = LatencyRecorder(window=4)
    for n in range(1, 11):
        recorder.record("health", "file", n * MS, tier=TIER_WARM)
    assert recorder.snapshot().routes[0].count == 10


def test_percentiles_use_only_the_most_recent_window() -> None:
    """window=4 over samples 1..10 ms leaves [7, 8, 9, 10]:
    p50 rank = ceil(0.50 * 4) = 2 -> index 1 -> 8 ms."""
    recorder = LatencyRecorder(window=4)
    for n in range(1, 11):
        recorder.record("health", "file", n * MS, tier=TIER_WARM)
    assert recorder.snapshot().routes[0].p50_ns == 8 * MS


def test_window_p95_is_the_newest_sample_when_window_is_ascending() -> None:
    # window [7, 8, 9, 10]: rank = ceil(0.95 * 4) = 4 -> index 3 -> 10 ms
    recorder = LatencyRecorder(window=4)
    for n in range(1, 11):
        recorder.record("health", "file", n * MS, tier=TIER_WARM)
    assert recorder.snapshot().routes[0].p95_ns == 10 * MS


def test_default_window_is_two_hundred_fifty_six() -> None:
    assert DEFAULT_WINDOW == 256


# --------------------------------------------------------------------------
# p50 <= p95 by construction (relationship, not a ceiling)
# --------------------------------------------------------------------------


def test_p50_never_exceeds_p95_for_a_descending_sample_run() -> None:
    recorder = LatencyRecorder()
    for n in range(100, 0, -1):
        recorder.record("health", "file", n * MS, tier=TIER_WARM)
    route = recorder.snapshot().routes[0]
    assert route.p50_ns <= route.p95_ns


def test_p50_never_exceeds_p95_for_a_real_timed_route() -> None:
    """The only test that times real work — and it asserts a *relationship*,
    never a millisecond ceiling (see the #1314 flake: 5.07s > 5.0s)."""
    recorder = LatencyRecorder()
    for _ in range(5):
        with recorder.measure("structure", "outline", tier=TIER_WARM):
            sum(range(1000))
    route = recorder.snapshot().routes[0]
    assert route.p50_ns <= route.p95_ns


# --------------------------------------------------------------------------
# measure() context manager
# --------------------------------------------------------------------------


def test_measure_records_exactly_one_observation() -> None:
    recorder = LatencyRecorder()
    with recorder.measure("structure", "outline"):
        pass
    assert recorder.snapshot().total_invocations == 1


def test_measure_still_records_when_the_body_raises() -> None:
    """A route that fails slowly is exactly the route you need in the p95."""
    recorder = LatencyRecorder()
    try:
        with recorder.measure("structure", "outline"):
            raise ValueError("boom")
    except ValueError:
        pass
    assert recorder.snapshot().total_invocations == 1


# --------------------------------------------------------------------------
# Disabled recorder
# --------------------------------------------------------------------------


def test_disabled_recorder_drops_observations() -> None:
    recorder = LatencyRecorder(enabled=False)
    recorder.record("health", "file", 5 * MS)
    assert recorder.snapshot().total_invocations == 0


def test_disabled_recorder_reports_no_observations_status() -> None:
    recorder = LatencyRecorder(enabled=False)
    recorder.record("health", "file", 5 * MS)
    assert recorder.snapshot().status == NO_OBSERVATIONS


def test_snapshot_reports_the_enabled_flag() -> None:
    assert LatencyRecorder(enabled=False).snapshot().enabled is False


# --------------------------------------------------------------------------
# Housekeeping
# --------------------------------------------------------------------------


def test_reset_clears_every_route() -> None:
    recorder = LatencyRecorder()
    recorder.record("health", "file", 5 * MS)
    recorder.reset()
    assert recorder.snapshot().total_invocations == 0


def test_reset_reinstates_cold_labelling_for_a_seen_route() -> None:
    recorder = LatencyRecorder()
    recorder.record("health", "file", 5 * MS)
    recorder.reset()
    recorder.record("health", "file", 5 * MS)
    assert recorder.snapshot().routes[0].tier == TIER_COLD


def test_action_is_normalised_to_a_stable_placeholder_when_absent() -> None:
    recorder = LatencyRecorder()
    recorder.record("set_project_path", None, 1 * MS)
    assert recorder.snapshot().routes[0].action == "-"


def test_routes_are_sorted_by_tool_action_tier() -> None:
    recorder = LatencyRecorder()
    recorder.record("nav", "callers", 1 * MS)
    recorder.record("edit", "safe", 1 * MS)
    recorder.record("health", "file", 1 * MS)
    tools = [route.tool for route in recorder.snapshot().routes]
    assert tools == ["edit", "health", "nav"]


def test_window_below_one_is_rejected() -> None:
    """A zero-size reservoir would silently discard every sample."""
    with pytest.raises(ValueError, match="window must be >= 1"):
        LatencyRecorder(window=0)


def test_window_property_reports_the_configured_window() -> None:
    assert LatencyRecorder(window=8).window == 8


def test_route_latency_p50_ms_is_none_when_no_percentile_exists() -> None:
    """``_ns_to_ms`` preserves ``None`` — a missing percentile must never be
    rendered as ``0.0`` (the fabricated-zero rule, applied to the ms view)."""
    route = RouteLatency(
        tool="t",
        action="a",
        tier=TIER_COLD,
        count=0,
        samples_in_window=0,
        p50_ns=None,
        p95_ns=None,
    )
    assert route.p50_ms is None


def test_route_latency_report_row_renders_null_not_zero_for_missing_p95() -> None:
    route = RouteLatency(
        tool="t",
        action="a",
        tier=TIER_COLD,
        count=0,
        samples_in_window=0,
        p50_ns=None,
        p95_ns=None,
    )
    assert route.as_report_row()["p95_ms"] is None


def test_get_latency_recorder_returns_one_process_global_instance() -> None:
    assert get_latency_recorder() is get_latency_recorder()


def test_get_latency_recorder_keeps_an_instance_created_during_lock_wait() -> None:
    """Double-checked locking: if another thread created the recorder while we
    were blocked on the lock, return theirs rather than replacing it — two
    recorders would split the reservoirs and halve every count."""
    import tree_sitter_analyzer.latency as latency_module

    theirs = LatencyRecorder()

    class _LockThatPublishesAnotherRecorder:
        def __enter__(self) -> object:
            latency_module._recorder = theirs
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

    with (
        mock.patch.object(latency_module, "_recorder", None),
        mock.patch.object(
            latency_module, "_recorder_lock", _LockThatPublishesAnotherRecorder()
        ),
    ):
        assert get_latency_recorder() is theirs


def _run_two_concurrent_first_calls(recorder: LatencyRecorder) -> None:
    """Hold two calls on one route inside ``measure()`` simultaneously."""
    start = threading.Barrier(3)
    release = threading.Event()

    def call() -> None:
        with recorder.measure("nav", "callers"):
            start.wait(timeout=5)
            release.wait(timeout=5)

    threads = [threading.Thread(target=call) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)  # both are now inside measure()
    release.set()
    for thread in threads:
        thread.join(timeout=5)


def test_two_concurrent_first_calls_are_both_cold() -> None:
    # Reviewer P2-2: deciding the tier in record() (i.e. at exit) classifies by
    # completion order, so under the MCP server's concurrent dispatch one of two
    # simultaneous cold calls was labelled warm -- putting a multi-second cold
    # sample into the warm p95, contradicting this module's own contract.
    recorder = LatencyRecorder()
    _run_two_concurrent_first_calls(recorder)
    tiers = sorted(route.tier for route in recorder.snapshot().routes)
    assert tiers == [TIER_COLD]


def test_two_concurrent_first_calls_land_in_one_cold_reservoir() -> None:
    # Reviewer P2-2: both concurrent cold calls counted, in the cold reservoir.
    recorder = LatencyRecorder()
    _run_two_concurrent_first_calls(recorder)
    route = recorder.snapshot().routes[0]
    assert (route.tier, route.count) == (TIER_COLD, 2)


def test_call_starting_after_a_completed_call_is_warm() -> None:
    """Entry-time classification must not make the sequential case cold."""
    recorder = LatencyRecorder()
    with recorder.measure("nav", "callers"):
        pass
    with recorder.measure("nav", "callers"):
        pass
    tiers = sorted(route.tier for route in recorder.snapshot().routes)
    assert tiers == [TIER_COLD, TIER_WARM]


def test_disabled_measure_does_not_call_perf_counter() -> None:
    # Reviewer P3: measure() never consulted _enabled, so opting out still paid
    # both perf_counter_ns calls. Disabled must be a true no-op.
    recorder = LatencyRecorder(enabled=False)
    calls = 0
    real = time.perf_counter_ns

    def counting() -> int:
        nonlocal calls
        calls += 1
        return real()

    with mock.patch.object(time, "perf_counter_ns", counting):
        with recorder.measure("health", "file"):
            pass
    assert calls == 0


def test_empty_env_value_disables_instrumentation() -> None:
    # Reviewer P3: TSA_LATENCY_INSTRUMENTATION= (empty) evaluated to enabled.
    with mock.patch.dict(os.environ, {ENV_ENABLED: ""}):
        assert LatencyRecorder().enabled is False


def test_unset_env_leaves_instrumentation_enabled() -> None:
    """On by default — the opt-out must not become an opt-in."""
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop(ENV_ENABLED, None)
        assert LatencyRecorder().enabled is True


def test_concurrent_records_are_all_counted() -> None:
    """Thread-safety guarantee: no lost updates under concurrent record()."""
    recorder = LatencyRecorder()
    threads = [
        threading.Thread(
            target=lambda: [
                recorder.record("health", "file", MS, tier=TIER_WARM)
                for _ in range(200)
            ]
        )
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert recorder.snapshot().total_invocations == 1600
