"""Unit tests for SubscriptionRegistry (RFC-0001 criterion 1)."""

from __future__ import annotations

from tree_sitter_analyzer.mcp.subscription_registry import (
    SubscriptionRegistry,
    _hashable,
)


class TestSubscribeUnsubscribe:
    def test_subscribe_adds_selector(self) -> None:
        reg = SubscriptionRegistry()
        reg.subscribe("s1", "selector:A")
        assert "selector:A" in reg.subscriptions_for("s1")

    def test_subscribe_is_idempotent(self) -> None:
        reg = SubscriptionRegistry()
        reg.subscribe("s1", "A")
        reg.subscribe("s1", "A")
        assert reg.subscription_count() == 1

    def test_unsubscribe_removes_selector(self) -> None:
        reg = SubscriptionRegistry()
        reg.subscribe("s1", "A")
        reg.unsubscribe("s1", "A")
        assert reg.subscriptions_for("s1") == []

    def test_unsubscribe_noop_if_absent(self) -> None:
        reg = SubscriptionRegistry()
        reg.unsubscribe("no_session", "no_selector")  # must not raise

    def test_remove_session_clears_all(self) -> None:
        reg = SubscriptionRegistry()
        reg.subscribe("s1", "A")
        reg.subscribe("s1", "B")
        reg.remove_session("s1")
        assert reg.subscriptions_for("s1") == []
        assert reg.subscription_count() == 0

    def test_multiple_sessions_independent(self) -> None:
        reg = SubscriptionRegistry()
        reg.subscribe("s1", "A")
        reg.subscribe("s2", "B")
        reg.remove_session("s1")
        assert "B" in reg.subscriptions_for("s2")
        assert reg.subscriptions_for("s1") == []


class TestDeltaComputation:
    def test_empty_to_items_produces_added(self) -> None:
        reg = SubscriptionRegistry(min_interval_s=0)
        reg.subscribe("s1", "sel")
        added, removed = reg.compute_delta("s1", "sel", [{"name": "foo"}])
        assert len(added) == 1
        assert removed == []

    def test_items_to_empty_produces_removed(self) -> None:
        reg = SubscriptionRegistry(min_interval_s=0)
        reg.subscribe("s1", "sel")
        reg.compute_delta("s1", "sel", [{"name": "foo"}])
        added, removed = reg.compute_delta("s1", "sel", [])
        assert added == []
        assert len(removed) == 1

    def test_unchanged_snapshot_produces_no_delta(self) -> None:
        reg = SubscriptionRegistry(min_interval_s=0)
        reg.subscribe("s1", "sel")
        reg.compute_delta("s1", "sel", [{"name": "foo"}])
        added, removed = reg.compute_delta("s1", "sel", [{"name": "foo"}])
        assert added == []
        assert removed == []

    def test_unknown_session_returns_empty(self) -> None:
        reg = SubscriptionRegistry(min_interval_s=0)
        added, removed = reg.compute_delta("ghost", "sel", [])
        assert added == [] and removed == []

    def test_throttle_suppresses_rapid_calls(self) -> None:
        reg = SubscriptionRegistry(min_interval_s=3600)
        reg.subscribe("s1", "sel")
        reg.compute_delta("s1", "sel", [{"name": "a"}])
        # Second call within throttle window — even with a new item — returns empty
        added, removed = reg.compute_delta("s1", "sel", [{"name": "a"}, {"name": "b"}])
        assert added == [] and removed == []


class TestNotifyAll:
    def test_on_delta_callback_fires(self) -> None:
        fired: list[tuple] = []

        def cb(session_id: str, selector: str, added: list, removed: list) -> None:
            fired.append((session_id, selector, added, removed))

        reg = SubscriptionRegistry(min_interval_s=0, on_delta=cb)
        reg.subscribe("s1", "sel")
        # First call: baseline (empty → [item])
        reg.notify_change("s1", "sel", [{"name": "x"}])
        # Second call: delta
        reg.notify_change("s1", "sel", [{"name": "x"}, {"name": "y"}])
        assert len(fired) == 2
        assert fired[1][2] == [{"name": "y"}]  # added

    def test_notify_all_evaluates_all_subscriptions(self) -> None:
        evaluated: list[tuple] = []

        def evaluate(session_id: str, selector: str) -> list:
            evaluated.append((session_id, selector))
            return []

        reg = SubscriptionRegistry(min_interval_s=0)
        reg.subscribe("s1", "A")
        reg.subscribe("s1", "B")
        reg.subscribe("s2", "A")
        reg.notify_all(evaluate)
        assert len(evaluated) == 3


class TestGC:
    def test_gc_removes_empty_sessions(self) -> None:
        reg = SubscriptionRegistry()
        reg.subscribe("s1", "A")
        reg.unsubscribe("s1", "A")
        removed = reg.gc_empty_sessions()
        assert removed == 1
        assert reg.all_sessions() == []


class TestHashable:
    def test_dict_is_hashable(self) -> None:
        h = _hashable({"a": 1, "b": [1, 2]})
        assert isinstance(h, tuple)

    def test_nested_dict_is_hashable(self) -> None:
        h = _hashable({"x": {"y": 3}})
        assert isinstance(h, tuple)
