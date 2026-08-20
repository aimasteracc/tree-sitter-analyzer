#!/usr/bin/env python3
"""Unit tests for :mod:`tree_sitter_analyzer.cache.answer_cache_policy`.

RFC-0027 L6.1 rule 1: an action may enter ``CACHEABLE_ACTIONS`` only if it
performs no filesystem write, no index mutation, no lease acquisition and no
ledger append. The allowlist "may never be editable by hand alone" — so the
contract test below derives the *pure* set mechanically from each inner tool's
own MCP ``annotations`` and asserts the allowlist is a subset of it.

Without that fence a cache hit would return the previous answer **without
performing the requested side effect**.
"""

from __future__ import annotations

import asyncio

import pytest

from tree_sitter_analyzer.cache.answer_cache import reset_answer_cache
from tree_sitter_analyzer.cache.answer_cache_policy import (
    CACHEABLE_ACTIONS,
    audited_pure_actions,
    build_answer_key,
    current_generation,
    extra_inputs_digest,
    normalize_args,
    producer_version,
)


@pytest.fixture(autouse=True)
def _fresh_singleton():
    reset_answer_cache()
    yield
    reset_answer_cache()


# --------------------------------------------------------------------------
# Rule 1 — the allowlist fence
# --------------------------------------------------------------------------


class TestAllowlistFence:
    def test_allowlist_is_a_subset_of_the_audited_pure_set(self) -> None:
        pure = audited_pure_actions(".")
        assert CACHEABLE_ACTIONS <= pure, (
            "CACHEABLE_ACTIONS contains routes the side-effect audit does not "
            f"mark pure: {sorted(CACHEABLE_ACTIONS - pure)}"
        )

    def test_index_build_is_absent_from_the_allowlist(self) -> None:
        """A mutating action: caching it would skip the index rebuild."""
        assert ("index", "build") not in CACHEABLE_ACTIONS

    def test_index_build_is_absent_from_the_audited_pure_set(self) -> None:
        assert ("index", "build") not in audited_pure_actions(".")

    def test_ledger_append_route_is_absent_from_the_audited_pure_set(self) -> None:
        # project action=journal appends to the decision ledger.
        assert ("project", "journal") not in audited_pure_actions(".")

    def test_snapshot_acquire_route_is_absent_from_the_audited_pure_set(self) -> None:
        # edit action=release_snapshot acquires/releases a lease.
        assert ("edit", "release_snapshot") not in audited_pure_actions(".")

    def test_doc_sync_is_absent_from_the_allowlist(self) -> None:
        # Structurally excluded by the RFC even though its annotations are
        # read-only: the allowlist is a *subset*, never the whole pure set.
        assert ("project", "doc_sync") not in CACHEABLE_ACTIONS

    def test_edit_safe_is_in_the_allowlist(self) -> None:
        assert ("edit", "safe") in CACHEABLE_ACTIONS

    def test_health_file_is_in_the_allowlist(self) -> None:
        assert ("health", "file") in CACHEABLE_ACTIONS

    def test_allowlist_holds_exactly_the_two_certified_expensive_routes(self) -> None:
        assert CACHEABLE_ACTIONS == frozenset({("edit", "safe"), ("health", "file")})


# --------------------------------------------------------------------------
# Key components
# --------------------------------------------------------------------------


class TestNormalizeArgs:
    def test_action_is_never_part_of_the_args_digest(self) -> None:
        assert normalize_args({"action": "safe", "x": 1}, ".") == normalize_args(
            {"x": 1}, "."
        )

    def test_key_order_does_not_change_the_canonical_form(self) -> None:
        assert normalize_args({"a": 1, "b": 2}, ".") == normalize_args(
            {"b": 2, "a": 1}, "."
        )

    def test_output_format_is_part_of_the_args_digest(self) -> None:
        assert normalize_args({"output_format": "toon"}, ".") != normalize_args(
            {"output_format": "json"}, "."
        )

    def test_absolute_and_relative_target_paths_normalize_together(
        self, tmp_path
    ) -> None:
        target = tmp_path / "pkg" / "mod.py"
        target.parent.mkdir(parents=True)
        target.write_text("x = 1\n", encoding="utf-8")
        assert normalize_args({"file_path": str(target)}, str(tmp_path)) == (
            normalize_args({"file_path": "pkg/mod.py"}, str(tmp_path))
        )

    def test_a_path_outside_the_project_is_left_alone(self, tmp_path) -> None:
        outside = tmp_path.parent / "elsewhere.py"
        inside = tmp_path / "elsewhere.py"
        assert normalize_args({"file_path": str(outside)}, str(tmp_path)) != (
            normalize_args({"file_path": str(inside)}, str(tmp_path))
        )


class TestGeneration:
    def test_generation_is_stable_across_repeat_calls(self, tmp_path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        assert current_generation(str(tmp_path)) == current_generation(str(tmp_path))

    def test_adding_a_source_file_bumps_the_generation(self, tmp_path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        before = current_generation(str(tmp_path))
        (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
        assert current_generation(str(tmp_path)) != before

    def test_two_distinct_project_roots_never_share_a_generation(
        self, tmp_path
    ) -> None:
        """The AnswerKey has no project_root field, so the root is folded into
        the generation — otherwise two projects could collide in one process."""
        left = tmp_path / "left"
        right = tmp_path / "right"
        for root in (left, right):
            root.mkdir()
        assert current_generation(str(left)) != current_generation(str(right))


class TestProducerVersion:
    def test_producer_version_is_stable_for_one_route(self) -> None:
        assert producer_version("edit", "safe") == producer_version("edit", "safe")

    def test_two_routes_with_different_action_versions_differ(self) -> None:
        assert producer_version("edit", "safe") != producer_version("edit", "impact")

    def test_a_package_version_bump_changes_the_producer_version(
        self, monkeypatch
    ) -> None:
        before = producer_version("edit", "safe")
        monkeypatch.setattr("tree_sitter_analyzer.__version__", "0.0.0-test")
        assert producer_version("edit", "safe") != before


class TestExtraInputs:
    def test_absent_constraint_config_yields_a_stable_digest(self, tmp_path) -> None:
        assert extra_inputs_digest(str(tmp_path)) == extra_inputs_digest(str(tmp_path))

    def test_editing_the_constraint_config_changes_the_digest(self, tmp_path) -> None:
        config = tmp_path / "architectural-constraints.yml"
        config.write_text("rules: []\n", encoding="utf-8")
        before = extra_inputs_digest(str(tmp_path))
        config.write_text("rules: [{name: a}]\n", encoding="utf-8")
        assert extra_inputs_digest(str(tmp_path)) != before


class TestBuildAnswerKey:
    def test_key_is_none_for_a_non_allowlisted_route(self, tmp_path) -> None:
        assert build_answer_key("index", "build", {}, str(tmp_path)) is None

    def test_key_is_none_without_a_project_root(self) -> None:
        assert build_answer_key("edit", "safe", {"file_path": "a.py"}, None) is None

    def test_key_carries_the_route_it_was_built_for(self, tmp_path) -> None:
        key = build_answer_key("edit", "safe", {"file_path": "a.py"}, str(tmp_path))
        assert key is not None
        assert (key.tool, key.action) == ("edit", "safe")


# --------------------------------------------------------------------------
# Rule 5 — a cache hit is visible, end to end through the real facade
# --------------------------------------------------------------------------


def _run_edit_safe(facade, **extra):
    return asyncio.run(
        facade.execute(
            {
                "action": "safe",
                "file_path": "tree_sitter_analyzer/latency.py",
                "output_format": "json",
                **extra,
            }
        )
    )


@pytest.fixture
def edit_facade():
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    return build_edit_facade(".")


def _reset_recorder():
    """Return an emptied latency recorder.

    The recorder is process-global and is NOT in ``conftest``'s singleton reset
    list, so a test that reads it must empty it itself rather than reason about
    what other tests in the same xdist worker recorded.
    """
    from tree_sitter_analyzer.latency import get_latency_recorder

    recorder = get_latency_recorder()
    recorder.reset()
    return recorder


def _warm_row(recorder):
    """Return the single ``(edit, safe, warm)`` row, asserting it is unique."""
    rows = [
        route
        for route in recorder.snapshot().routes
        if (route.tool, route.action, route.tier) == ("edit", "safe", "warm")
    ]
    assert len(rows) == 1
    assert rows[0].p50_ns is not None
    return rows[0]


class TestServedFromIsVisible:
    def test_first_call_is_served_from_computed(self, edit_facade) -> None:
        first = _run_edit_safe(edit_facade)
        assert first["provenance"]["served_from"] == "computed"

    def test_second_identical_call_is_served_from_cache(self, edit_facade) -> None:
        _run_edit_safe(edit_facade)
        second = _run_edit_safe(edit_facade)
        assert second["provenance"]["served_from"] == "cache"

    def test_cache_hit_carries_every_key_component(self, edit_facade) -> None:
        _run_edit_safe(edit_facade)
        second = _run_edit_safe(edit_facade)
        assert set(second["provenance"]) == {
            "served_from",
            "tool",
            "action",
            "normalized_args",
            "generation",
            "producer_version",
            "extra_inputs",
        }

    def test_cache_hit_returns_the_same_verdict(self, edit_facade) -> None:
        first = _run_edit_safe(edit_facade)
        second = _run_edit_safe(edit_facade)
        assert second["verdict"] == first["verdict"]

    def test_cache_hit_returns_the_same_risk_level(self, edit_facade) -> None:
        first = _run_edit_safe(edit_facade)
        second = _run_edit_safe(edit_facade)
        assert second["risk_level"] == first["risk_level"]

    def test_a_non_allowlisted_route_never_claims_a_cache_serve(
        self, edit_facade
    ) -> None:
        result = asyncio.run(edit_facade.execute({"action": "nope"}))
        assert "provenance" not in result


class TestCacheHitIsHonestlyMeasured:
    """The cost of serving a hit must land in the RFC-0025 latency reservoir.

    The first version of the wiring derived the cache key *outside*
    ``recorder.measure``, so the baseline reported a hit as ``0.0 ms`` while the
    caller was still paying ~20 ms for the source-tree fingerprint. That is
    instrumentation that flatters the change, which is worse than none.
    """

    def test_a_cache_hit_adds_exactly_one_latency_observation(
        self, edit_facade
    ) -> None:
        recorder = _reset_recorder()
        _run_edit_safe(edit_facade)
        _run_edit_safe(edit_facade)
        # One cold row (the compute) and one warm row (the hit), 1 sample each.
        assert _warm_row(recorder).count == 1

    def test_the_measured_cost_of_a_hit_is_not_zero(self, edit_facade) -> None:
        recorder = _reset_recorder()
        _run_edit_safe(edit_facade)
        second = _run_edit_safe(edit_facade)
        assert second["provenance"]["served_from"] == "cache"
        # Deriving the key costs a source-tree fingerprint, so a hit can never
        # legitimately be free. Zero here means the key work escaped the window.
        assert _warm_row(recorder).p50_ns > 0
