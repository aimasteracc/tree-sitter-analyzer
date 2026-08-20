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
import os
import time

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

    def test_a_same_size_edit_bumps_the_generation(self, tmp_path) -> None:
        """The dangerous everyday case, and the reason recent files are hashed.

        ``x = 1`` -> ``x = 2`` changes neither the path, the count nor the size,
        and on Windows it left ``mtime_ns`` unchanged in 15 of 20 measured
        trials — so a ``(path, mtime, size)`` digest alone served a stale verdict
        most of the time.
        """
        target = tmp_path / "a.py"
        target.write_text("x = 1\n", encoding="utf-8")
        before = current_generation(str(tmp_path))
        target.write_text("x = 2\n", encoding="utf-8")
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
            (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        assert current_generation(str(left)) != current_generation(str(right))


class TestGenerationSeesTheCasesAMaxMtimeStampCannot:
    """Review P1-1 / P1-2: the failures of a ``(file_count, max_mtime_ns)`` stamp.

    Each case below leaves BOTH the file count and the maximum mtime unchanged,
    so the previous stamp could not see any of them. They are not exotic: a
    rename is what an agent does mid-refactor, and it made the cache answer
    ``verdict=CAUTION, downstream_count=1`` for a path that no longer exists —
    where the live code raises ``File not found``.
    """

    def test_renaming_a_file_bumps_the_generation(self, tmp_path) -> None:
        """``os.rename`` changes no file's mtime and not the count — only the
        directory's mtime, which a max-mtime stamp never stats."""
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "keep.py").write_text("y = 2\n", encoding="utf-8")
        before = current_generation(str(tmp_path))
        (tmp_path / "a.py").rename(tmp_path / "b.py")
        assert current_generation(str(tmp_path)) != before

    def test_deleting_a_file_bumps_the_generation(self, tmp_path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
        before = current_generation(str(tmp_path))
        (tmp_path / "a.py").unlink()
        assert current_generation(str(tmp_path)) != before

    def test_a_size_changing_replacement_at_a_pinned_mtime_bumps_it(
        self, tmp_path
    ) -> None:
        """``tar -x`` / ``cp -p`` / ``rsync --times`` restore the old mtime."""
        target = tmp_path / "a.py"
        target.write_text("x = 1\n", encoding="utf-8")
        stat = target.stat()
        before = current_generation(str(tmp_path))
        target.write_text("x = 1\nadded = True\n", encoding="utf-8")
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        assert target.stat().st_mtime_ns == stat.st_mtime_ns
        assert current_generation(str(tmp_path)) != before

    def test_a_file_with_a_future_mtime_does_not_blind_the_tree(self, tmp_path) -> None:
        """A single future mtime pins ``max_mtime_ns`` ahead of the wall clock,
        so every later real edit is invisible until time catches up.

        The edit below rewrites an EXISTING file, so the file count is
        unchanged and cannot rescue the stamp — this isolates the max-mtime
        blindness rather than accidentally testing the count.
        """
        (tmp_path / "future.py").write_text("x = 1\n", encoding="utf-8")
        edited = tmp_path / "edited.py"
        edited.write_text("y = 1\n", encoding="utf-8")
        future_ns = time.time_ns() + 10 * 365 * 24 * 3600 * 1_000_000_000
        os.utime(tmp_path / "future.py", ns=(future_ns, future_ns))
        before = current_generation(str(tmp_path))
        edited.write_text("y = 2\n", encoding="utf-8")
        assert current_generation(str(tmp_path)) != before

    @pytest.mark.parametrize("extension", [".rb", ".kt", ".php", ".cs", ".swift"])
    def test_a_language_outside_graph_source_exts_still_gets_a_generation(
        self, tmp_path, extension
    ) -> None:
        """``GRAPH_SOURCE_EXTS`` covers 19 of the 30 supported extensions. For
        the other 11 the old stamp was the constant ``0:0`` for the whole
        process, so nothing could ever invalidate."""
        (tmp_path / f"a{extension}").write_text("x = 1\n", encoding="utf-8")
        before = current_generation(str(tmp_path))
        assert before is not None
        (tmp_path / f"b{extension}").write_text("y = 2\n", encoding="utf-8")
        assert current_generation(str(tmp_path)) != before


class TestGenerationFailsClosedWhenItCanSeeNothing:
    """Review P1-2: an empty fingerprint must yield NO key, not a constant one.

    ``GraphFingerprint.is_empty()`` existed for exactly this state and had zero
    callers.
    """

    def test_a_tree_with_no_supported_source_file_has_no_generation(
        self, tmp_path
    ) -> None:
        (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")
        assert current_generation(str(tmp_path)) is None

    def test_an_empty_tree_has_no_generation(self, tmp_path) -> None:
        assert current_generation(str(tmp_path)) is None

    def test_no_generation_means_no_answer_key(self, tmp_path) -> None:
        (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")
        assert (
            build_answer_key("edit", "safe", {"file_path": "a.py"}, str(tmp_path))
            is None
        )

    @staticmethod
    def _checkout_like(tmp_path, count: int) -> None:
        """Write ``count`` files all bearing the SAME mtime, as a checkout does."""
        stamp_ns = 1_700_000_000_000_000_000
        for index in range(count):
            path = tmp_path / f"m{index}.py"
            path.write_text(f"x = {index}\n", encoding="utf-8")
            os.utime(path, ns=(stamp_ns, stamp_ns))

    def test_a_freshly_checked_out_tree_has_no_generation(self, tmp_path) -> None:
        """A checkout stamps every file with one mtime, so there is no small
        "recently touched" set to hash and no way to tell which file is at risk.
        Hashing them all would cost more than the answer being cached, so the
        digest declares itself untrustworthy and caching is skipped."""
        self._checkout_like(tmp_path, 20)
        assert current_generation(str(tmp_path)) is None

    def test_the_cost_bound_reports_the_same_tick_file_count(self, tmp_path) -> None:
        from tree_sitter_analyzer.cache.fingerprint import compute_source_tree_digest

        self._checkout_like(tmp_path, 20)
        digest = compute_source_tree_digest(str(tmp_path))
        assert digest.unstable_file_count == 20
        assert digest.is_trustworthy() is False

    def test_a_tree_under_the_bound_is_trustworthy(self, tmp_path) -> None:
        from tree_sitter_analyzer.cache.fingerprint import compute_source_tree_digest

        self._checkout_like(tmp_path, 5)
        digest = compute_source_tree_digest(str(tmp_path))
        assert digest.unstable_file_count == 0
        assert digest.is_trustworthy() is True

    def test_a_tree_under_the_bound_still_invalidates_on_an_edit(
        self, tmp_path
    ) -> None:
        self._checkout_like(tmp_path, 5)
        before = current_generation(str(tmp_path))
        (tmp_path / "m0.py").write_text("x = 999\n", encoding="utf-8")
        assert current_generation(str(tmp_path)) != before


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
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
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
                "file_path": "target.py",
                "output_format": "json",
                **extra,
            }
        )
    )


@pytest.fixture
def edit_facade(tmp_path):
    """A facade bound to an ISOLATED project, not the live repo root.

    These tests must not run against ``"."``. The generation stamp covers the
    whole source tree, so under ``pytest -n auto`` another worker writing
    anywhere in the repo bumps it between two calls — the cache then correctly
    reports ``computed`` and a "second call is a hit" assertion goes red for a
    reason that has nothing to do with the cache. That is exactly how the first
    version of these tests flaked: 3 failures under xdist, 0 when serial.
    """
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    (tmp_path / "target.py").write_text(
        "def thing():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "other.py").write_text("x = 1\n", encoding="utf-8")
    return build_edit_facade(str(tmp_path))


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
    if rows[0].p50_ns is None:  # pragma: no cover - a recorded row has a p50
        raise AssertionError("the recorded (edit, safe, warm) row carried no p50")
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

    def test_the_measured_hit_cost_includes_the_key_derivation(
        self, edit_facade, tmp_path
    ) -> None:
        """Review P2-1: ``p50_ns > 0`` did not guard anything.

        The reviewer moved ``build_answer_key`` back OUTSIDE
        ``recorder.measure`` and both measurement tests still passed — the
        sub-microsecond dict lookup and ``deepcopy`` left inside the window
        satisfy ``> 0``, so the assertion could not tell the bug from the fix.

        The real invariant is a RELATIONSHIP between two measured quantities:
        the recorded warm cost must be at least the same order as a separately
        timed ``build_answer_key``, because that derivation is the dominant
        cost of serving a hit. No wall-clock ceiling is asserted.
        """
        recorder = _reset_recorder()
        _run_edit_safe(edit_facade)
        second = _run_edit_safe(edit_facade)
        assert second["provenance"]["served_from"] == "cache"

        # Time the key derivation on its own, same root, best of several.
        samples = []
        for _ in range(5):
            started = time.perf_counter_ns()
            build_answer_key("edit", "safe", {"file_path": "target.py"}, str(tmp_path))
            samples.append(time.perf_counter_ns() - started)
        key_ns = sorted(samples)[len(samples) // 2]

        measured_ns = _warm_row(recorder).p50_ns
        print(f"measured_value: warm_p50_ns={measured_ns} key_derivation_ns={key_ns}")
        # Half of the standalone derivation is a generous floor for scheduling
        # noise while still being orders of magnitude above the ~1us that the
        # reverted (key-outside-window) wiring records.
        assert measured_ns >= key_ns / 2


# --------------------------------------------------------------------------
# The property whose failure would silently serve a wrong verdict
# --------------------------------------------------------------------------


class TestARealEditInvalidatesTheAnswer:
    """A real edit to a real file must change the answer, not replay it.

    Every other test here checks a fence in isolation. This one asserts the
    thing an agent actually depends on: after it edits a file, the pre-edit gate
    tells it the truth. If this ever goes red, the cache is serving stale
    verdicts and the feature is worse than not existing.
    """

    @staticmethod
    def _ask(facade):
        return _run_edit_safe(facade)

    @staticmethod
    def _add_importer(project, name: str) -> None:
        (project / name).write_text(
            "from target import thing\nx = thing()\n", encoding="utf-8"
        )

    def test_editing_a_file_in_place_forces_a_recompute(
        self, edit_facade, tmp_path
    ) -> None:
        """An in-place edit leaves the file COUNT unchanged — the case the
        directory-mtime keying this replaces got wrong."""
        self._ask(edit_facade)
        self._add_importer(tmp_path, "other.py")
        assert self._ask(edit_facade)["provenance"]["served_from"] == "computed"

    def test_editing_a_file_in_place_changes_the_downstream_count(
        self, edit_facade, tmp_path
    ) -> None:
        before = self._ask(edit_facade)["downstream_count"]
        self._add_importer(tmp_path, "other.py")
        assert self._ask(edit_facade)["downstream_count"] == before + 1

    def test_adding_a_file_forces_a_recompute(self, edit_facade, tmp_path) -> None:
        self._ask(edit_facade)
        self._add_importer(tmp_path, "third.py")
        assert self._ask(edit_facade)["provenance"]["served_from"] == "computed"

    def test_adding_a_file_changes_the_downstream_count(
        self, edit_facade, tmp_path
    ) -> None:
        before = self._ask(edit_facade)["downstream_count"]
        self._add_importer(tmp_path, "third.py")
        assert self._ask(edit_facade)["downstream_count"] == before + 1

    def test_a_repeat_after_the_edit_is_served_from_cache_again(
        self, edit_facade, tmp_path
    ) -> None:
        self._ask(edit_facade)
        self._add_importer(tmp_path, "other.py")
        self._ask(edit_facade)
        assert self._ask(edit_facade)["provenance"]["served_from"] == "cache"

    def test_renaming_the_target_away_is_not_answered_from_cache(
        self, edit_facade, tmp_path
    ) -> None:
        """Review P1-1, the sharpest case: the cached answer said
        ``success=True, verdict=CAUTION, downstream_count=1`` for a path that
        no longer existed, where the live code raises ``File not found``.
        ``git mv`` then a safety check on the old path is a normal refactor.
        """
        self._ask(edit_facade)
        (tmp_path / "target.py").rename(tmp_path / "renamed.py")
        assert not (tmp_path / "target.py").exists()
        with pytest.raises(ValueError, match="File not found"):
            self._ask(edit_facade)


class TestTheAllowlistedRoutesDoNotEvictEachOther:
    """Review P1-3: ``producer_version`` was route-scoped AND inside ``prelude``,
    whose change evicts the WHOLE cache — so the two allowlisted routes could
    never be resident together and the hit rate was 0% in the prescribed
    workflow (``.claude/skills/tsa-edit-safety/SKILL.md:16``,
    ``tsa-edit-then-verify/SKILL.md:6``). Every call then paid the generation
    fingerprint for nothing: a net regression.

    Driven through the real ``AnswerCache`` with real keys from
    ``build_answer_key`` rather than through both facades, because
    ``health action=file`` cannot be executed against a ``tmp_path`` root at
    all: ``health_scorer.score_dependencies`` builds a ``DependencyGraph`` for a
    *different* project root and walks it, which hangs (>500 s). That is
    pre-existing and unrelated — it is the same
    ``compute_graph_fingerprint`` <- ``project_graph._cache_key_for`` stack that
    fails identically on the base commit in ``test_file_health_tool.py`` and the
    ``test_toon_compact_only`` boundary tests. The interleaved *measurement*
    runs against the real repo, where that route works.
    """

    @pytest.fixture
    def keys(self, tmp_path):
        (tmp_path / "target.py").write_text(
            "def thing():\n    return 1\n", encoding="utf-8"
        )
        args = {"file_path": "target.py"}
        edit_key = build_answer_key("edit", "safe", args, str(tmp_path))
        health_key = build_answer_key("health", "file", args, str(tmp_path))
        assert edit_key is not None
        assert health_key is not None
        return edit_key, health_key

    @staticmethod
    def _answer(verdict):
        return {"success": True, "verdict": verdict}

    def test_the_two_routes_share_one_eviction_prelude(self, keys) -> None:
        """The property the whole fix rests on: the prelude is global."""
        edit_key, health_key = keys
        assert edit_key.prelude == health_key.prelude

    def test_the_two_routes_are_still_distinct_keys(self, keys) -> None:
        edit_key, health_key = keys
        assert edit_key != health_key

    def test_switching_route_does_not_evict_the_whole_cache(self, keys) -> None:
        from tree_sitter_analyzer.cache.answer_cache import AnswerCache

        edit_key, health_key = keys
        cache = AnswerCache()
        cache.store(edit_key, self._answer("SAFE"))
        cache.store(health_key, self._answer("INFO"))
        assert cache.whole_cache_evictions == 0

    def test_both_routes_are_resident_at_the_same_generation(self, keys) -> None:
        from tree_sitter_analyzer.cache.answer_cache import AnswerCache

        edit_key, health_key = keys
        cache = AnswerCache()
        cache.store(edit_key, self._answer("SAFE"))
        cache.store(health_key, self._answer("INFO"))
        assert cache.entry_count == 2

    def test_the_prescribed_interleaved_loop_hits_on_every_repeat(self, keys) -> None:
        """The documented pair, three rounds, no edits: 2 misses then 4 hits.

        Before the fix this was 0 hits / 5 misses / 4 whole-cache evictions.
        """
        from tree_sitter_analyzer.cache.answer_cache import AnswerCache

        edit_key, health_key = keys
        cache = AnswerCache()
        served = []
        for _ in range(3):
            for key, verdict in ((edit_key, "SAFE"), (health_key, "INFO")):
                if cache.lookup(key) is not None:
                    served.append("cache")
                    continue
                cache.store(key, self._answer(verdict))
                served.append("computed")
        assert served == ["computed", "computed", "cache", "cache", "cache", "cache"]

    def test_the_interleaved_loop_never_evicts_the_whole_cache(self, keys) -> None:
        from tree_sitter_analyzer.cache.answer_cache import AnswerCache

        edit_key, health_key = keys
        cache = AnswerCache()
        for _ in range(3):
            for key, verdict in ((edit_key, "SAFE"), (health_key, "INFO")):
                if cache.lookup(key) is None:
                    cache.store(key, self._answer(verdict))
        assert cache.whole_cache_evictions == 0

    def test_an_action_version_bump_still_misses_without_evicting_the_sibling(
        self, keys
    ) -> None:
        """Route identity must still key the entry — just not the prelude."""
        import dataclasses

        from tree_sitter_analyzer.cache.answer_cache import AnswerCache

        edit_key, health_key = keys
        cache = AnswerCache()
        cache.store(edit_key, self._answer("SAFE"))
        cache.store(health_key, self._answer("INFO"))
        bumped = dataclasses.replace(
            edit_key, producer_version=f"{edit_key.global_producer_version}:pvr1:NEW"
        )
        assert cache.lookup(bumped) is None
        assert cache.lookup(health_key) is not None
