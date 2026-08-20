#!/usr/bin/env python3
"""Unit tests for :mod:`tree_sitter_analyzer.cache.answer_cache` (RFC-0027 L6.1).

The cache exists because ``edit action=safe`` — the one call an agent makes
before *every* edit — was measured at 3.3-3.8 s **warm** on Windows
(``docs/baselines/rfc0025-l5-latency-windows-e0.json``). Every rule below is a
soundness fence: a cache that serves a wrong or stale verdict is worse than no
cache at all, because an agent cannot tell.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.cache.answer_cache import (
    CERTIFIED_FRESHNESS,
    NON_CERTIFIED_FRESHNESS,
    AnswerCache,
    AnswerKey,
    get_answer_cache,
    reset_answer_cache,
)
from tree_sitter_analyzer.task.freshness import FRESHNESS_STATES

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_BASE = {
    "tool": "edit",
    "action": "safe",
    "normalized_args": '{"file_path":"a.py"}',
    "generation": "gfp1:root:10:1000",
    "producer_version": "pv1:aaaa",
    "extra_inputs": "xi1:bbbb",
}


def _key(**overrides: str) -> AnswerKey:
    return AnswerKey(**{**_BASE, **overrides})


def _certified(**extra: object) -> dict[str, object]:
    """A minimal certified answer payload."""
    return {"success": True, "verdict": "SAFE", **extra}


@pytest.fixture(autouse=True)
def _fresh_singleton():
    reset_answer_cache()
    yield
    reset_answer_cache()


# --------------------------------------------------------------------------
# AnswerKey: every component is independently load-bearing
# --------------------------------------------------------------------------


class TestAnswerKeyIdentity:
    """Two calls share an answer only when ALL six components agree."""

    def test_identical_components_compare_equal(self) -> None:
        assert _key() == _key()

    def test_identical_components_share_one_hash(self) -> None:
        assert len({_key(), _key()}) == 1

    def test_tool_bump_changes_identity(self) -> None:
        assert _key() != _key(tool="health")

    def test_action_bump_changes_identity(self) -> None:
        assert _key() != _key(action="impact")

    def test_normalized_args_bump_changes_identity(self) -> None:
        assert _key() != _key(normalized_args='{"file_path":"b.py"}')

    def test_generation_bump_changes_identity(self) -> None:
        assert _key() != _key(generation="gfp1:root:11:2000")

    def test_producer_version_bump_changes_identity(self) -> None:
        assert _key() != _key(producer_version="pv1:cccc")

    def test_extra_inputs_bump_changes_identity(self) -> None:
        assert _key() != _key(extra_inputs="xi1:dddd")

    def test_key_is_frozen(self) -> None:
        with pytest.raises(AttributeError):
            _key().generation = "mutated"  # type: ignore[misc]

    def test_component_count_is_exactly_six(self) -> None:
        # The RFC's key deliberately has three independent components beyond
        # the args. A field silently dropped here is an upgrade-replay bug.
        assert len(AnswerKey.__dataclass_fields__) == 6


# --------------------------------------------------------------------------
# Lookup / store
# --------------------------------------------------------------------------


class TestLookup:
    def test_lookup_misses_on_empty_cache(self) -> None:
        assert AnswerCache().lookup(_key()) is None

    def test_lookup_hits_after_store(self) -> None:
        cache = AnswerCache()
        cache.store(_key(), _certified(risk_level="safe"))
        hit = cache.lookup(_key())
        assert hit is not None
        assert hit.payload["risk_level"] == "safe"

    def test_lookup_misses_on_generation_mismatch(self) -> None:
        cache = AnswerCache()
        cache.store(_key(), _certified())
        assert cache.lookup(_key(generation="gfp1:root:11:2000")) is None

    def test_producer_version_bump_misses_at_unchanged_generation(self) -> None:
        """The upgrade-replay case: same source tree, new schema/resolver.

        Without this, a TSA upgrade would silently replay the previous
        release's verdict under the new schema.
        """
        cache = AnswerCache()
        cache.store(_key(), _certified())
        assert cache.lookup(_key(producer_version="pv1:NEW")) is None

    def test_extra_inputs_bump_misses_at_unchanged_generation(self) -> None:
        cache = AnswerCache()
        cache.store(_key(), _certified())
        assert cache.lookup(_key(extra_inputs="xi1:NEW")) is None

    def test_hit_payload_is_a_copy_not_the_stored_object(self) -> None:
        """The MCP boundary mutates the returned envelope in place."""
        cache = AnswerCache()
        cache.store(_key(), _certified(nested={"n": 1}))
        first = cache.lookup(_key())
        assert first is not None
        first.payload["nested"]["n"] = 999
        second = cache.lookup(_key())
        assert second is not None
        assert second.payload["nested"]["n"] == 1

    def test_stored_payload_is_isolated_from_later_caller_mutation(self) -> None:
        cache = AnswerCache()
        payload = _certified(nested={"n": 1})
        cache.store(_key(), payload)
        payload["nested"]["n"] = 999  # type: ignore[index]
        hit = cache.lookup(_key())
        assert hit is not None
        assert hit.payload["nested"]["n"] == 1


# --------------------------------------------------------------------------
# Rule 2 — only certified answers are stored
# --------------------------------------------------------------------------


class TestCertificationGate:
    def test_stale_freshness_is_not_stored(self) -> None:
        cache = AnswerCache()
        assert cache.store(_key(), _certified(freshness="stale")) is False
        assert cache.lookup(_key()) is None

    def test_missing_freshness_is_not_stored(self) -> None:
        cache = AnswerCache()
        assert cache.store(_key(), _certified(freshness="missing")) is False
        assert cache.lookup(_key()) is None

    def test_unknown_freshness_is_not_stored(self) -> None:
        cache = AnswerCache()
        assert cache.store(_key(), _certified(freshness="unknown")) is False
        assert cache.lookup(_key()) is None

    def test_fresh_freshness_is_stored(self) -> None:
        cache = AnswerCache()
        assert cache.store(_key(), _certified(freshness="fresh")) is True

    def test_nested_provenance_freshness_is_honoured(self) -> None:
        cache = AnswerCache()
        payload = _certified(provenance={"freshness": "stale"})
        assert cache.store(_key(), payload) is False

    def test_failed_answer_is_not_stored(self) -> None:
        cache = AnswerCache()
        assert cache.store(_key(), {"success": False, "verdict": "SAFE"}) is False

    def test_error_verdict_is_not_stored(self) -> None:
        cache = AnswerCache()
        assert cache.store(_key(), {"success": True, "verdict": "ERROR"}) is False

    def test_non_dict_answer_is_not_stored(self) -> None:
        cache = AnswerCache()
        assert cache.store(_key(), 3) is False  # type: ignore[arg-type]

    def test_unknown_access_state_is_not_stored(self) -> None:
        """RFC-0022 P0.4's capability dimension, same rule as freshness.

        ``edit action=safe`` with ``access_mode=read_existing`` returns
        ``access_state="unknown"`` wherever the source oracle cannot run;
        replaying that would make a one-off "could not certify" permanent.
        """
        cache = AnswerCache()
        payload = _certified(verdict="WARN", access_state="unknown")
        assert cache.store(_key(), payload) is False

    def test_missing_access_state_is_not_stored(self) -> None:
        cache = AnswerCache()
        assert cache.store(_key(), _certified(access_state="missing")) is False

    def test_available_access_state_is_stored(self) -> None:
        cache = AnswerCache()
        assert cache.store(_key(), _certified(access_state="available")) is True

    def test_not_applicable_access_state_is_stored(self) -> None:
        # "not applicable" means the capability gate does not apply, which is
        # the legacy (uncertified-by-design) path — nothing can be stale.
        cache = AnswerCache()
        assert cache.store(_key(), _certified(access_state="not_applicable")) is True


class TestFreshnessDenylistIsDerivedFromTheClosedDomain:
    """Review P2-2: on a function whose failure mode is a PERMANENT lie, the
    denylist must be the complement of an explicit allowlist over RFC-0022's
    closed ``FRESHNESS_STATES``. A hand-listed denylist would let a sixth state
    become silently cacheable.
    """

    def test_the_two_sets_partition_the_domain(self) -> None:
        assert CERTIFIED_FRESHNESS | NON_CERTIFIED_FRESHNESS == set(FRESHNESS_STATES)

    def test_the_two_sets_are_disjoint(self) -> None:
        assert CERTIFIED_FRESHNESS & NON_CERTIFIED_FRESHNESS == set()

    def test_only_fresh_and_not_applicable_are_certified(self) -> None:
        assert CERTIFIED_FRESHNESS == {"fresh", "not_applicable"}

    def test_every_other_declared_state_is_refused(self) -> None:
        assert NON_CERTIFIED_FRESHNESS == {"stale", "missing", "unknown"}

    def test_a_new_freshness_state_would_be_refused_not_cached(self) -> None:
        """The ratchet: adding a state to FRESHNESS_STATES without deciding it
        is certified must make it non-certified, never cacheable by default."""
        hypothetical = set(FRESHNESS_STATES) | {"degraded"}
        assert (hypothetical - CERTIFIED_FRESHNESS) >= {"degraded"}


# --------------------------------------------------------------------------
# Rule 3 — whole-cache eviction on any key-component bump
# --------------------------------------------------------------------------


class TestWholeCacheEviction:
    def test_generation_bump_evicts_every_unrelated_entry(self) -> None:
        """No partial invalidation: proving which answers a file change can
        affect is the unresolved-edge problem and cannot be proved sound."""
        cache = AnswerCache()
        cache.store(_key(normalized_args="A"), _certified())
        cache.store(_key(normalized_args="B"), _certified())
        assert cache.entry_count == 2
        cache.store(
            _key(normalized_args="C", generation="gfp1:root:11:2"), _certified()
        )
        assert cache.entry_count == 1

    def test_producer_version_bump_evicts_every_unrelated_entry(self) -> None:
        cache = AnswerCache()
        cache.store(_key(normalized_args="A"), _certified())
        cache.store(_key(normalized_args="B"), _certified())
        cache.store(_key(normalized_args="C", producer_version="pv1:NEW"), _certified())
        assert cache.entry_count == 1

    def test_extra_inputs_bump_evicts_every_unrelated_entry(self) -> None:
        cache = AnswerCache()
        cache.store(_key(normalized_args="A"), _certified())
        cache.store(_key(normalized_args="B"), _certified())
        cache.store(_key(normalized_args="C", extra_inputs="xi1:NEW"), _certified())
        assert cache.entry_count == 1

    def test_lookup_at_a_new_prelude_evicts_before_returning_none(self) -> None:
        cache = AnswerCache()
        cache.store(_key(normalized_args="A"), _certified())
        assert cache.lookup(_key(normalized_args="A", generation="gfp1:x:1:1")) is None
        assert cache.entry_count == 0

    def test_eviction_counter_records_exactly_one_whole_cache_eviction(self) -> None:
        cache = AnswerCache()
        cache.store(_key(normalized_args="A"), _certified())
        cache.store(_key(normalized_args="B", generation="gfp1:x:1:1"), _certified())
        assert cache.whole_cache_evictions == 1


# --------------------------------------------------------------------------
# Rule 4 — bounded, LRU
# --------------------------------------------------------------------------


class TestBudgetAndLru:
    def test_entry_larger_than_the_whole_budget_is_refused(self) -> None:
        cache = AnswerCache(budget_bytes=64)
        assert cache.store(_key(), _certified(blob="x" * 500)) is False
        assert cache.entry_count == 0

    def test_eviction_happens_at_the_bound(self) -> None:
        cache = AnswerCache(budget_bytes=400)
        for name in ("A", "B", "C", "D", "E", "F", "G", "H"):
            cache.store(_key(normalized_args=name), _certified(blob="y" * 40))
        assert cache.total_bytes <= 400

    def test_least_recently_used_is_the_exact_victim(self) -> None:
        cache = AnswerCache(budget_bytes=400)
        for name in ("A", "B", "C"):
            cache.store(_key(normalized_args=name), _certified(blob="y" * 80))
        # Touch A so B becomes the least-recently-used entry.
        assert cache.lookup(_key(normalized_args="A")) is not None
        cache.store(_key(normalized_args="D"), _certified(blob="y" * 80))
        assert cache.lookup(_key(normalized_args="B")) is None
        assert cache.lookup(_key(normalized_args="A")) is not None
        assert cache.lookup(_key(normalized_args="C")) is not None
        assert cache.lookup(_key(normalized_args="D")) is not None

    def test_default_budget_is_128_mib(self) -> None:
        assert AnswerCache().budget_bytes == 128 * 1024 * 1024

    def test_budget_is_read_from_the_environment(self, monkeypatch) -> None:
        monkeypatch.setenv("ANSWER_CACHE_BUDGET_MB", "7")
        reset_answer_cache()
        assert get_answer_cache().budget_bytes == 7 * 1024 * 1024

    def test_unparseable_budget_falls_back_to_the_default(self, monkeypatch) -> None:
        monkeypatch.setenv("ANSWER_CACHE_BUDGET_MB", "not-a-number")
        reset_answer_cache()
        assert get_answer_cache().budget_bytes == 128 * 1024 * 1024

    def test_zero_budget_disables_storage(self, monkeypatch) -> None:
        monkeypatch.setenv("ANSWER_CACHE_BUDGET_MB", "0")
        reset_answer_cache()
        cache = get_answer_cache()
        assert cache.store(_key(), _certified()) is False


# --------------------------------------------------------------------------
# Statistics an agent (and --self-health) can read
# --------------------------------------------------------------------------


class TestStatistics:
    def test_hits_counts_exactly_the_served_answers(self) -> None:
        cache = AnswerCache()
        cache.store(_key(), _certified())
        cache.lookup(_key())
        cache.lookup(_key())
        assert cache.hits == 2

    def test_misses_counts_exactly_the_unserved_lookups(self) -> None:
        cache = AnswerCache()
        cache.lookup(_key())
        assert cache.misses == 1

    def test_singleton_is_stable_within_a_process(self) -> None:
        assert get_answer_cache() is get_answer_cache()

    def test_reset_replaces_the_singleton(self) -> None:
        first = get_answer_cache()
        reset_answer_cache()
        assert get_answer_cache() is not first
